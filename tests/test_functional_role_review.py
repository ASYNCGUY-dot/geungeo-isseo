import copy
import csv
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from claimledger import functional_role_review as role_review_module
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
    FunctionalRoleBuildError,
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
    validate_functional_role_review_pack,
    write_functional_role_review_pack,
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
    wilson_interval,
)
from scripts import validate_functional_role_review as validate_functional_review_module
from scripts.validate_functional_role_review import main as validate_functional_review_main

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


@pytest.mark.parametrize("model_kind", ("label", "sample", "counts", "summary"))
def test_review_models_reject_ingredients_outside_approved_comparison(model_kind: str) -> None:
    model, values = {
        "label": (FunctionalRoleLabel, _valid_label_values()),
        "sample": (FunctionalRoleSample, _valid_sample_values()),
        "counts": (FunctionalRoleGroupCounts, _valid_group_count(IngredientGroup.MAGNESIUM)),
        "summary": (
            FunctionalRoleGroupSummary,
            _valid_group_summary(IngredientGroup.MAGNESIUM).model_dump(),
        ),
    }[model_kind]
    values["group"] = IngredientGroup.OMEGA3

    with pytest.raises(ValidationError, match="comparison ingredient group"):
        model.model_validate(values)


@pytest.mark.parametrize("versions", ((), ("",), (" padded-version ",)))
def test_manifest_rejects_empty_or_unnormalized_version_provenance(
    versions: tuple[str, ...],
) -> None:
    values = _valid_manifest_values()
    values["mapping_rule_versions"] = versions

    with pytest.raises(ValidationError, match="normalized and nonblank|must not be empty"):
        FunctionalRoleManifest.model_validate(values)


@pytest.mark.parametrize("excerpt", ("not-json", '{"raw_materials":'))
def test_label_rejects_unparseable_both_field_evidence(excerpt: str) -> None:
    values = _valid_label_values()
    values["evidence_excerpt"] = excerpt

    with pytest.raises(ValidationError, match="canonical both-field JSON"):
        FunctionalRoleLabel.model_validate(values)


def test_label_rejects_blank_single_field_evidence() -> None:
    values = _valid_label_values()
    values.update(
        human_verdict=HumanRoleVerdict.UNCERTAIN,
        reason_code=FunctionalRoleReasonCode.INSUFFICIENT_LINKAGE,
        evidence_field=RoleEvidenceField.RAW_MATERIALS,
        evidence_excerpt="   ",
    )

    with pytest.raises(ValidationError, match="must be nonblank"):
        FunctionalRoleLabel.model_validate(values)


@pytest.mark.parametrize(
    ("group", "scope", "message"),
    (
        (IngredientGroup.OMEGA3, "positive", "comparison ingredient group"),
        (IngredientGroup.MAGNESIUM, "unknown-scope", "scope is invalid"),
    ),
)
def test_sampling_seed_rejects_out_of_scope_requests(
    group: IngredientGroup,
    scope: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        derive_sample_seed(20260823, group, scope)


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


@pytest.mark.parametrize(
    ("mutation", "cause"),
    (
        ("missing_directory", "directory is missing"),
        ("extra_file", "file set is invalid"),
        ("sample_hash", "sample hash is invalid"),
        ("sample_header", "CSV header"),
        ("sample_short_row", "CSV row is malformed"),
        ("missing_sample", "100 complete rows"),
        ("duplicate_source", "duplicate report numbers"),
        ("duplicate_sample", "samples contain duplicate keys"),
        ("changed_product", "does not match source products"),
        ("stale_mapping", "mapping is stale"),
        ("manifest_counts", "Input should be 20"),
        ("manifest_versions", "mapping versions are stale"),
        ("duplicate_label", "labels contain duplicate keys"),
        ("unknown_label", "labels do not match sample keys"),
    ),
)
def test_sampling_rejects_corrupted_prerequisites_even_with_recomputed_hash(
    tmp_path: Path,
    mutation: str,
    cause: str,
) -> None:
    products = _synthetic_source_products()
    pack_dir, _, _ = _write_completed_v2_pack(tmp_path / "corrupt-prerequisite", products)
    samples_path = pack_dir / "samples.csv"
    manifest_path = pack_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if mutation == "missing_directory":
        pack_dir = pack_dir / "missing"
    elif mutation == "extra_file":
        (pack_dir / "unexpected.txt").write_text("unexpected", encoding="utf-8")
    elif mutation == "duplicate_source":
        products = (*products, products[0])
    elif mutation in {"manifest_counts", "manifest_versions"}:
        if mutation == "manifest_counts":
            manifest["group_counts"]["milk_thistle"] -= 1
            manifest["group_counts"]["vitamin_d"] += 1
        else:
            manifest["mapping_rule_versions"] = ["stale-map-v999"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif mutation in {"duplicate_label", "unknown_label"}:
        labels_path = pack_dir / "product_review_labels.csv"
        fields, rows = _read_csv_fields_and_rows(labels_path)
        if mutation == "duplicate_label":
            rows[-1] = dict(rows[0])
        else:
            rows[0]["report_no"] = "unknown-report"
        _write_csv_rows(labels_path, fields, rows)
    else:
        fields, rows = _read_csv_fields_and_rows(samples_path)
        if mutation == "sample_header":
            fields = ("wrong_column", *fields[1:])
            rows = []
        elif mutation == "missing_sample":
            rows.pop()
        elif mutation == "duplicate_sample":
            rows[-1] = dict(rows[0])
        elif mutation == "stale_mapping":
            rows[0]["mapping_rule_version"] = "stale-map-v999"
        else:
            rows[0]["company"] = "changed-source-company"
        _write_csv_rows(samples_path, fields, rows)
        if mutation == "sample_short_row":
            samples_path.write_text(",".join(fields) + "\nshort-row\n", encoding="utf-8")
        if mutation != "sample_hash":
            # A matching hash is not sufficient proof of source or review integrity.
            manifest["samples_sha256"] = sha256_file(samples_path)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="must be COMPLETE") as error:
        build_functional_role_samples(
            products,
            product_review_pack_dir=pack_dir,
            registry=_registry(),
        )

    assert cause in str(error.value.__cause__)


def test_sampling_rejects_insufficient_same_group_replacements(tmp_path: Path) -> None:
    products = tuple(
        product for product in _synthetic_source_products() if "-V2-" in product.report_no
    )
    pack_dir, _, _ = _write_completed_v2_pack(tmp_path / "no-replacements", products)

    with pytest.raises(ValueError, match="insufficient same-group general replacement"):
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


def _write_functional_pack(
    tmp_path: Path,
    *,
    root_name: str = "functional-pack",
    magnesium_positive_count: int = 40,
) -> tuple[Path, Path, Path, tuple[ExtensionReviewProduct, ...], FunctionalRoleManifest]:
    root = tmp_path / root_name
    products = _synthetic_source_products(
        magnesium_positive_count=magnesium_positive_count,
    )
    product_review_pack, source_export, _ = _write_completed_v2_pack(root, products)
    output_dir = root / "functional-role-review-v1"
    manifest = write_functional_role_review_pack(
        output_dir,
        products=products,
        source_export_path=source_export,
        product_review_pack_dir=product_review_pack,
        rules_path=RULE_FIXTURE_PATH,
        registry=_registry(),
        generated_at=NOW,
    )
    return output_dir, product_review_pack, source_export, products, manifest


def _read_csv(path: Path) -> tuple[dict[str, str], ...]:
    with path.open(encoding="utf-8", newline="") as handle:
        return tuple(csv.DictReader(handle))


def test_writer_creates_exactly_four_files_with_lf_utf8(tmp_path: Path) -> None:
    output_dir, *_ = _write_functional_pack(tmp_path)

    assert {path.name for path in output_dir.iterdir()} == {
        "README.md",
        "manifest.json",
        "samples.csv",
        "functional_role_labels.csv",
    }
    for path in output_dir.iterdir():
        raw = path.read_bytes()
        assert raw.decode("utf-8")
        assert b"\r\n" not in raw
        assert raw.endswith(b"\n")


def test_writer_refuses_an_existing_output_directory(tmp_path: Path) -> None:
    root = tmp_path / "existing-output"
    products = _synthetic_source_products()
    product_review_pack, source_export, _ = _write_completed_v2_pack(root, products)
    output_dir = root / "functional-role-review-v1"
    output_dir.mkdir()
    sentinel = output_dir / "keep.txt"
    sentinel.write_text("preserve me\n", encoding="utf-8", newline="\n")

    with pytest.raises(FunctionalRoleBuildError, match="already exists"):
        write_functional_role_review_pack(
            output_dir,
            products=products,
            source_export_path=source_export,
            product_review_pack_dir=product_review_pack,
            rules_path=RULE_FIXTURE_PATH,
            registry=_registry(),
            generated_at=NOW,
        )

    assert sentinel.read_text(encoding="utf-8") == "preserve me\n"
    assert {path.name for path in output_dir.iterdir()} == {"keep.txt"}


def test_writer_refuses_products_not_identical_to_the_bound_source_export(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source-binding"
    products = _synthetic_source_products()
    product_review_pack, source_export, _ = _write_completed_v2_pack(root, products)
    target_report_no = _report_no(IngredientGroup.MAGNESIUM, "NEG", 20)
    altered_products = tuple(
        product.model_copy(update={"company": "원본과 다른 제조사"})
        if product.report_no == target_report_no
        else product
        for product in products
    )
    output_dir = root / "functional-role-review-v1"

    with pytest.raises(FunctionalRoleBuildError, match="source export"):
        write_functional_role_review_pack(
            output_dir,
            products=altered_products,
            source_export_path=source_export,
            product_review_pack_dir=product_review_pack,
            rules_path=RULE_FIXTURE_PATH,
            registry=_registry(),
            generated_at=NOW,
        )

    assert not output_dir.exists()


def test_writer_refuses_output_nested_inside_the_product_review_pack(
    tmp_path: Path,
) -> None:
    root = tmp_path / "nested-output"
    products = _synthetic_source_products()
    product_review_pack, source_export, _ = _write_completed_v2_pack(root, products)
    output_dir = product_review_pack / "functional-role-review-v1"
    original_files = {path.name for path in product_review_pack.iterdir()}

    with pytest.raises(FunctionalRoleBuildError, match="inside the product review pack"):
        write_functional_role_review_pack(
            output_dir,
            products=products,
            source_export_path=source_export,
            product_review_pack_dir=product_review_pack,
            rules_path=RULE_FIXTURE_PATH,
            registry=_registry(),
            generated_at=NOW,
        )

    assert not output_dir.exists()
    assert {path.name for path in product_review_pack.iterdir()} == original_files


def test_writer_removes_a_partially_created_directory_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "partial-output"
    products = _synthetic_source_products()
    product_review_pack, source_export, _ = _write_completed_v2_pack(root, products)
    output_dir = root / "functional-role-review-v1"
    original_open = Path.open

    def fail_manifest_write(path: Path, *args: object, **kwargs: object) -> object:
        mode = str(args[0]) if args else str(kwargs.get("mode", "r"))
        if path == output_dir / "manifest.json" and "w" in mode:
            raise OSError("synthetic write failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_manifest_write)
    with pytest.raises(FunctionalRoleBuildError, match="could not write"):
        write_functional_role_review_pack(
            output_dir,
            products=products,
            source_export_path=source_export,
            product_review_pack_dir=product_review_pack,
            rules_path=RULE_FIXTURE_PATH,
            registry=_registry(),
            generated_at=NOW,
        )

    assert not output_dir.exists()


@pytest.mark.parametrize("failure", ("mkdir", "missing_rules", "registry_mismatch"))
def test_writer_rejects_unavailable_storage_or_unbound_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    products = _synthetic_source_products()
    pack_dir, source_export, _ = _write_completed_v2_pack(tmp_path / "write-precondition", products)
    output_dir = pack_dir.parent / "role-output"
    registry = _registry()
    rules_path = RULE_FIXTURE_PATH
    if failure == "mkdir":
        original_mkdir = Path.mkdir

        def deny_output_creation(path: Path, *args: object, **kwargs: object):
            if path == output_dir:
                raise PermissionError("synthetic output access denied")
            return original_mkdir(path, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", deny_output_creation)
        message = "could not create"
    elif failure == "missing_rules":
        rules_path = pack_dir.parent / "missing-rules.json"
        message = "could not build"
    else:
        values = registry.model_dump()
        values["rules"][0]["source_id"] = "different-source"
        registry = FunctionalRoleRuleRegistry.model_validate(values)
        message = "registry input does not match"

    with pytest.raises(FunctionalRoleBuildError, match=message):
        write_functional_role_review_pack(
            output_dir,
            products=products,
            source_export_path=source_export,
            product_review_pack_dir=pack_dir,
            rules_path=rules_path,
            registry=registry,
            generated_at=NOW,
        )

    assert not output_dir.exists()


@pytest.mark.parametrize("failure", ("truncated_samples", "missing_labels", "cleanup_denied"))
def test_writer_detects_silent_write_loss_and_reports_failed_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    products = _synthetic_source_products()
    pack_dir, source_export, _ = _write_completed_v2_pack(tmp_path / "write-loss", products)
    output_dir = pack_dir.parent / "role-output"
    original_write_text = Path.write_text

    def lose_output_bytes(path: Path, data: str, *args: object, **kwargs: object):
        if path == output_dir / "samples.csv" and failure != "missing_labels":
            return original_write_text(path, data[:10], *args, **kwargs)
        if path == output_dir / "functional_role_labels.csv" and failure == "missing_labels":
            return len(data)
        return original_write_text(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", lose_output_bytes)
    if failure == "cleanup_denied":
        original_rmtree = role_review_module.shutil.rmtree

        def deny_output_cleanup(path: Path, *args: object, **kwargs: object):
            if path == output_dir:
                raise PermissionError("synthetic cleanup access denied")
            return original_rmtree(path, *args, **kwargs)

        monkeypatch.setattr(role_review_module.shutil, "rmtree", deny_output_cleanup)

    message = "could not clean a partial" if failure == "cleanup_denied" else "could not write"
    with pytest.raises(FunctionalRoleBuildError, match=message):
        write_functional_role_review_pack(
            output_dir,
            products=products,
            source_export_path=source_export,
            product_review_pack_dir=pack_dir,
            rules_path=RULE_FIXTURE_PATH,
            registry=_registry(),
            generated_at=NOW,
        )

    assert output_dir.exists() is (failure == "cleanup_denied")
    if failure == "cleanup_denied":
        result = _validate_generated_pack((output_dir, source_export, pack_dir, RULE_FIXTURE_PATH))
        _assert_role_validation_is_blocked(result, "SAMPLES_HASH_MISMATCH")


def test_manifest_binds_source_v2_rules_and_samples_hashes(tmp_path: Path) -> None:
    output_dir, product_review_pack, source_export, _, manifest = _write_functional_pack(tmp_path)

    assert manifest.source_export_sha256 == sha256_file(source_export)
    assert manifest.product_review_manifest_sha256 == sha256_file(
        product_review_pack / "manifest.json"
    )
    assert manifest.product_review_samples_sha256 == sha256_file(
        product_review_pack / "samples.csv"
    )
    assert manifest.product_review_labels_sha256 == sha256_file(
        product_review_pack / "product_review_labels.csv"
    )
    assert manifest.rules_sha256 == sha256_file(RULE_FIXTURE_PATH)
    assert manifest.samples_sha256 == sha256_file(output_dir / "samples.csv")
    on_disk = FunctionalRoleManifest.model_validate_json(
        (output_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert on_disk == manifest


def test_manifest_records_exact_per_group_pool_and_sample_counts(tmp_path: Path) -> None:
    output_dir, _, _, _, manifest = _write_functional_pack(tmp_path)
    sample_rows = _read_csv(output_dir / "samples.csv")

    assert tuple(count.group for count in manifest.group_counts) == COMPARISON_GROUPS
    for count in manifest.group_counts:
        inherited_count = 1 if count.group is IngredientGroup.RED_GINSENG else 0
        assert count.original_v2_count == 20
        assert count.inherited_mapping_error_count == inherited_count
        assert count.general_replacement_count == inherited_count
        assert count.general_evaluable_count == 20
        assert count.positive_pool_count == 40
        assert count.positive_sample_count == 35
        assert count.total_unique_rows == sum(
            row["group"] == count.group.value for row in sample_rows
        )


def test_label_template_has_one_row_for_every_sample_key(tmp_path: Path) -> None:
    output_dir, *_ = _write_functional_pack(tmp_path)
    sample_rows = _read_csv(output_dir / "samples.csv")
    label_rows = _read_csv(output_dir / "functional_role_labels.csv")

    sample_keys = [(row["group"], row["report_no"]) for row in sample_rows]
    label_keys = [(row["group"], row["report_no"]) for row in label_rows]
    assert label_keys == sample_keys
    assert len(label_keys) == len(set(label_keys))


def test_inherited_mapping_error_label_copies_v2_reviewer_and_time(tmp_path: Path) -> None:
    output_dir, product_review_pack, _, _, _ = _write_functional_pack(tmp_path)
    inherited_report_no = _report_no(IngredientGroup.RED_GINSENG, "V2", 0)
    v2_label = next(
        row
        for row in _read_csv(product_review_pack / "product_review_labels.csv")
        if row["group"] == IngredientGroup.RED_GINSENG.value
        and row["report_no"] == inherited_report_no
    )
    role_label = next(
        row
        for row in _read_csv(output_dir / "functional_role_labels.csv")
        if row["group"] == IngredientGroup.RED_GINSENG.value
        and row["report_no"] == inherited_report_no
    )

    assert role_label["human_verdict"] == "excluded_mapping_error"
    assert role_label["reason_code"] == "inherited_mapping_error"
    assert role_label["evidence_field"] == "none"
    assert role_label["evidence_excerpt"] == ""
    assert role_label["reviewer"] == v2_label["reviewer"]
    assert role_label["reviewed_at_iso8601"] == v2_label["reviewed_at_iso8601"]
    assert role_label["review_note"] == (
        "Inherited c003-product-review-v2 mapping verdict: "
        f"{v2_label['mapping_verdict']}/{v2_label['mapping_reason_code']}."
    )


def test_all_non_inherited_label_rows_are_completely_blank_human_inputs(
    tmp_path: Path,
) -> None:
    output_dir, *_ = _write_functional_pack(tmp_path)
    inherited_report_no = _report_no(IngredientGroup.RED_GINSENG, "V2", 0)
    human_fields = (
        "human_verdict",
        "reason_code",
        "evidence_field",
        "evidence_excerpt",
        "rule_version",
        "review_note",
        "reviewer",
        "reviewed_at_iso8601",
    )

    for row in _read_csv(output_dir / "functional_role_labels.csv"):
        if row["report_no"] == inherited_report_no:
            continue
        assert all(row[field] == "" for field in human_fields)
        assert row["machine_verdict"] in {verdict.value for verdict in MachineRoleVerdict}


def test_pack_readme_states_pending_not_measured_blocked_and_not_finalized(
    tmp_path: Path,
) -> None:
    output_dir, *_ = _write_functional_pack(tmp_path)
    readme = (output_dir / "README.md").read_text(encoding="utf-8")

    assert "Review status: PENDING" in readme
    assert "advertising evidence: NOT_MEASURED" in readme
    assert "extension recommendation: BLOCKED" in readme
    assert "finalized: false" in readme


@pytest.mark.parametrize(
    "overrides",
    (
        {"base_seed": 1},
        {"general_size": 19},
        {"positive_size": 34},
    ),
)
def test_builder_refuses_nondefault_general_or_positive_sizes(
    tmp_path: Path,
    overrides: dict[str, int],
) -> None:
    root = tmp_path / f"locked-{next(iter(overrides))}"
    products = _synthetic_source_products()
    product_review_pack, source_export, _ = _write_completed_v2_pack(root, products)
    output_dir = root / "functional-role-review-v1"

    with pytest.raises(FunctionalRoleBuildError, match="locked"):
        write_functional_role_review_pack(
            output_dir,
            products=products,
            source_export_path=source_export,
            product_review_pack_dir=product_review_pack,
            rules_path=RULE_FIXTURE_PATH,
            registry=_registry(),
            generated_at=NOW,
            **overrides,
        )

    assert not output_dir.exists()


def _write_cli_rule_fixture(root: Path, *, verification_age_days: int = 0) -> Path:
    # The subprocess uses the real clock; only this temporary synthetic fixture is rebased.
    data = json.loads(RULE_FIXTURE_PATH.read_text(encoding="utf-8"))
    verified_at = datetime.now(UTC) - timedelta(days=verification_age_days)
    for rule in data["rules"]:
        rule["retrieved_at"] = verified_at.isoformat()
        rule["verified_current_at"] = verified_at.isoformat()
    rules_path = root / "cli-synthetic-rules.json"
    rules_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return rules_path


@pytest.mark.parametrize("verification_age_days", [0, 8])
def test_build_cli_returns_zero_only_after_a_complete_write(
    tmp_path: Path, verification_age_days: int
) -> None:
    root = tmp_path / "cli-success"
    products = _synthetic_source_products()
    product_review_pack, source_export, _ = _write_completed_v2_pack(root, products)
    output_dir = root / "functional-role-review-v1"
    script = Path(__file__).parents[1] / "scripts" / "build_functional_role_review.py"
    rules_path = _write_cli_rule_fixture(root, verification_age_days=verification_age_days)

    completed = subprocess.run(
        (
            sys.executable,
            str(script),
            "--source-export",
            str(source_export),
            "--product-review-pack",
            str(product_review_pack),
            "--rules",
            str(rules_path),
            "--output-dir",
            str(output_dir),
        ),
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    if verification_age_days == 8:
        assert completed.returncode != 0
        assert "rule verification must be current" in completed.stderr
        assert not output_dir.exists()
        return

    assert completed.returncode == 0, completed.stderr
    assert {path.name for path in output_dir.iterdir()} == {
        "README.md",
        "manifest.json",
        "samples.csv",
        "functional_role_labels.csv",
    }


def test_build_cli_returns_a_nonzero_error_without_a_partial_pack(tmp_path: Path) -> None:
    root = tmp_path / "cli-failure"
    products = _synthetic_source_products()
    product_review_pack, source_export, _ = _write_completed_v2_pack(root, products)
    output_dir = root / "functional-role-review-v1"
    script = Path(__file__).parents[1] / "scripts" / "build_functional_role_review.py"
    rules_path = _write_cli_rule_fixture(root)

    completed = subprocess.run(
        (
            sys.executable,
            str(script),
            "--source-export",
            str(source_export),
            "--product-review-pack",
            str(product_review_pack),
            "--rules",
            str(rules_path),
            "--output-dir",
            str(output_dir),
            "--positive-size",
            "34",
        ),
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "error:" in completed.stderr
    assert "locked sampling settings" in completed.stderr
    assert not output_dir.exists()


def _write_validation_pack(
    tmp_path: Path,
    *,
    root_name: str,
    non_inherited_unverifiable: bool = False,
    source_products: tuple[ExtensionReviewProduct, ...] | None = None,
    rule_fixture_path: Path = RULE_FIXTURE_PATH,
    generated_at: datetime = NOW,
) -> tuple[Path, Path, Path, Path]:
    root = tmp_path / root_name
    products = source_products or _synthetic_source_products()
    if non_inherited_unverifiable:
        target_report_no = _report_no(IngredientGroup.MAGNESIUM, "V2", 0)
        products = tuple(
            product.model_copy(update={"primary_function": "일반적인 영양 보충"})
            if product.report_no == target_report_no
            else product
            for product in products
        )
    product_review_pack, source_export, _ = _write_completed_v2_pack(root, products)
    rules_path = root / "functional-role-rules.json"
    rules_path.write_bytes(rule_fixture_path.read_bytes())
    registry = load_functional_role_registry(rules_path, evaluated_at=generated_at)
    pack_dir = root / "functional-role-review-v1"
    write_functional_role_review_pack(
        pack_dir,
        products=products,
        source_export_path=source_export,
        product_review_pack_dir=product_review_pack,
        rules_path=rules_path,
        registry=registry,
        generated_at=generated_at,
    )
    return pack_dir, source_export, product_review_pack, rules_path


def _validate_generated_pack(
    paths: tuple[Path, Path, Path, Path],
    *,
    validated_at: datetime = NOW,
) -> FunctionalRoleValidationResult:
    pack_dir, source_export, product_review_pack, rules_path = paths
    return validate_functional_role_review_pack(
        pack_dir,
        source_export,
        product_review_pack,
        rules_path,
        validated_at=validated_at,
    )


def _read_csv_fields_and_rows(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return tuple(reader.fieldnames or ()), list(reader)


def _write_csv_rows(
    path: Path,
    fields: tuple[str, ...],
    rows: list[dict[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _complete_one_functional_label(pack_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    _, sample_rows = _read_csv_fields_and_rows(pack_dir / "samples.csv")
    label_fields, label_rows = _read_csv_fields_and_rows(pack_dir / "functional_role_labels.csv")
    samples_by_key = {(row["group"], row["report_no"]): row for row in sample_rows}
    for label_row in label_rows:
        sample_row = samples_by_key[(label_row["group"], label_row["report_no"])]
        if (
            not label_row["human_verdict"]
            and sample_row["machine_verdict"] == MachineRoleVerdict.FUNCTIONAL_CONFIRMED.value
        ):
            label_row.update(
                {
                    "human_verdict": HumanRoleVerdict.FUNCTIONAL_CONFIRMED.value,
                    "reason_code": FunctionalRoleReasonCode.EXPLICIT_TARGET_FUNCTION.value,
                    "evidence_field": RoleEvidenceField.BOTH.value,
                    "evidence_excerpt": sample_row["machine_evidence_excerpt"],
                    "rule_version": sample_row["functional_role_rule_version"],
                    "review_note": "",
                    "reviewer": "synthetic-role-reviewer",
                    "reviewed_at_iso8601": "2026-08-30T09:00:00Z",
                }
            )
            _write_csv_rows(
                pack_dir / "functional_role_labels.csv",
                label_fields,
                label_rows,
            )
            return sample_row, label_row
    raise AssertionError("synthetic pack has no pending machine-positive row")


def test_validator_returns_pending_for_a_clean_incomplete_pack(tmp_path: Path) -> None:
    paths = _write_validation_pack(tmp_path, root_name="clean-pending")
    pack_dir = paths[0]
    label_rows = _read_csv(pack_dir / "functional_role_labels.csv")
    prefilled_count = sum(bool(row["human_verdict"]) for row in label_rows)

    result = _validate_generated_pack(paths)

    assert result.status is ReviewGateStatus.PENDING
    assert result.expected_label_count == len(label_rows)
    assert result.valid_label_count == prefilled_count == 1
    assert result.pending_label_count == len(label_rows) - prefilled_count
    assert result.issues == ()
    assert result.summary is None
    assert result.advertising_evidence_status == "NOT_MEASURED"
    assert result.extension_recommendation_status == "BLOCKED"
    assert result.finalized is False


def _assert_role_validation_is_blocked(
    result: FunctionalRoleValidationResult,
    expected_code: str,
) -> None:
    assert result.status is ReviewGateStatus.INVALID
    assert expected_code in {issue.code for issue in result.issues}
    assert result.valid_label_count is None
    assert result.pending_label_count is None
    assert result.summary is None
    assert result.advertising_evidence_status == "NOT_MEASURED"
    assert result.extension_recommendation_status == "BLOCKED"
    assert result.finalized is False


@pytest.mark.parametrize("validated_at", (None, "2026-08-30", NOW.replace(tzinfo=None)))
def test_validator_blocks_invalid_validation_clock(tmp_path: Path, validated_at: object) -> None:
    paths = tuple(tmp_path / name for name in ("pack", "source", "v2", "rules"))

    result = _validate_generated_pack(paths, validated_at=validated_at)

    _assert_role_validation_is_blocked(result, "VALIDATED_AT_INVALID")


def test_validator_blocks_a_missing_pack_directory(tmp_path: Path) -> None:
    paths = tuple(tmp_path / name for name in ("pack", "source", "v2", "rules"))

    result = _validate_generated_pack(paths)

    _assert_role_validation_is_blocked(result, "PACK_DIRECTORY_MISSING")


def test_validator_blocks_an_unreadable_pack_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="unreadable-directory")
    original_iterdir = Path.iterdir

    def deny_pack_listing(path: Path):
        if path == paths[0]:
            raise PermissionError("synthetic directory access denied")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", deny_pack_listing)

    result = _validate_generated_pack(paths)

    _assert_role_validation_is_blocked(result, "PACK_DIRECTORY_INVALID")


@pytest.mark.parametrize(
    ("path_index", "document", "issue_code"),
    (
        (0, "README.md", "PACK_README_UNREADABLE"),
        (0, "manifest.json", "PACK_MANIFEST_UNREADABLE"),
        (0, "samples.csv", "PACK_SAMPLES_UNREADABLE"),
        (0, "functional_role_labels.csv", "PACK_LABELS_UNREADABLE"),
        (1, "", "SOURCE_EXPORT_UNREADABLE"),
        (2, "README.md", "V2_README_UNREADABLE"),
        (2, "manifest.json", "V2_MANIFEST_UNREADABLE"),
        (2, "samples.csv", "V2_SAMPLES_UNREADABLE"),
        (2, "product_review_labels.csv", "V2_LABELS_UNREADABLE"),
        (3, "", "RULES_UNREADABLE"),
    ),
)
def test_validator_blocks_each_unreadable_authoritative_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path_index: int,
    document: str,
    issue_code: str,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="unreadable-document")
    target = paths[path_index] / document if document else paths[path_index]
    original_open = Path.open

    def deny_target_read(path: Path, *args: object, **kwargs: object):
        if path == target:
            raise PermissionError("synthetic document access denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_target_read)

    result = _validate_generated_pack(paths)

    _assert_role_validation_is_blocked(result, issue_code)
    if target.name != "README.md" and path_index != 0:
        assert "HASH_READ_FAILED" in {issue.code for issue in result.issues}


@pytest.mark.parametrize(
    ("content", "issue_code"),
    ((b"\xff\xfe", "PACK_README_UNREADABLE"), (b"before\x00after", "NUL_BYTE")),
)
def test_validator_blocks_corrupt_document_encoding(
    tmp_path: Path,
    content: bytes,
    issue_code: str,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="corrupt-encoding")
    (paths[0] / "README.md").write_bytes(content)

    result = _validate_generated_pack(paths)

    _assert_role_validation_is_blocked(result, issue_code)


def test_validator_blocks_an_oversized_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="oversized-document")
    # Lower only the I/O limit; keep the real decoder, validator and fixtures.
    limit = max(path.stat().st_size for path in paths[0].parent.rglob("*") if path.is_file())
    monkeypatch.setattr(role_review_module, "_MAX_VALIDATION_DOCUMENT_BYTES", limit)
    (paths[0] / "README.md").write_bytes(b"x" * (limit + 1))

    result = _validate_generated_pack(paths)

    _assert_role_validation_is_blocked(result, "DOCUMENT_TOO_LARGE")
    assert {issue.code for issue in result.issues} == {"DOCUMENT_TOO_LARGE"}


@pytest.mark.parametrize("document", ("samples.csv", "functional_role_labels.csv"))
@pytest.mark.parametrize("corruption", ("header", "short_row", "extra_column", "unclosed_quote"))
def test_validator_blocks_malformed_csv_documents(
    tmp_path: Path,
    document: str,
    corruption: str,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="malformed-csv")
    target = paths[0] / document
    header = target.read_text(encoding="utf-8").splitlines()[0]
    column_count = len(header.split(","))
    if corruption == "header":
        content = "wrong,header\n"
    elif corruption == "short_row":
        content = header + "\nonly-one-cell\n"
    elif corruption == "extra_column":
        content = header + "\n" + ",".join(["cell"] * (column_count + 1)) + "\n"
    else:
        content = header + '\n"unterminated\n'
    target.write_text(content, encoding="utf-8", newline="\n")

    result = _validate_generated_pack(paths)

    prefix = "SAMPLE" if document == "samples.csv" else "LABEL"
    suffix = "HEADER_MISMATCH" if corruption == "header" else "ROW_INVALID"
    _assert_role_validation_is_blocked(result, f"{prefix}_{suffix}")


@pytest.mark.parametrize(
    ("mutation", "issue_code"),
    (
        ("invalid_json", "MANIFEST_INVALID"),
        ("future_generation", "MANIFEST_GENERATED_AT_FUTURE"),
        ("mapping_version", "MANIFEST_MAPPING_VERSIONS_MISMATCH"),
        ("role_version", "MANIFEST_ROLE_VERSIONS_MISMATCH"),
        ("group_counts", "MANIFEST_GROUP_COUNTS_MISMATCH"),
    ),
)
def test_validator_blocks_unbound_manifest_metadata(
    tmp_path: Path,
    mutation: str,
    issue_code: str,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="unbound-manifest")
    target = paths[0] / "manifest.json"
    values = json.loads(target.read_text(encoding="utf-8"))
    if mutation == "future_generation":
        values["generated_at"] = (NOW + timedelta(seconds=1)).isoformat()
    elif mutation == "mapping_version":
        values["mapping_rule_versions"] = ["unbound-map-v999"]
    elif mutation == "role_version":
        values["functional_role_rule_versions"] = ["unbound-role-v999"]
    elif mutation == "group_counts":
        values["group_counts"][0]["positive_pool_count"] += 1
    content = "{invalid-json" if mutation == "invalid_json" else json.dumps(values)
    target.write_text(content, encoding="utf-8", newline="\n")

    result = _validate_generated_pack(paths)

    _assert_role_validation_is_blocked(result, issue_code)


@pytest.mark.parametrize("corruption", ("invalid_json", "duplicate_report"))
def test_validator_blocks_unparseable_or_duplicate_source_records(
    tmp_path: Path,
    corruption: str,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="corrupt-source")
    source = paths[1]
    content = source.read_text(encoding="utf-8")
    addition = "{invalid-json" if corruption == "invalid_json" else content.splitlines()[0]
    source.write_text(content + addition + "\n", encoding="utf-8", newline="\n")

    result = _validate_generated_pack(paths)

    _assert_role_validation_is_blocked(result, "SOURCE_EXPORT_INVALID")


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("source_id", 12345),
        ("reviewed_by", None),
        ("accepted_functional_forms", None),
        ("recognized_function_texts", [12345]),
    ),
)
def test_validator_blocks_wrong_types_in_rule_evidence(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="wrong-rule-type")
    values = json.loads(paths[3].read_text(encoding="utf-8"))
    values["rules"][0][field] = value
    paths[3].write_text(json.dumps(values), encoding="utf-8", newline="\n")

    result = _validate_generated_pack(paths)

    _assert_role_validation_is_blocked(result, "RULES_INVALID")
    assert "12345" not in result.model_dump_json()


def test_validate_cli_returns_invalid_json_for_wrong_rule_types(tmp_path: Path) -> None:
    current_rules = _write_cli_rule_fixture(tmp_path)
    paths = _write_validation_pack(
        tmp_path,
        root_name="cli-wrong-rule-type",
        rule_fixture_path=current_rules,
        generated_at=datetime.now(UTC),
    )
    summary_path = paths[0].parent / "summary.json"
    script = Path(__file__).parents[1] / "scripts" / "validate_functional_role_review.py"
    command = (
        sys.executable,
        str(script),
        "--pack-dir",
        str(paths[0]),
        "--source-export",
        str(paths[1]),
        "--product-review-pack",
        str(paths[2]),
        "--rules",
        str(paths[3]),
        "--summary-output",
        str(summary_path),
    )

    def run_cli() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=Path(__file__).parents[1],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=30,
        )

    baseline = run_cli()
    assert baseline.returncode == 2, baseline.stdout + baseline.stderr
    baseline_result = FunctionalRoleValidationResult.model_validate_json(baseline.stdout)
    assert baseline_result.status is ReviewGateStatus.PENDING
    assert baseline_result.issues == ()
    assert not summary_path.exists()

    values = json.loads(paths[3].read_text(encoding="utf-8"))
    values["rules"][0]["source_id"] = 654321
    paths[3].write_text(json.dumps(values), encoding="utf-8", newline="\n")
    completed = run_cli()

    assert completed.returncode == 3
    result = FunctionalRoleValidationResult.model_validate_json(completed.stdout)
    _assert_role_validation_is_blocked(result, "RULES_INVALID")
    assert not summary_path.exists()
    assert "Traceback" not in completed.stderr
    assert "654321" not in completed.stdout + completed.stderr


@pytest.mark.parametrize(
    ("mutation", "issue_code"),
    (
        ("invalid_group", "INVALID_LABEL_KEY"),
        ("duplicate_key", "DUPLICATE_LABEL_KEY"),
        ("audit_round", "LABEL_MACHINE_MISMATCH"),
        ("machine_verdict", "LABEL_MACHINE_MISMATCH"),
        ("inherited_reviewer", "INHERITED_LABEL_MISMATCH"),
        ("rule_version", "LABEL_RULE_VERSION_MISMATCH"),
    ),
)
def test_validator_blocks_label_identity_and_provenance_changes(
    tmp_path: Path,
    mutation: str,
    issue_code: str,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="label-provenance")
    if mutation in {"rule_version", "machine_verdict"}:
        _complete_one_functional_label(paths[0])
    target = paths[0] / "functional_role_labels.csv"
    fields, rows = _read_csv_fields_and_rows(target)
    if mutation == "invalid_group":
        rows[0]["group"] = "unknown_group"
    elif mutation == "duplicate_key":
        rows.append(dict(rows[0]))
    elif mutation == "inherited_reviewer":
        inherited = next(row for row in rows if row["human_verdict"] == "excluded_mapping_error")
        inherited["reviewer"] = "unbound-reviewer"
    elif mutation == "audit_round":
        pending = next(row for row in rows if not row["human_verdict"])
        pending["audit_round"] = "2" if pending["audit_round"] == "1" else "1"
    else:
        completed = next(row for row in rows if row["human_verdict"] == "functional_confirmed")
        completed[mutation] = "unbound-role-v999" if mutation == "rule_version" else "unverifiable"
    _write_csv_rows(target, fields, rows)

    result = _validate_generated_pack(paths)

    _assert_role_validation_is_blocked(result, issue_code)


@pytest.mark.parametrize("mutation", ("missing", "extra", "renamed"))
def test_validator_rejects_missing_extra_or_renamed_pack_files(
    tmp_path: Path,
    mutation: str,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name=f"file-set-{mutation}")
    pack_dir = paths[0]
    if mutation == "missing":
        (pack_dir / "README.md").unlink()
    elif mutation == "extra":
        (pack_dir / "unexpected.txt").write_text(
            "unexpected\n",
            encoding="utf-8",
            newline="\n",
        )
    else:
        (pack_dir / "manifest.json").rename(pack_dir / "renamed-manifest.json")

    result = _validate_generated_pack(paths)

    assert result.status is ReviewGateStatus.INVALID
    assert {issue.code for issue in result.issues} == {"PACK_FILE_SET"}


@pytest.mark.parametrize("mutation", ("reorder", "product_text"))
def test_validator_rejects_source_export_hash_or_product_text_changes(
    tmp_path: Path,
    mutation: str,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name=f"source-{mutation}")
    source_export = paths[1]
    lines = source_export.read_text(encoding="utf-8").splitlines()
    if mutation == "reorder":
        lines.reverse()
    else:
        value = json.loads(lines[-1])
        value["company"] = "원본 변조 제조사"
        lines[-1] = json.dumps(value, ensure_ascii=False)
    source_export.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    result = _validate_generated_pack(paths)

    assert result.status is ReviewGateStatus.INVALID
    assert "SOURCE_EXPORT_HASH_MISMATCH" in {issue.code for issue in result.issues}


@pytest.mark.parametrize("document", ("manifest.json", "samples.csv", "product_review_labels.csv"))
def test_validator_rejects_any_v2_manifest_sample_or_label_hash_change(
    tmp_path: Path,
    document: str,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name=f"v2-hash-{document}")
    target = paths[2] / document
    target.write_text(
        target.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
        newline="\n",
    )

    result = _validate_generated_pack(paths)

    assert result.status is ReviewGateStatus.INVALID
    expected_code = {
        "manifest.json": "PRODUCT_REVIEW_MANIFEST_HASH_MISMATCH",
        "samples.csv": "PRODUCT_REVIEW_SAMPLES_HASH_MISMATCH",
        "product_review_labels.csv": "PRODUCT_REVIEW_LABELS_HASH_MISMATCH",
    }[document]
    assert expected_code in {issue.code for issue in result.issues}


@pytest.mark.parametrize("mutation", ("hash", "rule_version", "freshness"))
def test_validator_rejects_rules_hash_rule_version_or_freshness_change(
    tmp_path: Path,
    mutation: str,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name=f"rules-{mutation}")
    rules_path = paths[3]
    if mutation == "hash":
        rules_path.write_text(
            rules_path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
            newline="\n",
        )
    else:
        values = json.loads(rules_path.read_text(encoding="utf-8"))
        if mutation == "rule_version":
            values["rules"][0]["rule_version"] = "functional-role-rule-v2"
        else:
            for rule in values["rules"]:
                rule["verified_current_at"] = "2026-08-20T09:00:00Z"
        rules_path.write_text(
            json.dumps(values, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    result = _validate_generated_pack(paths)

    assert result.status is ReviewGateStatus.INVALID
    codes = {issue.code for issue in result.issues}
    assert "RULES_HASH_MISMATCH" in codes
    if mutation == "freshness":
        assert "RULES_INVALID" in codes


@pytest.mark.parametrize("mutation", ("add", "delete", "duplicate", "reorder"))
def test_validator_rejects_sample_add_delete_duplicate_or_reordering(
    tmp_path: Path,
    mutation: str,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name=f"samples-{mutation}")
    samples_path = paths[0] / "samples.csv"
    fields, rows = _read_csv_fields_and_rows(samples_path)
    if mutation == "add":
        extra = dict(rows[-1])
        extra["report_no"] = "SYNTHETIC-EXTRA-ROW"
        rows.append(extra)
    elif mutation == "delete":
        rows.pop()
    elif mutation == "duplicate":
        rows[-1] = dict(rows[0])
    else:
        rows[0], rows[1] = rows[1], rows[0]
    _write_csv_rows(samples_path, fields, rows)

    result = _validate_generated_pack(paths)

    assert result.status is ReviewGateStatus.INVALID
    assert "SAMPLES_HASH_MISMATCH" in {issue.code for issue in result.issues}


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("audit_round", "2"),
        ("sample_origin", SampleOrigin.GENERAL_REPLACEMENT.value),
        ("is_general_audit", "False"),
    ),
)
def test_validator_rejects_changed_audit_round_origin_or_scope_flags(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name=f"audit-{field}")
    samples_path = paths[0] / "samples.csv"
    fields, rows = _read_csv_fields_and_rows(samples_path)
    rows[0][field] = value
    _write_csv_rows(samples_path, fields, rows)

    result = _validate_generated_pack(paths)

    assert result.status is ReviewGateStatus.INVALID
    assert any(issue.code.startswith("SAMPLE") for issue in result.issues)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("machine_verdict", MachineRoleVerdict.UNVERIFIABLE.value),
        ("machine_reason_code", MachineRoleReasonCode.NO_APPLICABLE_EVIDENCE.value),
        (
            "machine_evidence_excerpt",
            '{"raw_materials":"없는 원료","primary_function":"없는 기능"}',
        ),
    ),
)
def test_validator_rejects_changed_machine_verdict_reason_or_evidence(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name=f"machine-{field}")
    samples_path = paths[0] / "samples.csv"
    fields, rows = _read_csv_fields_and_rows(samples_path)
    rows[0][field] = value
    _write_csv_rows(samples_path, fields, rows)

    result = _validate_generated_pack(paths)

    assert result.status is ReviewGateStatus.INVALID
    assert any(issue.code.startswith("SAMPLE") for issue in result.issues)


def test_validator_rejects_label_keys_not_equal_to_sample_keys(tmp_path: Path) -> None:
    paths = _write_validation_pack(tmp_path, root_name="label-keys")
    labels_path = paths[0] / "functional_role_labels.csv"
    fields, rows = _read_csv_fields_and_rows(labels_path)
    rows[0]["report_no"] = "UNKNOWN-LABEL-KEY"
    _write_csv_rows(labels_path, fields, rows)

    result = _validate_generated_pack(paths)

    assert result.status is ReviewGateStatus.INVALID
    assert "LABEL_KEY_SET_MISMATCH" in {issue.code for issue in result.issues}


def test_validator_rejects_a_partial_human_label_row(tmp_path: Path) -> None:
    paths = _write_validation_pack(tmp_path, root_name="partial-label")
    labels_path = paths[0] / "functional_role_labels.csv"
    fields, rows = _read_csv_fields_and_rows(labels_path)
    pending = next(row for row in rows if not row["human_verdict"])
    pending["human_verdict"] = HumanRoleVerdict.FUNCTIONAL_CONFIRMED.value
    _write_csv_rows(labels_path, fields, rows)

    result = _validate_generated_pack(paths)

    assert result.status is ReviewGateStatus.INVALID
    assert "PARTIAL_LABEL" in {issue.code for issue in result.issues}


def test_validator_rejects_mapping_exclusion_for_a_non_inherited_sample(
    tmp_path: Path,
) -> None:
    paths = _write_validation_pack(
        tmp_path,
        root_name="false-mapping-exclusion",
        non_inherited_unverifiable=True,
    )
    pack_dir = paths[0]
    target_report_no = _report_no(IngredientGroup.MAGNESIUM, "V2", 0)
    _, sample_rows = _read_csv_fields_and_rows(pack_dir / "samples.csv")
    sample = next(row for row in sample_rows if row["report_no"] == target_report_no)
    assert sample["machine_verdict"] == MachineRoleVerdict.UNVERIFIABLE.value
    assert sample["machine_reason_code"] != MachineRoleReasonCode.INHERITED_MAPPING_ERROR.value
    labels_path = pack_dir / "functional_role_labels.csv"
    fields, rows = _read_csv_fields_and_rows(labels_path)
    target = next(row for row in rows if row["report_no"] == target_report_no)
    target.update(
        {
            "human_verdict": HumanRoleVerdict.EXCLUDED_MAPPING_ERROR.value,
            "reason_code": FunctionalRoleReasonCode.INHERITED_MAPPING_ERROR.value,
            "evidence_field": RoleEvidenceField.NONE.value,
            "evidence_excerpt": "",
            "rule_version": sample["functional_role_rule_version"],
            "review_note": "",
            "reviewer": "synthetic-role-reviewer",
            "reviewed_at_iso8601": "2026-08-30T09:00:00Z",
        }
    )
    _write_csv_rows(labels_path, fields, rows)

    result = _validate_generated_pack(paths)

    assert result.status is ReviewGateStatus.INVALID
    assert "NON_INHERITED_MAPPING_EXCLUSION" in {issue.code for issue in result.issues}


def test_validator_rejects_evidence_not_literal_in_the_declared_source_field(
    tmp_path: Path,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="nonliteral-evidence")
    pack_dir = paths[0]
    _, completed = _complete_one_functional_label(pack_dir)
    labels_path = pack_dir / "functional_role_labels.csv"
    fields, rows = _read_csv_fields_and_rows(labels_path)
    target = next(
        row
        for row in rows
        if (row["group"], row["report_no"]) == (completed["group"], completed["report_no"])
    )
    target["evidence_excerpt"] = '{"raw_materials":"없는 원료","primary_function":"없는 기능"}'
    _write_csv_rows(labels_path, fields, rows)

    result = _validate_generated_pack(paths)

    assert result.status is ReviewGateStatus.INVALID
    assert "EVIDENCE_NOT_LITERAL" in {issue.code for issue in result.issues}


def test_validator_rejects_noncanonical_both_evidence_json(tmp_path: Path) -> None:
    paths = _write_validation_pack(tmp_path, root_name="noncanonical-evidence")
    pack_dir = paths[0]
    _, completed = _complete_one_functional_label(pack_dir)
    labels_path = pack_dir / "functional_role_labels.csv"
    fields, rows = _read_csv_fields_and_rows(labels_path)
    target = next(
        row
        for row in rows
        if (row["group"], row["report_no"]) == (completed["group"], completed["report_no"])
    )
    evidence = json.loads(target["evidence_excerpt"])
    target["evidence_excerpt"] = json.dumps(evidence, ensure_ascii=False)
    _write_csv_rows(labels_path, fields, rows)

    result = _validate_generated_pack(paths)

    assert result.status is ReviewGateStatus.INVALID
    assert "LABEL_VALUE_INVALID" in {issue.code for issue in result.issues}


def test_validator_rejects_future_review_times(tmp_path: Path) -> None:
    paths = _write_validation_pack(tmp_path, root_name="future-review")
    pack_dir = paths[0]
    _, completed = _complete_one_functional_label(pack_dir)
    labels_path = pack_dir / "functional_role_labels.csv"
    fields, rows = _read_csv_fields_and_rows(labels_path)
    target = next(
        row
        for row in rows
        if (row["group"], row["report_no"]) == (completed["group"], completed["report_no"])
    )
    target["reviewed_at_iso8601"] = (NOW + timedelta(seconds=1)).isoformat()
    _write_csv_rows(labels_path, fields, rows)

    result = _validate_generated_pack(paths)

    assert result.status is ReviewGateStatus.INVALID
    assert "LABEL_REVIEWED_AT_FUTURE" in {issue.code for issue in result.issues}


def test_validator_rejects_a_future_inherited_v2_review_time(tmp_path: Path) -> None:
    paths = _write_validation_pack(tmp_path, root_name="future-inherited-review")
    pack_dir, _, product_review_pack, _ = paths
    inherited_report_no = _report_no(IngredientGroup.RED_GINSENG, "V2", 0)
    future_time = "2026-08-30T09:00:01Z"
    v2_labels_path = product_review_pack / "product_review_labels.csv"
    v2_fields, v2_rows = _read_csv_fields_and_rows(v2_labels_path)
    v2_target = next(row for row in v2_rows if row["report_no"] == inherited_report_no)
    v2_target["reviewed_at_iso8601"] = future_time
    _write_csv_rows(v2_labels_path, v2_fields, v2_rows)
    role_labels_path = pack_dir / "functional_role_labels.csv"
    role_fields, role_rows = _read_csv_fields_and_rows(role_labels_path)
    role_target = next(row for row in role_rows if row["report_no"] == inherited_report_no)
    role_target["reviewed_at_iso8601"] = future_time
    _write_csv_rows(role_labels_path, role_fields, role_rows)
    manifest_path = pack_dir / "manifest.json"
    manifest_values = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_values["product_review_labels_sha256"] = sha256_file(v2_labels_path)
    manifest_path.write_text(
        json.dumps(manifest_values, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    result = _validate_generated_pack(paths)

    assert result.status is ReviewGateStatus.INVALID
    assert "LABEL_REVIEWED_AT_FUTURE" in {issue.code for issue in result.issues}


@pytest.mark.parametrize("mutation", ("formula", "secret", "nul"))
def test_validator_rejects_formula_prefixes_and_secret_patterns(
    tmp_path: Path,
    mutation: str,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name=f"unsafe-{mutation}")
    pack_dir = paths[0]
    if mutation == "formula":
        _, completed = _complete_one_functional_label(pack_dir)
        labels_path = pack_dir / "functional_role_labels.csv"
        fields, rows = _read_csv_fields_and_rows(labels_path)
        target = next(
            row
            for row in rows
            if (row["group"], row["report_no"]) == (completed["group"], completed["report_no"])
        )
        target["reviewer"] = "=SUM(1,1)"
        _write_csv_rows(labels_path, fields, rows)
    elif mutation == "secret":
        readme = pack_dir / "README.md"
        secret_marker = "api" + "_key=" + "livevalue123456"
        readme.write_text(
            readme.read_text(encoding="utf-8") + secret_marker + "\n",
            encoding="utf-8",
            newline="\n",
        )
    else:
        readme = pack_dir / "README.md"
        readme.write_bytes(readme.read_bytes() + b"\x00")

    result = _validate_generated_pack(paths)

    assert result.status is ReviewGateStatus.INVALID
    expected = {
        "formula": "LABEL_VALUE_INVALID",
        "secret": "POSSIBLE_SECRET",
        "nul": "NUL_BYTE",
    }[mutation]
    assert expected in {issue.code for issue in result.issues}


def test_invalid_result_hides_progress_counts_and_has_sorted_issues(tmp_path: Path) -> None:
    paths = _write_validation_pack(tmp_path, root_name="sorted-invalid")
    pack_dir, source_export, _, _ = paths
    source_lines = source_export.read_text(encoding="utf-8").splitlines()
    source_lines.reverse()
    source_export.write_text(
        "\n".join(source_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    samples_path = pack_dir / "samples.csv"
    sample_fields, sample_rows = _read_csv_fields_and_rows(samples_path)
    sample_rows[0], sample_rows[1] = sample_rows[1], sample_rows[0]
    _write_csv_rows(samples_path, sample_fields, sample_rows)
    labels_path = pack_dir / "functional_role_labels.csv"
    label_fields, label_rows = _read_csv_fields_and_rows(labels_path)
    pending = next(row for row in label_rows if not row["human_verdict"])
    pending["human_verdict"] = HumanRoleVerdict.FUNCTIONAL_CONFIRMED.value
    _write_csv_rows(labels_path, label_fields, label_rows)

    result = _validate_generated_pack(paths)
    sort_keys = [
        (
            issue.line_number if issue.line_number is not None else -1,
            issue.code,
            issue.group or "",
            issue.report_no or "",
            issue.message,
        )
        for issue in result.issues
    ]

    assert result.status is ReviewGateStatus.INVALID
    assert len(result.issues) >= 3
    assert sort_keys == sorted(sort_keys)
    assert result.expected_label_count is not None
    assert result.valid_label_count is None
    assert result.pending_label_count is None
    assert result.summary is None
    assert result.advertising_evidence_status == "NOT_MEASURED"
    assert result.extension_recommendation_status == "BLOCKED"
    assert result.finalized is False


def _products_with_magnesium_general_verdict(
    verdict: MachineRoleVerdict,
) -> tuple[ExtensionReviewProduct, ...]:
    if verdict not in {
        MachineRoleVerdict.PRESENT_NONFUNCTIONAL,
        MachineRoleVerdict.UNVERIFIABLE,
    }:
        raise ValueError("test helper supports only non-positive general verdicts")
    target_report_no = _report_no(IngredientGroup.MAGNESIUM, "V2", 0)
    products: list[ExtensionReviewProduct] = []
    for product in _synthetic_source_products():
        if product.report_no != target_report_no:
            products.append(product)
            continue
        updates = {"primary_function": "일반적인 영양 보충"}
        if verdict is MachineRoleVerdict.PRESENT_NONFUNCTIONAL:
            updates["raw_materials"] = "스테아린산 마그네슘"
        products.append(product.model_copy(update=updates))
    return tuple(products)


def _products_with_zero_magnesium_addressable() -> tuple[ExtensionReviewProduct, ...]:
    return tuple(
        product.model_copy(update={"primary_function": "일반적인 영양 보충"})
        if map_ingredients(product).groups == (IngredientGroup.MAGNESIUM,)
        else product
        for product in _synthetic_source_products()
    )


def _label_values_for_human_verdict(
    sample: dict[str, str],
    verdict: HumanRoleVerdict,
) -> dict[str, str]:
    common = {
        "human_verdict": verdict.value,
        "rule_version": sample["functional_role_rule_version"],
        "review_note": "",
        "reviewer": "synthetic-role-reviewer",
        "reviewed_at_iso8601": "2026-08-30T09:00:00Z",
    }
    if verdict is HumanRoleVerdict.FUNCTIONAL_CONFIRMED:
        return {
            **common,
            "reason_code": FunctionalRoleReasonCode.EXPLICIT_TARGET_FUNCTION.value,
            "evidence_field": RoleEvidenceField.BOTH.value,
            "evidence_excerpt": _both_evidence(
                sample["raw_materials"],
                sample["primary_function"],
            ),
        }
    if verdict is HumanRoleVerdict.PRESENT_NONFUNCTIONAL:
        return {
            **common,
            "reason_code": FunctionalRoleReasonCode.EXPLICIT_NONFUNCTIONAL_ROLE.value,
            "evidence_field": RoleEvidenceField.RAW_MATERIALS.value,
            "evidence_excerpt": sample["raw_materials"],
        }
    if verdict is HumanRoleVerdict.UNCERTAIN:
        return {
            **common,
            "reason_code": FunctionalRoleReasonCode.INSUFFICIENT_LINKAGE.value,
            "evidence_field": RoleEvidenceField.NONE.value,
            "evidence_excerpt": "",
        }
    raise ValueError("mapping exclusions are inherited, not synthetic human overrides")


def _complete_metric_labels(
    pack_dir: Path,
    *,
    overrides: dict[tuple[str, str], HumanRoleVerdict] | None = None,
) -> None:
    _, sample_rows = _read_csv_fields_and_rows(pack_dir / "samples.csv")
    label_fields, label_rows = _read_csv_fields_and_rows(pack_dir / "functional_role_labels.csv")
    samples_by_key = {(row["group"], row["report_no"]): row for row in sample_rows}
    overrides = overrides or {}
    default_human_verdict = {
        MachineRoleVerdict.FUNCTIONAL_CONFIRMED.value: HumanRoleVerdict.FUNCTIONAL_CONFIRMED,
        MachineRoleVerdict.PRESENT_NONFUNCTIONAL.value: HumanRoleVerdict.PRESENT_NONFUNCTIONAL,
        MachineRoleVerdict.UNVERIFIABLE.value: HumanRoleVerdict.UNCERTAIN,
    }
    for label in label_rows:
        if label["human_verdict"]:
            continue
        key = (label["group"], label["report_no"])
        sample = samples_by_key[key]
        verdict = overrides.get(
            key,
            default_human_verdict[sample["machine_verdict"]],
        )
        label.update(_label_values_for_human_verdict(sample, verdict))
    _write_csv_rows(
        pack_dir / "functional_role_labels.csv",
        label_fields,
        label_rows,
    )


def _complete_and_validate(
    paths: tuple[Path, Path, Path, Path],
    *,
    overrides: dict[tuple[str, str], HumanRoleVerdict] | None = None,
) -> FunctionalRoleValidationResult:
    _complete_metric_labels(paths[0], overrides=overrides)
    return _validate_generated_pack(paths)


def _group_result(
    result: FunctionalRoleValidationResult,
    group: IngredientGroup,
) -> FunctionalRoleGroupSummary:
    assert result.summary is not None
    return next(item for item in result.summary.groups if item.group is group)


def _positive_only_sample(pack_dir: Path, group: IngredientGroup) -> dict[str, str]:
    return next(
        row
        for row in _read_csv(pack_dir / "samples.csv")
        if row["group"] == group.value
        and row["is_positive_audit"] == "True"
        and row["is_general_audit"] == "False"
    )


def test_wilson_35_of_35_lower_is_09010990076755959() -> None:
    interval = wilson_interval(35, 35)

    assert interval is not None
    assert interval.lower == pytest.approx(0.9010990076755959)


def test_all_clean_complete_groups_are_role_eligible(tmp_path: Path) -> None:
    paths = _write_validation_pack(tmp_path, root_name="metrics-all-clean")

    result = _complete_and_validate(paths)

    assert result.status is ReviewGateStatus.COMPLETE
    assert result.issues == ()
    assert result.summary is not None
    assert result.summary.audited_row_count == result.expected_label_count
    for group in result.summary.groups:
        assert group.eligibility is RoleEligibility.ROLE_ELIGIBLE
        assert group.eligibility_reasons == ()
        assert group.general_evaluable_count == 20
        assert group.positive_pool_count == 40
        assert group.positive_sample_count == 35
        assert group.true_functional_confirmed_count == 35
        assert group.positive_precision == 1.0
        assert group.positive_precision_wilson_95 is not None
        assert group.positive_precision_wilson_95.lower >= 0.90


def test_pack_can_be_complete_with_a_role_insufficient_group(tmp_path: Path) -> None:
    products = _synthetic_source_products(magnesium_positive_count=34)
    paths = _write_validation_pack(
        tmp_path,
        root_name="metrics-complete-insufficient",
        source_products=products,
    )

    result = _complete_and_validate(paths)

    assert result.status is ReviewGateStatus.COMPLETE
    magnesium = _group_result(result, IngredientGroup.MAGNESIUM)
    assert magnesium.eligibility is RoleEligibility.ROLE_INSUFFICIENT
    assert all(
        group.eligibility is RoleEligibility.ROLE_ELIGIBLE
        for group in result.summary.groups
        if group.group is not IngredientGroup.MAGNESIUM
    )


def test_positive_pool_or_sample_below_35_is_insufficient(tmp_path: Path) -> None:
    products = _synthetic_source_products(magnesium_positive_count=34)
    paths = _write_validation_pack(
        tmp_path,
        root_name="metrics-small-positive-pool",
        source_products=products,
    )

    result = _complete_and_validate(paths)
    magnesium = _group_result(result, IngredientGroup.MAGNESIUM)

    assert magnesium.positive_pool_count == 34
    assert magnesium.positive_sample_count == 34
    assert magnesium.positive_precision == 1.0
    assert magnesium.positive_precision_wilson_95 is not None
    assert magnesium.positive_precision_wilson_95.lower < 0.90
    assert {
        EligibilityReasonCode.POSITIVE_POOL_TOO_SMALL,
        EligibilityReasonCode.POSITIVE_SAMPLE_TOO_SMALL,
        EligibilityReasonCode.POSITIVE_WILSON_BELOW_THRESHOLD,
    }.issubset(magnesium.eligibility_reasons)


def test_one_false_confirmation_is_insufficient(tmp_path: Path) -> None:
    paths = _write_validation_pack(tmp_path, root_name="metrics-false-confirmation")
    target = _positive_only_sample(paths[0], IngredientGroup.MAGNESIUM)
    result = _complete_and_validate(
        paths,
        overrides={(target["group"], target["report_no"]): HumanRoleVerdict.PRESENT_NONFUNCTIONAL},
    )
    magnesium = _group_result(result, IngredientGroup.MAGNESIUM)

    assert magnesium.false_confirmation_count == 1
    assert magnesium.true_functional_confirmed_count == 34
    assert magnesium.positive_precision == pytest.approx(34 / 35)
    assert EligibilityReasonCode.FALSE_CONFIRMATION in magnesium.eligibility_reasons
    assert magnesium.eligibility is RoleEligibility.ROLE_INSUFFICIENT


def test_one_false_exclusion_is_insufficient(tmp_path: Path) -> None:
    products = _products_with_magnesium_general_verdict(MachineRoleVerdict.PRESENT_NONFUNCTIONAL)
    paths = _write_validation_pack(
        tmp_path,
        root_name="metrics-false-exclusion",
        source_products=products,
    )
    target = next(
        row
        for row in _read_csv(paths[0] / "samples.csv")
        if row["group"] == IngredientGroup.MAGNESIUM.value
        and row["machine_verdict"] == MachineRoleVerdict.PRESENT_NONFUNCTIONAL.value
    )
    result = _complete_and_validate(
        paths,
        overrides={(target["group"], target["report_no"]): HumanRoleVerdict.FUNCTIONAL_CONFIRMED},
    )
    magnesium = _group_result(result, IngredientGroup.MAGNESIUM)

    assert magnesium.false_exclusion_count == 1
    assert EligibilityReasonCode.FALSE_EXCLUSION in magnesium.eligibility_reasons
    assert EligibilityReasonCode.GENERAL_AUDIT_CONFLICT in magnesium.eligibility_reasons
    assert magnesium.eligibility is RoleEligibility.ROLE_INSUFFICIENT


def test_one_unresolved_positive_is_insufficient(tmp_path: Path) -> None:
    paths = _write_validation_pack(tmp_path, root_name="metrics-unresolved-positive")
    target = _positive_only_sample(paths[0], IngredientGroup.MAGNESIUM)
    result = _complete_and_validate(
        paths,
        overrides={(target["group"], target["report_no"]): HumanRoleVerdict.UNCERTAIN},
    )
    magnesium = _group_result(result, IngredientGroup.MAGNESIUM)

    assert magnesium.unresolved_positive_count == 1
    assert magnesium.false_confirmation_count == 0
    assert EligibilityReasonCode.UNRESOLVED_POSITIVE in magnesium.eligibility_reasons
    assert magnesium.eligibility is RoleEligibility.ROLE_INSUFFICIENT


def test_one_overconfident_machine_decision_is_insufficient(tmp_path: Path) -> None:
    products = _products_with_magnesium_general_verdict(MachineRoleVerdict.PRESENT_NONFUNCTIONAL)
    paths = _write_validation_pack(
        tmp_path,
        root_name="metrics-overconfident",
        source_products=products,
    )
    target = next(
        row
        for row in _read_csv(paths[0] / "samples.csv")
        if row["group"] == IngredientGroup.MAGNESIUM.value
        and row["machine_verdict"] == MachineRoleVerdict.PRESENT_NONFUNCTIONAL.value
    )
    result = _complete_and_validate(
        paths,
        overrides={(target["group"], target["report_no"]): HumanRoleVerdict.UNCERTAIN},
    )
    magnesium = _group_result(result, IngredientGroup.MAGNESIUM)

    assert magnesium.overconfident_decision_count == 1
    assert magnesium.unresolved_positive_count == 0
    assert magnesium.false_exclusion_count == 0
    assert EligibilityReasonCode.OVERCONFIDENT_DECISION in magnesium.eligibility_reasons
    assert magnesium.eligibility is RoleEligibility.ROLE_INSUFFICIENT


def test_general_audit_conflict_is_insufficient_even_outside_positive_scope(
    tmp_path: Path,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="metrics-general-conflict")
    target = next(
        row
        for row in _read_csv(paths[0] / "samples.csv")
        if row["group"] == IngredientGroup.MAGNESIUM.value
        and row["is_general_audit"] == "True"
        and row["is_positive_audit"] == "False"
        and row["machine_verdict"] == MachineRoleVerdict.FUNCTIONAL_CONFIRMED.value
    )
    result = _complete_and_validate(
        paths,
        overrides={(target["group"], target["report_no"]): HumanRoleVerdict.PRESENT_NONFUNCTIONAL},
    )
    magnesium = _group_result(result, IngredientGroup.MAGNESIUM)

    assert magnesium.false_confirmation_count == 0
    assert magnesium.positive_precision == 1.0
    assert magnesium.positive_precision_wilson_95 is not None
    assert magnesium.positive_precision_wilson_95.lower >= 0.90
    assert magnesium.eligibility_reasons == (EligibilityReasonCode.GENERAL_AUDIT_CONFLICT,)


def test_wilson_lower_below_point_nine_is_insufficient(tmp_path: Path) -> None:
    paths = _write_validation_pack(tmp_path, root_name="metrics-wilson-below")
    target = _positive_only_sample(paths[0], IngredientGroup.VITAMIN_D)
    result = _complete_and_validate(
        paths,
        overrides={(target["group"], target["report_no"]): HumanRoleVerdict.PRESENT_NONFUNCTIONAL},
    )
    vitamin_d = _group_result(result, IngredientGroup.VITAMIN_D)

    assert vitamin_d.positive_precision_wilson_95 is not None
    assert vitamin_d.positive_precision_wilson_95.lower < 0.90
    assert EligibilityReasonCode.POSITIVE_WILSON_BELOW_THRESHOLD in vitamin_d.eligibility_reasons
    assert vitamin_d.eligibility is RoleEligibility.ROLE_INSUFFICIENT


def test_zero_addressable_products_is_insufficient(tmp_path: Path) -> None:
    paths = _write_validation_pack(
        tmp_path,
        root_name="metrics-zero-addressable",
        source_products=_products_with_zero_magnesium_addressable(),
    )

    result = _complete_and_validate(paths)
    magnesium = _group_result(result, IngredientGroup.MAGNESIUM)

    assert result.status is ReviewGateStatus.COMPLETE
    assert magnesium.addressable_product_count == 0
    assert magnesium.positive_pool_count == 0
    assert magnesium.positive_sample_count == 0
    assert magnesium.positive_precision is None
    assert magnesium.positive_precision_wilson_95 is None
    assert magnesium.decidable_agreement_rate is None
    assert magnesium.decision_coverage == 0.0
    assert magnesium.unverifiable_rate == 1.0
    assert magnesium.human_uncertainty_rate == 1.0
    assert EligibilityReasonCode.NO_ADDRESSABLE_PRODUCTS in magnesium.eligibility_reasons
    assert magnesium.eligibility is RoleEligibility.ROLE_INSUFFICIENT


def test_avoidable_unverifiable_reduces_coverage_without_becoming_false_positive(
    tmp_path: Path,
) -> None:
    products = _products_with_magnesium_general_verdict(MachineRoleVerdict.UNVERIFIABLE)
    paths = _write_validation_pack(
        tmp_path,
        root_name="metrics-avoidable-unverifiable",
        source_products=products,
    )
    target = next(
        row
        for row in _read_csv(paths[0] / "samples.csv")
        if row["group"] == IngredientGroup.MAGNESIUM.value
        and row["machine_verdict"] == MachineRoleVerdict.UNVERIFIABLE.value
    )
    result = _complete_and_validate(
        paths,
        overrides={(target["group"], target["report_no"]): HumanRoleVerdict.FUNCTIONAL_CONFIRMED},
    )
    magnesium = _group_result(result, IngredientGroup.MAGNESIUM)

    assert magnesium.avoidable_unverifiable_count == 1
    assert magnesium.false_confirmation_count == 0
    assert magnesium.false_exclusion_count == 0
    assert magnesium.decision_coverage == pytest.approx(
        (magnesium.audited_row_count - 1) / magnesium.audited_row_count
    )
    assert magnesium.eligibility is RoleEligibility.ROLE_ELIGIBLE


def test_uncertain_is_reported_separately_from_incorrect(tmp_path: Path) -> None:
    paths = _write_validation_pack(tmp_path, root_name="metrics-uncertainty-separated")
    target = _positive_only_sample(paths[0], IngredientGroup.COENZYME_Q10)
    result = _complete_and_validate(
        paths,
        overrides={(target["group"], target["report_no"]): HumanRoleVerdict.UNCERTAIN},
    )
    group = _group_result(result, IngredientGroup.COENZYME_Q10)
    uncertain_cell = next(
        cell
        for cell in group.confusion_matrix
        if cell.machine_verdict is MachineRoleVerdict.FUNCTIONAL_CONFIRMED
        and cell.human_verdict is HumanRoleVerdict.UNCERTAIN
    )

    assert uncertain_cell.row_count == 1
    assert group.human_uncertainty_rate == pytest.approx(1 / group.audited_row_count)
    assert group.unresolved_positive_count == 1
    assert group.false_confirmation_count == 0


def test_excluded_mapping_errors_are_not_metric_denominators(tmp_path: Path) -> None:
    paths = _write_validation_pack(tmp_path, root_name="metrics-excluded-denominator")

    result = _complete_and_validate(paths)
    red_ginseng = _group_result(result, IngredientGroup.RED_GINSENG)
    group_label_count = sum(
        row["group"] == IngredientGroup.RED_GINSENG.value
        for row in _read_csv(paths[0] / "functional_role_labels.csv")
    )

    assert red_ginseng.audited_row_count == group_label_count
    assert red_ginseng.general_evaluable_count == 20
    assert (
        sum(
            cell.row_count
            for cell in red_ginseng.confusion_matrix
            if cell.human_verdict is HumanRoleVerdict.EXCLUDED_MAPPING_ERROR
        )
        == 1
    )
    assert sum(cell.row_count for cell in red_ginseng.confusion_matrix) == (
        red_ginseng.audited_row_count
    )
    samples_by_key = {
        (row["group"], row["report_no"]): row for row in _read_csv(paths[0] / "samples.csv")
    }
    evaluable_labels = [
        row
        for row in _read_csv(paths[0] / "functional_role_labels.csv")
        if row["group"] == IngredientGroup.RED_GINSENG.value
        and row["human_verdict"] != HumanRoleVerdict.EXCLUDED_MAPPING_ERROR.value
    ]
    decisive_count = sum(
        samples_by_key[(row["group"], row["report_no"])]["machine_verdict"]
        in {
            MachineRoleVerdict.FUNCTIONAL_CONFIRMED.value,
            MachineRoleVerdict.PRESENT_NONFUNCTIONAL.value,
        }
        for row in evaluable_labels
    )
    unverifiable_count = len(evaluable_labels) - decisive_count
    uncertain_count = sum(
        row["human_verdict"] == HumanRoleVerdict.UNCERTAIN.value for row in evaluable_labels
    )
    assert red_ginseng.decision_coverage == pytest.approx(decisive_count / len(evaluable_labels))
    assert red_ginseng.unverifiable_rate == pytest.approx(
        unverifiable_count / len(evaluable_labels)
    )
    assert red_ginseng.human_uncertainty_rate == pytest.approx(
        uncertain_count / len(evaluable_labels)
    )


def test_summary_contains_no_product_names_raw_text_excerpts_notes_or_reviewer_ids(
    tmp_path: Path,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="metrics-redacted-summary")

    result = _complete_and_validate(paths)

    assert result.status is ReviewGateStatus.COMPLETE
    assert result.summary is not None
    assert result.summary.functional_role_labels_sha256 == sha256_file(
        paths[0] / "functional_role_labels.csv"
    )
    values = result.summary.model_dump(mode="json")
    serialized = result.summary.model_dump_json()
    forbidden_fields = {
        "name",
        "company",
        "primary_function",
        "raw_materials",
        "intake_method",
        "evidence_excerpt",
        "review_note",
        "reviewer",
        "reviewed_at_iso8601",
        "reason_code",
        "report_no",
    }

    def all_keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | set().union(*(all_keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(all_keys(item) for item in value))
        return set()

    assert forbidden_fields.isdisjoint(all_keys(values))
    for forbidden_text in (
        "합성 감사 제품",
        "합성 제조사",
        "밀크씨슬추출물",
        "간 건강에 도움을 줄 수 있음",
        "synthetic-role-reviewer",
        "synthetic-reviewer",
        "Inherited c003-product-review-v2 mapping verdict",
    ):
        assert forbidden_text not in serialized


def _functional_validate_cli_args(
    paths: tuple[Path, Path, Path, Path],
    *,
    summary_output: Path | None = None,
) -> list[str]:
    pack_dir, source_export, product_review_pack, rules_path = paths
    argv = [
        "--pack-dir",
        str(pack_dir),
        "--source-export",
        str(source_export),
        "--product-review-pack",
        str(product_review_pack),
        "--rules",
        str(rules_path),
    ]
    if summary_output is not None:
        argv.extend(("--summary-output", str(summary_output)))
    return argv


def test_validate_cli_exit_codes_are_complete_zero_pending_two_invalid_three(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    complete_paths = _write_validation_pack(tmp_path, root_name="cli-exit-complete")
    _complete_metric_labels(complete_paths[0])
    pending_paths = _write_validation_pack(tmp_path, root_name="cli-exit-pending")
    invalid_paths = _write_validation_pack(tmp_path, root_name="cli-exit-invalid")
    (invalid_paths[0] / "unexpected.txt").write_text(
        "unexpected\n",
        encoding="utf-8",
        newline="\n",
    )

    for paths, expected_exit, expected_status in (
        (complete_paths, 0, ReviewGateStatus.COMPLETE),
        (pending_paths, 2, ReviewGateStatus.PENDING),
        (invalid_paths, 3, ReviewGateStatus.INVALID),
    ):
        exit_code = validate_functional_review_main(
            _functional_validate_cli_args(paths),
            validated_at=NOW,
        )
        payload = json.loads(capsys.readouterr().out)
        assert exit_code == expected_exit
        assert payload["status"] == expected_status.value


def test_validate_cli_prints_the_exact_result_as_sorted_utf8_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="cli-exact-json")
    expected_result = _validate_generated_pack(paths)
    expected = (
        json.dumps(
            expected_result.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    exit_code = validate_functional_review_main(
        _functional_validate_cli_args(paths),
        validated_at=NOW,
    )
    stdout = capsys.readouterr().out

    assert exit_code == 2
    assert stdout == expected
    assert stdout.endswith("\n") and not stdout.endswith("\n\n")
    assert stdout.encode("utf-8").decode("utf-8") == stdout


def test_validate_cli_writes_summary_only_for_complete(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="cli-write-complete")
    _complete_metric_labels(paths[0])
    output = tmp_path / "published" / "functional-role-summary.json"

    exit_code = validate_functional_review_main(
        _functional_validate_cli_args(paths, summary_output=output),
        validated_at=NOW,
    )
    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert output.read_text(encoding="utf-8") == stdout
    assert json.loads(stdout)["status"] == ReviewGateStatus.COMPLETE.value


def test_pending_or_invalid_does_not_create_or_overwrite_summary_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pending_paths = _write_validation_pack(tmp_path, root_name="cli-preserve-pending")
    invalid_paths = _write_validation_pack(tmp_path, root_name="cli-preserve-invalid")
    (invalid_paths[0] / "unexpected.txt").write_text(
        "unexpected\n",
        encoding="utf-8",
        newline="\n",
    )
    output = tmp_path / "existing-summary.json"
    sentinel = b"PREEXISTING-SUMMARY-MUST-SURVIVE\r\n"
    output.write_bytes(sentinel)

    for paths, expected_exit in ((pending_paths, 2), (invalid_paths, 3)):
        exit_code = validate_functional_review_main(
            _functional_validate_cli_args(paths, summary_output=output),
            validated_at=NOW,
        )
        capsys.readouterr()
        assert exit_code == expected_exit
        assert output.read_bytes() == sentinel
        assert list(tmp_path.glob(".existing-summary.json.*.tmp")) == []


def test_complete_summary_replaces_atomically_and_leaves_no_temp_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="cli-atomic-complete")
    _complete_metric_labels(paths[0])
    output = tmp_path / "atomic-summary.json"
    sentinel = b"OLD-SUMMARY\n"
    output.write_bytes(sentinel)
    observed: list[tuple[Path, Path]] = []
    real_replace = validate_functional_review_module.os.replace

    def record_replace(source: Path, destination: Path) -> None:
        observed.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(validate_functional_review_module.os, "replace", record_replace)

    exit_code = validate_functional_review_main(
        _functional_validate_cli_args(paths, summary_output=output),
        validated_at=NOW,
    )
    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert output.read_bytes() != sentinel
    assert output.read_text(encoding="utf-8") == stdout
    assert len(observed) == 1
    temporary, destination = observed[0]
    assert destination == output
    assert temporary.parent == output.parent
    assert temporary.name.startswith(f".{output.name}.")
    assert temporary.name.endswith(".tmp")
    temporary_token = temporary.name.removeprefix(f".{output.name}.").removesuffix(".tmp")
    assert len(temporary_token) == 32
    assert all(character in "0123456789abcdef" for character in temporary_token)
    assert not temporary.exists()
    assert list(tmp_path.glob(".atomic-summary.json.*.tmp")) == []


def test_write_failure_cleans_the_temp_file_and_preserves_previous_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="cli-write-failure")
    _complete_metric_labels(paths[0])
    output = tmp_path / "preserved-summary.json"
    sentinel = b"KEEP-THIS-EXACT-SUMMARY\r\n"
    output.write_bytes(sentinel)
    original_write_text = Path.write_text

    def fail_temporary_write(
        path: Path,
        data: str,
        *args: object,
        **kwargs: object,
    ) -> int:
        if path.parent == output.parent and path.name.startswith(f".{output.name}."):
            path.write_bytes(b"partial temporary data")
            raise OSError("synthetic temporary write failure")
        return original_write_text(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_temporary_write)

    with pytest.raises(OSError, match="synthetic temporary write failure"):
        validate_functional_review_main(
            _functional_validate_cli_args(paths, summary_output=output),
            validated_at=NOW,
        )

    assert output.read_bytes() == sentinel
    assert list(tmp_path.glob(".preserved-summary.json.*.tmp")) == []


def test_replace_failure_cleans_the_temp_file_and_preserves_previous_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="cli-replace-failure")
    _complete_metric_labels(paths[0])
    output = tmp_path / "replace-preserved-summary.json"
    sentinel = b"KEEP-THIS-WHEN-REPLACE-FAILS\r\n"
    output.write_bytes(sentinel)

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError(f"synthetic replace failure: {Path(source).name}")

    monkeypatch.setattr(validate_functional_review_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="synthetic replace failure"):
        validate_functional_review_main(
            _functional_validate_cli_args(paths, summary_output=output),
            validated_at=NOW,
        )

    assert output.read_bytes() == sentinel
    assert list(tmp_path.glob(".replace-preserved-summary.json.*.tmp")) == []


def test_cli_summary_contains_no_product_text_excerpt_note_or_reviewer(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_validation_pack(tmp_path, root_name="cli-redacted-summary")
    _complete_metric_labels(paths[0])
    output = tmp_path / "redacted-summary.json"

    exit_code = validate_functional_review_main(
        _functional_validate_cli_args(paths, summary_output=output),
        validated_at=NOW,
    )
    stdout = capsys.readouterr().out
    payload = json.loads(output.read_text(encoding="utf-8"))

    forbidden_fields = {
        "name",
        "company",
        "primary_function",
        "raw_materials",
        "intake_method",
        "evidence_excerpt",
        "review_note",
        "reviewer",
        "reviewed_at_iso8601",
        "reason_code",
        "report_no",
    }

    def all_keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | set().union(*(all_keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(all_keys(item) for item in value))
        return set()

    assert exit_code == 0
    assert stdout == output.read_text(encoding="utf-8")
    assert forbidden_fields.isdisjoint(all_keys(payload))
    for forbidden_text in (
        "합성 감사 제품",
        "합성 제조사",
        "밀크씨슬추출물",
        "간 건강에 도움을 줄 수 있음",
        "synthetic-role-reviewer",
        "synthetic-reviewer",
        "Inherited c003-product-review-v2 mapping verdict",
    ):
        assert forbidden_text not in stdout


@pytest.mark.parametrize(
    "protected_target",
    ("functional-pack", "product-review-pack", "source-export", "rules"),
)
def test_cli_refuses_summary_output_that_overlaps_any_validation_input(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    protected_target: str,
) -> None:
    paths = _write_validation_pack(
        tmp_path,
        root_name=f"cli-protected-{protected_target}",
    )
    _complete_metric_labels(paths[0])
    pack_dir, source_export, product_review_pack, rules_path = paths
    summary_output = {
        "functional-pack": pack_dir / "published-summary.json",
        "product-review-pack": product_review_pack / "published-summary.json",
        "source-export": source_export,
        "rules": rules_path,
    }[protected_target]
    pack_snapshot = {
        path.relative_to(pack_dir): path.read_bytes()
        for path in pack_dir.rglob("*")
        if path.is_file()
    }
    product_review_snapshot = {
        path.relative_to(product_review_pack): path.read_bytes()
        for path in product_review_pack.rglob("*")
        if path.is_file()
    }
    source_snapshot = source_export.read_bytes()
    rules_snapshot = rules_path.read_bytes()

    with pytest.raises(ValueError, match="must not overwrite validation inputs"):
        validate_functional_review_main(
            _functional_validate_cli_args(paths, summary_output=summary_output),
            validated_at=NOW,
        )

    assert capsys.readouterr().out == ""
    assert {
        path.relative_to(pack_dir): path.read_bytes()
        for path in pack_dir.rglob("*")
        if path.is_file()
    } == pack_snapshot
    assert {
        path.relative_to(product_review_pack): path.read_bytes()
        for path in product_review_pack.rglob("*")
        if path.is_file()
    } == product_review_snapshot
    assert source_export.read_bytes() == source_snapshot
    assert rules_path.read_bytes() == rules_snapshot


def test_noncomplete_status_never_enters_overlapping_summary_write_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pending_paths = _write_validation_pack(
        tmp_path,
        root_name="cli-overlap-pending",
    )
    invalid_paths = _write_validation_pack(
        tmp_path,
        root_name="cli-overlap-invalid",
    )
    (invalid_paths[0] / "unexpected.txt").write_text(
        "unexpected\n",
        encoding="utf-8",
        newline="\n",
    )

    for paths, expected_exit, expected_status in (
        (pending_paths, 2, ReviewGateStatus.PENDING),
        (invalid_paths, 3, ReviewGateStatus.INVALID),
    ):
        protected_output = paths[0] / "must-not-be-created.json"
        original_files = {path.name for path in paths[0].iterdir()}
        exit_code = validate_functional_review_main(
            _functional_validate_cli_args(paths, summary_output=protected_output),
            validated_at=NOW,
        )
        payload = json.loads(capsys.readouterr().out)
        assert exit_code == expected_exit
        assert payload["status"] == expected_status.value
        assert not protected_output.exists()
        assert {path.name for path in paths[0].iterdir()} == original_files
