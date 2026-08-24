from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    AwareDatetime,
    BaseModel,
    StringConstraints,
    model_validator,
)

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _require_literal_nonblank_text(value: str) -> str:
    if not value.strip():
        raise ValueError("literal source text must not be blank")
    return value


LiteralSourceText = Annotated[str, AfterValidator(_require_literal_nonblank_text)]
CLAIM_FINGERPRINT_VERSION = "claim-sha256-v1"
ClaimFingerprint = Annotated[
    str,
    StringConstraints(pattern=rf"^{CLAIM_FINGERPRINT_VERSION}:[0-9a-f]{{64}}$"),
]


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


class ExtensionReviewProduct(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}

    report_no: NonBlankText
    name: NonBlankText
    company: NonBlankText
    primary_function: str
    raw_materials: str
    intake_method: str

    @classmethod
    def from_candidate(cls, candidate: ProductCandidate) -> "ExtensionReviewProduct":
        return cls(
            report_no=candidate.report_no,
            name=candidate.name,
            company=candidate.company,
            primary_function=candidate.primary_function,
            raw_materials=candidate.raw_materials,
            intake_method=candidate.intake_method,
        )


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


SafetySignalKind = Literal["official_product_caution", "official_interaction_caution"]
SafetyCautionCategory = Literal["consult_professional"]
OfficialInteractionSourceId = Literal["MFDS"]
OfficialInteractionSourceCategory = Literal["official_ingredient_guidance"]

_APPROVED_GENERAL_CAUTION_TEXTS: dict[SafetyCautionCategory, frozenset[str]] = {
    "consult_professional": frozenset({"의약품 복용 시 전문가와 상담하십시오."}),
}


def _is_registered_mfds_url(source_url: str) -> bool:
    host = urlparse(source_url).hostname
    return host == "foodsafetykorea.go.kr" or (
        host is not None and host.endswith(".foodsafetykorea.go.kr")
    )


def _validate_general_caution_text(category: SafetyCautionCategory, source_text: str) -> None:
    if source_text not in _APPROVED_GENERAL_CAUTION_TEXTS[category]:
        raise ValueError("caution text is not an approved literal general caution")


def classify_general_caution(source_text: str) -> SafetyCautionCategory | None:
    for category, approved_texts in _APPROVED_GENERAL_CAUTION_TEXTS.items():
        if source_text in approved_texts:
            return category
    return None


class InteractionEvidence(BaseModel):
    model_config = {"frozen": True}

    source_id: OfficialInteractionSourceId
    source_url: NonBlankText | None = None
    official_identifier: NonBlankText | None = None
    retrieved_at: datetime
    source_text: LiteralSourceText
    product_report_no: NonBlankText | None = None
    official_source_category: OfficialInteractionSourceCategory
    official_source_verified: Literal[True]
    caution_category: SafetyCautionCategory

    @model_validator(mode="after")
    def _require_source_reference(self) -> "InteractionEvidence":
        if self.source_url is None and self.official_identifier is None:
            raise ValueError("interaction evidence requires a source URL or official identifier")
        if self.source_url is not None and not _is_registered_mfds_url(self.source_url):
            raise ValueError("interaction evidence URL must belong to the registered official source")
        _validate_general_caution_text(self.caution_category, self.source_text)
        return self


class SafetySignal(BaseModel):
    model_config = {"frozen": True}

    kind: SafetySignalKind
    message: NonBlankText
    source_id: NonBlankText
    source_url: NonBlankText | None = None
    official_identifier: NonBlankText | None = None
    retrieved_at: datetime
    source_text: LiteralSourceText
    caution_category: SafetyCautionCategory
    official_source_category: OfficialInteractionSourceCategory | None = None
    official_source_verified: Literal[True] | None = None
    is_safety_clearance: Literal[False] = False

    @model_validator(mode="after")
    def _require_general_caution_only(self) -> "SafetySignal":
        if self.source_url is None and self.official_identifier is None:
            raise ValueError("safety signal requires a source URL or official identifier")

        if self.kind == "official_product_caution":
            if self.source_id != "C003" or self.official_identifier is None:
                raise ValueError("official product caution requires C003 identity and official identifier")
        else:
            if (
                self.source_id != "MFDS"
                or self.official_source_category != "official_ingredient_guidance"
                or self.official_source_verified is not True
            ):
                raise ValueError("official interaction caution requires registered MFDS provenance")
            if self.source_url is not None and not _is_registered_mfds_url(self.source_url):
                raise ValueError("official interaction caution URL must belong to the registered official source")

        if self.message != self.source_text:
            raise ValueError("safety signal message must preserve literal source text")
        _validate_general_caution_text(self.caution_category, self.message)
        return self


class ConfirmedProduct(BaseModel):
    model_config = {"frozen": True}

    product: ProductCandidate
    confirmed_by_user: Literal[True]


class Claim(BaseModel):
    model_config = {"frozen": True}

    original_text: LiteralSourceText
    normalized_subject: NonBlankText


class ClaimSupportRecord(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}

    evidence_id: NonBlankText
    claim_fingerprint: ClaimFingerprint
    confirmed_product_report_no: NonBlankText
    matched_evidence_text: LiteralSourceText
    source_id: NonBlankText
    source_url: AnyHttpUrl
    retrieved_at: AwareDatetime
    applicability: Literal["direct"]
    applicability_rule_version: Literal["claim-support-v1"]


class EvidenceRecord(BaseModel):
    evidence_id: NonBlankText
    source_url: NonBlankText
    retrieved_at: datetime
    product_report_no: str | None = None
    supports_claim: bool
