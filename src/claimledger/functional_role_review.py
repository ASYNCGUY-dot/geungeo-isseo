import csv
import hashlib
import json
import shutil
from collections import Counter
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


def _products_match_source_export(
    products: tuple[ExtensionReviewProduct, ...],
    source_export_path: Path,
) -> bool:
    source_products = tuple(
        ExtensionReviewProduct.model_validate_json(line)
        for line in source_export_path.read_text(encoding="utf-8").splitlines()
    )
    source_by_report = {product.report_no: product for product in source_products}
    provided_by_report = {product.report_no: product for product in products}
    return (
        len(source_by_report) == len(source_products)
        and len(provided_by_report) == len(products)
        and provided_by_report == source_by_report
    )


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
