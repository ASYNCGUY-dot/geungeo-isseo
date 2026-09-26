import pytest

from claimledger.domain import IngredientGroup
from claimledger.official_v2 import (
    OFFICIAL_FUNCTION_V2_VERSION,
    EffectKey,
    effect_mentioned,
    parse_official_function_v2,
)

LUTEIN = IngredientGroup.LUTEIN_ZEAXANTHIN
OMEGA3 = IngredientGroup.OMEGA3
PROBIOTICS = IngredientGroup.PROBIOTICS


def _effects(text: str) -> list[tuple[EffectKey, tuple[IngredientGroup, ...]]]:
    parsed = parse_official_function_v2(text)
    return [(item.effect, item.attributed_groups) for item in parsed.effects]


def test_bracket_header_attributes_effect_to_target_group() -> None:
    text = (
        "[루테인] 노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음\n"
        "[비타민A] 어두운 곳에서 시각 적응을 위해 필요"
    )

    assert _effects(text) == [(EffectKey.MACULAR_PIGMENT_EYE_HEALTH, (LUTEIN,))]


def test_colon_header_with_marigold_counts_as_lutein_source() -> None:
    text = "마리골드꽃추출물 : 노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음."

    assert _effects(text) == [(EffectKey.MACULAR_PIGMENT_EYE_HEALTH, (LUTEIN,))]


def test_composite_omega3_statement_splits_into_each_effect() -> None:
    text = "[EPA 및 DHA 함유 유지] 혈중 중성지질 개선·혈행 개선·기억력 개선·건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음"

    assert _effects(text) == [
        (EffectKey.BLOOD_TRIGLYCERIDE, (OMEGA3,)),
        (EffectKey.BLOOD_CIRCULATION, (OMEGA3,)),
        (EffectKey.MEMORY, (OMEGA3,)),
        (EffectKey.DRY_EYE_EYE_HEALTH, (OMEGA3,)),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "혈중 중성지질 개선･혈행 개선에 도움을 줄 수 있음",
        "혈중 중성지질 개선 · 혈행 개선에 도움을 줄 수 있음",
        "혈중중성지질개선․혈행개선에 도움을 줄 수 있음",
    ],
)
def test_separator_and_spacing_variants_are_recognized(text: str) -> None:
    parsed = parse_official_function_v2("EPA 및 DHA 함유 유지 : " + text)

    assert [item.effect for item in parsed.effects] == [
        EffectKey.BLOOD_TRIGLYCERIDE,
        EffectKey.BLOOD_CIRCULATION,
    ]


def test_star_and_numbered_line_headers_start_blocks() -> None:
    text = (
        "* 프로바이오틱스\n"
        "① 유산균 증식 및 유해균 억제에 도움을 줄 수 있음\n"
        "② 배변활동 원활에 도움을 줄 수 있음\n"
        "\n"
        "1) 식이섬유 : 배변활동 원활에 도움을 줄 수 있음"
    )

    assert _effects(text) == [
        (EffectKey.PROBIOTIC_GROWTH_HARMFUL_INHIBITION, (PROBIOTICS,)),
        (EffectKey.BOWEL_MOVEMENT, (PROBIOTICS,)),
        (EffectKey.BOWEL_MOVEMENT, ()),
    ]


def test_inline_bracket_headers_on_one_line_are_separate_blocks() -> None:
    text = "[프로바이오틱스]유산균 증식 및 유해균 억제에 도움을 줄 수 있음 [은행잎추출물]기억력 개선에 도움을 줄 수 있음"

    assert _effects(text) == [
        (EffectKey.PROBIOTIC_GROWTH_HARMFUL_INHIBITION, (PROBIOTICS,)),
        (EffectKey.MEMORY, ()),
    ]


def test_headerless_text_leaves_effects_unattributed() -> None:
    text = "① 유산균 증식 및 유해균 억제･배변활동 원활･장 건강에 도움을 줄 수 있음"

    assert _effects(text) == [
        (EffectKey.PROBIOTIC_GROWTH_HARMFUL_INHIBITION, ()),
        (EffectKey.BOWEL_MOVEMENT, ()),
        (EffectKey.GUT_HEALTH, ()),
    ]


def test_same_phrase_under_other_ingredient_is_not_attributed_to_target() -> None:
    text = "[은행잎 추출물] 기억력 개선·혈행 개선에 도움을 줄 수 있음\n[EPA 및 DHA 함유 유지] 혈중 중성지질 개선에 도움을 줄 수 있음"

    assert _effects(text) == [
        (EffectKey.MEMORY, ()),
        (EffectKey.BLOOD_CIRCULATION, ()),
        (EffectKey.BLOOD_TRIGLYCERIDE, (OMEGA3,)),
    ]


def test_name_only_header_line_attributes_following_lines() -> None:
    text = "EPA 및 DHA 함유 유지\n(1) 혈중 중성지질 개선에 도움을 줄 수 있음\n비타민E\n항산화 작용을 하여 유해산소로부터 세포를 보호하는데 필요"

    assert _effects(text) == [(EffectKey.BLOOD_TRIGLYCERIDE, (OMEGA3,))]


def test_prebiotic_intestinal_microbiota_is_not_probiotic_growth() -> None:
    text = "[프락토올리고당] 장내 유익균 증식 및 배변활동 원활에 도움을 줄 수 있음"

    assert _effects(text) == [(EffectKey.BOWEL_MOVEMENT, ())]


def test_growth_word_is_not_gut_health() -> None:
    assert _effects("[칼슘] 뼈와 치아 형성에 필요, 성장 건강") == []


def test_quotes_are_literal_substrings_with_exact_spans() -> None:
    text = "[프로바이오틱스] 유산균 증식 및 유해균 억제 ･ 배변활동 원활 ･ 장 건강에 도움을 줄 수 있음"
    parsed = parse_official_function_v2(text)

    assert parsed.parser_version == OFFICIAL_FUNCTION_V2_VERSION
    for item in parsed.effects:
        start, end = item.matched_span
        assert text[start:end] == item.matched_text
        line_start, line_end = item.statement_span
        assert text[line_start:line_end] == item.statement_text
        assert item.matched_text in item.statement_text
        assert item.official_strength == "support"
    assert parsed.effects[0].block_header == "프로바이오틱스"


def test_effect_mentioned_uses_broad_whitespace_insensitive_keywords() -> None:
    text = "[은행잎추출물] 혈액흐름 개선에 도움을 줄 수 있음"

    assert effect_mentioned(text, EffectKey.BLOOD_CIRCULATION) is True
    assert effect_mentioned(text, EffectKey.MEMORY) is False
    assert effect_mentioned("안구 건조 개선", EffectKey.DRY_EYE_EYE_HEALTH) is True


def test_empty_text_has_no_effects() -> None:
    parsed = parse_official_function_v2("   ")

    assert parsed.effects == ()
    assert parsed.blocks == ()
