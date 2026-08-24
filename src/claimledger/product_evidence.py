from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, model_validator

from claimledger.domain import (
    ConfirmedProduct,
    IngredientMapping,
    MappingStatus,
    OfficialFieldStatus,
    OfficialFunctionStatement,
    OfficialProductCaution,
    ProductCandidate,
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


class ProductSourceSnapshot(BaseModel):
    model_config = {"frozen": True}

    report_no: str
    name: str
    company: str
    primary_function: str
    raw_materials: str
    intake_method: str
    source_id: Literal["C003"]
    retrieved_at: datetime

    @classmethod
    def from_candidate(cls, candidate: ProductCandidate) -> "ProductSourceSnapshot":
        return cls(**candidate.model_dump())

    def to_candidate(self) -> ProductCandidate:
        return ProductCandidate(**self.model_dump())


class ProductEvidenceBundle(BaseModel):
    model_config = {"frozen": True}

    product_snapshot: ProductSourceSnapshot
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
    def _require_canonical_composition(self) -> "ProductEvidenceBundle":
        composition = _compose_product_evidence(self.product_snapshot)
        conflict_codes = _bundle_conflict_codes(self, composition)
        if conflict_codes:
            raise ValueError(
                f"product evidence does not match its source snapshot: {', '.join(conflict_codes)}"
            )
        return self


@dataclass(frozen=True)
class _ProductEvidenceComposition:
    status: ProductEvidenceStatus
    ingredient_mapping: IngredientMapping
    official_functions: tuple[OfficialFunctionStatement, ...]
    official_cautions: tuple[OfficialProductCaution, ...]
    safety_signals: tuple[SafetySignal, ...]
    rule_versions: tuple[str, ...]
    source_ids: tuple[str, ...]
    source_timestamps: tuple[datetime, ...]
    reason_codes: tuple[str, ...]


def _unique[T](values: tuple[T, ...]) -> tuple[T, ...]:
    return tuple(dict.fromkeys(values))


def _reason_codes(
    candidate: ProductCandidate,
    ingredient_mapping: IngredientMapping,
    official_functions: tuple[OfficialFunctionStatement, ...],
) -> tuple[str, ...]:
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


def _compose_product_evidence(
    snapshot: ProductSourceSnapshot,
) -> _ProductEvidenceComposition:
    candidate = snapshot.to_candidate()
    confirmed_product = ConfirmedProduct(product=candidate, confirmed_by_user=True)
    ingredient_mapping = map_ingredients(candidate)
    official_functions = parse_official_functions(candidate)
    official_cautions = extract_official_cautions(candidate)
    safety_signals = build_safety_signals(confirmed_product, official_cautions, ())
    reason_codes = _reason_codes(candidate, ingredient_mapping, official_functions)

    return _ProductEvidenceComposition(
        status=_status(reason_codes),
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


def _verified_mapping_is_well_formed(mapping: IngredientMapping) -> bool:
    if mapping.status is not MappingStatus.VERIFIED:
        return True
    if len(mapping.groups) != 1 or not mapping.evidence:
        return False
    sole_group = mapping.groups[0]
    return all(item.group is sole_group for item in mapping.evidence)


def _bundle_conflict_codes(
    bundle: ProductEvidenceBundle,
    composition: _ProductEvidenceComposition,
) -> tuple[str, ...]:
    conflicts: list[str] = []

    if not isinstance(bundle.status, ProductEvidenceStatus):
        conflicts.append("INVALID_STATUS")
    elif bundle.status is not composition.status:
        conflicts.append("STATUS_CONFLICT")

    if bundle.report_no != bundle.product_snapshot.report_no:
        conflicts.append("REPORT_NUMBER_CONFLICT")

    mapping = bundle.ingredient_mapping
    if not isinstance(mapping, IngredientMapping):
        conflicts.append("INVALID_INGREDIENT_MAPPING")
    else:
        if not _verified_mapping_is_well_formed(mapping):
            conflicts.append("INVALID_VERIFIED_INGREDIENT_MAPPING")
        if mapping != composition.ingredient_mapping:
            if mapping.status is MappingStatus.AMBIGUOUS:
                conflicts.append("AMBIGUOUS_INGREDIENT_MAPPING")
            elif mapping.status is MappingStatus.UNVERIFIABLE:
                conflicts.append("UNVERIFIABLE_INGREDIENT_MAPPING")
            conflicts.append("INGREDIENT_MAPPING_CONFLICT")

    if bundle.official_functions != composition.official_functions:
        conflicts.append("OFFICIAL_FUNCTION_CONFLICT")
    if bundle.official_cautions != composition.official_cautions:
        conflicts.append("OFFICIAL_CAUTION_CONFLICT")
    if bundle.safety_signals != composition.safety_signals:
        conflicts.append("SAFETY_SIGNAL_CONFLICT")
    if bundle.rule_versions != composition.rule_versions:
        conflicts.append("INVALID_RULE_VERSIONS")
    if (
        bundle.source_ids != composition.source_ids
        or bundle.source_timestamps != composition.source_timestamps
    ):
        conflicts.append("SOURCE_PROVENANCE_CONFLICT")
    if bundle.reason_codes != composition.reason_codes:
        conflicts.append("REASON_CODES_CONFLICT")
    return tuple(conflicts)


def build_product_evidence(product: ConfirmedProduct) -> ProductEvidenceBundle:
    snapshot = ProductSourceSnapshot.from_candidate(product.product)
    composition = _compose_product_evidence(snapshot)
    return ProductEvidenceBundle(
        product_snapshot=snapshot,
        status=composition.status,
        report_no=snapshot.report_no,
        ingredient_mapping=composition.ingredient_mapping,
        official_functions=composition.official_functions,
        official_cautions=composition.official_cautions,
        safety_signals=composition.safety_signals,
        rule_versions=composition.rule_versions,
        source_ids=composition.source_ids,
        source_timestamps=composition.source_timestamps,
        reason_codes=composition.reason_codes,
    )


def require_product_evidence_ready(bundle: ProductEvidenceBundle) -> ProductEvidenceBundle:
    if not isinstance(bundle.status, ProductEvidenceStatus):
        raise DecisionInvariantError("product evidence is not ready: INVALID_STATUS")
    if not isinstance(bundle.product_snapshot, ProductSourceSnapshot):
        raise DecisionInvariantError("product evidence is not ready: INVALID_PRODUCT_SNAPSHOT")

    try:
        composition = _compose_product_evidence(bundle.product_snapshot)
    except (AttributeError, TypeError, ValueError) as exc:
        raise DecisionInvariantError(
            "product evidence is not ready: INVALID_PRODUCT_SNAPSHOT"
        ) from exc

    conflict_codes = _bundle_conflict_codes(bundle, composition)
    if conflict_codes:
        raise DecisionInvariantError(
            f"product evidence is not ready: {', '.join(conflict_codes)}"
        )
    if composition.status is not ProductEvidenceStatus.READY:
        reason_codes = composition.reason_codes or (
            f"STATUS_{composition.status.value.upper()}",
        )
        raise DecisionInvariantError(
            f"product evidence is not ready: {', '.join(reason_codes)}"
        )
    return bundle


__all__ = [
    "ProductEvidenceBundle",
    "ProductEvidenceStatus",
    "ProductSourceSnapshot",
    "build_product_evidence",
    "require_product_evidence_ready",
]
