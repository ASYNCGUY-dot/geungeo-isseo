import copy
import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from claimledger.domain import IngredientGroup, MappingStatus
from claimledger.extension_selection import COMPARISON_GROUPS
from claimledger.functional_role import (
    MachineRoleReasonCode,
    MachineRoleVerdict,
    RoleEvidenceField,
)
from claimledger.functional_role_review import (
    DEFAULT_GENERAL_AUDIT_SIZE,
    DEFAULT_POSITIVE_AUDIT_SIZE,
    FUNCTIONAL_ROLE_CONTRACT_VERSION,
    POSITIVE_WILSON_LOWER_THRESHOLD,
    EligibilityReasonCode,
    FunctionalRoleGroupCounts,
    FunctionalRoleGroupSummary,
    FunctionalRoleLabel,
    FunctionalRoleManifest,
    FunctionalRoleReasonCode,
    FunctionalRoleSample,
    FunctionalRoleSummary,
    FunctionalRoleValidationResult,
    HumanRoleVerdict,
    RoleConfusionCell,
    RoleEligibility,
    SampleOrigin,
)
from claimledger.product_review import ReviewGateStatus, ReviewIssue

NOW = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)
HASH = "A" * 64


def _both_evidence(
    raw_materials: str = "산화마그네슘",
    primary_function: str = "에너지 이용",
) -> str:
    return json.dumps(
        {
            "raw_materials": raw_materials,
            "primary_function": primary_function,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _valid_label_values() -> dict[str, object]:
    return {
        "group": IngredientGroup.MAGNESIUM,
        "report_no": "ROLE-LABEL-001",
        "audit_round": 1,
        "machine_verdict": MachineRoleVerdict.FUNCTIONAL_CONFIRMED,
        "human_verdict": HumanRoleVerdict.FUNCTIONAL_CONFIRMED,
        "reason_code": FunctionalRoleReasonCode.EXPLICIT_TARGET_FUNCTION,
        "evidence_field": RoleEvidenceField.BOTH,
        "evidence_excerpt": _both_evidence(),
        "rule_version": "functional-role-rule-v1",
        "review_note": "",
        "reviewer": "reviewer-01",
        "reviewed_at_iso8601": NOW,
    }


def _valid_sample_values() -> dict[str, object]:
    return {
        "seed": 20260823,
        "group": IngredientGroup.MAGNESIUM,
        "report_no": "ROLE-SAMPLE-001",
        "name": "합성 마그네슘 제품",
        "company": "합성 회사",
        "primary_function": "에너지 이용에 필요",
        "raw_materials": "산화마그네슘",
        "intake_method": "물과 함께 섭취",
        "mapping_status": MappingStatus.VERIFIED,
        "mapping_rule_version": "ingredient-map-v1",
        "audit_round": 1,
        "sample_origin": SampleOrigin.V2_ORIGINAL,
        "is_general_audit": True,
        "is_positive_audit": True,
        "machine_verdict": MachineRoleVerdict.FUNCTIONAL_CONFIRMED,
        "machine_reason_code": MachineRoleReasonCode.FUNCTION_AND_FORM_LINKED,
        "machine_evidence_field": RoleEvidenceField.BOTH,
        "machine_evidence_excerpt": _both_evidence(),
        "functional_role_rule_version": "functional-role-rule-v1",
    }


def _valid_group_count(group: IngredientGroup) -> dict[str, object]:
    return {
        "group": group,
        "original_v2_count": 20,
        "inherited_mapping_error_count": 0,
        "general_replacement_count": 0,
        "general_evaluable_count": 20,
        "positive_pool_count": 40,
        "positive_sample_count": 35,
        "total_unique_rows": 45,
    }


def _valid_manifest_values() -> dict[str, object]:
    return {
        "contract_version": FUNCTIONAL_ROLE_CONTRACT_VERSION,
        "seed": 20260823,
        "general_size_per_group": DEFAULT_GENERAL_AUDIT_SIZE,
        "positive_size_per_group": DEFAULT_POSITIVE_AUDIT_SIZE,
        "generated_at": NOW,
        "source_export_sha256": HASH,
        "product_review_manifest_sha256": HASH,
        "product_review_samples_sha256": HASH,
        "product_review_labels_sha256": HASH,
        "rules_sha256": HASH,
        "samples_sha256": HASH,
        "mapping_rule_versions": ("ingredient-map-v1",),
        "functional_role_rule_versions": ("functional-role-rule-v1",),
        "group_counts": tuple(_valid_group_count(group) for group in COMPARISON_GROUPS),
    }


def _confusion_matrix(
    *,
    nonzero_machine: MachineRoleVerdict = MachineRoleVerdict.UNVERIFIABLE,
    nonzero_human: HumanRoleVerdict = HumanRoleVerdict.UNCERTAIN,
) -> tuple[RoleConfusionCell, ...]:
    return tuple(
        RoleConfusionCell(
            machine_verdict=machine_verdict,
            human_verdict=human_verdict,
            row_count=int(machine_verdict is nonzero_machine and human_verdict is nonzero_human),
        )
        for machine_verdict in MachineRoleVerdict
        for human_verdict in HumanRoleVerdict
    )


def _valid_group_summary(group: IngredientGroup) -> FunctionalRoleGroupSummary:
    return FunctionalRoleGroupSummary(
        group=group,
        audited_row_count=1,
        addressable_product_count=1,
        general_evaluable_count=20,
        positive_pool_count=1,
        positive_sample_count=1,
        true_functional_confirmed_count=0,
        false_confirmation_count=0,
        unresolved_positive_count=0,
        false_exclusion_count=0,
        overconfident_decision_count=0,
        avoidable_unverifiable_count=0,
        positive_precision=None,
        positive_precision_wilson_95=None,
        decidable_agreement_rate=None,
        decision_coverage=0.0,
        unverifiable_rate=1.0,
        human_uncertainty_rate=1.0,
        confusion_matrix=_confusion_matrix(),
        eligibility=RoleEligibility.ROLE_INSUFFICIENT,
        eligibility_reasons=(EligibilityReasonCode.POSITIVE_POOL_TOO_SMALL,),
    )


def _valid_summary() -> FunctionalRoleSummary:
    groups = tuple(_valid_group_summary(group) for group in COMPARISON_GROUPS)
    return FunctionalRoleSummary(
        generated_at=NOW,
        validated_at=NOW,
        source_export_sha256=HASH,
        product_review_labels_sha256=HASH,
        rules_sha256=HASH,
        samples_sha256=HASH,
        functional_role_labels_sha256=HASH,
        audited_row_count=sum(group.audited_row_count for group in groups),
        groups=groups,
    )


def test_functional_role_label_accepts_confirmed_both_field_evidence() -> None:
    label = FunctionalRoleLabel.model_validate(_valid_label_values())

    assert label.human_verdict is HumanRoleVerdict.FUNCTIONAL_CONFIRMED
    assert label.reason_code is FunctionalRoleReasonCode.EXPLICIT_TARGET_FUNCTION
    assert label.evidence_field is RoleEvidenceField.BOTH
    assert label.evidence_excerpt == _both_evidence()
    with pytest.raises(ValidationError):
        label.review_note = "mutated"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("machine_verdict", "function_confirmed"),
        ("human_verdict", "confirmed"),
    ],
)
def test_label_rejects_machine_and_human_enum_misspellings(field: str, value: str) -> None:
    values = _valid_label_values()
    values[field] = value

    with pytest.raises(ValidationError):
        FunctionalRoleLabel.model_validate(values)


@pytest.mark.parametrize(
    "changes",
    [
        {"reason_code": FunctionalRoleReasonCode.INSUFFICIENT_LINKAGE},
        {
            "evidence_field": RoleEvidenceField.RAW_MATERIALS,
            "evidence_excerpt": "산화마그네슘",
        },
        {"evidence_excerpt": _both_evidence(raw_materials="")},
        {"evidence_excerpt": _both_evidence(primary_function="")},
        {
            "evidence_excerpt": json.dumps(
                {
                    "primary_function": "에너지 이용",
                    "raw_materials": "산화마그네슘",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        },
        {
            "evidence_excerpt": json.dumps(
                {
                    "raw_materials": "산화마그네슘",
                    "primary_function": "에너지 이용",
                    "extra": "not allowed",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        },
        {
            "evidence_excerpt": json.dumps(
                {
                    "raw_materials": "산화마그네슘",
                    "primary_function": "에너지 이용",
                },
                ensure_ascii=False,
            )
        },
        {
            "evidence_excerpt": json.dumps(
                {
                    "raw_materials": 1,
                    "primary_function": "에너지 이용",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        },
    ],
)
def test_confirmed_requires_explicit_target_reason_and_both_excerpts(
    changes: dict[str, object],
) -> None:
    values = _valid_label_values()
    values.update(changes)

    with pytest.raises(ValidationError):
        FunctionalRoleLabel.model_validate(values)


@pytest.mark.parametrize(
    "changes",
    [
        {"reason_code": FunctionalRoleReasonCode.INSUFFICIENT_LINKAGE},
        {
            "evidence_field": RoleEvidenceField.PRIMARY_FUNCTION,
            "evidence_excerpt": "에너지 이용",
        },
        {"evidence_field": RoleEvidenceField.NONE, "evidence_excerpt": ""},
    ],
)
def test_nonfunctional_requires_explicit_nonfunctional_reason(
    changes: dict[str, object],
) -> None:
    values = _valid_label_values()
    values.update(
        {
            "machine_verdict": MachineRoleVerdict.PRESENT_NONFUNCTIONAL,
            "human_verdict": HumanRoleVerdict.PRESENT_NONFUNCTIONAL,
            "reason_code": FunctionalRoleReasonCode.EXPLICIT_NONFUNCTIONAL_ROLE,
            "evidence_field": RoleEvidenceField.RAW_MATERIALS,
            "evidence_excerpt": "스테아린산 마그네슘",
        }
    )
    values.update(changes)

    with pytest.raises(ValidationError):
        FunctionalRoleLabel.model_validate(values)


@pytest.mark.parametrize(
    "reason_code",
    [
        FunctionalRoleReasonCode.INSUFFICIENT_LINKAGE,
        FunctionalRoleReasonCode.COMBINATION_AMBIGUOUS,
        FunctionalRoleReasonCode.NEEDS_EXPERT,
        FunctionalRoleReasonCode.OTHER,
    ],
)
def test_uncertain_requires_a_compatible_reason(
    reason_code: FunctionalRoleReasonCode,
) -> None:
    values = _valid_label_values()
    values.update(
        {
            "machine_verdict": MachineRoleVerdict.UNVERIFIABLE,
            "human_verdict": HumanRoleVerdict.UNCERTAIN,
            "reason_code": reason_code,
            "evidence_field": RoleEvidenceField.NONE,
            "evidence_excerpt": "",
            "review_note": (
                "전문가 확인 필요"
                if reason_code
                in {FunctionalRoleReasonCode.NEEDS_EXPERT, FunctionalRoleReasonCode.OTHER}
                else ""
            ),
        }
    )

    label = FunctionalRoleLabel.model_validate(values)
    assert label.reason_code is reason_code

    values["reason_code"] = FunctionalRoleReasonCode.EXPLICIT_TARGET_FUNCTION
    with pytest.raises(ValidationError):
        FunctionalRoleLabel.model_validate(values)


@pytest.mark.parametrize(
    "reason_code",
    [FunctionalRoleReasonCode.NEEDS_EXPERT, FunctionalRoleReasonCode.OTHER],
)
def test_needs_expert_and_other_require_a_note(
    reason_code: FunctionalRoleReasonCode,
) -> None:
    values = _valid_label_values()
    values.update(
        {
            "machine_verdict": MachineRoleVerdict.UNVERIFIABLE,
            "human_verdict": HumanRoleVerdict.UNCERTAIN,
            "reason_code": reason_code,
            "evidence_field": RoleEvidenceField.NONE,
            "evidence_excerpt": "",
            "review_note": "   ",
        }
    )

    with pytest.raises(ValidationError, match="review note"):
        FunctionalRoleLabel.model_validate(values)


@pytest.mark.parametrize(
    "changes",
    [
        {"reason_code": FunctionalRoleReasonCode.INSUFFICIENT_LINKAGE},
        {
            "evidence_field": RoleEvidenceField.RAW_MATERIALS,
            "evidence_excerpt": "홍삼향분말",
        },
        {"evidence_excerpt": "unexpected"},
    ],
)
def test_excluded_mapping_error_requires_empty_evidence(changes: dict[str, object]) -> None:
    values = _valid_label_values()
    values.update(
        {
            "machine_verdict": MachineRoleVerdict.UNVERIFIABLE,
            "human_verdict": HumanRoleVerdict.EXCLUDED_MAPPING_ERROR,
            "reason_code": FunctionalRoleReasonCode.INHERITED_MAPPING_ERROR,
            "evidence_field": RoleEvidenceField.NONE,
            "evidence_excerpt": "",
        }
    )
    values.update(changes)

    with pytest.raises(ValidationError):
        FunctionalRoleLabel.model_validate(values)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("report_no", "  =HYPERLINK(bad)", "spreadsheet formula prefix"),
        ("evidence_excerpt", "+SUM(1,1)", "spreadsheet formula prefix"),
        ("rule_version", "-1+2", "spreadsheet formula prefix"),
        ("review_note", "@command", "spreadsheet formula prefix"),
        ("reviewer", "\tcommand", "spreadsheet formula prefix"),
        ("report_no", "api_" + "key=live-secret-value-123456", "possible secret"),
        ("evidence_excerpt", "api_" + "key=live-secret-value-123456", "possible secret"),
        ("rule_version", "api_" + "key=live-secret-value-123456", "possible secret"),
        ("review_note", "api_" + "key=live-secret-value-123456", "possible secret"),
        ("reviewer", "api_" + "key=live-secret-value-123456", "possible secret"),
    ],
)
def test_label_rejects_formula_prefixes_and_secret_patterns_in_all_free_text(
    field: str,
    value: str,
    message: str,
) -> None:
    values = _valid_label_values()
    values.update(
        {
            "machine_verdict": MachineRoleVerdict.UNVERIFIABLE,
            "human_verdict": HumanRoleVerdict.UNCERTAIN,
            "reason_code": FunctionalRoleReasonCode.INSUFFICIENT_LINKAGE,
            "evidence_field": RoleEvidenceField.RAW_MATERIALS,
            "evidence_excerpt": "원재료 발췌",
        }
    )
    values[field] = value

    with pytest.raises(ValidationError, match=message) as error:
        FunctionalRoleLabel.model_validate(values)
    assert value not in str(error.value)


@pytest.mark.parametrize(
    "field",
    ["report_no", "evidence_excerpt", "rule_version", "review_note", "reviewer"],
)
def test_label_non_text_free_text_inputs_raise_redacted_validation_errors(field: str) -> None:
    values = _valid_label_values()
    values[field] = 123456789

    with pytest.raises(ValidationError) as error:
        FunctionalRoleLabel.model_validate(values)
    assert "123456789" not in str(error.value)


@pytest.mark.parametrize("audit_round", [0, 3, "0", "3"])
def test_label_rejects_naive_datetime_and_audit_round_outside_one_or_two(
    audit_round: object,
) -> None:
    values = _valid_label_values()
    values["audit_round"] = audit_round
    with pytest.raises(ValidationError):
        FunctionalRoleLabel.model_validate(values)

    values = _valid_label_values()
    values["reviewed_at_iso8601"] = datetime(2026, 8, 30, 9, 0)  # noqa: DTZ001
    with pytest.raises(ValidationError, match="timezone"):
        FunctionalRoleLabel.model_validate(values)


@pytest.mark.parametrize(
    "mutation",
    [
        "unsorted_mapping_versions",
        "duplicate_functional_versions",
        "non_sequence_versions",
        "bad_hash",
        "reordered_groups",
        "bad_positive_count",
        "bad_replacement_count",
        "naive_generated_at",
    ],
)
def test_manifest_rejects_unsorted_versions_bad_hashes_and_inconsistent_counts(
    mutation: str,
) -> None:
    values = copy.deepcopy(_valid_manifest_values())
    if mutation == "unsorted_mapping_versions":
        values["mapping_rule_versions"] = ("z-version", "a-version")
    elif mutation == "duplicate_functional_versions":
        values["functional_role_rule_versions"] = (
            "functional-role-rule-v1",
            "functional-role-rule-v1",
        )
    elif mutation == "non_sequence_versions":
        values["mapping_rule_versions"] = 123
    elif mutation == "bad_hash":
        values["samples_sha256"] = "a" * 64
    elif mutation == "reordered_groups":
        values["group_counts"] = tuple(reversed(values["group_counts"]))
    elif mutation == "bad_positive_count":
        values["group_counts"][0]["positive_sample_count"] = 34
    elif mutation == "bad_replacement_count":
        values["group_counts"][0]["inherited_mapping_error_count"] = 1
    else:
        values["generated_at"] = datetime(2026, 8, 30, 9, 0)  # noqa: DTZ001

    with pytest.raises(ValidationError):
        FunctionalRoleManifest.model_validate(values)


def test_validation_result_preserves_not_measured_blocked_and_false() -> None:
    result = FunctionalRoleValidationResult(
        status=ReviewGateStatus.PENDING,
        expected_label_count=10,
        valid_label_count=9,
        pending_label_count=1,
        issues=(),
        summary=None,
    )

    assert result.advertising_evidence_status == "NOT_MEASURED"
    assert result.extension_recommendation_status == "BLOCKED"
    assert result.finalized is False

    for changes in (
        {"advertising_evidence_status": "COMPLETE"},
        {"extension_recommendation_status": "READY"},
        {"finalized": True},
    ):
        values = result.model_dump()
        values.update(changes)
        with pytest.raises(ValidationError):
            FunctionalRoleValidationResult.model_validate(values)


def test_sample_requires_canonical_machine_evidence_and_consistent_audit_flags() -> None:
    sample = FunctionalRoleSample.model_validate(_valid_sample_values())
    assert sample.machine_evidence_excerpt == _both_evidence()

    values = _valid_sample_values()
    values["machine_evidence_excerpt"] = json.dumps(
        {
            "raw_materials": "산화마그네슘",
            "primary_function": "에너지 이용",
        },
        ensure_ascii=False,
    )
    with pytest.raises(ValidationError):
        FunctionalRoleSample.model_validate(values)

    values = _valid_sample_values()
    values["is_general_audit"] = False
    values["is_positive_audit"] = False
    with pytest.raises(ValidationError):
        FunctionalRoleSample.model_validate(values)

    values = _valid_sample_values()
    values.update(
        {
            "sample_origin": SampleOrigin.POSITIVE_PRECISION,
            "audit_round": 2,
            "is_general_audit": False,
        }
    )
    assert FunctionalRoleSample.model_validate(values).audit_round == 2


@pytest.mark.parametrize(
    ("changes", "is_valid"),
    [
        (
            {
                "machine_verdict": MachineRoleVerdict.PRESENT_NONFUNCTIONAL,
                "machine_reason_code": MachineRoleReasonCode.EXPLICIT_NONFUNCTIONAL_FORM,
                "machine_evidence_field": RoleEvidenceField.RAW_MATERIALS,
                "machine_evidence_excerpt": "스테아린산 마그네슘",
                "is_positive_audit": False,
            },
            True,
        ),
        (
            {
                "machine_verdict": MachineRoleVerdict.UNVERIFIABLE,
                "machine_reason_code": MachineRoleReasonCode.FORM_WITHOUT_FUNCTION,
                "machine_evidence_field": RoleEvidenceField.RAW_MATERIALS,
                "machine_evidence_excerpt": "산화마그네슘",
                "is_positive_audit": False,
            },
            True,
        ),
        (
            {
                "machine_verdict": MachineRoleVerdict.UNVERIFIABLE,
                "machine_reason_code": MachineRoleReasonCode.FUNCTION_WITHOUT_FORM,
                "machine_evidence_field": RoleEvidenceField.PRIMARY_FUNCTION,
                "machine_evidence_excerpt": "에너지 이용",
                "is_positive_audit": False,
            },
            True,
        ),
        (
            {
                "machine_verdict": MachineRoleVerdict.UNVERIFIABLE,
                "machine_reason_code": MachineRoleReasonCode.COMBINATION_LINKAGE_AMBIGUOUS,
                "machine_evidence_field": RoleEvidenceField.BOTH,
                "machine_evidence_excerpt": _both_evidence(),
                "is_positive_audit": False,
            },
            True,
        ),
        (
            {
                "machine_verdict": MachineRoleVerdict.UNVERIFIABLE,
                "machine_reason_code": MachineRoleReasonCode.CONFLICTING_ROLE_EVIDENCE,
                "machine_evidence_field": RoleEvidenceField.RAW_MATERIALS,
                "machine_evidence_excerpt": "산화마그네슘",
                "is_positive_audit": False,
            },
            True,
        ),
        (
            {
                "machine_verdict": MachineRoleVerdict.UNVERIFIABLE,
                "machine_reason_code": MachineRoleReasonCode.NO_APPLICABLE_EVIDENCE,
                "machine_evidence_field": RoleEvidenceField.NONE,
                "machine_evidence_excerpt": "",
                "is_positive_audit": False,
            },
            True,
        ),
        (
            {
                "machine_verdict": MachineRoleVerdict.UNVERIFIABLE,
                "machine_reason_code": MachineRoleReasonCode.INHERITED_MAPPING_ERROR,
                "machine_evidence_field": RoleEvidenceField.NONE,
                "machine_evidence_excerpt": "",
                "is_positive_audit": False,
            },
            True,
        ),
        (
            {"machine_reason_code": MachineRoleReasonCode.FORM_WITHOUT_FUNCTION},
            False,
        ),
        (
            {
                "machine_verdict": MachineRoleVerdict.PRESENT_NONFUNCTIONAL,
                "machine_reason_code": MachineRoleReasonCode.EXPLICIT_NONFUNCTIONAL_FORM,
                "machine_evidence_field": RoleEvidenceField.BOTH,
                "machine_evidence_excerpt": _both_evidence(),
                "is_positive_audit": False,
            },
            False,
        ),
        (
            {
                "machine_verdict": MachineRoleVerdict.UNVERIFIABLE,
                "machine_reason_code": MachineRoleReasonCode.NO_APPLICABLE_EVIDENCE,
                "machine_evidence_field": RoleEvidenceField.RAW_MATERIALS,
                "machine_evidence_excerpt": "산화마그네슘",
                "is_positive_audit": False,
            },
            False,
        ),
    ],
)
def test_sample_machine_decision_table_is_fail_closed(
    changes: dict[str, object],
    is_valid: bool,
) -> None:
    values = _valid_sample_values()
    values.update(changes)

    if is_valid:
        assert (
            FunctionalRoleSample.model_validate(values).machine_verdict is values["machine_verdict"]
        )
    else:
        with pytest.raises(ValidationError):
            FunctionalRoleSample.model_validate(values)


@pytest.mark.parametrize(
    "changes",
    [
        {"original_v2_count": 19, "general_evaluable_count": 19},
        {"inherited_mapping_error_count": 21, "general_replacement_count": 21},
        {"inherited_mapping_error_count": 1},
        {"general_evaluable_count": 19},
        {"positive_pool_count": 34, "positive_sample_count": 33},
        {"total_unique_rows": 19},
        {"total_unique_rows": 56},
    ],
)
def test_group_counts_reject_impossible_sampling_relationships(
    changes: dict[str, object],
) -> None:
    values = _valid_group_count(IngredientGroup.MAGNESIUM)
    values.update(changes)

    with pytest.raises(ValidationError):
        FunctionalRoleGroupCounts.model_validate(values)


def test_group_summary_requires_a_complete_matrix_and_reasoned_eligibility() -> None:
    summary = _valid_group_summary(IngredientGroup.MAGNESIUM)
    assert len(summary.confusion_matrix) == 12

    mutations = (
        {"confusion_matrix": summary.confusion_matrix[:-1]},
        {"audited_row_count": 2},
        {"eligibility_reasons": ()},
        {
            "eligibility": RoleEligibility.ROLE_ELIGIBLE,
            "eligibility_reasons": (EligibilityReasonCode.POSITIVE_POOL_TOO_SMALL,),
        },
        {
            "eligibility_reasons": (
                EligibilityReasonCode.POSITIVE_POOL_TOO_SMALL,
                EligibilityReasonCode.POSITIVE_POOL_TOO_SMALL,
            )
        },
    )
    for changes in mutations:
        values = summary.model_dump()
        values.update(changes)
        with pytest.raises(ValidationError):
            FunctionalRoleGroupSummary.model_validate(values)

    eligible_values = summary.model_dump()
    eligible_values.update(
        {
            "eligibility": RoleEligibility.ROLE_ELIGIBLE,
            "eligibility_reasons": (),
        }
    )
    assert (
        FunctionalRoleGroupSummary.model_validate(eligible_values).eligibility
        is RoleEligibility.ROLE_ELIGIBLE
    )


def test_summary_requires_exact_group_order_counts_and_time_order() -> None:
    summary = _valid_summary()
    assert summary.advertising_evidence_status == "NOT_MEASURED"
    assert summary.extension_recommendation_status == "BLOCKED"
    assert summary.finalized is False

    for changes in (
        {"groups": tuple(reversed(summary.groups))},
        {"audited_row_count": summary.audited_row_count + 1},
        {"generated_at": NOW, "validated_at": datetime(2026, 8, 30, 8, 59, tzinfo=UTC)},
    ):
        values = summary.model_dump()
        values.update(changes)
        with pytest.raises(ValidationError):
            FunctionalRoleSummary.model_validate(values)


def test_complete_validation_result_requires_a_clean_bound_summary() -> None:
    summary = _valid_summary()
    result = FunctionalRoleValidationResult(
        status=ReviewGateStatus.COMPLETE,
        expected_label_count=summary.audited_row_count,
        valid_label_count=summary.audited_row_count,
        pending_label_count=0,
        issues=(),
        summary=summary,
    )
    assert result.status is ReviewGateStatus.COMPLETE

    values = result.model_dump()
    values["valid_label_count"] = summary.audited_row_count - 1
    with pytest.raises(ValidationError):
        FunctionalRoleValidationResult.model_validate(values)

    values = result.model_dump()
    values["expected_label_count"] = summary.audited_row_count + 1
    values["valid_label_count"] = summary.audited_row_count + 1
    with pytest.raises(ValidationError):
        FunctionalRoleValidationResult.model_validate(values)


def test_locked_contract_values_and_model_field_order() -> None:
    assert FUNCTIONAL_ROLE_CONTRACT_VERSION == "c003-functional-role-v1"
    assert DEFAULT_GENERAL_AUDIT_SIZE == 20
    assert DEFAULT_POSITIVE_AUDIT_SIZE == 35
    assert POSITIVE_WILSON_LOWER_THRESHOLD == 0.90
    assert tuple(HumanRoleVerdict) == (
        HumanRoleVerdict.FUNCTIONAL_CONFIRMED,
        HumanRoleVerdict.PRESENT_NONFUNCTIONAL,
        HumanRoleVerdict.UNCERTAIN,
        HumanRoleVerdict.EXCLUDED_MAPPING_ERROR,
    )
    assert tuple(SampleOrigin) == (
        SampleOrigin.V2_ORIGINAL,
        SampleOrigin.GENERAL_REPLACEMENT,
        SampleOrigin.POSITIVE_PRECISION,
    )
    assert tuple(RoleEligibility) == (
        RoleEligibility.ROLE_ELIGIBLE,
        RoleEligibility.ROLE_INSUFFICIENT,
    )
    assert len(tuple(EligibilityReasonCode)) == 9
    assert tuple(FunctionalRoleSample.model_fields) == (
        "seed",
        "group",
        "report_no",
        "name",
        "company",
        "primary_function",
        "raw_materials",
        "intake_method",
        "mapping_status",
        "mapping_rule_version",
        "audit_round",
        "sample_origin",
        "is_general_audit",
        "is_positive_audit",
        "machine_verdict",
        "machine_reason_code",
        "machine_evidence_field",
        "machine_evidence_excerpt",
        "functional_role_rule_version",
    )
    assert tuple(FunctionalRoleLabel.model_fields) == (
        "group",
        "report_no",
        "audit_round",
        "machine_verdict",
        "human_verdict",
        "reason_code",
        "evidence_field",
        "evidence_excerpt",
        "rule_version",
        "review_note",
        "reviewer",
        "reviewed_at_iso8601",
    )
    assert tuple(FunctionalRoleGroupCounts.model_fields) == (
        "group",
        "original_v2_count",
        "inherited_mapping_error_count",
        "general_replacement_count",
        "general_evaluable_count",
        "positive_pool_count",
        "positive_sample_count",
        "total_unique_rows",
    )
    assert tuple(FunctionalRoleManifest.model_fields) == (
        "contract_version",
        "seed",
        "general_size_per_group",
        "positive_size_per_group",
        "generated_at",
        "source_export_sha256",
        "product_review_manifest_sha256",
        "product_review_samples_sha256",
        "product_review_labels_sha256",
        "rules_sha256",
        "samples_sha256",
        "mapping_rule_versions",
        "functional_role_rule_versions",
        "group_counts",
    )
    assert tuple(RoleConfusionCell.model_fields) == (
        "machine_verdict",
        "human_verdict",
        "row_count",
    )
    assert "eligibility" in FunctionalRoleGroupSummary.model_fields
    assert "groups" in FunctionalRoleSummary.model_fields
    assert tuple(FunctionalRoleValidationResult.model_fields)[-3:] == (
        "advertising_evidence_status",
        "extension_recommendation_status",
        "finalized",
    )


def test_validation_result_rejects_inconsistent_status_payloads() -> None:
    invalid_issue = ReviewIssue(code="TEST", message="invalid pack")

    with pytest.raises(ValidationError):
        FunctionalRoleValidationResult(
            status=ReviewGateStatus.PENDING,
            expected_label_count=10,
            valid_label_count=10,
            pending_label_count=0,
            issues=(),
            summary=None,
        )
    with pytest.raises(ValidationError):
        FunctionalRoleValidationResult(
            status=ReviewGateStatus.INVALID,
            expected_label_count=None,
            valid_label_count=None,
            pending_label_count=None,
            issues=(),
            summary=None,
        )
    result = FunctionalRoleValidationResult(
        status=ReviewGateStatus.INVALID,
        expected_label_count=None,
        valid_label_count=None,
        pending_label_count=None,
        issues=(invalid_issue,),
        summary=None,
    )
    assert result.status is ReviewGateStatus.INVALID
