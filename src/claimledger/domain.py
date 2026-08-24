from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, StringConstraints, model_validator

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


class IngredientGroup(StrEnum):
    LUTEIN_ZEAXANTHIN = "lutein_zeaxanthin"
    OMEGA3 = "omega3"
    PROBIOTICS = "probiotics"
    MILK_THISTLE = "milk_thistle"
    VITAMIN_D = "vitamin_d"
    RED_GINSENG = "red_ginseng"
    COENZYME_Q10 = "coenzyme_q10"
    MAGNESIUM = "magnesium"


class MappingStatus(StrEnum):
    VERIFIED = "verified_mapping"
    AMBIGUOUS = "ambiguous"
    UNVERIFIABLE = "unverifiable"


IngredientSourceField = Literal["name", "primary_function", "raw_materials"]


class IngredientMatchEvidence(BaseModel):
    model_config = {"frozen": True}

    group: IngredientGroup
    source_field: IngredientSourceField
    matched_text: LiteralSourceText


class IngredientMapping(BaseModel):
    model_config = {"frozen": True}

    status: MappingStatus
    groups: tuple[IngredientGroup, ...]
    evidence: tuple[IngredientMatchEvidence, ...]
    rule_version: Literal["ingredient-map-v1"] = "ingredient-map-v1"


class OfficialFieldStatus(StrEnum):
    VERIFIED = "verified"
    MISSING = "missing"
    UNVERIFIABLE = "unverifiable"


OfficialExpressionStrength = Literal[
    "possibility",
    "support",
    "improvement",
    "guarantee",
    "treatment_prevention",
]

OfficialCautionSourceField = Literal["raw_materials", "intake_method"]


class OfficialFunctionStatement(BaseModel):
    model_config = {"frozen": True}

    status: OfficialFieldStatus
    original_text: str
    effect_key: str | None = None
    expression_strength: OfficialExpressionStrength | None = None
    parser_version: Literal["official-function-v1"] = "official-function-v1"

    @model_validator(mode="after")
    def _validate_structured_meaning(self) -> "OfficialFunctionStatement":
        has_structured_meaning = self.effect_key is not None and self.expression_strength is not None
        if self.status is OfficialFieldStatus.VERIFIED and not has_structured_meaning:
            raise ValueError("verified official function requires effect key and expression strength")
        if self.status is not OfficialFieldStatus.VERIFIED and (
            self.effect_key is not None or self.expression_strength is not None
        ):
            raise ValueError("unverified official function must not contain structured meaning")
        return self


class OfficialProductCaution(BaseModel):
    model_config = {"frozen": True}

    status: OfficialFieldStatus
    source_field: OfficialCautionSourceField
    original_text: str
    parser_version: Literal["official-caution-v1"] = "official-caution-v1"


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
