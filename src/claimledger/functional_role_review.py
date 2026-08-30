import json
from enum import StrEnum
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from claimledger.domain import IngredientGroup, MappingStatus, NonBlankText
from claimledger.extension_selection import COMPARISON_GROUPS
from claimledger.functional_role import (
    MachineRoleReasonCode,
    MachineRoleVerdict,
    RoleEvidenceField,
    _reject_unsafe_text,
)
from claimledger.product_review import ReviewGateStatus, ReviewIssue, WilsonInterval

FUNCTIONAL_ROLE_CONTRACT_VERSION = "c003-functional-role-v1"
DEFAULT_GENERAL_AUDIT_SIZE = 20
DEFAULT_POSITIVE_AUDIT_SIZE = 35
POSITIVE_WILSON_LOWER_THRESHOLD = 0.90

_SHA256_PATTERN = r"^[0-9A-F]{64}$"
_BOTH_EVIDENCE_KEYS = ("raw_materials", "primary_function")


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
