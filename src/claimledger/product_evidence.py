from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, model_validator

from claimledger.domain import (
    ConfirmedProduct,
    IngredientMapping,
    MappingStatus,
    OfficialFieldStatus,
    OfficialFunctionStatement,
    OfficialProductCaution,
    SafetySignal,
)
from claimledger.errors import DecisionInvariantError
from claimledger.ingredients import map_ingredients
from claimledger.official import extract_official_cautions, parse_official_functions
from claimledger.safety import build_safety_signals

_REQUIRED_OFFICIAL_FIELDS = ("primary_function", "raw_materials", "intake_method")


class ProductEvidenceStatus(StrEnum):
    READY = "ready"
    AMBIGUOUS = "ambiguous"
    UNVERIFIABLE = "unverifiable"


class ProductEvidenceBundle(BaseModel):
    model_config = {"frozen": True}

    status: ProductEvidenceStatus
    report_no: str
    ingredient_mapping: IngredientMapping
    official_functions: tuple[OfficialFunctionStatement, ...]
    official_cautions: tuple[OfficialProductCaution, ...]
    safety_signals: tuple[SafetySignal, ...]
    rule_versions: tuple[str, ...]
    source_ids: tuple[str, ...]
    source_timestamps: tuple[datetime, ...]
    reason_codes: tuple[str, ...]

    @model_validator(mode="after")
    def _require_consistent_readiness(self) -> "ProductEvidenceBundle":
        structural_reasons = _structural_reason_codes(self)
        if self.reason_codes != structural_reasons or self.status is not _status(
            structural_reasons
        ):
            raise ValueError("product evidence status and reason codes must match its contents")
        return self


def _unique[T](values: tuple[T, ...]) -> tuple[T, ...]:
    return tuple(dict.fromkeys(values))


def _reason_codes(
    product: ConfirmedProduct,
    ingredient_mapping: IngredientMapping,
    official_functions: tuple[OfficialFunctionStatement, ...],
) -> tuple[str, ...]:
    candidate = product.product
    reasons = [
        f"MISSING_{field.upper()}"
        for field in _REQUIRED_OFFICIAL_FIELDS
        if not getattr(candidate, field).strip()
    ]

    if ingredient_mapping.status is MappingStatus.AMBIGUOUS:
        reasons.append("AMBIGUOUS_INGREDIENT_MAPPING")
    elif ingredient_mapping.status is MappingStatus.UNVERIFIABLE:
        reasons.append("UNVERIFIABLE_INGREDIENT_MAPPING")

    if candidate.primary_function.strip() and any(
        statement.status is not OfficialFieldStatus.VERIFIED
        for statement in official_functions
    ):
        reasons.append("UNPARSED_OFFICIAL_FUNCTION")
    return tuple(reasons)


def _status(reason_codes: tuple[str, ...]) -> ProductEvidenceStatus:
    if any(reason != "AMBIGUOUS_INGREDIENT_MAPPING" for reason in reason_codes):
        return ProductEvidenceStatus.UNVERIFIABLE
    if reason_codes:
        return ProductEvidenceStatus.AMBIGUOUS
    return ProductEvidenceStatus.READY


def _structural_reason_codes(bundle: ProductEvidenceBundle) -> tuple[str, ...]:
    reasons: list[str] = []
    if not bundle.report_no.strip():
        reasons.append("MISSING_REPORT_NUMBER")

    if not bundle.official_functions or any(
        statement.status is OfficialFieldStatus.MISSING
        for statement in bundle.official_functions
    ):
        reasons.append("MISSING_PRIMARY_FUNCTION")

    for source_field in ("raw_materials", "intake_method"):
        field_cautions = tuple(
            caution
            for caution in bundle.official_cautions
            if caution.source_field == source_field
        )
        if not field_cautions or any(
            caution.status is OfficialFieldStatus.MISSING for caution in field_cautions
        ):
            reasons.append(f"MISSING_{source_field.upper()}")

    if bundle.ingredient_mapping.status is MappingStatus.AMBIGUOUS:
        reasons.append("AMBIGUOUS_INGREDIENT_MAPPING")
    elif bundle.ingredient_mapping.status is MappingStatus.UNVERIFIABLE:
        reasons.append("UNVERIFIABLE_INGREDIENT_MAPPING")

    if bundle.official_functions and any(
        statement.status is OfficialFieldStatus.UNVERIFIABLE
        for statement in bundle.official_functions
    ):
        reasons.append("UNPARSED_OFFICIAL_FUNCTION")

    if bundle.rule_versions != ("ingredient-map-v1", "official-function-v1"):
        reasons.append("INVALID_RULE_VERSIONS")
    if "C003" not in bundle.source_ids:
        reasons.append("MISSING_C003_SOURCE")
    if not bundle.source_timestamps:
        reasons.append("MISSING_SOURCE_TIMESTAMP")
    return tuple(reasons)


def build_product_evidence(product: ConfirmedProduct) -> ProductEvidenceBundle:
    candidate = product.product
    ingredient_mapping = map_ingredients(candidate)
    official_functions = parse_official_functions(candidate)
    official_cautions = extract_official_cautions(candidate)
    safety_signals = build_safety_signals(product, official_cautions, ())
    reason_codes = _reason_codes(product, ingredient_mapping, official_functions)

    return ProductEvidenceBundle(
        status=_status(reason_codes),
        report_no=candidate.report_no,
        ingredient_mapping=ingredient_mapping,
        official_functions=official_functions,
        official_cautions=official_cautions,
        safety_signals=safety_signals,
        rule_versions=_unique(
            (ingredient_mapping.rule_version, *(item.parser_version for item in official_functions))
        ),
        source_ids=_unique((candidate.source_id, *(signal.source_id for signal in safety_signals))),
        source_timestamps=_unique(
            (candidate.retrieved_at, *(signal.retrieved_at for signal in safety_signals))
        ),
        reason_codes=reason_codes,
    )


def require_product_evidence_ready(bundle: ProductEvidenceBundle) -> ProductEvidenceBundle:
    structural_reasons = _structural_reason_codes(bundle)
    if (
        bundle.status is not ProductEvidenceStatus.READY
        or bundle.reason_codes
        or structural_reasons
    ):
        reason_codes = _unique((*bundle.reason_codes, *structural_reasons)) or (
            f"STATUS_{bundle.status.value.upper()}",
        )
        raise DecisionInvariantError(
            f"product evidence is not ready: {', '.join(reason_codes)}"
        )
    return bundle


__all__ = [
    "ProductEvidenceBundle",
    "ProductEvidenceStatus",
    "build_product_evidence",
    "require_product_evidence_ready",
]
