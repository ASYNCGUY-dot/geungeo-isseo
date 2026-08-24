from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from claimledger.domain import ProductCandidate
from claimledger.official import (
    OfficialFieldStatus,
    OfficialFunctionStatement,
    extract_official_cautions,
    parse_official_functions,
)

NOW = datetime(2026, 8, 24, tzinfo=UTC)


def product(**updates: str) -> ProductCandidate:
    values = {
        "report_no": "TEST-OFFICIAL-001",
        "name": "공식 문구 테스트 제품",
        "company": "테스트 제조사",
        "primary_function": "눈 건강에 도움을 줄 수 있음",
        "raw_materials": "루테인지아잔틴복합추출물",
        "intake_method": "1일 1회, 1회 1캡슐을 섭취하십시오.",
        "source_id": "C003",
        "retrieved_at": NOW,
    }
    values.update(updates)
    return ProductCandidate(**values)


PRODUCT = product()
UNKNOWN_FUNCTION_PRODUCT = product(primary_function="눈 건강이 놀랍게 달라집니다")
MISSING_FUNCTION_PRODUCT = product(primary_function="")


def test_official_function_preserves_literal_text_and_expression_strength() -> None:
    statements = parse_official_functions(PRODUCT)

    assert statements[0].original_text == "눈 건강에 도움을 줄 수 있음"
    assert statements[0].effect_key == "eye_health_support"
    assert statements[0].expression_strength == "support"
    assert statements[0].parser_version == "official-function-v1"


@pytest.mark.parametrize(
    ("primary_function", "effect_key", "strength"),
    [
        ("눈 건강에 도움을 줄 수 있음", "eye_health_support", "support"),
        ("혈중 중성지질 개선에 도움을 줄 수 있음", "blood_triglyceride_improvement", "improvement"),
        ("유산균 증식 및 유해균 억제에 도움을 줄 수 있음", "intestinal_microbiota_support", "support"),
    ],
)
def test_three_core_group_vocabulary_uses_reviewed_literal_phrases(
    primary_function: str, effect_key: str, strength: str
) -> None:
    statement = parse_official_functions(product(primary_function=primary_function))[0]

    assert statement.status is OfficialFieldStatus.VERIFIED
    assert statement.original_text == primary_function
    assert statement.effect_key == effect_key
    assert statement.expression_strength == strength


def test_reviewed_semicolon_delimiter_retains_each_literal_source_segment() -> None:
    source_text = "눈 건강에 도움을 줄 수 있음;혈행 개선에 도움을 줄 수 있음"

    statements = parse_official_functions(product(primary_function=source_text))

    assert [statement.original_text for statement in statements] == [
        "눈 건강에 도움을 줄 수 있음",
        "혈행 개선에 도움을 줄 수 있음",
    ]
    assert [statement.effect_key for statement in statements] == [
        "eye_health_support",
        "blood_circulation_improvement",
    ]


def test_unknown_wording_is_unverifiable_not_rewritten() -> None:
    result = parse_official_functions(UNKNOWN_FUNCTION_PRODUCT)

    assert result[0].status is OfficialFieldStatus.UNVERIFIABLE
    assert result[0].original_text == UNKNOWN_FUNCTION_PRODUCT.primary_function
    assert result[0].effect_key is None
    assert result[0].expression_strength is None


def test_malformed_delimiter_input_remains_one_unverifiable_literal() -> None:
    source_text = "눈 건강에 도움을 줄 수 있음;"

    result = parse_official_functions(product(primary_function=source_text))

    assert result[0].status is OfficialFieldStatus.UNVERIFIABLE
    assert result[0].original_text == source_text


def test_blank_required_fields_remain_explicitly_missing() -> None:
    result = parse_official_functions(MISSING_FUNCTION_PRODUCT)

    assert result[0].status is OfficialFieldStatus.MISSING
    assert result[0].original_text == ""


def test_expression_strength_is_limited_to_the_five_reviewed_values() -> None:
    with pytest.raises(ValidationError):
        OfficialFunctionStatement(
            status=OfficialFieldStatus.VERIFIED,
            original_text="눈 건강에 도움을 줄 수 있음",
            effect_key="eye_health_support",
            expression_strength="certainty",
        )


def test_caution_extraction_preserves_literal_intake_source_text() -> None:
    source_text = "의약품 복용 시 전문가와 상담하십시오."

    cautions = extract_official_cautions(product(intake_method=source_text))

    assert cautions[0].status is OfficialFieldStatus.VERIFIED
    assert cautions[0].source_field == "intake_method"
    assert cautions[0].original_text == source_text
    assert cautions[0].parser_version == "official-caution-v1"


def test_caution_extraction_uses_reviewed_raw_material_allergen_text() -> None:
    source_text = "정제어유, 대두 함유"

    cautions = extract_official_cautions(product(raw_materials=source_text))

    raw_material_cautions = [
        caution for caution in cautions if caution.source_field == "raw_materials"
    ]
    assert raw_material_cautions[0].status is OfficialFieldStatus.VERIFIED
    assert raw_material_cautions[0].original_text == source_text


def test_unknown_caution_text_is_unverifiable_not_rewritten() -> None:
    source_text = "맛있게 드십시오."

    cautions = extract_official_cautions(product(intake_method=source_text))

    assert cautions[0].status is OfficialFieldStatus.UNVERIFIABLE
    assert cautions[0].original_text == source_text
