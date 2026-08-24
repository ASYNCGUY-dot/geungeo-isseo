from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, StringConstraints

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _require_literal_nonblank_text(value: str) -> str:
    if not value.strip():
        raise ValueError("literal source text must not be blank")
    return value


LiteralSourceText = Annotated[str, AfterValidator(_require_literal_nonblank_text)]


class Verdict(StrEnum):
    CONFIRMED = "confirmed"
    MISMATCH = "mismatch"
    INSUFFICIENT = "insufficient"
    UNVERIFIABLE = "unverifiable"
    CONTRADICTED = "contradicted"


class EvaluationCase(BaseModel):
    model_config = {"frozen": True}

    case_id: NonBlankText
    ingredient_group: NonBlankText
    expected_verdict: Verdict
    frozen: Literal[True]
    report_no: NonBlankText
    source_id: NonBlankText
    retrieved_at: datetime
    rule_version: NonBlankText
    matched_source_text: LiteralSourceText
    source_url: NonBlankText


class EvaluationSummary(BaseModel):
    model_config = {"frozen": True}

    sample_size: int
    false_clearance_rate: float
    confirmed_recall: float
    coverage: float
    unverifiable_count: int


class ProductCandidate(BaseModel):
    report_no: NonBlankText
    name: NonBlankText
    company: NonBlankText
    primary_function: str = ""
    raw_materials: str = ""
    intake_method: str = ""
    source_id: Literal["C003"]
    retrieved_at: datetime


SearchMatchedField = Literal["report_no", "name", "company"]


class ProductSearchDocument(BaseModel):
    model_config = {"frozen": True}

    product: ProductCandidate
    normalized_report_no: str
    normalized_name: str
    normalized_company: str
    normalization_version: Literal["product-search-v1"] = "product-search-v1"


class ProductSearchResult(BaseModel):
    model_config = {"frozen": True}

    candidate: ProductCandidate
    matched_fields: tuple[SearchMatchedField, ...]
    normalization_version: Literal["product-search-v1"] = "product-search-v1"


class ConfirmedProduct(BaseModel):
    product: ProductCandidate
    confirmed_by_user: Literal[True]


class Claim(BaseModel):
    original_text: NonBlankText
    normalized_subject: NonBlankText


class EvidenceRecord(BaseModel):
    evidence_id: NonBlankText
    source_url: NonBlankText
    retrieved_at: datetime
    product_report_no: str | None = None
    supports_claim: bool
