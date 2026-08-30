import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from claimledger.domain import ExtensionReviewProduct, IngredientGroup
from claimledger.extension_selection import COMPARISON_GROUPS
from claimledger.functional_role import (
    FunctionalRoleRuleRegistry,
    MachineRoleReasonCode,
    MachineRoleVerdict,
    RoleEvidenceField,
    classify_functional_role,
    load_functional_role_registry,
)

NOW = datetime(2026, 8, 30, tzinfo=UTC)
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "functional_role_rules.json"


def _fixture_data() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _write_registry(tmp_path: Path, data: dict[str, object]) -> Path:
    path = tmp_path / "functional-role-rules.json"
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _load(tmp_path: Path, data: dict[str, object]) -> FunctionalRoleRuleRegistry:
    return load_functional_role_registry(_write_registry(tmp_path, data), evaluated_at=NOW)


def _registry() -> FunctionalRoleRuleRegistry:
    return load_functional_role_registry(FIXTURE_PATH, evaluated_at=NOW)


def _registry_with_rule_changes(
    group: IngredientGroup,
    **changes: object,
) -> FunctionalRoleRuleRegistry:
    data = _fixture_data()
    rules = data["rules"]
    assert isinstance(rules, list)
    matching_rules = [rule for rule in rules if rule["group"] == group.value]
    assert len(matching_rules) == 1
    matching_rules[0].update(changes)
    return FunctionalRoleRuleRegistry.model_validate(data)


def _product(
    *,
    report_no: str,
    raw_materials: str,
    primary_function: str,
    name: str = "합성 테스트 제품",
) -> ExtensionReviewProduct:
    return ExtensionReviewProduct(
        report_no=report_no,
        name=name,
        company="합성 테스트 회사",
        primary_function=primary_function,
        raw_materials=raw_materials,
        intake_method="물과 함께 섭취",
    )


def test_load_functional_role_registry_accepts_exact_current_five_group_contract() -> None:
    registry = load_functional_role_registry(FIXTURE_PATH, evaluated_at=NOW)

    assert registry.contract_version == "functional-role-rules-v1"
    assert tuple(rule.group for rule in registry.rules) == COMPARISON_GROUPS
    assert all(rule.status.value == "active" for rule in registry.rules)
    assert all(rule.content_sha256.isupper() for rule in registry.rules)
    with pytest.raises(ValueError):
        registry.rules[0].source_id = "mutated"


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "reordered"])
def test_registry_rejects_a_missing_or_duplicate_comparison_group(
    tmp_path: Path,
    mutation: str,
) -> None:
    data = _fixture_data()
    rules = data["rules"]
    assert isinstance(rules, list)
    if mutation == "missing":
        rules.pop()
    elif mutation == "duplicate":
        rules[-1]["group"] = "milk_thistle"
    else:
        rules.reverse()

    with pytest.raises(ValueError):
        _load(tmp_path, data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "proposed"),
        ("status", "expired"),
        ("effective_to", "2026-08-29"),
        ("effective_from", "2026-08-31"),
    ],
)
def test_registry_rejects_proposed_expired_or_not_yet_effective_rules(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    data = _fixture_data()
    rules = data["rules"]
    assert isinstance(rules, list)
    rules[0][field] = value

    with pytest.raises(ValueError):
        _load(tmp_path, data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("verified_current_at", "2026-08-22T23:59:59Z"),
        ("verified_current_at", "2026-08-30T00:00:01Z"),
    ],
)
def test_registry_rejects_stale_or_future_verification_times(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    data = _fixture_data()
    rules = data["rules"]
    assert isinstance(rules, list)
    rules[0][field] = value

    with pytest.raises(ValueError):
        _load(tmp_path, data)


@pytest.mark.parametrize(
    "source_url",
    [
        "ftp://www.mfds.go.kr/synthetic-fixture/rule",
        "https://mfds.go.kr.attacker.example/synthetic-fixture/rule",
        "https://user:password@www.mfds.go.kr/synthetic-fixture/rule",
        "https://www.mfds.go.kr/synthetic-fixture/rule#fragment",
        "https://www.mfds.go.kr:not-a-port/synthetic-fixture/rule",
        "https://example.test/synthetic-fixture/rule",
    ],
)
def test_registry_rejects_non_official_or_non_http_sources(
    tmp_path: Path,
    source_url: str,
) -> None:
    data = _fixture_data()
    rules = data["rules"]
    assert isinstance(rules, list)
    rules[0]["source_url"] = source_url

    with pytest.raises(ValueError):
        _load(tmp_path, data)


@pytest.mark.parametrize("content_sha256", ["a" * 64, "A" * 63, "G" * 64])
def test_registry_rejects_lowercase_or_non_sha256_content_hashes(
    tmp_path: Path,
    content_sha256: str,
) -> None:
    data = _fixture_data()
    rules = data["rules"]
    assert isinstance(rules, list)
    rules[0]["content_sha256"] = content_sha256

    with pytest.raises(ValueError):
        _load(tmp_path, data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("accepted_functional_forms", []),
        ("recognized_function_texts", []),
        ("accepted_functional_forms", ["홍삼농축액", "  가  "]),
        ("accepted_functional_forms", ["홍삼농축액", "가"]),
        ("recognized_function_texts", ["간 건강", "간   건강"]),
        ("recognized_function_texts", ["간 건강", "간 건강"]),
    ],
)
def test_registry_rejects_empty_unsorted_or_duplicate_phrase_lists(
    tmp_path: Path,
    field: str,
    value: list[str],
) -> None:
    data = _fixture_data()
    rules = data["rules"]
    assert isinstance(rules, list)
    rules[0][field] = value

    with pytest.raises(ValueError):
        _load(tmp_path, data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_id", '=HYPERLINK("bad")'),
        ("source_id", "  =HYPERLINK(bad)"),
        ("canonical_ingredient", "+SUM(1,1)"),
        ("source_locator", "api_key=live-secret-value-123456"),
        ("source_locator", "FOOD_SAFETY_API_KEY"),
        ("extracted_by", "sk-proj-abcdefghijklmnop"),
    ],
)
def test_registry_rejects_formula_prefixes_and_secret_patterns(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    data = _fixture_data()
    rules = data["rules"]
    assert isinstance(rules, list)
    rules[0][field] = value

    with pytest.raises(ValueError):
        _load(tmp_path, data)


def test_loader_redacts_rejected_registry_input_from_validation_errors(tmp_path: Path) -> None:
    sentinel = "api_key=SHOULD_NOT_ECHO_12345"
    data = _fixture_data()
    rules = data["rules"]
    assert isinstance(rules, list)
    rules[0]["source_locator"] = sentinel

    with pytest.raises(ValidationError) as error:
        _load(tmp_path, data)

    leaked = sentinel in str(error.value)
    assert not leaked, "validation error echoed rejected source locator"


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        ("extra_rule", "unused"),
        ("extra_registry", "unused"),
        ("naive_datetime", "retrieved_at"),
        ("naive_evaluated_at", ""),
    ],
)
def test_registry_rejects_extra_fields_and_naive_datetimes(
    tmp_path: Path,
    mutation: str,
    field: str,
) -> None:
    data = copy.deepcopy(_fixture_data())
    rules = data["rules"]
    assert isinstance(rules, list)
    if mutation == "extra_rule":
        rules[0][field] = "not allowed"
    elif mutation == "extra_registry":
        data[field] = "not allowed"
    elif mutation == "naive_datetime":
        rules[0][field] = "2026-08-30T00:00:00"
    else:
        with pytest.raises(ValueError):
            load_functional_role_registry(
                _write_registry(tmp_path, data),
                evaluated_at=datetime(2026, 8, 30),  # noqa: DTZ001
            )
        return

    with pytest.raises(ValidationError):
        _load(tmp_path, data)


def test_classifier_confirms_a_single_target_form_with_its_recognized_function() -> None:
    decision = classify_functional_role(
        _product(
            report_no="ROLE-001",
            raw_materials="정제수, 밀크씨슬추출물, 기타 원료",
            primary_function="간 건강에 도움을 줄 수 있음",
        ),
        IngredientGroup.MILK_THISTLE,
        _registry(),
    )

    assert decision.verdict is MachineRoleVerdict.FUNCTIONAL_CONFIRMED
    assert decision.reason_code is MachineRoleReasonCode.FUNCTION_AND_FORM_LINKED
    assert decision.evidence_field is RoleEvidenceField.BOTH
    assert decision.matched_functional_form == "밀크씨슬추출물"
    assert decision.matched_function_text == "간 건강"
    assert decision.matched_nonfunctional_form == ""


def test_classifier_does_not_use_product_name_as_role_evidence() -> None:
    decision = classify_functional_role(
        _product(
            report_no="ROLE-002",
            name="밀크씨슬추출물 간 건강",
            raw_materials="정제수",
            primary_function="간 건강에 도움을 줄 수 있음",
        ),
        IngredientGroup.MILK_THISTLE,
        _registry(),
    )

    assert decision.verdict is MachineRoleVerdict.UNVERIFIABLE
    assert decision.reason_code is MachineRoleReasonCode.FUNCTION_WITHOUT_FORM
    assert decision.evidence_field is RoleEvidenceField.PRIMARY_FUNCTION
    assert decision.matched_functional_form == ""


def test_classifier_returns_unverifiable_for_form_without_function() -> None:
    decision = classify_functional_role(
        _product(
            report_no="ROLE-003",
            raw_materials="밀크씨슬추출물",
            primary_function="일상적인 영양 보충",
        ),
        IngredientGroup.MILK_THISTLE,
        _registry(),
    )

    assert decision.verdict is MachineRoleVerdict.UNVERIFIABLE
    assert decision.reason_code is MachineRoleReasonCode.FORM_WITHOUT_FUNCTION
    assert decision.evidence_field is RoleEvidenceField.RAW_MATERIALS
    assert decision.matched_functional_form == "밀크씨슬추출물"
    assert decision.matched_function_text == ""


def test_classifier_returns_unverifiable_for_function_without_form() -> None:
    decision = classify_functional_role(
        _product(
            report_no="ROLE-004",
            raw_materials="정제수, 기타 원료",
            primary_function="간 건강에 도움을 줄 수 있음",
        ),
        IngredientGroup.MILK_THISTLE,
        _registry(),
    )

    assert decision.verdict is MachineRoleVerdict.UNVERIFIABLE
    assert decision.reason_code is MachineRoleReasonCode.FUNCTION_WITHOUT_FORM
    assert decision.evidence_field is RoleEvidenceField.PRIMARY_FUNCTION
    assert decision.matched_functional_form == ""
    assert decision.matched_function_text == "간 건강"


def test_classifier_returns_unverifiable_for_unlinked_combination_product() -> None:
    decision = classify_functional_role(
        _product(
            report_no="ROLE-005",
            raw_materials="밀크씨슬추출물, 비타민 D",
            primary_function=(
                "비타민 D는 칼슘과 인의 흡수에 도움을 주며 간 건강에도 도움을 줄 수 있음"
            ),
        ),
        IngredientGroup.MILK_THISTLE,
        _registry(),
    )

    assert decision.verdict is MachineRoleVerdict.UNVERIFIABLE
    assert decision.reason_code is MachineRoleReasonCode.COMBINATION_LINKAGE_AMBIGUOUS
    assert decision.evidence_field is RoleEvidenceField.BOTH


@pytest.mark.parametrize("target_wording", ["밀크씨슬", "밀크씨슬추출물"])
def test_classifier_accepts_explicit_target_linkage_in_a_combination_product(
    target_wording: str,
) -> None:
    decision = classify_functional_role(
        _product(
            report_no="ROLE-006",
            raw_materials="밀크씨슬추출물, 비타민 D",
            primary_function=f"{target_wording}은 간 건강에 도움을 줄 수 있음",
        ),
        IngredientGroup.MILK_THISTLE,
        _registry(),
    )

    assert decision.verdict is MachineRoleVerdict.FUNCTIONAL_CONFIRMED
    assert decision.reason_code is MachineRoleReasonCode.FUNCTION_AND_FORM_LINKED
    assert decision.evidence_field is RoleEvidenceField.BOTH


def test_classifier_never_confirms_red_ginseng_flavor_powder() -> None:
    decision = classify_functional_role(
        _product(
            report_no="ROLE-007",
            raw_materials="홍삼향분말",
            primary_function="면역력 증진에 도움을 줄 수 있음",
            name="홍삼 면역 건강",
        ),
        IngredientGroup.RED_GINSENG,
        _registry(),
    )

    assert decision.verdict is MachineRoleVerdict.PRESENT_NONFUNCTIONAL
    assert decision.reason_code is MachineRoleReasonCode.EXPLICIT_NONFUNCTIONAL_FORM
    assert decision.evidence_field is RoleEvidenceField.RAW_MATERIALS
    assert decision.matched_nonfunctional_form == "홍삼향분말"


def test_classifier_marks_an_explicitly_registered_nonfunctional_form() -> None:
    decision = classify_functional_role(
        _product(
            report_no="ROLE-008",
            raw_materials="스테아린산 마그네슘",
            primary_function="",
        ),
        IngredientGroup.MAGNESIUM,
        _registry(),
    )

    assert decision.verdict is MachineRoleVerdict.PRESENT_NONFUNCTIONAL
    assert decision.reason_code is MachineRoleReasonCode.EXPLICIT_NONFUNCTIONAL_FORM
    assert decision.evidence_field is RoleEvidenceField.RAW_MATERIALS
    assert decision.matched_nonfunctional_form == "스테아린산 마그네슘"


def test_classifier_does_not_infer_nonfunctional_role_from_missing_function_text() -> None:
    registry = _registry_with_rule_changes(
        IngredientGroup.MAGNESIUM,
        known_nonfunctional_forms=[],
    )
    decision = classify_functional_role(
        _product(
            report_no="ROLE-009",
            raw_materials="스테아린산 마그네슘",
            primary_function="",
        ),
        IngredientGroup.MAGNESIUM,
        registry,
    )

    assert decision.verdict is MachineRoleVerdict.UNVERIFIABLE
    assert decision.reason_code is MachineRoleReasonCode.NO_APPLICABLE_EVIDENCE
    assert decision.evidence_field is RoleEvidenceField.NONE
    assert decision.matched_nonfunctional_form == ""


def test_classifier_returns_unverifiable_for_conflicting_functional_and_nonfunctional_forms() -> (
    None
):
    decision = classify_functional_role(
        _product(
            report_no="ROLE-010",
            raw_materials="홍삼농축액, 홍삼향분말",
            primary_function="홍삼농축액은 면역력 증진에 도움을 줄 수 있음",
        ),
        IngredientGroup.RED_GINSENG,
        _registry(),
    )

    assert decision.verdict is MachineRoleVerdict.UNVERIFIABLE
    assert decision.reason_code is MachineRoleReasonCode.CONFLICTING_ROLE_EVIDENCE
    assert decision.evidence_field is RoleEvidenceField.BOTH
    assert decision.matched_functional_form == "홍삼농축액"
    assert decision.matched_function_text == "면역력 증진"
    assert decision.matched_nonfunctional_form == "홍삼향분말"


def test_classifier_conflict_without_function_uses_only_raw_material_evidence() -> None:
    decision = classify_functional_role(
        _product(
            report_no="ROLE-010-B",
            raw_materials="홍삼농축액, 홍삼향분말",
            primary_function="홍삼 함유 제품",
        ),
        IngredientGroup.RED_GINSENG,
        _registry(),
    )

    assert decision.verdict is MachineRoleVerdict.UNVERIFIABLE
    assert decision.reason_code is MachineRoleReasonCode.CONFLICTING_ROLE_EVIDENCE
    assert decision.evidence_field is RoleEvidenceField.RAW_MATERIALS
    assert decision.primary_function_excerpt == ""


def test_classifier_preserves_literal_excerpts_and_rule_version() -> None:
    registry = _registry_with_rule_changes(
        IngredientGroup.COENZYME_Q10,
        accepted_functional_forms=["Q10", "코엔자임 Q10"],
        recognized_function_texts=["A효과", "B효과"],
    )
    decision = classify_functional_role(
        _product(
            report_no="ROLE-011",
            raw_materials="정제수, 코엔자임   q10, 코엔자임 Q10, 포도당",
            primary_function="B효과 다음 A효과",
        ),
        IngredientGroup.COENZYME_Q10,
        registry,
    )

    assert decision.verdict is MachineRoleVerdict.FUNCTIONAL_CONFIRMED
    assert decision.raw_materials_excerpt == "코엔자임   q10"
    assert decision.primary_function_excerpt == "A효과"
    assert decision.matched_functional_form == "코엔자임   q10"
    assert decision.matched_function_text == "A효과"
    assert decision.rule_version == "functional-role-rule-v1"


def test_classifier_is_invariant_to_nfkc_case_and_repeated_whitespace() -> None:
    registry = _registry()
    baseline = classify_functional_role(
        _product(
            report_no="ROLE-012-A",
            raw_materials="코엔자임 Q10",
            primary_function="항산화",
        ),
        IngredientGroup.COENZYME_Q10,
        registry,
    )
    variant = classify_functional_role(
        _product(
            report_no="ROLE-012-B",
            raw_materials="코엔자임　　　ｑ１０",
            primary_function="항산화",
        ),
        IngredientGroup.COENZYME_Q10,
        registry,
    )

    assert baseline.verdict is variant.verdict is MachineRoleVerdict.FUNCTIONAL_CONFIRMED
    assert baseline.reason_code is variant.reason_code
    assert baseline.evidence_field is variant.evidence_field
    assert baseline.matched_functional_form == "코엔자임 Q10"
    assert variant.matched_functional_form == "코엔자임　　　ｑ１０"
    assert baseline.rule_version == variant.rule_version


def test_classifier_nfkc_composition_preserves_decomposed_literal_slices() -> None:
    registry = _registry_with_rule_changes(
        IngredientGroup.MILK_THISTLE,
        accepted_functional_forms=["é"],
        recognized_function_texts=["café"],
    )
    raw_literal = "e\N{COMBINING ACUTE ACCENT}"
    function_literal = "CAFE\N{COMBINING ACUTE ACCENT}"
    decision = classify_functional_role(
        _product(
            report_no="ROLE-012-C",
            raw_materials=f"원료: {raw_literal}",
            primary_function=f"기능: {function_literal}",
        ),
        IngredientGroup.MILK_THISTLE,
        registry,
    )

    assert decision.verdict is MachineRoleVerdict.FUNCTIONAL_CONFIRMED
    assert decision.matched_functional_form == raw_literal
    assert decision.matched_function_text == function_literal
    assert decision.raw_materials_excerpt == raw_literal
    assert decision.primary_function_excerpt == function_literal


def test_classifier_rejects_a_non_comparison_group() -> None:
    with pytest.raises(ValueError, match="comparison ingredient group"):
        classify_functional_role(
            _product(
                report_no="ROLE-013",
                raw_materials="루테인",
                primary_function="눈 건강",
            ),
            IngredientGroup.LUTEIN_ZEAXANTHIN,
            _registry(),
        )


@pytest.mark.parametrize(
    ("raw_materials", "primary_function", "expected_reason", "expected_evidence"),
    [
        (
            "밀크씨슬추출물, 간 건강",
            "일상적인 영양 보충",
            MachineRoleReasonCode.FORM_WITHOUT_FUNCTION,
            RoleEvidenceField.RAW_MATERIALS,
        ),
        (
            "정제수",
            "밀크씨슬추출물은 간 건강에 도움을 줄 수 있음",
            MachineRoleReasonCode.FUNCTION_WITHOUT_FORM,
            RoleEvidenceField.PRIMARY_FUNCTION,
        ),
    ],
)
def test_classifier_enforces_raw_material_and_primary_function_field_boundaries(
    raw_materials: str,
    primary_function: str,
    expected_reason: MachineRoleReasonCode,
    expected_evidence: RoleEvidenceField,
) -> None:
    decision = classify_functional_role(
        _product(
            report_no="ROLE-014",
            raw_materials=raw_materials,
            primary_function=primary_function,
        ),
        IngredientGroup.MILK_THISTLE,
        _registry(),
    )

    assert decision.verdict is MachineRoleVerdict.UNVERIFIABLE
    assert decision.reason_code is expected_reason
    assert decision.evidence_field is expected_evidence


def test_classifier_uses_only_the_target_rule_for_nonfunctional_forms() -> None:
    decision = classify_functional_role(
        _product(
            report_no="ROLE-015",
            raw_materials="스테아린산 마그네슘",
            primary_function="",
        ),
        IngredientGroup.RED_GINSENG,
        _registry(),
    )

    assert decision.verdict is MachineRoleVerdict.UNVERIFIABLE
    assert decision.reason_code is MachineRoleReasonCode.NO_APPLICABLE_EVIDENCE
    assert decision.matched_nonfunctional_form == ""


def test_classifier_does_not_match_half_of_a_casefold_expansion() -> None:
    registry = _registry_with_rule_changes(
        IngredientGroup.MILK_THISTLE,
        accepted_functional_forms=["s"],
    )
    decision = classify_functional_role(
        _product(
            report_no="ROLE-016",
            raw_materials="ß",
            primary_function="간 건강",
        ),
        IngredientGroup.MILK_THISTLE,
        registry,
    )

    assert decision.verdict is MachineRoleVerdict.UNVERIFIABLE
    assert decision.reason_code is MachineRoleReasonCode.FUNCTION_WITHOUT_FORM
    assert decision.matched_functional_form == ""
