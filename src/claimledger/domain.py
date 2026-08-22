from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Verdict(StrEnum):
    CONFIRMED = "confirmed"
    MISMATCH = "mismatch"
    INSUFFICIENT = "insufficient"
    UNVERIFIABLE = "unverifiable"
    CONTRADICTED = "contradicted"


class ProductCandidate(BaseModel):
    report_no: NonBlankText
    name: NonBlankText
    company: NonBlankText
    primary_function: str = ""
    raw_materials: str = ""
    intake_method: str = ""
    source_id: Literal["C003"]
    retrieved_at: datetime


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
