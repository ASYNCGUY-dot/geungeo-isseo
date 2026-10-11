"""Whitening and wrinkle claims against a functional cosmetic's official efficacy (synthetic products)."""

from datetime import UTC, datetime

import pytest

from claimledger.claims_v1 import ExpressionStrength
from claimledger.cosmetics_claims import confirm_cosmetic_claims, extract_cosmetic_claims
from claimledger.cosmetics_official import CosmeticFunction
from claimledger.cosmetics_verdict import (
    COSMETIC_VERDICT_VERSION,
    ConfirmedCosmetic,
    CosmeticVerdictReason,
    decide_cosmetic_claim,
)
from claimledger.domain import Verdict
from claimledger.sources.functional_cosmetics import FunctionalCosmetic

AT = datetime(2026, 10, 11, tzinfo=UTC)
F = CosmeticFunction
R = CosmeticVerdictReason
WHITENING = "피부의 미백에 도움을 준다."
WRINKLE = "피부의 주름개선에 도움을 준다."
BOTH = f"{WHITENING} {WRINKLE}"
SUN = "자외선으로부터 피부를 보호한다.(SPF50+, PA++++)"


def _product(sentence: str = "", document: str = "") -> ConfirmedCosmetic:
    product = FunctionalCosmetic(
        record_id="SYNTHETIC-1", item_name="합성 테스트 크림", company="합성 테스트 업체",
        registered_on="20250102", effect_text=document, effect_name=sentence,
        source_id="data.go.kr:15095680", retrieved_at=AT,
    )
    return ConfirmedCosmetic(product=product, confirmed_by_user=True)


def _decide(ad: str, product: ConfirmedCosmetic | None):
    claims = confirm_cosmetic_claims(extract_cosmetic_claims(ad), "all")
    assert len(claims) == 1, "A risky sentence must remain visible for review"
    return decide_cosmetic_claim(claims[0], product)


def test_extraction_reads_functions_and_strength_with_literal_spans() -> None:
    text = "피부 미백에 도움을 줍니다.\n주름을 확실하게 없애줍니다!\n본 제품은 의약품이 아닙니다.\n촉촉한 사용감."
    claims = extract_cosmetic_claims(text)

    assert [claim.claim_id for claim in claims] == ["C1", "C2"]
    assert claims[0].function_candidates == (F.WHITENING,) and claims[0].strength is ExpressionStrength.SUPPORT
    assert claims[1].function_candidates == (F.WRINKLE,) and claims[1].strength is ExpressionStrength.GUARANTEE
    assert text[slice(*claims[1].span)] == "주름을 확실하게 없애줍니다!"
    assert claims[0].function_cues == ("미백",) and not claims[0].confirmed_by_user


@pytest.mark.parametrize(("ad", "official"), [
    ("피부 미백에 도움을 줍니다.", WHITENING),
    ("이 제품은 피부의 미백에 도움을 준다.", BOTH),
    ("미백에 도움을 줄 수 있습니다.", WHITENING),
    ("주름개선에 도움을 줍니다.", WRINKLE),
    ("본 제품은 피부 주름개선에 도움을 줄 수 있어요.", BOTH),
    ("미백 기능성화장품입니다.", WHITENING),
    ("주름개선 기능성 화장품", BOTH),
    ("미백과 주름개선에 도움을 줍니다.", BOTH),
    ("주름개선 및 미백에 도움을 줄 수 있습니다.", BOTH),
    ("미백·주름개선 2중 기능성 화장품입니다.", BOTH),
    ("미백, 주름개선 이중 기능성화장품", BOTH),
])
def test_claims_within_the_official_efficacy_are_confirmed(ad: str, official: str) -> None:
    decision = _decide(ad, _product(sentence=official))

    assert decision.verdict is Verdict.CONFIRMED and decision.reason is R.MATCHES_OFFICIAL_EFFICACY
    assert decision.official_sentences and decision.verdict_version == COSMETIC_VERDICT_VERSION
    assert {item.function for item in decision.official_sentences} == set(decision.claim.function_candidates)


def test_the_official_quote_comes_from_the_document_when_that_is_the_source() -> None:
    decision = _decide("미백에 도움을 줍니다.", _product(document=f"1. {WHITENING}\n2. {SUN}"))
    assert decision.verdict is Verdict.CONFIRMED
    assert [(item.text, item.source) for item in decision.official_sentences] == [(WHITENING, "document")]


@pytest.mark.parametrize(("ad", "official", "reason"), [
    # The product was not reported for the claimed function.
    ("주름개선에 도움을 줍니다.", WHITENING, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    ("미백과 주름개선에 도움을 줍니다.", WHITENING, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    ("미백·주름개선 2중 기능성 화장품입니다.", WRINKLE, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    ("주름을 싹 없애줍니다.", SUN, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    # Stronger than "도움을 준다".
    ("주름을 개선합니다.", WRINKLE, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("피부가 하얗게 밝아지는 미백 크림", WHITENING, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("미백 효과 100% 보장", WHITENING, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("7일 만에 주름개선에 도움을 줍니다.", WRINKLE, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    # Medical wording is outside what a cosmetic may claim, whatever the product.
    ("기미를 치료하는 미백 크림", WHITENING, R.MEDICAL_CLAIM_BEYOND_COSMETIC_SCOPE),
    ("피부 재생으로 주름개선에 도움을 줍니다.", WRINKLE, R.MEDICAL_CLAIM_BEYOND_COSMETIC_SCOPE),
    ("보톡스 맞은 듯한 주름개선", WRINKLE, R.MEDICAL_CLAIM_BEYOND_COSMETIC_SCOPE),
])
def test_claims_beyond_the_official_efficacy_are_mismatches(
    ad: str, official: str, reason: CosmeticVerdictReason,
) -> None:
    decision = _decide(ad, _product(document=official) if official is SUN else _product(sentence=official))
    assert decision.verdict is Verdict.MISMATCH and decision.reason is reason
    assert decision.official_sentences == ()


@pytest.mark.parametrize("ad", [
    # Subjects, conditions and extra content the rules cannot read stay unresolved.
    "나이아신아마이드가 피부 미백에 도움을 줍니다.",
    "미백에 도움을 주고 피부결도 매끄럽게 가꿔 줍니다.",
    "민감한 피부의 미백에 도움을 줍니다.",
    "미백에 도움을 줄 수 있나요?",
    "미백에 도움이 되지 않습니다.",
    "미백에 3배 도움을 줍니다.",
    "화이트닝에 도움을 줍니다.",
    "미백과 주름개선, 탄력에 도움을 줍니다.",
    "미백 기능성 인증을 받은 유일한 화장품입니다.",
])
def test_unreadable_claims_are_not_confirmed(ad: str) -> None:
    decision = _decide(ad, _product(sentence=BOTH))
    assert decision.verdict is Verdict.UNVERIFIABLE and decision.official_sentences == ()
    assert decision.reason is R.CLAIM_SCOPE_UNRESOLVED


@pytest.mark.parametrize(("product", "reason"), [
    (_product(), R.OFFICIAL_EFFICACY_MISSING),
    (_product(document=f"{WHITENING}\n※ 해당하는 효능효과 이외에는 모두 삭제하시기 바랍니다."), R.OFFICIAL_EFFICACY_TEMPLATE_REMNANT),
    (_product(sentence=WHITENING, document=SUN), R.OFFICIAL_EFFICACY_CONFLICTING),
    (_product(document="피부의 미백에 도움은 준다."), R.OFFICIAL_EFFICACY_UNRECOGNIZED),
])
def test_official_data_that_cannot_be_trusted_never_clears_or_condemns(
    product: ConfirmedCosmetic, reason: CosmeticVerdictReason,
) -> None:
    for ad in ("미백에 도움을 줍니다.", "주름개선에 도움을 줍니다.", "미백 효과 100% 보장"):
        decision = _decide(ad, product)
        assert decision.verdict is Verdict.UNVERIFIABLE and decision.reason is reason


def test_identity_and_claim_confirmation_gates() -> None:
    claim = extract_cosmetic_claims("미백에 도움을 줍니다.")[0]
    product = _product(sentence=WHITENING)

    assert decide_cosmetic_claim(claim, product).reason is R.CLAIM_UNCONFIRMED
    confirmed = confirm_cosmetic_claims([claim], ["C1"])[0]
    assert decide_cosmetic_claim(confirmed, None).reason is R.PRODUCT_IDENTITY_UNCONFIRMED
    unconfirmed = ConfirmedCosmetic(product=product.product, confirmed_by_user=False)
    assert decide_cosmetic_claim(confirmed, unconfirmed).reason is R.PRODUCT_IDENTITY_UNCONFIRMED
    assert decide_cosmetic_claim(confirmed, product).verdict is Verdict.CONFIRMED
    with pytest.raises(ValueError):
        confirm_cosmetic_claims([claim], ["C9"])


@pytest.mark.parametrize(("ad", "reason"), [
    ("자외선 차단에 도움을 줍니다.", R.FUNCTION_RULE_NOT_READY),
    ("미백과 자외선 차단에 도움을 줍니다.", R.FUNCTION_RULE_NOT_READY),
    ("입술 주름개선에 도움을 줍니다.", R.FUNCTION_RULE_NOT_READY),
    ("탈모 증상 완화에 도움을 줍니다.", R.FUNCTION_RULE_NOT_READY),
    ("피부 탄력을 확실하게 높여 줍니다.", R.CLAIM_OUTSIDE_RULE_SCOPE),
    ("미백 크림", R.CLAIM_STRENGTH_UNCLEAR),
])
def test_claims_outside_the_first_two_functions_are_unverifiable(
    ad: str, reason: CosmeticVerdictReason,
) -> None:
    document = f"{WHITENING}\n{WRINKLE}\n{SUN}\n입술의 주름개선에 도움을 준다."
    decision = _decide(ad, _product(document=document))
    assert decision.verdict is Verdict.UNVERIFIABLE and decision.reason is reason


@pytest.mark.parametrize("ad", [
    "질병 치료 목적의 제품이 아닙니다.",
    "이 제품은 피부 질환을 치료하지 않습니다.",
    "의약품처럼 염증을 없애는 제품은 아니에요.",
])
def test_a_denied_medical_effect_is_not_condemned_as_a_medical_claim(ad: str) -> None:
    decision = _decide(ad, _product(sentence=BOTH))
    assert decision.verdict is Verdict.UNVERIFIABLE and decision.reason is R.CLAIM_SCOPE_UNRESOLVED


def test_a_safety_assurance_stays_visible_as_an_unverified_claim() -> None:
    claims = confirm_cosmetic_claims(
        extract_cosmetic_claims("미백에 도움을 줍니다. 부작용이 전혀 없습니다."), "all"
    )
    decisions = [decide_cosmetic_claim(claim, _product(sentence=BOTH)) for claim in claims]
    assert [decision.verdict for decision in decisions] == [Verdict.CONFIRMED, Verdict.UNVERIFIABLE]
    assert decisions[1].reason is R.CLAIM_OUTSIDE_RULE_SCOPE
    # In one sentence the assurance blocks the confirmation as well.
    joined = _decide("미백에 도움을 주며 부작용이 없습니다.", _product(sentence=BOTH))
    assert joined.verdict is not Verdict.CONFIRMED


def test_a_lip_wrinkle_product_does_not_clear_or_condemn_a_skin_wrinkle_claim() -> None:
    decision = _decide("주름개선에 도움을 줍니다.", _product(document="입술의 주름개선에 도움을 준다."))
    assert decision.verdict is Verdict.UNVERIFIABLE and decision.reason is R.CLAIM_SCOPE_UNRESOLVED


def test_two_sentences_do_not_share_one_confirmation() -> None:
    claims = confirm_cosmetic_claims(
        extract_cosmetic_claims("미백에 도움을 줍니다. 주름을 완벽하게 제거합니다."), "all"
    )
    product = _product(sentence=BOTH)
    verdicts = [decide_cosmetic_claim(claim, product).verdict for claim in claims]
    assert verdicts == [Verdict.CONFIRMED, Verdict.MISMATCH]
