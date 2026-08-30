import copy
import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from claimledger.domain import ExtensionReviewProduct, IngredientGroup, MappingStatus
from claimledger.extension_selection import COMPARISON_GROUPS
from claimledger.functional_role import (
    FunctionalRoleRuleRegistry,
    MachineRoleReasonCode,
    MachineRoleVerdict,
    RoleEvidenceField,
    load_functional_role_registry,
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
    build_functional_role_samples,
    derive_sample_seed,
)
from claimledger.ingredients import map_ingredients
from claimledger.product_review import (
    FunctionReasonCode,
    FunctionTextStatus,
    MappingReasonCode,
    MappingVerdict,
    ProductReviewLabel,
    ProductReviewManifest,
    ProductReviewSample,
    ReviewGateStatus,
    ReviewGroupCounts,
    ReviewIssue,
    sha256_file,
    validate_product_review_pack,
)

NOW = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)
HASH = "A" * 64
RULE_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "functional_role_rules.json"
PRODUCT_REVIEW_SAMPLE_FIELDS = tuple(ProductReviewSample.model_fields)
PRODUCT_REVIEW_LABEL_FIELDS = tuple(ProductReviewLabel.model_fields)

FUNCTIONAL_FORMS = {
    IngredientGroup.MILK_THISTLE: "밀크씨슬추출물",
    IngredientGroup.VITAMIN_D: "비타민 D",
    IngredientGroup.RED_GINSENG: "홍삼농축액",
    IngredientGroup.COENZYME_Q10: "코엔자임 Q10",
    IngredientGroup.MAGNESIUM: "산화마그네슘",
}
FUNCTION_TEXTS = {
    IngredientGroup.MILK_THISTLE: "간 건강",
    IngredientGroup.VITAMIN_D: "칼슘과 인의 흡수",
    IngredientGroup.RED_GINSENG: "면역력 증진",
    IngredientGroup.COENZYME_Q10: "항산화",
    IngredientGroup.MAGNESIUM: "에너지 이용",
}


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


def _registry() -> FunctionalRoleRuleRegistry:
    return load_functional_role_registry(RULE_FIXTURE_PATH, evaluated_at=NOW)


def _report_no(group: IngredientGroup, scope: str, index: int) -> str:
    return f"{group.value.upper()}-{scope}-{index:03d}"


def _synthetic_product(
    group: IngredientGroup,
    *,
    report_no: str,
    machine_positive: bool,
    inherited_red_ginseng_error: bool = False,
) -> ExtensionReviewProduct:
    if inherited_red_ginseng_error:
        return ExtensionReviewProduct(
            report_no=report_no,
            name="홍삼 원료 합성 향 제품",
            company="합성 제조사",
            primary_function="일반적인 영양 보충",
            raw_materials="홍삼향분말",
            intake_method="하루 한 번 섭취",
        )
    return ExtensionReviewProduct(
        report_no=report_no,
        name=f"합성 감사 제품 {report_no}",
        company="합성 제조사",
        primary_function=(
            f"{FUNCTION_TEXTS[group]}에 도움을 줄 수 있음"
            if machine_positive
            else "일반적인 영양 보충"
        ),
        raw_materials=FUNCTIONAL_FORMS[group],
        intake_method="하루 한 번 섭취",
    )


def _synthetic_source_products(
    *,
    magnesium_positive_count: int = 40,
) -> tuple[ExtensionReviewProduct, ...]:
    products: list[ExtensionReviewProduct] = []
    for group in COMPARISON_GROUPS:
        target_positive_count = (
            magnesium_positive_count if group is IngredientGroup.MAGNESIUM else 40
        )
        v2_positive_count = 0
        for index in range(20):
            inherited_error = group is IngredientGroup.RED_GINSENG and index == 0
            product = _synthetic_product(
                group,
                report_no=_report_no(group, "V2", index),
                machine_positive=not inherited_error,
                inherited_red_ginseng_error=inherited_error,
            )
            products.append(product)
            if not inherited_error:
                v2_positive_count += 1
        for index in range(target_positive_count - v2_positive_count):
            products.append(
                _synthetic_product(
                    group,
                    report_no=_report_no(group, "POS", index),
                    machine_positive=True,
                )
            )
        for index in range(21):
            products.append(
                _synthetic_product(
                    group,
                    report_no=_report_no(group, "NEG", index),
                    machine_positive=False,
                )
            )

    for product in products:
        mapping = map_ingredients(product)
        assert mapping.status is MappingStatus.VERIFIED
        assert len(mapping.groups) == 1
    return tuple(products)


def _write_csv_models(
    path: Path,
    fields: tuple[str, ...],
    models: tuple[ProductReviewSample | ProductReviewLabel, ...],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(model.model_dump(mode="json") for model in models)


def _write_completed_v2_pack(
    root: Path,
    products: tuple[ExtensionReviewProduct, ...],
) -> tuple[Path, Path, tuple[ProductReviewSample, ...]]:
    root.mkdir(parents=True)
    pack_dir = root / "v2-pack"
    pack_dir.mkdir()
    source_export = root / "source-products.jsonl"
    source_export.write_text(
        "".join(
            json.dumps(product.model_dump(mode="json"), ensure_ascii=False) + "\n"
            for product in products
        ),
        encoding="utf-8",
        newline="\n",
    )
    products_by_report = {product.report_no: product for product in products}

    samples: list[ProductReviewSample] = []
    labels: list[ProductReviewLabel] = []
    for group in COMPARISON_GROUPS:
        for index in range(20):
            report_no = _report_no(group, "V2", index)
            product = products_by_report[report_no]
            mapping = map_ingredients(product)
            assert mapping.groups == (group,)
            sample = ProductReviewSample(
                seed=20260823,
                group=group,
                **product.model_dump(),
                mapping_status=mapping.status,
                mapping_rule_version=mapping.rule_version,
            )
            samples.append(sample)
            inherited_error = group is IngredientGroup.RED_GINSENG and index == 0
            labels.append(
                ProductReviewLabel(
                    group=group,
                    report_no=report_no,
                    mapping_verdict=(
                        MappingVerdict.INCORRECT if inherited_error else MappingVerdict.CORRECT
                    ),
                    mapping_reason_code=(
                        MappingReasonCode.ALIAS_COLLISION
                        if inherited_error
                        else MappingReasonCode.NONE
                    ),
                    function_text_status=FunctionTextStatus.USABLE,
                    function_reason_code=FunctionReasonCode.NONE,
                    review_note=("합성 홍삼향 원료 alias collision" if inherited_error else ""),
                    reviewer="synthetic-reviewer",
                    reviewed_at_iso8601=NOW,
                )
            )

    sample_tuple = tuple(samples)
    label_tuple = tuple(labels)
    _write_csv_models(
        pack_dir / "samples.csv",
        PRODUCT_REVIEW_SAMPLE_FIELDS,
        sample_tuple,
    )
    _write_csv_models(
        pack_dir / "product_review_labels.csv",
        PRODUCT_REVIEW_LABEL_FIELDS,
        label_tuple,
    )
    (pack_dir / "README.md").write_text(
        "# Synthetic completed c003-product-review-v2 pack\n",
        encoding="utf-8",
        newline="\n",
    )
    manifest = ProductReviewManifest(
        group_counts=ReviewGroupCounts(),
        samples_sha256=sha256_file(pack_dir / "samples.csv"),
        source_export_sha256=sha256_file(source_export),
        mapping_rule_versions=("ingredient-map-v1",),
    )
    (pack_dir / "manifest.json").write_text(
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    validation = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)
    assert validation.status is ReviewGateStatus.COMPLETE, validation.model_dump_json()
    return pack_dir, source_export, sample_tuple


def _build_synthetic_samples(
    tmp_path: Path,
    *,
    magnesium_positive_count: int = 40,
    reverse_source: bool = False,
    root_name: str = "sampling",
) -> tuple[
    tuple[FunctionalRoleSample, ...],
    tuple[ExtensionReviewProduct, ...],
    Path,
    Path,
    tuple[ProductReviewSample, ...],
]:
    products = _synthetic_source_products(magnesium_positive_count=magnesium_positive_count)
    if reverse_source:
        products = tuple(reversed(products))
    pack_dir, source_export, v2_samples = _write_completed_v2_pack(
        tmp_path / root_name,
        products,
    )
    samples = build_functional_role_samples(
        products,
        product_review_pack_dir=pack_dir,
        registry=_registry(),
    )
    return samples, products, pack_dir, source_export, v2_samples


def _hash_rank(
    base_seed: int,
    group: IngredientGroup,
    scope: str,
    report_no: str,
) -> bytes:
    derived_seed = derive_sample_seed(base_seed, group, scope)
    material = f"{derived_seed}|{group.value}|{scope}|{report_no}".encode()
    return hashlib.sha256(material).digest()


def test_sampling_refuses_a_non_complete_v2_pack(tmp_path: Path) -> None:
    products = _synthetic_source_products()
    pack_dir, source_export, _ = _write_completed_v2_pack(tmp_path / "pending", products)
    labels_path = pack_dir / "product_review_labels.csv"
    with labels_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for field in PRODUCT_REVIEW_LABEL_FIELDS[2:]:
        rows[0][field] = ""
    with labels_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=PRODUCT_REVIEW_LABEL_FIELDS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    validation = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)
    assert validation.status is ReviewGateStatus.PENDING

    with pytest.raises(ValueError, match="COMPLETE"):
        build_functional_role_samples(
            products,
            product_review_pack_dir=pack_dir,
            registry=_registry(),
        )


def test_first_100_rows_preserve_v2_order_keys_and_product_fields(tmp_path: Path) -> None:
    samples, _, _, _, v2_samples = _build_synthetic_samples(tmp_path)
    source_fields = tuple(ExtensionReviewProduct.model_fields)

    assert len(samples) >= 100
    for functional_sample, v2_sample in zip(samples[:100], v2_samples, strict=True):
        assert (functional_sample.group, functional_sample.report_no) == (
            v2_sample.group,
            v2_sample.report_no,
        )
        assert tuple(getattr(functional_sample, field) for field in source_fields) == tuple(
            getattr(v2_sample, field) for field in source_fields
        )


def test_inherited_mapping_error_is_preserved_and_replaced_deterministically(
    tmp_path: Path,
) -> None:
    samples, products, _, _, v2_samples = _build_synthetic_samples(tmp_path)
    inherited_key = (
        IngredientGroup.RED_GINSENG,
        _report_no(IngredientGroup.RED_GINSENG, "V2", 0),
    )
    inherited = next(
        sample for sample in samples if (sample.group, sample.report_no) == inherited_key
    )
    assert inherited.machine_verdict is MachineRoleVerdict.UNVERIFIABLE
    assert inherited.machine_reason_code is MachineRoleReasonCode.INHERITED_MAPPING_ERROR
    assert inherited.sample_origin is SampleOrigin.V2_ORIGINAL
    assert inherited.is_general_audit is True

    replacements = [
        sample
        for sample in samples
        if sample.group is IngredientGroup.RED_GINSENG
        and sample.sample_origin is SampleOrigin.GENERAL_REPLACEMENT
    ]
    assert len(replacements) == 1
    existing_keys = {(sample.group, sample.report_no) for sample in v2_samples}
    candidates = [
        product
        for product in products
        if map_ingredients(product).groups == (IngredientGroup.RED_GINSENG,)
        and (IngredientGroup.RED_GINSENG, product.report_no) not in existing_keys
    ]
    expected = min(
        candidates,
        key=lambda product: (
            _hash_rank(
                20260823,
                IngredientGroup.RED_GINSENG,
                "general-replacement",
                product.report_no,
            ),
            product.report_no,
            product.name,
            product.company,
        ),
    )
    assert replacements[0].report_no == expected.report_no


def test_each_group_has_exactly_20_evaluable_general_rows(tmp_path: Path) -> None:
    samples, *_ = _build_synthetic_samples(tmp_path)

    for group in COMPARISON_GROUPS:
        evaluable = [
            sample
            for sample in samples
            if sample.group is group
            and sample.is_general_audit
            and sample.machine_reason_code is not MachineRoleReasonCode.INHERITED_MAPPING_ERROR
        ]
        assert len(evaluable) == 20


def test_positive_audit_selects_at_most_35_machine_positive_unique_products(
    tmp_path: Path,
) -> None:
    samples, *_ = _build_synthetic_samples(tmp_path)

    for group in COMPARISON_GROUPS:
        positives = [
            sample for sample in samples if sample.group is group and sample.is_positive_audit
        ]
        assert len(positives) == 35
        assert len({sample.report_no for sample in positives}) == len(positives)
        assert all(
            sample.machine_verdict is MachineRoleVerdict.FUNCTIONAL_CONFIRMED
            for sample in positives
        )


def test_existing_general_positive_is_marked_without_a_duplicate_row(
    tmp_path: Path,
) -> None:
    samples, *_ = _build_synthetic_samples(tmp_path)
    keys = [(sample.group, sample.report_no) for sample in samples]

    assert len(keys) == len(set(keys))
    for group in COMPARISON_GROUPS:
        assert any(
            sample.group is group and sample.is_general_audit and sample.is_positive_audit
            for sample in samples
        )


def test_positive_pool_below_35_keeps_all_rows_for_insufficient_status(
    tmp_path: Path,
) -> None:
    samples, *_ = _build_synthetic_samples(
        tmp_path,
        magnesium_positive_count=34,
    )
    magnesium_positive = [
        sample
        for sample in samples
        if sample.group is IngredientGroup.MAGNESIUM and sample.is_positive_audit
    ]

    assert len(magnesium_positive) == 34
    assert all(
        sample.machine_verdict is MachineRoleVerdict.FUNCTIONAL_CONFIRMED
        for sample in magnesium_positive
    )


def test_group_and_report_number_are_unique_across_the_pack(tmp_path: Path) -> None:
    samples, *_ = _build_synthetic_samples(tmp_path)
    keys = tuple((sample.group, sample.report_no) for sample in samples)

    assert len(keys) == len(set(keys))


def test_sampling_is_invariant_to_source_order(tmp_path: Path) -> None:
    baseline, *_ = _build_synthetic_samples(tmp_path, root_name="baseline")
    reversed_samples, *_ = _build_synthetic_samples(
        tmp_path,
        reverse_source=True,
        root_name="reversed",
    )

    assert [sample.model_dump(mode="json") for sample in baseline] == [
        sample.model_dump(mode="json") for sample in reversed_samples
    ]


def test_sampling_changes_when_the_seed_changes() -> None:
    group = IngredientGroup.MAGNESIUM
    reports = tuple(f"SEED-CANDIDATE-{index:03d}" for index in range(40))

    first_order = tuple(
        sorted(reports, key=lambda report: (_hash_rank(1, group, "positive", report), report))
    )
    second_order = tuple(
        sorted(reports, key=lambda report: (_hash_rank(2, group, "positive", report), report))
    )
    assert first_order != second_order


def test_every_group_uses_the_same_scope_specific_hash_rule() -> None:
    observed: set[int] = set()
    for group in COMPARISON_GROUPS:
        for scope in ("general-replacement", "positive"):
            expected_material = (f"c003-functional-role-v1|20260823|{group.value}|{scope}").encode()
            expected = int.from_bytes(hashlib.sha256(expected_material).digest()[:8], "big")
            actual = derive_sample_seed(20260823, group, scope)
            assert actual == expected
            observed.add(actual)
    assert len(observed) == len(COMPARISON_GROUPS) * 2


def test_non_machine_positive_products_never_enter_positive_audit_only_rows(
    tmp_path: Path,
) -> None:
    samples, *_ = _build_synthetic_samples(tmp_path)

    assert all(
        sample.machine_verdict is MachineRoleVerdict.FUNCTIONAL_CONFIRMED
        for sample in samples
        if sample.sample_origin is SampleOrigin.POSITIVE_PRECISION
    )
    assert all(not sample.is_positive_audit for sample in samples if "-NEG-" in sample.report_no)
