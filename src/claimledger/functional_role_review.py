import csv
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime
from enum import StrEnum
from io import StringIO
from pathlib import Path
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from claimledger.domain import (
    ExtensionReviewProduct,
    IngredientGroup,
    MappingStatus,
    NonBlankText,
)
from claimledger.extension_selection import COMPARISON_GROUPS
from claimledger.functional_role import (
    _SECRET_PATTERNS,
    FunctionalRoleRuleRegistry,
    MachineRoleDecision,
    MachineRoleReasonCode,
    MachineRoleVerdict,
    RoleEvidenceField,
    _reject_unsafe_text,
    classify_functional_role,
    load_functional_role_registry,
)
from claimledger.ingredients import map_ingredients
from claimledger.product_review import (
    MappingVerdict,
    ProductReviewLabel,
    ProductReviewManifest,
    ProductReviewSample,
    ReviewGateStatus,
    ReviewIssue,
    WilsonInterval,
    sha256_file,
    validate_product_review_pack,
    wilson_interval,
)

FUNCTIONAL_ROLE_CONTRACT_VERSION = "c003-functional-role-v1"
DEFAULT_GENERAL_AUDIT_SIZE = 20
DEFAULT_POSITIVE_AUDIT_SIZE = 35
POSITIVE_WILSON_LOWER_THRESHOLD = 0.90

_SHA256_PATTERN = r"^[0-9A-F]{64}$"
_BOTH_EVIDENCE_KEYS = ("raw_materials", "primary_function")
_HASH_ENCODING = "utf-8"
_PRODUCT_REVIEW_PACK_FILES = {
    "README.md",
    "manifest.json",
    "product_review_labels.csv",
    "samples.csv",
}
_FUNCTIONAL_ROLE_PACK_FILES = {
    "README.md",
    "manifest.json",
    "samples.csv",
    "functional_role_labels.csv",
}
_SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_PRODUCT_SOURCE_FIELDS = tuple(ExtensionReviewProduct.model_fields)
_MAX_VALIDATION_DOCUMENT_BYTES = 256 * 1024 * 1024
_HUMAN_ROLE_INPUT_FIELDS = (
    "human_verdict",
    "reason_code",
    "evidence_field",
    "evidence_excerpt",
    "rule_version",
    "review_note",
    "reviewer",
    "reviewed_at_iso8601",
)
_REQUIRED_COMPLETED_ROLE_FIELDS = (
    "human_verdict",
    "reason_code",
    "evidence_field",
    "rule_version",
    "reviewer",
    "reviewed_at_iso8601",
)

SamplingScope = Literal["general-replacement", "positive"]


class FunctionalRoleBuildError(ValueError):
    pass


class HumanRoleVerdict(StrEnum):
    FUNCTIONAL_CONFIRMED = "functional_confirmed"
    PRESENT_NONFUNCTIONAL = "present_nonfunctional"
    UNCERTAIN = "uncertain"
    EXCLUDED_MAPPING_ERROR = "excluded_mapping_error"


class FunctionalRoleReasonCode(StrEnum):
    EXPLICIT_TARGET_FUNCTION = "explicit_target_function"
    EXPLICIT_NONFUNCTIONAL_ROLE = "explicit_nonfunctional_role"
    INSUFFICIENT_LINKAGE = "insufficient_linkage"
    COMBINATION_AMBIGUOUS = "combination_ambiguous"
    NEEDS_EXPERT = "needs_expert"
    INHERITED_MAPPING_ERROR = "inherited_mapping_error"
    OTHER = "other"


class SampleOrigin(StrEnum):
    V2_ORIGINAL = "v2_original"
    GENERAL_REPLACEMENT = "general_replacement"
    POSITIVE_PRECISION = "positive_precision"


class RoleEligibility(StrEnum):
    ROLE_ELIGIBLE = "ROLE_ELIGIBLE"
    ROLE_INSUFFICIENT = "ROLE_INSUFFICIENT"


class EligibilityReasonCode(StrEnum):
    POSITIVE_POOL_TOO_SMALL = "POSITIVE_POOL_TOO_SMALL"
    POSITIVE_SAMPLE_TOO_SMALL = "POSITIVE_SAMPLE_TOO_SMALL"
    GENERAL_AUDIT_CONFLICT = "GENERAL_AUDIT_CONFLICT"
    FALSE_CONFIRMATION = "FALSE_CONFIRMATION"
    FALSE_EXCLUSION = "FALSE_EXCLUSION"
    UNRESOLVED_POSITIVE = "UNRESOLVED_POSITIVE"
    OVERCONFIDENT_DECISION = "OVERCONFIDENT_DECISION"
    POSITIVE_WILSON_BELOW_THRESHOLD = "POSITIVE_WILSON_BELOW_THRESHOLD"
    NO_ADDRESSABLE_PRODUCTS = "NO_ADDRESSABLE_PRODUCTS"


class _ImmutableContractModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


def _parse_csv_literal_int(value: object, allowed: tuple[int, ...]) -> object:
    if isinstance(value, str) and value in {str(item) for item in allowed}:
        return int(value)
    return value


def _reject_review_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        # Pydantic v2 does not wrap TypeError raised by validators.
        raise ValueError(f"{field_name} must be text")  # noqa: TRY004
    if isinstance(value, str) and value.startswith(("\t", "\r")):
        raise ValueError(f"{field_name} starts with a spreadsheet formula prefix")
    return _reject_unsafe_text(value, field_name)


def _parse_canonical_both_evidence(value: str, field_name: str) -> tuple[str, str]:
    try:
        pairs = json.loads(value, object_pairs_hook=lambda items: items)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"{field_name} must be canonical both-field JSON") from exc
    if (
        not isinstance(pairs, list)
        or len(pairs) != 2
        or any(not isinstance(pair, tuple) or len(pair) != 2 for pair in pairs)
        or tuple(pair[0] for pair in pairs) != _BOTH_EVIDENCE_KEYS
    ):
        raise ValueError(f"{field_name} must contain exactly the ordered both-field keys")
    raw_materials = pairs[0][1]
    primary_function = pairs[1][1]
    if not isinstance(raw_materials, str) or not isinstance(primary_function, str):
        # Keep malformed JSON values inside the model ValidationError contract.
        raise ValueError(f"{field_name} both-field values must be text")  # noqa: TRY004
    _reject_review_text(raw_materials, f"{field_name}.raw_materials")
    _reject_review_text(primary_function, f"{field_name}.primary_function")
    if not raw_materials.strip() or not primary_function.strip():
        raise ValueError(f"{field_name} both-field excerpts must be nonblank")
    canonical = json.dumps(
        {
            "raw_materials": raw_materials,
            "primary_function": primary_function,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if value != canonical:
        raise ValueError(f"{field_name} must use canonical compact JSON")
    return raw_materials, primary_function


def _validate_evidence_encoding(
    evidence_field: RoleEvidenceField,
    evidence_excerpt: str,
    field_name: str,
) -> None:
    _reject_review_text(evidence_excerpt, field_name)
    if evidence_field is RoleEvidenceField.NONE:
        if evidence_excerpt:
            raise ValueError(f"{field_name} must be empty when evidence_field is none")
        return
    if evidence_field is RoleEvidenceField.BOTH:
        _parse_canonical_both_evidence(evidence_excerpt, field_name)
        return
    if not evidence_excerpt.strip():
        raise ValueError(f"{field_name} must be nonblank for a source evidence field")


def _validate_version_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        # Pydantic v2 does not wrap TypeError raised by validators.
        raise ValueError(f"{field_name} must be a tuple-compatible list")  # noqa: TRY004
    versions: list[str] = []
    for item in value:
        text = _reject_review_text(item, field_name)
        if not text.strip() or text != text.strip():
            raise ValueError(f"{field_name} values must be normalized and nonblank")
        versions.append(text)
    version_tuple = tuple(versions)
    if not version_tuple:
        raise ValueError(f"{field_name} must not be empty")
    if version_tuple != tuple(sorted(set(version_tuple))):
        raise ValueError(f"{field_name} must be sorted and unique")
    return version_tuple


class FunctionalRoleSample(_ImmutableContractModel):
    seed: Literal[20260823]
    group: IngredientGroup
    report_no: NonBlankText
    name: NonBlankText
    company: NonBlankText
    primary_function: str
    raw_materials: str
    intake_method: str
    mapping_status: MappingStatus
    mapping_rule_version: NonBlankText
    audit_round: Literal[1, 2]
    sample_origin: SampleOrigin
    is_general_audit: bool
    is_positive_audit: bool
    machine_verdict: MachineRoleVerdict
    machine_reason_code: MachineRoleReasonCode
    machine_evidence_field: RoleEvidenceField
    machine_evidence_excerpt: str
    functional_role_rule_version: NonBlankText

    @field_validator("seed", mode="before")
    @classmethod
    def _parse_csv_seed(cls, value: object) -> object:
        return _parse_csv_literal_int(value, (20260823,))

    @field_validator("audit_round", mode="before")
    @classmethod
    def _parse_csv_audit_round(cls, value: object) -> object:
        return _parse_csv_literal_int(value, (1, 2))

    @field_validator(
        "report_no",
        "mapping_rule_version",
        "machine_evidence_excerpt",
        "functional_role_rule_version",
        mode="before",
    )
    @classmethod
    def _reject_unsafe_machine_text(cls, value: object, info: object) -> str:
        return _reject_review_text(value, getattr(info, "field_name", "machine text"))

    @model_validator(mode="after")
    def _validate_machine_and_audit_contract(self) -> "FunctionalRoleSample":
        if self.group not in COMPARISON_GROUPS:
            raise ValueError("functional-role review requires a comparison ingredient group")
        _validate_evidence_encoding(
            self.machine_evidence_field,
            self.machine_evidence_excerpt,
            "machine_evidence_excerpt",
        )

        if self.machine_verdict is MachineRoleVerdict.FUNCTIONAL_CONFIRMED:
            if (
                self.machine_reason_code is not MachineRoleReasonCode.FUNCTION_AND_FORM_LINKED
                or self.machine_evidence_field is not RoleEvidenceField.BOTH
            ):
                raise ValueError(
                    "functional_confirmed machine rows require linked both-field evidence"
                )
        elif self.machine_verdict is MachineRoleVerdict.PRESENT_NONFUNCTIONAL:
            if (
                self.machine_reason_code is not MachineRoleReasonCode.EXPLICIT_NONFUNCTIONAL_FORM
                or self.machine_evidence_field is not RoleEvidenceField.RAW_MATERIALS
            ):
                raise ValueError(
                    "present_nonfunctional machine rows require explicit raw-material evidence"
                )
        else:
            allowed_fields = {
                MachineRoleReasonCode.FORM_WITHOUT_FUNCTION: {RoleEvidenceField.RAW_MATERIALS},
                MachineRoleReasonCode.FUNCTION_WITHOUT_FORM: {RoleEvidenceField.PRIMARY_FUNCTION},
                MachineRoleReasonCode.COMBINATION_LINKAGE_AMBIGUOUS: {RoleEvidenceField.BOTH},
                MachineRoleReasonCode.CONFLICTING_ROLE_EVIDENCE: {
                    RoleEvidenceField.RAW_MATERIALS,
                    RoleEvidenceField.BOTH,
                },
                MachineRoleReasonCode.NO_APPLICABLE_EVIDENCE: {RoleEvidenceField.NONE},
                MachineRoleReasonCode.INHERITED_MAPPING_ERROR: {RoleEvidenceField.NONE},
            }
            if self.machine_evidence_field not in allowed_fields.get(
                self.machine_reason_code, set()
            ):
                raise ValueError("unverifiable machine reason and evidence field are inconsistent")

        if not self.is_general_audit and not self.is_positive_audit:
            raise ValueError("a sample must participate in at least one audit scope")
        if self.is_positive_audit and (
            self.machine_verdict is not MachineRoleVerdict.FUNCTIONAL_CONFIRMED
        ):
            raise ValueError("positive-audit samples must be machine functional_confirmed")
        if self.sample_origin in {SampleOrigin.V2_ORIGINAL, SampleOrigin.GENERAL_REPLACEMENT}:
            if self.audit_round != 1 or not self.is_general_audit:
                raise ValueError("general-origin samples require round one general audit")
        elif self.audit_round != 2 or self.is_general_audit or not self.is_positive_audit:
            raise ValueError("positive-only origin requires round two positive audit")
        return self


class FunctionalRoleLabel(_ImmutableContractModel):
    group: IngredientGroup
    report_no: NonBlankText
    audit_round: Literal[1, 2]
    machine_verdict: MachineRoleVerdict
    human_verdict: HumanRoleVerdict
    reason_code: FunctionalRoleReasonCode
    evidence_field: RoleEvidenceField
    evidence_excerpt: str
    rule_version: NonBlankText
    review_note: str
    reviewer: NonBlankText
    reviewed_at_iso8601: AwareDatetime

    @field_validator("audit_round", mode="before")
    @classmethod
    def _parse_csv_audit_round(cls, value: object) -> object:
        return _parse_csv_literal_int(value, (1, 2))

    @field_validator(
        "report_no",
        "evidence_excerpt",
        "rule_version",
        "review_note",
        "reviewer",
        mode="before",
    )
    @classmethod
    def _reject_unsafe_human_text(cls, value: object, info: object) -> str:
        return _reject_review_text(value, getattr(info, "field_name", "human text"))

    @model_validator(mode="after")
    def _validate_human_role_contract(self) -> "FunctionalRoleLabel":
        if self.group not in COMPARISON_GROUPS:
            raise ValueError("functional-role review requires a comparison ingredient group")
        _validate_evidence_encoding(
            self.evidence_field,
            self.evidence_excerpt,
            "evidence_excerpt",
        )

        if self.human_verdict is HumanRoleVerdict.FUNCTIONAL_CONFIRMED:
            if (
                self.reason_code is not FunctionalRoleReasonCode.EXPLICIT_TARGET_FUNCTION
                or self.evidence_field is not RoleEvidenceField.BOTH
            ):
                raise ValueError(
                    "functional_confirmed requires explicit_target_function and both evidence"
                )
        elif self.human_verdict is HumanRoleVerdict.PRESENT_NONFUNCTIONAL:
            if (
                self.reason_code is not FunctionalRoleReasonCode.EXPLICIT_NONFUNCTIONAL_ROLE
                or self.evidence_field
                not in {RoleEvidenceField.RAW_MATERIALS, RoleEvidenceField.BOTH}
            ):
                raise ValueError(
                    "present_nonfunctional requires explicit_nonfunctional_role evidence"
                )
        elif self.human_verdict is HumanRoleVerdict.UNCERTAIN:
            if self.reason_code not in {
                FunctionalRoleReasonCode.INSUFFICIENT_LINKAGE,
                FunctionalRoleReasonCode.COMBINATION_AMBIGUOUS,
                FunctionalRoleReasonCode.NEEDS_EXPERT,
                FunctionalRoleReasonCode.OTHER,
            }:
                raise ValueError("uncertain requires a compatible uncertainty reason")
        elif (
            self.machine_verdict is not MachineRoleVerdict.UNVERIFIABLE
            or self.reason_code is not FunctionalRoleReasonCode.INHERITED_MAPPING_ERROR
            or self.evidence_field is not RoleEvidenceField.NONE
            or self.evidence_excerpt
        ):
            raise ValueError("excluded_mapping_error requires empty inherited-mapping evidence")

        if (
            self.reason_code
            in {
                FunctionalRoleReasonCode.NEEDS_EXPERT,
                FunctionalRoleReasonCode.OTHER,
            }
            and not self.review_note.strip()
        ):
            raise ValueError("needs_expert and other reasons require a review note")
        return self


class FunctionalRoleGroupCounts(_ImmutableContractModel):
    group: IngredientGroup
    original_v2_count: int = Field(ge=0)
    inherited_mapping_error_count: int = Field(ge=0)
    general_replacement_count: int = Field(ge=0)
    general_evaluable_count: int = Field(ge=0)
    positive_pool_count: int = Field(ge=0)
    positive_sample_count: int = Field(ge=0)
    total_unique_rows: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_count_contract(self) -> "FunctionalRoleGroupCounts":
        if self.group not in COMPARISON_GROUPS:
            raise ValueError("functional-role counts require a comparison ingredient group")
        if self.original_v2_count != DEFAULT_GENERAL_AUDIT_SIZE:
            raise ValueError("each group must preserve exactly 20 original v2 rows")
        if self.inherited_mapping_error_count > self.original_v2_count:
            raise ValueError("inherited mapping errors cannot exceed original rows")
        if self.general_replacement_count != self.inherited_mapping_error_count:
            raise ValueError("every inherited mapping error requires one general replacement")
        expected_evaluable = (
            self.original_v2_count
            - self.inherited_mapping_error_count
            + self.general_replacement_count
        )
        if self.general_evaluable_count != expected_evaluable:
            raise ValueError("general evaluable count is inconsistent")
        expected_positive_sample = min(
            self.positive_pool_count,
            DEFAULT_POSITIVE_AUDIT_SIZE,
        )
        if self.positive_sample_count != expected_positive_sample:
            raise ValueError("positive sample count is inconsistent with its pool")
        general_unique_count = self.original_v2_count + self.general_replacement_count
        minimum_unique_count = max(general_unique_count, self.positive_sample_count)
        maximum_unique_count = general_unique_count + self.positive_sample_count
        if not minimum_unique_count <= self.total_unique_rows <= maximum_unique_count:
            raise ValueError("total unique row count is inconsistent with audit scopes")
        return self


class FunctionalRoleManifest(_ImmutableContractModel):
    contract_version: Literal["c003-functional-role-v1"] = FUNCTIONAL_ROLE_CONTRACT_VERSION
    seed: Literal[20260823] = 20260823
    general_size_per_group: Literal[20] = DEFAULT_GENERAL_AUDIT_SIZE
    positive_size_per_group: Literal[35] = DEFAULT_POSITIVE_AUDIT_SIZE
    generated_at: AwareDatetime
    source_export_sha256: str = Field(pattern=_SHA256_PATTERN)
    product_review_manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    product_review_samples_sha256: str = Field(pattern=_SHA256_PATTERN)
    product_review_labels_sha256: str = Field(pattern=_SHA256_PATTERN)
    rules_sha256: str = Field(pattern=_SHA256_PATTERN)
    samples_sha256: str = Field(pattern=_SHA256_PATTERN)
    mapping_rule_versions: tuple[NonBlankText, ...]
    functional_role_rule_versions: tuple[NonBlankText, ...]
    group_counts: tuple[FunctionalRoleGroupCounts, ...]

    @field_validator("mapping_rule_versions", "functional_role_rule_versions", mode="before")
    @classmethod
    def _require_sorted_versions(cls, value: object, info: object) -> tuple[str, ...]:
        return _validate_version_tuple(value, getattr(info, "field_name", "versions"))

    @model_validator(mode="after")
    def _validate_manifest_contract(self) -> "FunctionalRoleManifest":
        if tuple(count.group for count in self.group_counts) != COMPARISON_GROUPS:
            raise ValueError("group counts must contain each comparison group in exact order")
        return self


class RoleConfusionCell(_ImmutableContractModel):
    machine_verdict: MachineRoleVerdict
    human_verdict: HumanRoleVerdict
    row_count: int = Field(ge=0)


class FunctionalRoleGroupSummary(_ImmutableContractModel):
    group: IngredientGroup
    audited_row_count: int = Field(ge=0)
    addressable_product_count: int = Field(ge=0)
    general_evaluable_count: int = Field(ge=0)
    positive_pool_count: int = Field(ge=0)
    positive_sample_count: int = Field(ge=0)
    true_functional_confirmed_count: int = Field(ge=0)
    false_confirmation_count: int = Field(ge=0)
    unresolved_positive_count: int = Field(ge=0)
    false_exclusion_count: int = Field(ge=0)
    overconfident_decision_count: int = Field(ge=0)
    avoidable_unverifiable_count: int = Field(ge=0)
    positive_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    positive_precision_wilson_95: WilsonInterval | None
    decidable_agreement_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    decision_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    unverifiable_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    human_uncertainty_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    confusion_matrix: tuple[RoleConfusionCell, ...]
    eligibility: RoleEligibility
    eligibility_reasons: tuple[EligibilityReasonCode, ...]

    @model_validator(mode="after")
    def _validate_summary_contract(self) -> "FunctionalRoleGroupSummary":
        if self.group not in COMPARISON_GROUPS:
            raise ValueError("functional-role summary requires a comparison ingredient group")
        expected_cells = tuple(
            (machine_verdict, human_verdict)
            for machine_verdict in MachineRoleVerdict
            for human_verdict in HumanRoleVerdict
        )
        actual_cells = tuple(
            (cell.machine_verdict, cell.human_verdict) for cell in self.confusion_matrix
        )
        if actual_cells != expected_cells:
            raise ValueError("confusion matrix must contain the complete ordered 3x4 grid")
        if sum(cell.row_count for cell in self.confusion_matrix) != self.audited_row_count:
            raise ValueError("confusion matrix count must equal audited row count")
        expected_reasons = tuple(sorted(set(self.eligibility_reasons), key=lambda item: item.value))
        if self.eligibility_reasons != expected_reasons:
            raise ValueError("eligibility reasons must be sorted and unique")
        if self.eligibility is RoleEligibility.ROLE_ELIGIBLE:
            if self.eligibility_reasons:
                raise ValueError("ROLE_ELIGIBLE must not have insufficiency reasons")
        elif not self.eligibility_reasons:
            raise ValueError("ROLE_INSUFFICIENT requires at least one reason")
        return self


class FunctionalRoleSummary(_ImmutableContractModel):
    contract_version: Literal["c003-functional-role-v1"] = FUNCTIONAL_ROLE_CONTRACT_VERSION
    generated_at: AwareDatetime
    validated_at: AwareDatetime
    source_export_sha256: str = Field(pattern=_SHA256_PATTERN)
    product_review_labels_sha256: str = Field(pattern=_SHA256_PATTERN)
    rules_sha256: str = Field(pattern=_SHA256_PATTERN)
    samples_sha256: str = Field(pattern=_SHA256_PATTERN)
    functional_role_labels_sha256: str = Field(pattern=_SHA256_PATTERN)
    audited_row_count: int = Field(ge=0)
    groups: tuple[FunctionalRoleGroupSummary, ...]
    advertising_evidence_status: Literal["NOT_MEASURED"] = "NOT_MEASURED"
    extension_recommendation_status: Literal["BLOCKED"] = "BLOCKED"
    finalized: Literal[False] = False

    @model_validator(mode="after")
    def _validate_summary_contract(self) -> "FunctionalRoleSummary":
        if self.validated_at < self.generated_at:
            raise ValueError("validation time must not precede generation time")
        if tuple(group.group for group in self.groups) != COMPARISON_GROUPS:
            raise ValueError("summary groups must contain each comparison group in exact order")
        if sum(group.audited_row_count for group in self.groups) != self.audited_row_count:
            raise ValueError("summary audited row count is inconsistent")
        return self


class FunctionalRoleValidationResult(_ImmutableContractModel):
    status: ReviewGateStatus
    expected_label_count: int | None = Field(default=None, ge=1)
    valid_label_count: int | None = Field(default=None, ge=0)
    pending_label_count: int | None = Field(default=None, ge=0)
    issues: tuple[ReviewIssue, ...]
    summary: FunctionalRoleSummary | None
    advertising_evidence_status: Literal["NOT_MEASURED"] = "NOT_MEASURED"
    extension_recommendation_status: Literal["BLOCKED"] = "BLOCKED"
    finalized: Literal[False] = False

    @model_validator(mode="after")
    def _require_status_consistency(self) -> "FunctionalRoleValidationResult":
        if self.status is ReviewGateStatus.COMPLETE:
            if (
                self.expected_label_count is None
                or self.valid_label_count != self.expected_label_count
                or self.pending_label_count != 0
                or self.summary is None
                or self.summary.audited_row_count != self.expected_label_count
                or self.issues
            ):
                raise ValueError("COMPLETE requires all expected labels and a clean summary")
        elif self.status is ReviewGateStatus.PENDING:
            if (
                self.expected_label_count is None
                or self.valid_label_count is None
                or self.pending_label_count is None
                or self.valid_label_count + self.pending_label_count != self.expected_label_count
                or self.pending_label_count == 0
                or self.summary is not None
                or self.issues
            ):
                raise ValueError("PENDING requires a clean incomplete label pack")
        elif (
            self.valid_label_count is not None
            or self.pending_label_count is not None
            or self.summary is not None
            or not self.issues
        ):
            raise ValueError("INVALID requires issues and unreported progress counts")
        return self


def derive_sample_seed(
    base_seed: int,
    group: IngredientGroup,
    scope: SamplingScope,
) -> int:
    if group not in COMPARISON_GROUPS:
        raise ValueError("sampling requires a comparison ingredient group")
    if scope not in {"general-replacement", "positive"}:
        raise ValueError("sampling scope is invalid")
    material = (f"c003-functional-role-v1|{base_seed}|{group.value}|{scope}").encode(_HASH_ENCODING)
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def _candidate_rank(
    product: ExtensionReviewProduct,
    *,
    base_seed: int,
    group: IngredientGroup,
    scope: SamplingScope,
) -> bytes:
    derived_seed = derive_sample_seed(base_seed, group, scope)
    rank_material = (f"{derived_seed}|{group.value}|{scope}|{product.report_no}").encode(
        _HASH_ENCODING
    )
    return hashlib.sha256(rank_material).digest()


def _candidate_sort_key(
    product: ExtensionReviewProduct,
    *,
    base_seed: int,
    group: IngredientGroup,
    scope: SamplingScope,
) -> tuple[bytes, str, str, str]:
    return (
        _candidate_rank(
            product,
            base_seed=base_seed,
            group=group,
            scope=scope,
        ),
        product.report_no,
        product.name,
        product.company,
    )


def _restore_spreadsheet_literal(value: str) -> str:
    if len(value) >= 2 and value[0] == "'" and value[1] in _SPREADSHEET_FORMULA_PREFIXES:
        return value[1:]
    return value


def _spreadsheet_safe_literal(value: str) -> str:
    if value.startswith(_SPREADSHEET_FORMULA_PREFIXES):
        return f"'{value}"
    return value


def _read_csv_contract(
    path: Path,
    expected_fields: tuple[str, ...],
) -> tuple[dict[str, str], ...]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != expected_fields:
            raise ValueError("CSV header does not match its contract")
        rows: list[dict[str, str]] = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("CSV row is malformed")
            rows.append({key: value for key, value in row.items() if key is not None})
    return tuple(rows)


def _load_completed_product_review_pack(
    pack_dir: Path,
    products: tuple[ExtensionReviewProduct, ...],
) -> tuple[
    tuple[ProductReviewSample, ...],
    dict[tuple[IngredientGroup, str], ProductReviewLabel],
    dict[str, ExtensionReviewProduct],
]:
    try:
        if not pack_dir.is_dir():
            raise ValueError("product review pack directory is missing")
        if {path.name for path in pack_dir.iterdir()} != _PRODUCT_REVIEW_PACK_FILES:
            raise ValueError("product review pack file set is invalid")
        manifest = ProductReviewManifest.model_validate_json(
            (pack_dir / "manifest.json").read_text(encoding="utf-8")
        )
        if sha256_file(pack_dir / "samples.csv") != manifest.samples_sha256:
            raise ValueError("product review sample hash is invalid")

        sample_rows = _read_csv_contract(
            pack_dir / "samples.csv",
            tuple(ProductReviewSample.model_fields),
        )
        label_rows = _read_csv_contract(
            pack_dir / "product_review_labels.csv",
            tuple(ProductReviewLabel.model_fields),
        )
        samples = tuple(ProductReviewSample.model_validate(row) for row in sample_rows)
        labels = tuple(ProductReviewLabel.model_validate(row) for row in label_rows)
        if len(samples) != 100 or len(labels) != 100:
            raise ValueError("product review pack must have 100 complete rows")

        product_by_report: dict[str, ExtensionReviewProduct] = {}
        for product in products:
            if product.report_no in product_by_report:
                raise ValueError("source products contain duplicate report numbers")
            product_by_report[product.report_no] = product

        sample_keys: list[tuple[IngredientGroup, str]] = []
        sample_counts: Counter[IngredientGroup] = Counter()
        for sample in samples:
            key = (sample.group, sample.report_no)
            if key in sample_keys:
                raise ValueError("product review samples contain duplicate keys")
            sample_keys.append(key)
            sample_counts[sample.group] += 1
            source_report_no = _restore_spreadsheet_literal(sample.report_no)
            source = product_by_report.get(source_report_no)
            if source is None or any(
                _restore_spreadsheet_literal(getattr(sample, field)) != getattr(source, field)
                for field in _PRODUCT_SOURCE_FIELDS
            ):
                raise ValueError("product review sample does not match source products")
            mapping = map_ingredients(source)
            if (
                sample.group not in mapping.groups
                or sample.mapping_status is not mapping.status
                or sample.mapping_rule_version != mapping.rule_version
            ):
                raise ValueError("product review sample mapping is stale")

        expected_counts = Counter({group: 20 for group in COMPARISON_GROUPS})
        if sample_counts != expected_counts:
            raise ValueError("product review sample group counts are invalid")
        manifest_counts = Counter(
            {
                IngredientGroup(group): count
                for group, count in manifest.group_counts.model_dump().items()
            }
        )
        if sample_counts != manifest_counts:
            raise ValueError("product review manifest counts are stale")
        if tuple(sorted({sample.mapping_rule_version for sample in samples})) != (
            manifest.mapping_rule_versions
        ):
            raise ValueError("product review mapping versions are stale")

        labels_by_key: dict[tuple[IngredientGroup, str], ProductReviewLabel] = {}
        for label in labels:
            key = (label.group, label.report_no)
            if key in labels_by_key:
                raise ValueError("product review labels contain duplicate keys")
            labels_by_key[key] = label
        if set(labels_by_key) != set(sample_keys):
            raise ValueError("product review labels do not match sample keys")
        return samples, labels_by_key, product_by_report
    except (OSError, csv.Error, ValidationError, ValueError, KeyError, TypeError) as exc:
        raise ValueError("product review pack must be COMPLETE") from exc


def _machine_evidence_excerpt(decision: MachineRoleDecision) -> str:
    if decision.evidence_field is RoleEvidenceField.BOTH:
        return json.dumps(
            {
                "raw_materials": decision.raw_materials_excerpt,
                "primary_function": decision.primary_function_excerpt,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    if decision.evidence_field is RoleEvidenceField.RAW_MATERIALS:
        return decision.raw_materials_excerpt
    if decision.evidence_field is RoleEvidenceField.PRIMARY_FUNCTION:
        return decision.primary_function_excerpt
    return ""


def _target_rule_version(
    registry: FunctionalRoleRuleRegistry,
    group: IngredientGroup,
) -> str:
    matching = tuple(rule for rule in registry.rules if rule.group is group)
    if len(matching) != 1:
        raise ValueError("functional-role registry must contain one target rule")
    return matching[0].rule_version


def _functional_sample(
    *,
    source_values: ProductReviewSample | ExtensionReviewProduct,
    decision_product: ExtensionReviewProduct,
    group: IngredientGroup,
    mapping_status: MappingStatus,
    mapping_rule_version: str,
    audit_round: Literal[1, 2],
    sample_origin: SampleOrigin,
    is_general_audit: bool,
    is_positive_audit: bool,
    registry: FunctionalRoleRuleRegistry,
    inherited_mapping_error: bool = False,
) -> FunctionalRoleSample:
    report_no = source_values.report_no
    if isinstance(source_values, ExtensionReviewProduct):
        report_no = _spreadsheet_safe_literal(report_no)
    if inherited_mapping_error:
        machine_verdict = MachineRoleVerdict.UNVERIFIABLE
        machine_reason_code = MachineRoleReasonCode.INHERITED_MAPPING_ERROR
        machine_evidence_field = RoleEvidenceField.NONE
        machine_evidence_excerpt = ""
    else:
        decision = classify_functional_role(decision_product, group, registry)
        machine_verdict = decision.verdict
        machine_reason_code = decision.reason_code
        machine_evidence_field = decision.evidence_field
        machine_evidence_excerpt = _machine_evidence_excerpt(decision)
    return FunctionalRoleSample(
        seed=20260823,
        group=group,
        report_no=report_no,
        name=source_values.name,
        company=source_values.company,
        primary_function=source_values.primary_function,
        raw_materials=source_values.raw_materials,
        intake_method=source_values.intake_method,
        mapping_status=mapping_status,
        mapping_rule_version=mapping_rule_version,
        audit_round=audit_round,
        sample_origin=sample_origin,
        is_general_audit=is_general_audit,
        is_positive_audit=is_positive_audit,
        machine_verdict=machine_verdict,
        machine_reason_code=machine_reason_code,
        machine_evidence_field=machine_evidence_field,
        machine_evidence_excerpt=machine_evidence_excerpt,
        functional_role_rule_version=_target_rule_version(registry, group),
    )


def _mark_positive_audit(sample: FunctionalRoleSample) -> FunctionalRoleSample:
    values = sample.model_dump()
    values["is_positive_audit"] = True
    return FunctionalRoleSample.model_validate(values)


def build_functional_role_samples(
    products: tuple[ExtensionReviewProduct, ...],
    *,
    product_review_pack_dir: Path,
    registry: FunctionalRoleRuleRegistry,
    base_seed: int = 20260823,
    general_size: int = 20,
    positive_size: int = 35,
) -> tuple[FunctionalRoleSample, ...]:
    if (
        base_seed != 20260823
        or general_size != DEFAULT_GENERAL_AUDIT_SIZE
        or positive_size != DEFAULT_POSITIVE_AUDIT_SIZE
    ):
        raise ValueError("functional-role sampling requires the locked seed and sample sizes")
    v2_samples, labels_by_key, product_by_report = _load_completed_product_review_pack(
        product_review_pack_dir,
        products,
    )
    mapping_by_report = {
        report_no: map_ingredients(product) for report_no, product in product_by_report.items()
    }

    samples_by_key: dict[tuple[IngredientGroup, str], FunctionalRoleSample] = {}
    original_keys: list[tuple[IngredientGroup, str]] = []
    inherited_keys_by_group: dict[IngredientGroup, list[tuple[IngredientGroup, str]]] = {
        group: [] for group in COMPARISON_GROUPS
    }
    inherited_source_keys: set[tuple[IngredientGroup, str]] = set()
    for v2_sample in v2_samples:
        key = (v2_sample.group, v2_sample.report_no)
        label = labels_by_key[key]
        source_report_no = _restore_spreadsheet_literal(v2_sample.report_no)
        source = product_by_report[source_report_no]
        inherited_mapping_error = label.mapping_verdict is not MappingVerdict.CORRECT
        sample = _functional_sample(
            source_values=v2_sample,
            decision_product=source,
            group=v2_sample.group,
            mapping_status=v2_sample.mapping_status,
            mapping_rule_version=v2_sample.mapping_rule_version,
            audit_round=1,
            sample_origin=SampleOrigin.V2_ORIGINAL,
            is_general_audit=True,
            is_positive_audit=False,
            registry=registry,
            inherited_mapping_error=inherited_mapping_error,
        )
        samples_by_key[key] = sample
        original_keys.append(key)
        if inherited_mapping_error:
            inherited_keys_by_group[v2_sample.group].append(key)
            inherited_source_keys.add((v2_sample.group, source_report_no))

    replacement_keys_by_group: dict[IngredientGroup, list[tuple[IngredientGroup, str]]] = {
        group: [] for group in COMPARISON_GROUPS
    }
    for group in COMPARISON_GROUPS:
        replacement_count = len(inherited_keys_by_group[group])
        if not replacement_count:
            continue
        candidates = [
            product
            for product in products
            if mapping_by_report[product.report_no].status is MappingStatus.VERIFIED
            and mapping_by_report[product.report_no].groups == (group,)
            and (group, _spreadsheet_safe_literal(product.report_no)) not in samples_by_key
        ]
        ranked_candidates = sorted(
            candidates,
            key=lambda product: _candidate_sort_key(
                product,
                base_seed=base_seed,
                group=group,
                scope="general-replacement",
            ),
        )
        if len(ranked_candidates) < replacement_count:
            raise ValueError("insufficient same-group general replacement candidates")
        for product in ranked_candidates[:replacement_count]:
            mapping = mapping_by_report[product.report_no]
            sample = _functional_sample(
                source_values=product,
                decision_product=product,
                group=group,
                mapping_status=mapping.status,
                mapping_rule_version=mapping.rule_version,
                audit_round=1,
                sample_origin=SampleOrigin.GENERAL_REPLACEMENT,
                is_general_audit=True,
                is_positive_audit=False,
                registry=registry,
            )
            key = (group, sample.report_no)
            samples_by_key[key] = sample
            replacement_keys_by_group[group].append(key)

    positive_only_keys_by_group: dict[IngredientGroup, list[tuple[IngredientGroup, str]]] = {
        group: [] for group in COMPARISON_GROUPS
    }
    for group in COMPARISON_GROUPS:
        positive_pool: list[ExtensionReviewProduct] = []
        for product in products:
            mapping = mapping_by_report[product.report_no]
            if group not in mapping.groups or (group, product.report_no) in inherited_source_keys:
                continue
            decision = classify_functional_role(product, group, registry)
            if decision.verdict is MachineRoleVerdict.FUNCTIONAL_CONFIRMED:
                positive_pool.append(product)
        ranked_positive_pool = sorted(
            positive_pool,
            key=lambda product: _candidate_sort_key(
                product,
                base_seed=base_seed,
                group=group,
                scope="positive",
            ),
        )
        for product in ranked_positive_pool[:positive_size]:
            output_key = (group, _spreadsheet_safe_literal(product.report_no))
            if output_key in samples_by_key:
                samples_by_key[output_key] = _mark_positive_audit(samples_by_key[output_key])
                continue
            mapping = mapping_by_report[product.report_no]
            sample = _functional_sample(
                source_values=product,
                decision_product=product,
                group=group,
                mapping_status=mapping.status,
                mapping_rule_version=mapping.rule_version,
                audit_round=2,
                sample_origin=SampleOrigin.POSITIVE_PRECISION,
                is_general_audit=False,
                is_positive_audit=True,
                registry=registry,
            )
            samples_by_key[output_key] = sample
            positive_only_keys_by_group[group].append(output_key)

    ordered_keys = [*original_keys]
    for group in COMPARISON_GROUPS:
        ordered_keys.extend(replacement_keys_by_group[group])
    for group in COMPARISON_GROUPS:
        ordered_keys.extend(positive_only_keys_by_group[group])
    if len(ordered_keys) != len(set(ordered_keys)):
        raise ValueError("functional-role samples contain duplicate composite keys")
    return tuple(samples_by_key[key] for key in ordered_keys)


def _serialize_csv(
    fields: tuple[str, ...],
    rows: tuple[dict[str, object], ...],
) -> str:
    handle = StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue()


def _sample_csv_row(sample: FunctionalRoleSample) -> dict[str, object]:
    row = sample.model_dump(mode="json")
    for field in _PRODUCT_SOURCE_FIELDS:
        row[field] = _spreadsheet_safe_literal(str(row[field]))
    return row


def _functional_role_label_rows(
    samples: tuple[FunctionalRoleSample, ...],
    v2_labels_by_key: dict[tuple[IngredientGroup, str], ProductReviewLabel],
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for sample in samples:
        row: dict[str, object] = {
            "group": sample.group.value,
            "report_no": sample.report_no,
            "audit_round": sample.audit_round,
            "machine_verdict": sample.machine_verdict.value,
            "human_verdict": "",
            "reason_code": "",
            "evidence_field": "",
            "evidence_excerpt": "",
            "rule_version": "",
            "review_note": "",
            "reviewer": "",
            "reviewed_at_iso8601": "",
        }
        if sample.machine_reason_code is MachineRoleReasonCode.INHERITED_MAPPING_ERROR:
            v2_label = v2_labels_by_key[(sample.group, sample.report_no)]
            row.update(
                {
                    "human_verdict": HumanRoleVerdict.EXCLUDED_MAPPING_ERROR.value,
                    "reason_code": FunctionalRoleReasonCode.INHERITED_MAPPING_ERROR.value,
                    "evidence_field": RoleEvidenceField.NONE.value,
                    "rule_version": sample.functional_role_rule_version,
                    "review_note": (
                        "Inherited c003-product-review-v2 mapping verdict: "
                        f"{v2_label.mapping_verdict.value}/"
                        f"{v2_label.mapping_reason_code.value}."
                    ),
                    "reviewer": v2_label.reviewer,
                    "reviewed_at_iso8601": v2_label.model_dump(mode="json")["reviewed_at_iso8601"],
                }
            )
        rows.append(row)
    return tuple(rows)


def _functional_role_group_counts(
    products: tuple[ExtensionReviewProduct, ...],
    samples: tuple[FunctionalRoleSample, ...],
    v2_samples: tuple[ProductReviewSample, ...],
    v2_labels_by_key: dict[tuple[IngredientGroup, str], ProductReviewLabel],
    registry: FunctionalRoleRuleRegistry,
) -> tuple[FunctionalRoleGroupCounts, ...]:
    inherited_source_keys = {
        (sample.group, _restore_spreadsheet_literal(sample.report_no))
        for sample in v2_samples
        if v2_labels_by_key[(sample.group, sample.report_no)].mapping_verdict
        is not MappingVerdict.CORRECT
    }
    counts: list[FunctionalRoleGroupCounts] = []
    for group in COMPARISON_GROUPS:
        group_samples = tuple(sample for sample in samples if sample.group is group)
        positive_pool_count = sum(
            group in map_ingredients(product).groups
            and (group, product.report_no) not in inherited_source_keys
            and classify_functional_role(product, group, registry).verdict
            is MachineRoleVerdict.FUNCTIONAL_CONFIRMED
            for product in products
        )
        counts.append(
            FunctionalRoleGroupCounts(
                group=group,
                original_v2_count=sum(
                    sample.sample_origin is SampleOrigin.V2_ORIGINAL for sample in group_samples
                ),
                inherited_mapping_error_count=sum(
                    sample.machine_reason_code is MachineRoleReasonCode.INHERITED_MAPPING_ERROR
                    for sample in group_samples
                ),
                general_replacement_count=sum(
                    sample.sample_origin is SampleOrigin.GENERAL_REPLACEMENT
                    for sample in group_samples
                ),
                general_evaluable_count=sum(
                    sample.is_general_audit
                    and sample.machine_reason_code
                    is not MachineRoleReasonCode.INHERITED_MAPPING_ERROR
                    for sample in group_samples
                ),
                positive_pool_count=positive_pool_count,
                positive_sample_count=sum(sample.is_positive_audit for sample in group_samples),
                total_unique_rows=len(group_samples),
            )
        )
    return tuple(counts)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode(_HASH_ENCODING)).hexdigest().upper()


def _functional_role_readme(
    samples: tuple[FunctionalRoleSample, ...],
    group_counts: tuple[FunctionalRoleGroupCounts, ...],
) -> str:
    group_lines = "\n".join(
        f"- `{count.group.value}`: {count.total_unique_rows} unique audit rows"
        for count in group_counts
    )
    return f"""# C003 Functional-Role Review Pack v1

- Seed: `20260823`
- General audit size: `20` evaluable rows per comparison group
- Positive audit target: up to `35` machine-positive rows per comparison group
- Total unique rows: `{len(samples)}`
- Review status: PENDING
- advertising evidence: NOT_MEASURED
- extension recommendation: BLOCKED
- finalized: false

## Sample counts

{group_lines}

## Human review contract

Review each machine decision against the literal product fields and the bound functional-role
rule. Rows inherited from a non-correct v2 mapping remain excluded. Every other row stays blank
until a human reviewer records a compatible verdict, reason, literal evidence, rule version,
reviewer identifier, and timezone-aware timestamp. This pack cannot measure advertising evidence,
select an extension ingredient, or finalize a recommendation.
"""


def _write_utf8_lf(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _load_source_products(source_export_path: Path) -> tuple[ExtensionReviewProduct, ...]:
    products = tuple(
        ExtensionReviewProduct.model_validate_json(line)
        for line in source_export_path.read_text(encoding="utf-8").splitlines()
    )
    if len({product.report_no for product in products}) != len(products):
        raise ValueError("source export contains duplicate report numbers")
    return products


def _products_match_source_export(
    products: tuple[ExtensionReviewProduct, ...],
    source_export_path: Path,
) -> bool:
    source_products = _load_source_products(source_export_path)
    source_by_report = {product.report_no: product for product in source_products}
    provided_by_report = {product.report_no: product for product in products}
    return len(provided_by_report) == len(products) and provided_by_report == source_by_report


def write_functional_role_review_pack(
    output_dir: Path,
    *,
    products: tuple[ExtensionReviewProduct, ...],
    source_export_path: Path,
    product_review_pack_dir: Path,
    rules_path: Path,
    registry: FunctionalRoleRuleRegistry,
    generated_at: AwareDatetime,
    base_seed: int = 20260823,
    general_size: int = DEFAULT_GENERAL_AUDIT_SIZE,
    positive_size: int = DEFAULT_POSITIVE_AUDIT_SIZE,
) -> FunctionalRoleManifest:
    if output_dir.exists():
        raise FunctionalRoleBuildError("output directory already exists")
    try:
        output_inside_product_review_pack = output_dir.resolve().is_relative_to(
            product_review_pack_dir.resolve()
        )
    except OSError as exc:
        raise FunctionalRoleBuildError("functional-role output path is invalid") from exc
    if output_inside_product_review_pack:
        raise FunctionalRoleBuildError(
            "output directory must not be inside the product review pack"
        )
    if (
        base_seed != 20260823
        or general_size != DEFAULT_GENERAL_AUDIT_SIZE
        or positive_size != DEFAULT_POSITIVE_AUDIT_SIZE
    ):
        raise FunctionalRoleBuildError("functional-role build requires locked sampling settings")

    try:
        v2_validation = validate_product_review_pack(
            product_review_pack_dir,
            source_export_path,
            validated_at=generated_at,
        )
        if v2_validation.status is not ReviewGateStatus.COMPLETE:
            raise FunctionalRoleBuildError("product review pack must be COMPLETE")
        if not _products_match_source_export(products, source_export_path):
            raise FunctionalRoleBuildError("products do not match the bound source export")
        loaded_registry = load_functional_role_registry(
            rules_path,
            evaluated_at=generated_at,
        )
        if loaded_registry != registry:
            raise FunctionalRoleBuildError("registry input does not match the validated rules file")
        samples = build_functional_role_samples(
            products,
            product_review_pack_dir=product_review_pack_dir,
            registry=loaded_registry,
            base_seed=base_seed,
            general_size=general_size,
            positive_size=positive_size,
        )
        v2_samples, v2_labels_by_key, _ = _load_completed_product_review_pack(
            product_review_pack_dir,
            products,
        )
        group_counts = _functional_role_group_counts(
            products,
            samples,
            v2_samples,
            v2_labels_by_key,
            loaded_registry,
        )
        samples_text = _serialize_csv(
            tuple(FunctionalRoleSample.model_fields),
            tuple(_sample_csv_row(sample) for sample in samples),
        )
        labels_text = _serialize_csv(
            tuple(FunctionalRoleLabel.model_fields),
            _functional_role_label_rows(samples, v2_labels_by_key),
        )
        manifest = FunctionalRoleManifest(
            seed=base_seed,
            general_size_per_group=general_size,
            positive_size_per_group=positive_size,
            generated_at=generated_at,
            source_export_sha256=sha256_file(source_export_path),
            product_review_manifest_sha256=sha256_file(product_review_pack_dir / "manifest.json"),
            product_review_samples_sha256=sha256_file(product_review_pack_dir / "samples.csv"),
            product_review_labels_sha256=sha256_file(
                product_review_pack_dir / "product_review_labels.csv"
            ),
            rules_sha256=sha256_file(rules_path),
            samples_sha256=_sha256_text(samples_text),
            mapping_rule_versions=tuple(
                sorted({sample.mapping_rule_version for sample in samples})
            ),
            functional_role_rule_versions=tuple(
                sorted({sample.functional_role_rule_version for sample in samples})
            ),
            group_counts=group_counts,
        )
        manifest_text = (
            json.dumps(
                manifest.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        readme_text = _functional_role_readme(samples, group_counts)
    except FunctionalRoleBuildError:
        raise
    except Exception as exc:
        raise FunctionalRoleBuildError("could not build functional-role review pack") from exc

    try:
        output_dir.mkdir(parents=True)
    except Exception as exc:
        raise FunctionalRoleBuildError("could not create functional-role review pack") from exc
    try:
        _write_utf8_lf(output_dir / "README.md", readme_text)
        _write_utf8_lf(output_dir / "manifest.json", manifest_text)
        _write_utf8_lf(output_dir / "samples.csv", samples_text)
        _write_utf8_lf(output_dir / "functional_role_labels.csv", labels_text)
        if {path.name for path in output_dir.iterdir()} != _FUNCTIONAL_ROLE_PACK_FILES:
            raise OSError("functional-role pack file set is incomplete")
        if sha256_file(output_dir / "samples.csv") != manifest.samples_sha256:
            raise OSError("functional-role sample write is inconsistent")
    except Exception as exc:
        try:
            shutil.rmtree(output_dir)
        except OSError as cleanup_exc:
            raise FunctionalRoleBuildError(
                "could not clean a partial functional-role review pack"
            ) from cleanup_exc
        raise FunctionalRoleBuildError("could not write functional-role review pack") from exc
    return manifest


def _role_issue(
    code: str,
    message: str,
    *,
    line_number: int | None = None,
    group: str | None = None,
    report_no: str | None = None,
) -> ReviewIssue:
    return ReviewIssue(
        code=code,
        message=message,
        line_number=line_number,
        group=group,
        report_no=report_no,
    )


def _role_issue_sort_key(issue: ReviewIssue) -> tuple[int, str, str, str, str]:
    return (
        issue.line_number if issue.line_number is not None else -1,
        issue.code,
        issue.group or "",
        issue.report_no or "",
        issue.message,
    )


def _invalid_role_result(
    issues: list[ReviewIssue],
    *,
    expected_label_count: int | None = None,
) -> FunctionalRoleValidationResult:
    return FunctionalRoleValidationResult(
        status=ReviewGateStatus.INVALID,
        expected_label_count=expected_label_count,
        valid_label_count=None,
        pending_label_count=None,
        issues=tuple(sorted(issues, key=_role_issue_sort_key)),
        summary=None,
    )


def _read_bounded_utf8(
    path: Path,
    *,
    document_name: str,
    read_issue_code: str,
    issues: list[ReviewIssue],
) -> str | None:
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX_VALIDATION_DOCUMENT_BYTES + 1)
    except OSError:
        issues.append(_role_issue(read_issue_code, f"{document_name} is unreadable"))
        return None
    if len(raw) > _MAX_VALIDATION_DOCUMENT_BYTES:
        issues.append(
            _role_issue(
                "DOCUMENT_TOO_LARGE",
                f"{document_name} exceeds the validation size limit",
            )
        )
        return None
    if b"\x00" in raw:
        issues.append(_role_issue("NUL_BYTE", f"{document_name} contains a NUL byte"))
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        issues.append(_role_issue(read_issue_code, f"{document_name} is not UTF-8"))
        return None
    if any(pattern.search(text) for pattern in _SECRET_PATTERNS):
        issues.append(_role_issue("POSSIBLE_SECRET", f"{document_name} contains a possible secret"))
    return text


def _parse_validation_csv(
    text: str,
    expected_fields: tuple[str, ...],
    *,
    header_issue_code: str,
    row_issue_code: str,
    document_name: str,
    issues: list[ReviewIssue],
) -> list[tuple[int, dict[str, str]]]:
    try:
        reader = csv.DictReader(StringIO(text, newline=""), strict=True)
        if tuple(reader.fieldnames or ()) != expected_fields:
            issues.append(
                _role_issue(
                    header_issue_code,
                    f"{document_name} header does not match the contract",
                )
            )
            return []
        rows: list[tuple[int, dict[str, str]]] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                issues.append(
                    _role_issue(
                        row_issue_code,
                        f"{document_name} row is malformed",
                        line_number=line_number,
                    )
                )
                continue
            rows.append(
                (
                    line_number,
                    {key: value for key, value in row.items() if key is not None},
                )
            )
        return rows
    except csv.Error:
        issues.append(_role_issue(row_issue_code, f"{document_name} is malformed"))
        return []


def _hash_matches(
    expected: str,
    path: Path,
    *,
    mismatch_code: str,
    document_name: str,
    issues: list[ReviewIssue],
) -> None:
    try:
        actual = sha256_file(path)
    except OSError:
        issues.append(_role_issue("HASH_READ_FAILED", f"{document_name} hash is unreadable"))
        return
    if actual != expected:
        issues.append(_role_issue(mismatch_code, f"{document_name} hash does not match manifest"))


def _csv_rows_from_serialized(text: str) -> tuple[dict[str, str], ...]:
    return tuple(csv.DictReader(StringIO(text, newline="")))


def _compare_expected_samples(
    actual_rows: list[tuple[int, dict[str, str]]],
    expected_samples: tuple[FunctionalRoleSample, ...],
    issues: list[ReviewIssue],
) -> None:
    expected_text = _serialize_csv(
        tuple(FunctionalRoleSample.model_fields),
        tuple(_sample_csv_row(sample) for sample in expected_samples),
    )
    expected_rows = _csv_rows_from_serialized(expected_text)
    if len(actual_rows) != len(expected_rows):
        issues.append(
            _role_issue(
                "SAMPLE_COUNT_MISMATCH",
                "sample row count does not match deterministic reconstruction",
            )
        )
    for index, ((line_number, actual), expected) in enumerate(
        zip(actual_rows, expected_rows, strict=False)
    ):
        if actual != expected:
            expected_sample = expected_samples[index]
            issues.append(
                _role_issue(
                    "SAMPLE_MISMATCH",
                    "sample row does not match deterministic reconstruction",
                    line_number=line_number,
                    group=expected_sample.group.value,
                    report_no=expected_sample.report_no,
                )
            )


def _validate_manifest_derived_values(
    manifest: FunctionalRoleManifest,
    *,
    products: tuple[ExtensionReviewProduct, ...],
    expected_samples: tuple[FunctionalRoleSample, ...],
    product_review_pack_dir: Path,
    registry: FunctionalRoleRuleRegistry,
    validated_at: datetime,
    issues: list[ReviewIssue],
) -> dict[tuple[IngredientGroup, str], ProductReviewLabel] | None:
    if manifest.generated_at > validated_at:
        issues.append(
            _role_issue(
                "MANIFEST_GENERATED_AT_FUTURE",
                "manifest generation time is later than validation time",
            )
        )
    expected_mapping_versions = tuple(
        sorted({sample.mapping_rule_version for sample in expected_samples})
    )
    if manifest.mapping_rule_versions != expected_mapping_versions:
        issues.append(
            _role_issue(
                "MANIFEST_MAPPING_VERSIONS_MISMATCH",
                "manifest mapping versions do not match reconstructed samples",
            )
        )
    expected_role_versions = tuple(
        sorted({sample.functional_role_rule_version for sample in expected_samples})
    )
    if manifest.functional_role_rule_versions != expected_role_versions:
        issues.append(
            _role_issue(
                "MANIFEST_ROLE_VERSIONS_MISMATCH",
                "manifest functional-role versions do not match reconstructed samples",
            )
        )
    try:
        v2_samples, v2_labels_by_key, _ = _load_completed_product_review_pack(
            product_review_pack_dir,
            products,
        )
        expected_counts = _functional_role_group_counts(
            products,
            expected_samples,
            v2_samples,
            v2_labels_by_key,
            registry,
        )
    except (OSError, ValidationError, ValueError, csv.Error):
        issues.append(
            _role_issue(
                "MANIFEST_RECOMPUTE_FAILED",
                "manifest counts could not be independently reconstructed",
            )
        )
        return None
    if manifest.group_counts != expected_counts:
        issues.append(
            _role_issue(
                "MANIFEST_GROUP_COUNTS_MISMATCH",
                "manifest group counts do not match reconstructed samples",
            )
        )
    return v2_labels_by_key


def _sample_models_by_key(
    sample_rows: list[tuple[int, dict[str, str]]],
    issues: list[ReviewIssue],
) -> dict[tuple[IngredientGroup, str], FunctionalRoleSample]:
    samples_by_key: dict[tuple[IngredientGroup, str], FunctionalRoleSample] = {}
    for line_number, row in sample_rows:
        try:
            sample = FunctionalRoleSample.model_validate(row)
        except ValidationError:
            issues.append(
                _role_issue(
                    "SAMPLE_ROW_INVALID",
                    "sample row violates the functional-role contract",
                    line_number=line_number,
                )
            )
            continue
        key = (sample.group, sample.report_no)
        if key in samples_by_key:
            issues.append(
                _role_issue(
                    "DUPLICATE_SAMPLE_KEY",
                    "samples contain a duplicate composite key",
                    line_number=line_number,
                    group=sample.group.value,
                    report_no=sample.report_no,
                )
            )
            continue
        samples_by_key[key] = sample
    return samples_by_key


def _evidence_is_literal(
    label: FunctionalRoleLabel,
    source: ExtensionReviewProduct,
) -> bool:
    if label.evidence_field is RoleEvidenceField.NONE:
        return True
    if label.evidence_field is RoleEvidenceField.RAW_MATERIALS:
        return label.evidence_excerpt in source.raw_materials
    if label.evidence_field is RoleEvidenceField.PRIMARY_FUNCTION:
        return label.evidence_excerpt in source.primary_function
    try:
        evidence = json.loads(label.evidence_excerpt)
    except (json.JSONDecodeError, TypeError):
        return False
    return (
        isinstance(evidence, dict)
        and evidence.get("raw_materials") in source.raw_materials
        and evidence.get("primary_function") in source.primary_function
    )


def _validate_role_labels(
    label_rows: list[tuple[int, dict[str, str]]],
    *,
    expected_samples: tuple[FunctionalRoleSample, ...],
    products: tuple[ExtensionReviewProduct, ...],
    v2_labels_by_key: dict[tuple[IngredientGroup, str], ProductReviewLabel],
    validated_at: datetime,
    issues: list[ReviewIssue],
) -> tuple[int, int]:
    expected_by_key = {(sample.group, sample.report_no): sample for sample in expected_samples}
    source_by_report = {product.report_no: product for product in products}
    inherited_expected_by_key: dict[tuple[IngredientGroup, str], dict[str, str]] = {}
    for sample in expected_samples:
        if sample.machine_reason_code is not MachineRoleReasonCode.INHERITED_MAPPING_ERROR:
            continue
        key = (sample.group, sample.report_no)
        v2_label = v2_labels_by_key[key]
        inherited_expected_by_key[key] = {
            "group": sample.group.value,
            "report_no": sample.report_no,
            "audit_round": str(sample.audit_round),
            "machine_verdict": sample.machine_verdict.value,
            "human_verdict": HumanRoleVerdict.EXCLUDED_MAPPING_ERROR.value,
            "reason_code": FunctionalRoleReasonCode.INHERITED_MAPPING_ERROR.value,
            "evidence_field": RoleEvidenceField.NONE.value,
            "evidence_excerpt": "",
            "rule_version": sample.functional_role_rule_version,
            "review_note": (
                "Inherited c003-product-review-v2 mapping verdict: "
                f"{v2_label.mapping_verdict.value}/{v2_label.mapping_reason_code.value}."
            ),
            "reviewer": v2_label.reviewer,
            "reviewed_at_iso8601": v2_label.model_dump(mode="json")["reviewed_at_iso8601"],
        }
    seen_keys: set[tuple[IngredientGroup, str]] = set()
    valid_count = 0
    pending_count = 0
    for line_number, row in label_rows:
        try:
            group = IngredientGroup(row["group"])
        except (KeyError, ValueError):
            issues.append(
                _role_issue(
                    "INVALID_LABEL_KEY",
                    "label row has an invalid group",
                    line_number=line_number,
                )
            )
            continue
        report_no = row.get("report_no", "")
        key = (group, report_no)
        if key in seen_keys:
            issues.append(
                _role_issue(
                    "DUPLICATE_LABEL_KEY",
                    "labels contain a duplicate composite key",
                    line_number=line_number,
                    group=group.value,
                    report_no=report_no or None,
                )
            )
            continue
        seen_keys.add(key)
        sample = expected_by_key.get(key)
        if sample is None:
            issues.append(
                _role_issue(
                    "UNKNOWN_LABEL_KEY",
                    "label key is absent from reconstructed samples",
                    line_number=line_number,
                    group=group.value,
                    report_no=report_no or None,
                )
            )
            continue
        row_issue_count = len(issues)
        if (
            row.get("audit_round") != str(sample.audit_round)
            or row.get("machine_verdict") != sample.machine_verdict.value
        ):
            issues.append(
                _role_issue(
                    "LABEL_MACHINE_MISMATCH",
                    "label audit round or machine verdict does not match its sample",
                    line_number=line_number,
                    group=group.value,
                    report_no=report_no,
                )
            )
        inherited_expected = inherited_expected_by_key.get(key)
        if inherited_expected is not None:
            if row != inherited_expected:
                issues.append(
                    _role_issue(
                        "INHERITED_LABEL_MISMATCH",
                        "inherited mapping label does not match deterministic values",
                        line_number=line_number,
                        group=group.value,
                        report_no=report_no,
                    )
                )
            if v2_labels_by_key[key].reviewed_at_iso8601 > validated_at:
                issues.append(
                    _role_issue(
                        "LABEL_REVIEWED_AT_FUTURE",
                        "inherited label review time is later than validation time",
                        line_number=line_number,
                        group=group.value,
                        report_no=report_no,
                    )
                )
            if len(issues) == row_issue_count:
                valid_count += 1
            continue

        human_values = [row.get(field, "") for field in _HUMAN_ROLE_INPUT_FIELDS]
        if all(value == "" for value in human_values):
            if len(issues) == row_issue_count:
                pending_count += 1
            continue
        if any(not row.get(field, "").strip() for field in _REQUIRED_COMPLETED_ROLE_FIELDS):
            issues.append(
                _role_issue(
                    "PARTIAL_LABEL",
                    "label row contains only part of a human review",
                    line_number=line_number,
                    group=group.value,
                    report_no=report_no,
                )
            )
            continue
        try:
            label = FunctionalRoleLabel.model_validate(row)
        except ValidationError:
            issues.append(
                _role_issue(
                    "LABEL_VALUE_INVALID",
                    "label row violates the human review contract",
                    line_number=line_number,
                    group=group.value,
                    report_no=report_no,
                )
            )
            continue
        if label.machine_verdict is not sample.machine_verdict:
            issues.append(
                _role_issue(
                    "LABEL_MACHINE_MISMATCH",
                    "label machine verdict does not match reconstructed sample",
                    line_number=line_number,
                    group=group.value,
                    report_no=report_no,
                )
            )
        if (
            label.human_verdict is HumanRoleVerdict.EXCLUDED_MAPPING_ERROR
            and sample.machine_reason_code is not MachineRoleReasonCode.INHERITED_MAPPING_ERROR
        ):
            issues.append(
                _role_issue(
                    "NON_INHERITED_MAPPING_EXCLUSION",
                    "mapping exclusion is allowed only for an inherited v2 mapping error",
                    line_number=line_number,
                    group=group.value,
                    report_no=report_no,
                )
            )
        if label.rule_version != sample.functional_role_rule_version:
            issues.append(
                _role_issue(
                    "LABEL_RULE_VERSION_MISMATCH",
                    "label rule version does not match reconstructed sample",
                    line_number=line_number,
                    group=group.value,
                    report_no=report_no,
                )
            )
        if label.reviewed_at_iso8601 > validated_at:
            issues.append(
                _role_issue(
                    "LABEL_REVIEWED_AT_FUTURE",
                    "label review time is later than validation time",
                    line_number=line_number,
                    group=group.value,
                    report_no=report_no,
                )
            )
        source_report_no = _restore_spreadsheet_literal(report_no)
        source = source_by_report.get(source_report_no)
        if source is None or not _evidence_is_literal(label, source):
            issues.append(
                _role_issue(
                    "EVIDENCE_NOT_LITERAL",
                    "label evidence is not a literal substring of its declared source field",
                    line_number=line_number,
                    group=group.value,
                    report_no=report_no,
                )
            )
        if len(issues) == row_issue_count:
            valid_count += 1
    if seen_keys != set(expected_by_key):
        issues.append(
            _role_issue(
                "LABEL_KEY_SET_MISMATCH",
                "label and reconstructed sample key sets do not match",
            )
        )
    return valid_count, pending_count


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _group_accuracy_summary(
    group: IngredientGroup,
    *,
    samples: tuple[FunctionalRoleSample, ...],
    labels_by_key: dict[tuple[IngredientGroup, str], FunctionalRoleLabel],
    group_counts: FunctionalRoleGroupCounts,
) -> FunctionalRoleGroupSummary:
    group_pairs = tuple(
        (sample, labels_by_key[(sample.group, sample.report_no)])
        for sample in samples
        if sample.group is group
    )
    metric_pairs = tuple(
        pair
        for pair in group_pairs
        if pair[1].human_verdict is not HumanRoleVerdict.EXCLUDED_MAPPING_ERROR
    )
    positive_pairs = tuple(pair for pair in metric_pairs if pair[0].is_positive_audit)
    general_pairs = tuple(pair for pair in metric_pairs if pair[0].is_general_audit)

    decisive_machine = {
        MachineRoleVerdict.FUNCTIONAL_CONFIRMED,
        MachineRoleVerdict.PRESENT_NONFUNCTIONAL,
    }
    decisive_human = {
        HumanRoleVerdict.FUNCTIONAL_CONFIRMED,
        HumanRoleVerdict.PRESENT_NONFUNCTIONAL,
    }
    true_functional_confirmed_count = sum(
        label.human_verdict is HumanRoleVerdict.FUNCTIONAL_CONFIRMED for _, label in positive_pairs
    )
    false_confirmation_count = sum(
        label.human_verdict is HumanRoleVerdict.PRESENT_NONFUNCTIONAL for _, label in positive_pairs
    )
    unresolved_positive_count = sum(
        label.human_verdict is HumanRoleVerdict.UNCERTAIN for _, label in positive_pairs
    )
    false_exclusion_count = sum(
        sample.machine_verdict is MachineRoleVerdict.PRESENT_NONFUNCTIONAL
        and label.human_verdict is HumanRoleVerdict.FUNCTIONAL_CONFIRMED
        for sample, label in metric_pairs
    )
    overconfident_decision_count = sum(
        sample.machine_verdict in decisive_machine
        and label.human_verdict is HumanRoleVerdict.UNCERTAIN
        for sample, label in metric_pairs
    )
    avoidable_unverifiable_count = sum(
        sample.machine_verdict is MachineRoleVerdict.UNVERIFIABLE
        and label.human_verdict in decisive_human
        for sample, label in metric_pairs
    )
    general_conflict_count = sum(
        sample.machine_verdict in decisive_machine
        and label.human_verdict in decisive_human
        and sample.machine_verdict.value != label.human_verdict.value
        for sample, label in general_pairs
    )

    confusion_counts = Counter(
        (sample.machine_verdict, label.human_verdict) for sample, label in group_pairs
    )
    confusion_matrix = tuple(
        RoleConfusionCell(
            machine_verdict=machine_verdict,
            human_verdict=human_verdict,
            row_count=confusion_counts[(machine_verdict, human_verdict)],
        )
        for machine_verdict in MachineRoleVerdict
        for human_verdict in HumanRoleVerdict
    )

    metric_row_count = len(metric_pairs)
    decidable_pairs = tuple(
        (sample, label)
        for sample, label in metric_pairs
        if sample.machine_verdict in decisive_machine and label.human_verdict in decisive_human
    )
    decidable_agreement_count = sum(
        sample.machine_verdict.value == label.human_verdict.value
        for sample, label in decidable_pairs
    )
    machine_decisive_count = sum(
        sample.machine_verdict in decisive_machine for sample, _ in metric_pairs
    )
    machine_unverifiable_count = sum(
        sample.machine_verdict is MachineRoleVerdict.UNVERIFIABLE for sample, _ in metric_pairs
    )
    human_uncertain_count = sum(
        label.human_verdict is HumanRoleVerdict.UNCERTAIN for _, label in metric_pairs
    )

    positive_sample_count = len(positive_pairs)
    positive_precision = _rate(
        true_functional_confirmed_count,
        positive_sample_count,
    )
    positive_wilson = wilson_interval(
        true_functional_confirmed_count,
        positive_sample_count,
    )
    addressable_product_count = group_counts.positive_pool_count

    reasons: set[EligibilityReasonCode] = set()
    if group_counts.positive_pool_count < DEFAULT_POSITIVE_AUDIT_SIZE:
        reasons.add(EligibilityReasonCode.POSITIVE_POOL_TOO_SMALL)
    if positive_sample_count < DEFAULT_POSITIVE_AUDIT_SIZE:
        reasons.add(EligibilityReasonCode.POSITIVE_SAMPLE_TOO_SMALL)
    if len(general_pairs) != DEFAULT_GENERAL_AUDIT_SIZE or general_conflict_count:
        reasons.add(EligibilityReasonCode.GENERAL_AUDIT_CONFLICT)
    if false_confirmation_count:
        reasons.add(EligibilityReasonCode.FALSE_CONFIRMATION)
    if false_exclusion_count:
        reasons.add(EligibilityReasonCode.FALSE_EXCLUSION)
    if unresolved_positive_count:
        reasons.add(EligibilityReasonCode.UNRESOLVED_POSITIVE)
    if overconfident_decision_count:
        reasons.add(EligibilityReasonCode.OVERCONFIDENT_DECISION)
    if positive_wilson is None or positive_wilson.lower < POSITIVE_WILSON_LOWER_THRESHOLD:
        reasons.add(EligibilityReasonCode.POSITIVE_WILSON_BELOW_THRESHOLD)
    if addressable_product_count == 0:
        reasons.add(EligibilityReasonCode.NO_ADDRESSABLE_PRODUCTS)
    eligibility_reasons = tuple(sorted(reasons, key=lambda reason: reason.value))

    return FunctionalRoleGroupSummary(
        group=group,
        audited_row_count=len(group_pairs),
        addressable_product_count=addressable_product_count,
        general_evaluable_count=len(general_pairs),
        positive_pool_count=group_counts.positive_pool_count,
        positive_sample_count=positive_sample_count,
        true_functional_confirmed_count=true_functional_confirmed_count,
        false_confirmation_count=false_confirmation_count,
        unresolved_positive_count=unresolved_positive_count,
        false_exclusion_count=false_exclusion_count,
        overconfident_decision_count=overconfident_decision_count,
        avoidable_unverifiable_count=avoidable_unverifiable_count,
        positive_precision=positive_precision,
        positive_precision_wilson_95=positive_wilson,
        decidable_agreement_rate=_rate(
            decidable_agreement_count,
            len(decidable_pairs),
        ),
        decision_coverage=_rate(machine_decisive_count, metric_row_count),
        unverifiable_rate=_rate(machine_unverifiable_count, metric_row_count),
        human_uncertainty_rate=_rate(human_uncertain_count, metric_row_count),
        confusion_matrix=confusion_matrix,
        eligibility=(
            RoleEligibility.ROLE_INSUFFICIENT
            if eligibility_reasons
            else RoleEligibility.ROLE_ELIGIBLE
        ),
        eligibility_reasons=eligibility_reasons,
    )


def _functional_role_summary(
    *,
    manifest: FunctionalRoleManifest,
    samples: tuple[FunctionalRoleSample, ...],
    labels: tuple[FunctionalRoleLabel, ...],
    functional_role_labels_sha256: str,
    validated_at: datetime,
) -> FunctionalRoleSummary:
    labels_by_key = {(label.group, label.report_no): label for label in labels}
    expected_keys = {(sample.group, sample.report_no) for sample in samples}
    if len(labels_by_key) != len(labels) or set(labels_by_key) != expected_keys:
        raise ValueError("metric labels must match every unique sample key")
    group_counts_by_group = {counts.group: counts for counts in manifest.group_counts}
    groups = tuple(
        _group_accuracy_summary(
            group,
            samples=samples,
            labels_by_key=labels_by_key,
            group_counts=group_counts_by_group[group],
        )
        for group in COMPARISON_GROUPS
    )
    return FunctionalRoleSummary(
        generated_at=manifest.generated_at,
        validated_at=validated_at,
        source_export_sha256=manifest.source_export_sha256,
        product_review_labels_sha256=manifest.product_review_labels_sha256,
        rules_sha256=manifest.rules_sha256,
        samples_sha256=manifest.samples_sha256,
        functional_role_labels_sha256=functional_role_labels_sha256,
        audited_row_count=sum(group.audited_row_count for group in groups),
        groups=groups,
    )


def validate_functional_role_review_pack(
    pack_dir: Path,
    source_export_path: Path,
    product_review_pack_dir: Path,
    rules_path: Path,
    *,
    validated_at: AwareDatetime,
) -> FunctionalRoleValidationResult:
    issues: list[ReviewIssue] = []
    if not isinstance(validated_at, datetime) or validated_at.utcoffset() is None:
        return _invalid_role_result(
            [_role_issue("VALIDATED_AT_INVALID", "validated_at must be timezone-aware")]
        )
    if not pack_dir.is_dir():
        return _invalid_role_result(
            [_role_issue("PACK_DIRECTORY_MISSING", "functional-role pack is missing")]
        )
    try:
        actual_files = {path.name for path in pack_dir.iterdir()}
    except OSError:
        return _invalid_role_result(
            [_role_issue("PACK_DIRECTORY_INVALID", "functional-role pack is unreadable")]
        )
    if actual_files != _FUNCTIONAL_ROLE_PACK_FILES:
        return _invalid_role_result(
            [_role_issue("PACK_FILE_SET", "functional-role pack file set is invalid")]
        )

    document_specs = {
        "pack README": (pack_dir / "README.md", "PACK_README_UNREADABLE"),
        "pack manifest": (pack_dir / "manifest.json", "PACK_MANIFEST_UNREADABLE"),
        "pack samples": (pack_dir / "samples.csv", "PACK_SAMPLES_UNREADABLE"),
        "pack labels": (
            pack_dir / "functional_role_labels.csv",
            "PACK_LABELS_UNREADABLE",
        ),
        "source export": (source_export_path, "SOURCE_EXPORT_UNREADABLE"),
        "v2 README": (product_review_pack_dir / "README.md", "V2_README_UNREADABLE"),
        "v2 manifest": (
            product_review_pack_dir / "manifest.json",
            "V2_MANIFEST_UNREADABLE",
        ),
        "v2 samples": (
            product_review_pack_dir / "samples.csv",
            "V2_SAMPLES_UNREADABLE",
        ),
        "v2 labels": (
            product_review_pack_dir / "product_review_labels.csv",
            "V2_LABELS_UNREADABLE",
        ),
        "functional-role rules": (rules_path, "RULES_UNREADABLE"),
    }
    documents = {
        name: _read_bounded_utf8(
            path,
            document_name=name,
            read_issue_code=code,
            issues=issues,
        )
        for name, (path, code) in document_specs.items()
    }

    manifest: FunctionalRoleManifest | None = None
    manifest_text = documents["pack manifest"]
    if manifest_text is not None:
        try:
            manifest = FunctionalRoleManifest.model_validate_json(manifest_text)
        except (ValidationError, ValueError):
            issues.append(
                _role_issue("MANIFEST_INVALID", "manifest violates the functional-role contract")
            )
    if manifest is not None:
        _hash_matches(
            manifest.source_export_sha256,
            source_export_path,
            mismatch_code="SOURCE_EXPORT_HASH_MISMATCH",
            document_name="source export",
            issues=issues,
        )
        _hash_matches(
            manifest.product_review_manifest_sha256,
            product_review_pack_dir / "manifest.json",
            mismatch_code="PRODUCT_REVIEW_MANIFEST_HASH_MISMATCH",
            document_name="v2 manifest",
            issues=issues,
        )
        _hash_matches(
            manifest.product_review_samples_sha256,
            product_review_pack_dir / "samples.csv",
            mismatch_code="PRODUCT_REVIEW_SAMPLES_HASH_MISMATCH",
            document_name="v2 samples",
            issues=issues,
        )
        _hash_matches(
            manifest.product_review_labels_sha256,
            product_review_pack_dir / "product_review_labels.csv",
            mismatch_code="PRODUCT_REVIEW_LABELS_HASH_MISMATCH",
            document_name="v2 labels",
            issues=issues,
        )
        _hash_matches(
            manifest.rules_sha256,
            rules_path,
            mismatch_code="RULES_HASH_MISMATCH",
            document_name="functional-role rules",
            issues=issues,
        )
        _hash_matches(
            manifest.samples_sha256,
            pack_dir / "samples.csv",
            mismatch_code="SAMPLES_HASH_MISMATCH",
            document_name="functional-role samples",
            issues=issues,
        )

    v2_document_names = (
        "source export",
        "v2 README",
        "v2 manifest",
        "v2 samples",
        "v2 labels",
    )
    if all(documents[name] is not None for name in v2_document_names):
        v2_validation = validate_product_review_pack(
            product_review_pack_dir,
            source_export_path,
            validated_at=validated_at,
        )
        if v2_validation.status is not ReviewGateStatus.COMPLETE:
            issues.append(
                _role_issue(
                    "PRODUCT_REVIEW_INVALID",
                    "product review prerequisite is not COMPLETE",
                )
            )

    products: tuple[ExtensionReviewProduct, ...] = ()
    if documents["source export"] is not None:
        try:
            products = _load_source_products(source_export_path)
        except (OSError, ValidationError, ValueError):
            issues.append(
                _role_issue("SOURCE_EXPORT_INVALID", "source export cannot be parsed safely")
            )

    registry: FunctionalRoleRuleRegistry | None = None
    if documents["functional-role rules"] is not None:
        try:
            registry = load_functional_role_registry(rules_path, evaluated_at=validated_at)
        except (OSError, ValidationError, ValueError):
            issues.append(
                _role_issue("RULES_INVALID", "functional-role rules are not current and valid")
            )

    expected_samples: tuple[FunctionalRoleSample, ...] = ()
    if products and registry is not None:
        try:
            expected_samples = build_functional_role_samples(
                products,
                product_review_pack_dir=product_review_pack_dir,
                registry=registry,
            )
        except (OSError, ValidationError, ValueError, csv.Error):
            issues.append(
                _role_issue(
                    "EXPECTED_SAMPLES_UNAVAILABLE",
                    "deterministic samples could not be reconstructed",
                )
            )

    sample_rows: list[tuple[int, dict[str, str]]] = []
    samples_text = documents["pack samples"]
    if samples_text is not None:
        sample_rows = _parse_validation_csv(
            samples_text,
            tuple(FunctionalRoleSample.model_fields),
            header_issue_code="SAMPLE_HEADER_MISMATCH",
            row_issue_code="SAMPLE_ROW_INVALID",
            document_name="samples CSV",
            issues=issues,
        )
    _sample_models_by_key(sample_rows, issues)
    if expected_samples:
        _compare_expected_samples(sample_rows, expected_samples, issues)

    v2_labels_by_key: dict[tuple[IngredientGroup, str], ProductReviewLabel] | None = None
    if manifest is not None and expected_samples and products and registry is not None:
        v2_labels_by_key = _validate_manifest_derived_values(
            manifest,
            products=products,
            expected_samples=expected_samples,
            product_review_pack_dir=product_review_pack_dir,
            registry=registry,
            validated_at=validated_at,
            issues=issues,
        )

    label_rows: list[tuple[int, dict[str, str]]] = []
    labels_text = documents["pack labels"]
    if labels_text is not None:
        label_rows = _parse_validation_csv(
            labels_text,
            tuple(FunctionalRoleLabel.model_fields),
            header_issue_code="LABEL_HEADER_MISMATCH",
            row_issue_code="LABEL_ROW_INVALID",
            document_name="labels CSV",
            issues=issues,
        )
    expected_label_count = len(expected_samples) if expected_samples else len(sample_rows) or None
    valid_count = 0
    pending_count = 0
    if expected_samples and products and v2_labels_by_key is not None:
        valid_count, pending_count = _validate_role_labels(
            label_rows,
            expected_samples=expected_samples,
            products=products,
            v2_labels_by_key=v2_labels_by_key,
            validated_at=validated_at,
            issues=issues,
        )
    elif label_rows:
        issues.append(
            _role_issue(
                "LABEL_VALIDATION_UNAVAILABLE",
                "labels cannot be validated without reconstructed authoritative inputs",
            )
        )

    if issues:
        return _invalid_role_result(
            issues,
            expected_label_count=expected_label_count,
        )
    if expected_label_count is None:
        return _invalid_role_result(
            [_role_issue("EXPECTED_LABEL_COUNT_UNKNOWN", "expected label count is unavailable")]
        )
    if pending_count:
        return FunctionalRoleValidationResult(
            status=ReviewGateStatus.PENDING,
            expected_label_count=expected_label_count,
            valid_label_count=valid_count,
            pending_label_count=pending_count,
            issues=(),
            summary=None,
        )
    if manifest is None or not expected_samples or labels_text is None:
        return _invalid_role_result(
            [
                _role_issue(
                    "METRICS_INPUT_UNAVAILABLE",
                    "completed labels lack authoritative metric inputs",
                )
            ],
            expected_label_count=expected_label_count,
        )
    try:
        labels = tuple(FunctionalRoleLabel.model_validate(row) for _, row in label_rows)
        summary = _functional_role_summary(
            manifest=manifest,
            samples=expected_samples,
            labels=labels,
            functional_role_labels_sha256=_sha256_text(labels_text),
            validated_at=validated_at,
        )
    except (KeyError, ValidationError, ValueError, OSError):
        return _invalid_role_result(
            [
                _role_issue(
                    "METRICS_INVALID",
                    "completed labels could not produce a bound accuracy summary",
                )
            ],
            expected_label_count=expected_label_count,
        )
    return FunctionalRoleValidationResult(
        status=ReviewGateStatus.COMPLETE,
        expected_label_count=expected_label_count,
        valid_label_count=valid_count,
        pending_label_count=0,
        issues=(),
        summary=summary,
    )
