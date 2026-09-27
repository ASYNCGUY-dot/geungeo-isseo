"""HTTP API for the core MVP slice.

The API only moves an analysis through confirmation gates. Verdicts are produced by the
deterministic engine from server-side state; clients never submit verdicts.
"""

import threading
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, field_validator

from claimledger.claims_v1 import AdClaim, confirm_claims, extract_claims
from claimledger.domain import ConfirmedProduct, ProductCandidate
from claimledger.products import search_products
from claimledger.receipt import Receipt, build_receipt, render_markdown
from claimledger.verdict_v1 import decide_claim

MAX_AD_TEXT_LENGTH = 5000
_INDEX_HTML = Path(__file__).with_name("web") / "index.html"


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        user_action: str | None = None,
        retryable: bool = False,
        analysis_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.user_action = user_action
        self.retryable = retryable
        self.analysis_id = analysis_id


class CreateAnalysisRequest(BaseModel):
    ad_text: str = Field(max_length=MAX_AD_TEXT_LENGTH)

    @field_validator("ad_text")
    @classmethod
    def _require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("ad_text must not be blank")
        return value


class ProductConfirmationRequest(BaseModel):
    report_no: str = Field(min_length=1)


class ClaimConfirmationRequest(BaseModel):
    claim_ids: list[str]


@dataclass
class Analysis:
    analysis_id: str
    ad_text: str
    claims: tuple[AdClaim, ...]
    created_at: datetime
    product: ConfirmedProduct | None = None
    receipt: Receipt | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


def _error_body(error: ApiError) -> dict:
    return {
        "error": {
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
            "user_action": error.user_action,
            "analysis_id": error.analysis_id,
            "trace_id": uuid.uuid4().hex,
        }
    }


def _product_view(product: ProductCandidate) -> dict:
    return {
        "report_no": product.report_no,
        "name": product.name,
        "company": product.company,
        "primary_function": product.primary_function,
        "source_id": product.source_id,
        "retrieved_at": product.retrieved_at.isoformat(),
    }


def _analysis_view(analysis: Analysis) -> dict:
    return {
        "analysis_id": analysis.analysis_id,
        "ad_text": analysis.ad_text,
        "created_at": analysis.created_at.isoformat(),
        "claims": [claim.model_dump(mode="json") for claim in analysis.claims],
        "product": _product_view(analysis.product.product) if analysis.product else None,
        "receipt_available": analysis.receipt is not None,
    }


def create_app(products: Sequence[ProductCandidate], *, source_retrieved_at: datetime) -> FastAPI:
    by_report: dict[str, ProductCandidate] = {}
    for product in products:
        if product.report_no in by_report:
            raise ValueError(f"duplicate report number in snapshot: {product.report_no}")
        by_report[product.report_no] = product
    catalog = tuple(products)
    analyses: dict[str, Analysis] = {}
    store_lock = threading.Lock()

    app = FastAPI(title="근거있어 API", version="0.1.0")

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, error: ApiError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content=_error_body(error))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        api_error = ApiError(422, "INPUT_INVALID", "입력값을 확인해 주세요.")
        return JSONResponse(status_code=422, content=_error_body(api_error))

    def _get(analysis_id: str) -> Analysis:
        with store_lock:
            analysis = analyses.get(analysis_id)
        if analysis is None:
            raise ApiError(404, "ANALYSIS_NOT_FOUND", "분석을 찾을 수 없습니다.", user_action="start_over")
        return analysis

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(_INDEX_HTML.read_text(encoding="utf-8"))

    @app.get("/api/v1/health")
    def health() -> dict:
        return {
            "status": "ok",
            "product_count": len(catalog),
            "source_id": "C003",
            "source_retrieved_at": source_retrieved_at.isoformat(),
        }

    @app.get("/api/v1/products/search")
    def product_search(q: str = Query(max_length=100), limit: int = Query(10, ge=1, le=50)) -> dict:
        if not q.strip():
            raise ApiError(422, "INPUT_INVALID", "검색어를 입력해 주세요.", user_action="enter_query")
        results = search_products(catalog, q, limit=limit)
        return {"candidates": [_product_view(result.candidate) for result in results]}

    @app.post("/api/v1/analyses", status_code=201)
    def create_analysis(request: CreateAnalysisRequest) -> dict:
        analysis = Analysis(
            analysis_id=uuid.uuid4().hex,
            ad_text=request.ad_text,
            claims=extract_claims(request.ad_text),
            created_at=datetime.now(UTC),
        )
        with store_lock:
            analyses[analysis.analysis_id] = analysis
        return _analysis_view(analysis)

    @app.get("/api/v1/analyses/{analysis_id}")
    def get_analysis(analysis_id: str) -> dict:
        return _analysis_view(_get(analysis_id))

    @app.put("/api/v1/analyses/{analysis_id}/product-confirmation")
    def confirm_product(analysis_id: str, request: ProductConfirmationRequest) -> dict:
        analysis = _get(analysis_id)
        product = by_report.get(request.report_no)
        if product is None:
            raise ApiError(
                404,
                "PRODUCT_NOT_FOUND",
                "해당 신고번호의 제품을 찾을 수 없습니다.",
                user_action="select_product",
                analysis_id=analysis_id,
            )
        with analysis.lock:
            analysis.product = ConfirmedProduct(product=product, confirmed_by_user=True)
            analysis.receipt = None
        return _analysis_view(analysis)

    @app.put("/api/v1/analyses/{analysis_id}/claims/confirmation")
    def confirm_analysis_claims(analysis_id: str, request: ClaimConfirmationRequest) -> dict:
        analysis = _get(analysis_id)
        with analysis.lock:
            try:
                analysis.claims = confirm_claims(analysis.claims, request.claim_ids)
            except ValueError as exc:
                raise ApiError(
                    422, "CLAIM_NOT_FOUND", "선택한 주장을 찾을 수 없습니다.", analysis_id=analysis_id
                ) from exc
            analysis.receipt = None
        return _analysis_view(analysis)

    @app.post("/api/v1/analyses/{analysis_id}/evaluate")
    def evaluate(analysis_id: str) -> dict:
        analysis = _get(analysis_id)
        with analysis.lock:
            if analysis.product is None:
                raise ApiError(
                    409,
                    "PRODUCT_IDENTITY_UNCONFIRMED",
                    "제품을 먼저 확인해 주세요.",
                    user_action="select_product",
                    analysis_id=analysis_id,
                )
            decisions = [decide_claim(claim, analysis.product) for claim in analysis.claims]
            analysis.receipt = build_receipt(analysis.ad_text, analysis.product, decisions, datetime.now(UTC))
            return analysis.receipt.model_dump(mode="json")

    @app.get("/api/v1/analyses/{analysis_id}/receipt", response_model=None)
    def get_receipt(analysis_id: str, format: str = Query("json", pattern="^(json|markdown)$")) -> object:
        analysis = _get(analysis_id)
        with analysis.lock:
            receipt = analysis.receipt
        if receipt is None:
            raise ApiError(
                404,
                "RECEIPT_NOT_READY",
                "아직 영수증이 없습니다. 판정을 먼저 실행해 주세요.",
                user_action="evaluate",
                analysis_id=analysis_id,
            )
        if format == "markdown":
            return PlainTextResponse(render_markdown(receipt), media_type="text/markdown; charset=utf-8")
        return receipt.model_dump(mode="json")

    return app


__all__ = ["MAX_AD_TEXT_LENGTH", "ApiError", "create_app"]
