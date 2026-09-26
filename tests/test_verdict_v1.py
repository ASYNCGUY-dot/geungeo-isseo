from datetime import UTC, datetime
from itertools import product as cartesian

import pytest

from claimledger.claims_v1 import ExpressionStrength, confirm_claims, extract_claims
from claimledger.domain import ConfirmedProduct, ProductCandidate, Verdict
from claimledger.official_v2 import EFFECT_GROUP, EffectKey
from claimledger.verdict_v1 import CLAIM_VERDICT_VERSION, VerdictReason, decide_claim

RETRIEVED_AT = datetime(2026, 8, 27, 12, 42, tzinfo=UTC)


def _product(primary_function: str, raw_materials: str = "원재료") -> ConfirmedProduct:
    return ConfirmedProduct(
        product=ProductCandidate(
            report_no="200400000000001",
            name="테스트 제품",
            company="테스트 업체",
            primary_function=primary_function,
            raw_materials=raw_materials,
            intake_method="1일 1회",
            source_id="C003",
            retrieved_at=RETRIEVED_AT,
        ),
        confirmed_by_user=True,
    )


def _claim(sentence: str, confirmed: bool = True):
    claims = extract_claims(sentence)
    assert len(claims) == 1
    return confirm_claims(claims, "all")[0] if confirmed else claims[0]


OMEGA3_TEXT = "[EPA 및 DHA 함유 유지] 혈중 중성지질 개선·혈행 개선·건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음\n[은행잎 추출물] 기억력 개선에 도움을 줄 수 있음"


def test_unconfirmed_product_is_unverifiable_before_any_other_rule() -> None:
    decision = decide_claim(_claim("암을 치료합니다"), None)

    assert decision.verdict is Verdict.UNVERIFIABLE
    assert decision.reason is VerdictReason.PRODUCT_IDENTITY_UNCONFIRMED
    assert decision.rule_version == CLAIM_VERDICT_VERSION


def test_unconfirmed_claim_is_unverifiable() -> None:
    decision = decide_claim(_claim("혈행 개선에 도움을 줄 수 있어요", confirmed=False), _product(OMEGA3_TEXT))

    assert (decision.verdict, decision.reason) == (Verdict.UNVERIFIABLE, VerdictReason.CLAIM_UNCONFIRMED)


def test_disease_claim_is_mismatch_even_when_effect_is_official() -> None:
    decision = decide_claim(_claim("혈행 개선으로 고혈압을 예방합니다"), _product(OMEGA3_TEXT))

    assert (decision.verdict, decision.reason) == (
        Verdict.MISMATCH,
        VerdictReason.DISEASE_CLAIM_BEYOND_FUNCTIONAL_SCOPE,
    )


def test_claim_without_rule_effect_is_unverifiable() -> None:
    decision = decide_claim(_claim("피로가 싹 회복됩니다"), _product(OMEGA3_TEXT))

    assert (decision.verdict, decision.reason) == (Verdict.UNVERIFIABLE, VerdictReason.CLAIM_OUTSIDE_RULE_SCOPE)


def test_unclear_strength_is_unverifiable() -> None:
    decision = decide_claim(_claim("배변활동을 원활하게"), _product("[프로바이오틱스] 배변활동 원활에 도움을 줄 수 있음"))

    assert (decision.verdict, decision.reason) == (Verdict.UNVERIFIABLE, VerdictReason.CLAIM_STRENGTH_UNCLEAR)


def test_missing_official_function_is_unverifiable_not_mismatch() -> None:
    decision = decide_claim(_claim("혈행 개선에 도움을 줄 수 있어요"), _product("   "))

    assert (decision.verdict, decision.reason) == (Verdict.UNVERIFIABLE, VerdictReason.OFFICIAL_FUNCTION_MISSING)


def test_effect_absent_from_official_text_is_mismatch() -> None:
    decision = decide_claim(
        _claim("장 건강에 도움을 줄 수 있어요"),
        _product("[비타민C] 결합조직 형성과 기능유지에 필요"),
    )

    assert (decision.verdict, decision.reason) == (Verdict.MISMATCH, VerdictReason.EFFECT_NOT_IN_OFFICIAL_FUNCTIONS)
    assert decision.official_effect is None


def test_headerless_official_effect_is_attribution_ambiguous() -> None:
    decision = decide_claim(
        _claim("장 건강에 도움을 줄 수 있어요"),
        _product("① 유산균 증식 및 유해균 억제･배변활동 원활･장 건강에 도움을 줄 수 있음"),
    )

    assert (decision.verdict, decision.reason) == (
        Verdict.UNVERIFIABLE,
        VerdictReason.OFFICIAL_ATTRIBUTION_AMBIGUOUS,
    )


def test_effect_under_other_ingredient_header_is_not_confirmed() -> None:
    decision = decide_claim(_claim("기억력 개선에 도움을 줄 수 있어요"), _product(OMEGA3_TEXT))

    assert (decision.verdict, decision.reason) == (
        Verdict.UNVERIFIABLE,
        VerdictReason.OFFICIAL_ATTRIBUTION_AMBIGUOUS,
    )


def test_attributed_support_claim_is_confirmed_with_literal_quote() -> None:
    decision = decide_claim(_claim("혈중 중성지질 개선에 도움을 줄 수 있어요"), _product(OMEGA3_TEXT))

    assert (decision.verdict, decision.reason) == (Verdict.CONFIRMED, VerdictReason.MATCHES_OFFICIAL_FUNCTION)
    assert decision.official_effect is not None
    assert decision.official_effect.effect is EffectKey.BLOOD_TRIGLYCERIDE
    assert decision.official_effect.matched_text in OMEGA3_TEXT
    assert decision.official_effect.block_header == "EPA 및 DHA 함유 유지"


def test_definitive_improvement_exceeds_official_strength() -> None:
    decision = decide_claim(_claim("혈액순환이 좋아집니다"), _product(OMEGA3_TEXT))

    assert (decision.verdict, decision.reason) == (
        Verdict.MISMATCH,
        VerdictReason.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL,
    )
    assert decision.official_effect is not None


def test_generic_eye_claim_can_match_omega3_dry_eye_statement() -> None:
    decision = decide_claim(_claim("눈 건강에 도움을 줄 수 있어요"), _product(OMEGA3_TEXT))

    assert decision.verdict is Verdict.CONFIRMED
    assert decision.official_effect is not None
    assert decision.official_effect.effect is EffectKey.DRY_EYE_EYE_HEALTH


def test_specific_dry_eye_claim_does_not_match_lutein_statement() -> None:
    lutein = "[루테인] 노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음"
    decision = decide_claim(_claim("건조한 눈 개선에 도움을 줄 수 있어요"), _product(lutein))

    assert decision.verdict is not Verdict.CONFIRMED


@pytest.mark.parametrize(
    ("header", "strength_sentence"),
    list(
        cartesian(
            ["[EPA 및 DHA 함유 유지]", "[은행잎 추출물]", ""],
            [
                "혈행 개선에 도움을 줄 수 있어요",
                "혈행을 개선합니다",
                "혈행 개선 확실",
                "혈행 개선을 기대할 수 있어요",
            ],
        )
    ),
)
def test_confirmed_requires_target_attribution_and_official_strength(
    header: str, strength_sentence: str
) -> None:
    decision = decide_claim(
        _claim(strength_sentence), _product(f"{header} 혈행 개선에 도움을 줄 수 있음")
    )

    if decision.verdict is Verdict.CONFIRMED:
        assert decision.official_effect is not None
        assert EFFECT_GROUP[decision.official_effect.effect] in decision.official_effect.attributed_groups
        assert decision.claim.strength in (ExpressionStrength.POSSIBILITY, ExpressionStrength.SUPPORT)
        assert header == "[EPA 및 DHA 함유 유지]"
