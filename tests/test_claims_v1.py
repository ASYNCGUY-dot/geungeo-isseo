import pytest

from claimledger.claims_v1 import (
    CLAIM_EXTRACTION_VERSION,
    ExpressionStrength,
    confirm_claims,
    extract_claims,
    unread_sentences,
)
from claimledger.official_v2 import EffectKey


def test_sentences_become_claims_with_literal_spans() -> None:
    text = "루테인이 눈 건강에 도움을 줄 수 있어요. 하루 한 알로 간편하게!\n혈액순환이 좋아집니다"
    claims = extract_claims(text)

    assert [claim.claim_id for claim in claims] == ["C1", "C2"]
    for claim in claims:
        start, end = claim.span
        assert text[start:end] == claim.text
        assert claim.confirmed_by_user is False
        assert claim.extraction_version == CLAIM_EXTRACTION_VERSION
    assert claims[0].effect_candidates == (
        EffectKey.MACULAR_PIGMENT_EYE_HEALTH,
        EffectKey.DRY_EYE_EYE_HEALTH,
    )
    assert claims[0].strength is ExpressionStrength.SUPPORT
    assert claims[1].effect_candidates == (EffectKey.BLOOD_CIRCULATION,)
    assert claims[1].strength is ExpressionStrength.IMPROVEMENT


@pytest.mark.parametrize(
    ("sentence", "effects", "strength"),
    [
        ("황반변성을 예방합니다", (EffectKey.MACULAR_PIGMENT_EYE_HEALTH,), ExpressionStrength.TREATMENT_PREVENTION),
        ("중성지방을 확실하게 낮춰줍니다", (EffectKey.BLOOD_TRIGLYCERIDE,), ExpressionStrength.GUARANTEE),
        ("혈중 중성지질 개선에 도움을 줄 수 있습니다", (EffectKey.BLOOD_TRIGLYCERIDE,), ExpressionStrength.SUPPORT),
        ("기억력 향상!", (EffectKey.MEMORY,), ExpressionStrength.IMPROVEMENT),
        ("건조한 눈을 지킬 수 있어요", (EffectKey.DRY_EYE_EYE_HEALTH,), ExpressionStrength.POSSIBILITY),
        ("유산균 증식과 유해균 억제에 도움", (EffectKey.PROBIOTIC_GROWTH_HARMFUL_INHIBITION,), ExpressionStrength.SUPPORT),
        ("쾌변! 배변활동을 원활하게", (EffectKey.BOWEL_MOVEMENT,), None),
        ("장 건강에 도움을 줄 수 있음", (EffectKey.GUT_HEALTH,), ExpressionStrength.SUPPORT),
        ("눈의 피로가 사라집니다", (), ExpressionStrength.IMPROVEMENT),
        ("면역력을 높여줍니다", (), ExpressionStrength.IMPROVEMENT),
        ("체지방을 없애줍니다", (), ExpressionStrength.IMPROVEMENT),
    ],
)
def test_effect_and_strength_classification(
    sentence: str, effects: tuple[EffectKey, ...], strength: ExpressionStrength | None
) -> None:
    claims = extract_claims(sentence)

    assert len(claims) == 1
    assert claims[0].effect_candidates == effects
    assert claims[0].strength is strength


def test_disease_words_without_known_effect_still_form_a_claim() -> None:
    claims = extract_claims("암을 치료하는 기적의 원료")

    assert len(claims) == 1
    assert claims[0].effect_candidates == ()
    assert claims[0].strength is ExpressionStrength.TREATMENT_PREVENTION


def test_negated_disclaimer_is_not_a_claim() -> None:
    text = "본 제품은 질병의 예방 및 치료를 위한 의약품이 아닙니다. 부작용이 없습니다."

    assert extract_claims(text) == ()


@pytest.mark.parametrize(("text", "claim"), [
    # The notice on lines of its own is a sentence even without a period (independent review, 2026-10-26).
    ("혈행 개선에 도움을 줄 수 있습니다\n본 제품은 질병의 예방 및 치료를 위한 의약품이 아닙니다", "혈행 개선에 도움을 줄 수 있습니다"),
    ("본 제품은 의약품이 아닙니다\n혈행 개선에 도움을 줄 수 있습니다.", "혈행 개선에 도움을 줄 수 있습니다."),
    # Wrapping still keeps a sentence together, on either side of the notice.
    (
        "혈행 개선에\n도움을 줄 수 있습니다\n이 제품은 질병의 예방 및 치료를 위한\n의약품이 아닙니다",
        "혈행 개선에\n도움을 줄 수 있습니다",
    ),
    (
        "본 제품은 의약품이 아닙니다\n혈행 개선에 도움을 줄 수 있습니다\n본 제품은 질병의 예방 및 치료를 위한 의약품이 아닙니다",
        "혈행 개선에 도움을 줄 수 있습니다",
    ),
    # A notice line holds at most 48 characters without spaces.
    ("혈행 개선에 도움을 줄 수 있습니다\n본 제품은 질병의 예방 및 치료를 위한 의약품이 아닙니다" + "!" * 25, "혈행 개선에 도움을 줄 수 있습니다"),
])
def test_the_notice_on_lines_of_its_own_is_split_from_the_claim(text: str, claim: str) -> None:
    assert [item.text for item in extract_claims(text)] == [claim]
    assert unread_sentences(text) == ()


@pytest.mark.parametrize("text", [
    # Only lines that are the whole notice are split off; other words keep the lines together.
    "본 제품은 질병의 예방 및 치료를 위한\n의약품이 아닙니다",
    "혈행 개선에 도움을 줄 수 있습니다\n그래서 본 제품은 의약품이 아닙니다",
    "혈행 개선에 도움을 줄 수 있습니다\n본 제품은 질병의 예방 및 치료를 위한",
    "혈행 개선에 도움을 줄 수 있는\n본 제품은 의약품이 아닙니다 라고 합니다",
])
def test_lines_that_are_not_the_whole_notice_stay_together(text: str) -> None:
    spans = [item.span for item in extract_claims(text)] + list(unread_sentences(text))

    assert len(spans) <= 1


@pytest.mark.parametrize("text", [
    # A notice between lines of one sentence is not split off: the lines around it became sentences of
    # their own, and "혈행 개선에" read as an improvement claim (independent review, 2026-10-27).
    "혈행 개선에\n본 제품은 의약품이 아닙니다\n도움을 줄 수 있습니다",
    "혈행 개선에 도움을 줄 수 있습니다\n본 제품은 의약품이 아닙니다\n눈 건강에 도움을 줄 수 있습니다",
    "혈행 개선에 도움을 줄 수 있습니다\n본 제품은 질병의 예방 및 치료를 위한 의약품이 아닙니다" + "!" * 26,
])
def test_a_notice_between_lines_or_too_long_stays_in_the_sentence(text: str) -> None:
    assert [item.span for item in extract_claims(text)] == [(0, len(text))]
    assert unread_sentences(text) == ()


def test_growth_is_not_gut_health_and_plain_text_is_not_a_claim() -> None:
    claims = extract_claims("키 성장 건강 쑥쑥\n맛있는 딸기맛")

    assert len(claims) == 1
    assert claims[0].effect_candidates == ()
    assert claims[0].strength is ExpressionStrength.IMPROVEMENT


def test_cues_are_recorded_as_literal_text() -> None:
    claims = extract_claims("혈행 개선에 확실한 도움")

    assert claims[0].strength is ExpressionStrength.GUARANTEE
    assert "혈행 개선" in claims[0].effect_cues
    assert "확실" in claims[0].strength_cues


def test_confirm_claims_marks_selected_ids_only() -> None:
    claims = extract_claims("장 건강에 도움. 기억력 향상!")
    confirmed = confirm_claims(claims, ["C2"])

    assert [claim.confirmed_by_user for claim in confirmed] == [False, True]
    assert [claim.confirmed_by_user for claim in confirm_claims(claims, "all")] == [True, True]
    with pytest.raises(ValueError, match="unknown claim id"):
        confirm_claims(claims, ["C9"])
