from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from claimledger.domain import ProductCandidate
from claimledger.errors import DataSourceError

_MODEL_TO_SOURCE_FIELD = {
    "report_no": "PRDLST_REPORT_NO",
    "name": "PRDLST_NM",
    "company": "BSSH_NM",
    "primary_function": "PRIMARY_FNCLTY",
    "raw_materials": "RAWMTRL_NM",
    "intake_method": "NTK_MTHD",
}


@dataclass(frozen=True)
class C003Page:
    total_count: int
    products: tuple[ProductCandidate, ...]


class CoverageAudit(BaseModel):
    record_count: int
    unique_report_count: int
    duplicate_report_count: int
    missing_name_count: int
    missing_company_count: int
    missing_primary_function_count: int
    missing_raw_materials_count: int
    missing_intake_method_count: int
    candidate_counts: dict[str, int]


class C003Client:
    base_url = "https://openapi.foodsafetykorea.go.kr"

    def __init__(
        self,
        api_key: str,
        http_client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key.strip()
        if not self.api_key:
            raise DataSourceError("C003 API key is required")
        self.http_client = http_client or httpx.Client(timeout=timeout)
        self.timeout = timeout

    def fetch_page(self, start: int, end: int) -> C003Page:
        if start < 1 or end < start:
            raise DataSourceError("C003 page range must satisfy 1 <= start <= end")

        request_url = f"{self.base_url}/api/{self.api_key}/C003/json/{start}/{end}"
        try:
            response = self.http_client.get(request_url, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as error:
            raise DataSourceError("C003 request timeout") from error
        except httpx.HTTPStatusError as error:
            raise DataSourceError(f"C003 returned HTTP {error.response.status_code}") from error
        except (httpx.HTTPError, ValueError) as error:
            raise DataSourceError("C003 request or JSON parsing failed") from error

        if not isinstance(payload, dict):
            raise DataSourceError("C003 response must be a JSON object")
        return parse_c003_payload(payload, retrieved_at=datetime.now(UTC))


def parse_c003_payload(payload: dict[str, Any], retrieved_at: datetime) -> C003Page:
    envelope = payload.get("C003")
    if not isinstance(envelope, dict):
        raise DataSourceError("C003 response object is missing")

    result = envelope.get("RESULT")
    if not isinstance(result, dict):
        raise DataSourceError("C003 RESULT object is missing")

    code = str(result.get("CODE", "UNKNOWN"))
    message = str(result.get("MSG", ""))
    if code != "INFO-000":
        raise DataSourceError(f"C003 returned {code}: {message}")

    try:
        total_count = int(envelope["total_count"])
    except (KeyError, TypeError, ValueError) as error:
        raise DataSourceError("C003 total_count must be a non-negative integer") from error
    if total_count < 0:
        raise DataSourceError("C003 total_count must be a non-negative integer")

    rows = envelope.get("row")
    if not isinstance(rows, list):
        raise DataSourceError("C003 row must be a list")

    products = tuple(_parse_product(row, index, retrieved_at) for index, row in enumerate(rows))
    return C003Page(total_count=total_count, products=products)


def _parse_product(row: object, index: int, retrieved_at: datetime) -> ProductCandidate:
    if not isinstance(row, dict):
        raise DataSourceError(f"C003 row {index} must be an object")

    values = {
        "report_no": row.get("PRDLST_REPORT_NO"),
        "name": row.get("PRDLST_NM"),
        "company": row.get("BSSH_NM"),
        "primary_function": row.get("PRIMARY_FNCLTY", ""),
        "raw_materials": row.get("RAWMTRL_NM", ""),
        "intake_method": row.get("NTK_MTHD", ""),
        "source_id": "C003",
        "retrieved_at": retrieved_at,
    }
    try:
        return ProductCandidate.model_validate(values)
    except ValidationError as error:
        field = str(error.errors()[0]["loc"][0])
        source_field = _MODEL_TO_SOURCE_FIELD.get(field, field)
        raise DataSourceError(f"C003 row {index} has invalid {source_field}") from error


def audit_products(products: Sequence[ProductCandidate]) -> CoverageAudit:
    report_numbers = [product.report_no for product in products]
    unique_report_count = len(set(report_numbers))
    candidate_terms = {
        "lutein_zeaxanthin": ("루테인", "지아잔틴", "lutein", "zeaxanthin"),
        "omega3": ("오메가3", "오메가-3", "omega3", "omega-3", "epa", "dha"),
        "probiotics": ("프로바이오틱스", "유산균", "probiotic"),
    }

    candidate_counts = dict.fromkeys(candidate_terms, 0)
    for product in products:
        searchable = (
            f"{product.name} {product.primary_function} {product.raw_materials}"
        ).casefold()
        for candidate, terms in candidate_terms.items():
            if any(term.casefold() in searchable for term in terms):
                candidate_counts[candidate] += 1

    return CoverageAudit(
        record_count=len(products),
        unique_report_count=unique_report_count,
        duplicate_report_count=len(products) - unique_report_count,
        missing_name_count=sum(not product.name.strip() for product in products),
        missing_company_count=sum(not product.company.strip() for product in products),
        missing_primary_function_count=sum(
            not product.primary_function.strip() for product in products
        ),
        missing_raw_materials_count=sum(not product.raw_materials.strip() for product in products),
        missing_intake_method_count=sum(not product.intake_method.strip() for product in products),
        candidate_counts=candidate_counts,
    )
