"""Sunscreen claims against a functional cosmetic's official efficacy and its index (synthetic products)."""

from datetime import UTC, datetime

import pytest

from claimledger.cosmetics_claims import confirm_cosmetic_claims, extract_cosmetic_claims
from claimledger.cosmetics_official import (
    CosmeticFunction,
    EfficacyStatus,
    SunscreenIndex,
    parse_cosmetic_efficacy,
)
from claimledger.cosmetics_receipt import build_cosmetic_receipt
from claimledger.cosmetics_verdict import (
    ConfirmedCosmetic,
    CosmeticDecision,
    CosmeticVerdictReason,
    decide_cosmetic_ad,
)
from claimledger.domain import Verdict
from claimledger.sources.functional_cosmetics import FunctionalCosmetic

AT = datetime(2026, 10, 11, tzinfo=UTC)
F = CosmeticFunction
R = CosmeticVerdictReason
WHITENING = "피부의 미백에 도움을 준다."
WRINKLE = "피부의 주름개선에 도움을 준다."
PROTECTS = "자외선으로부터 피부를 보호한다."
SUN50 = f"{PROTECTS}(SPF50+, PA++++)"
SUN30 = f"{PROTECTS} (SPF30, PA++)"
SUN30_RESISTANT = f"{PROTECTS} (SPF30, PA++, 내수성)"
SUN30_NO_GRADE = f"{PROTECTS}(SPF 30)"
TRIPLE = f"{WHITENING}\n{WRINKLE}\n{SUN50}"
WHITENING_SUN = f"{WHITENING}\n{SUN50}"


def _product(document: str, **fields: object) -> ConfirmedCosmetic:
    product = FunctionalCosmetic(
        record_id="SYNTHETIC-1", item_name="합성 테스트 선크림", company="합성 테스트 업체",
        registered_on="20250102", effect_text=document, effect_name="",
        source_id="data.go.kr:15095680", retrieved_at=AT, **fields,
    )
    return ConfirmedCosmetic(product=product, confirmed_by_user=True)


def _decide_all(ad: str, product: ConfirmedCosmetic) -> tuple[CosmeticDecision, ...]:
    claims = confirm_cosmetic_claims(extract_cosmetic_claims(ad), "all")
    return decide_cosmetic_ad(ad, claims, product)


def _decide(ad: str, document: str, **fields: object) -> CosmeticDecision:
    decisions = _decide_all(ad, _product(document, **fields))
    assert len(decisions) == 1, "A sunscreen sentence must remain visible as one claim"
    return decisions[0]


def test_the_official_index_is_read_from_the_sunscreen_sentence() -> None:
    efficacy = parse_cosmetic_efficacy(f"{PROTECTS} (SPF50+, PA++++, 지속내수성)", "")
    (sentence,) = efficacy.sentences
    assert sentence.index == SunscreenIndex(spf=50, plus=True, pa=4, water="지속내수성")
    assert efficacy.status is EfficacyStatus.READABLE and efficacy.sunscreen_index == sentence.index

    assert parse_cosmetic_efficacy(SUN30_NO_GRADE, "").sunscreen_index == SunscreenIndex(spf=30)
    assert parse_cosmetic_efficacy(SUN30_RESISTANT, "").sunscreen_index == SunscreenIndex(spf=30, pa=2, water="내수성")
    # No index in the sentence, no sunscreen sentence, or wording that was not read: no index.
    assert parse_cosmetic_efficacy(PROTECTS, "").sunscreen_index is None
    assert parse_cosmetic_efficacy(TRIPLE, "").sunscreen_index == SunscreenIndex(spf=50, plus=True, pa=4)
    assert parse_cosmetic_efficacy("", WHITENING).sunscreen_index is None
    assert parse_cosmetic_efficacy(f"{PROTECTS} (SFP40, PA+++)", "").sunscreen_index is None


def test_the_index_of_an_advertisement_is_read_with_its_literals() -> None:
    (claim,) = extract_cosmetic_claims("SPF50+ PA++++ 지속내수성 선크림입니다.")
    assert claim.function_candidates == (F.SUNSCREEN,)
    assert (claim.spf, claim.pa, claim.water) == (("50+",), ("++++",), ("지속내수성",))

    (spaced,) = extract_cosmetic_claims("자외선 차단 지수 SPF 30, PA ++ 제품입니다.")
    assert (spaced.spf, spaced.pa, spaced.water) == (("30",), ("++",), ())
    # An index before a denial is not claimed.
    (denied,) = extract_cosmetic_claims("SPF50+ PA++++ 제품은 아닙니다.")
    assert (denied.spf, denied.pa) == ((), ()) and denied.function_candidates == ()


@pytest.mark.parametrize(("ad", "document"), [
    ("자외선으로부터 피부를 보호합니다.", SUN50),
    ("이 제품은 자외선으로부터 피부를 보호해 줍니다.", SUN30),
    ("자외선으로부터 피부를 보호하는 데 도움을 줍니다.", SUN50),
    ("자외선 차단에 도움을 줍니다.", SUN50),
    ("자외선 차단 기능성 화장품입니다.", SUN30),
    # A product whose sentence carries no index still has the function.
    ("자외선 차단 기능성 화장품입니다.", PROTECTS),
    # The same index as the official one, before or after the claim.
    ("자외선으로부터 피부를 보호합니다(SPF50+, PA++++).", SUN50),
    ("SPF50+ PA++++ 자외선 차단 기능성 화장품입니다.", SUN50),
    ("SPF30 PA++ 자외선 차단 기능성 화장품입니다.", SUN30),
    ("SPF 30 자외선 차단 기능성 화장품입니다.", SUN30_NO_GRADE),
    ("자외선 차단 기능성 화장품입니다 (SPF30/PA++, 내수성).", SUN30_RESISTANT),
    # Part of the official index is no more than the official index.
    ("SPF50+ 자외선 차단 기능성 화장품입니다.", SUN50),
    ("SPF30 PA++ 자외선 차단 기능성 화장품입니다.", SUN30_RESISTANT),
    # Several functions in one form.
    ("미백·주름개선·자외선 차단 3중 기능성 화장품입니다.", TRIPLE),
    ("미백과 자외선 차단에 도움을 줍니다.", WHITENING_SUN),
    ("미백에 도움을 줍니다. 자외선으로부터 피부를 보호합니다(SPF50+, PA++++).", WHITENING_SUN),
])
def test_sunscreen_claims_within_the_official_efficacy_are_confirmed(ad: str, document: str) -> None:
    for decision in _decide_all(ad, _product(document)):
        assert decision.verdict is Verdict.CONFIRMED and decision.reason is R.MATCHES_OFFICIAL_EFFICACY
        assert decision.official_sentences


def test_the_confirmation_quotes_the_official_sunscreen_sentence() -> None:
    decision = _decide("SPF50+ PA++++ 자외선 차단 기능성 화장품입니다.", TRIPLE)
    assert [(item.function, item.text) for item in decision.official_sentences] == [(F.SUNSCREEN, SUN50)]


@pytest.mark.parametrize(("ad", "document", "reason"), [
    # The product was not reported for sun protection, or is advertised for more than that.
    ("자외선 차단에 도움을 줍니다.", WHITENING, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    ("자외선으로부터 피부를 보호합니다.", f"{WHITENING}\n{WRINKLE}", R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    ("SPF50+ PA++++ 선크림입니다.", WHITENING, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    ("미백·주름개선·자외선 차단 3중 기능성 화장품입니다.", WHITENING_SUN, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    ("미백과 주름개선에 도움을 주는 선크림입니다.", SUN50, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    ("미백에 도움을 주는 SPF50+ 선크림으로 하루를 시작합니다.", SUN50, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    # A higher index than the official one.
    ("SPF50+ PA++++ 자외선 차단 기능성 화장품입니다.", SUN30, R.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL),
    ("SPF50 선크림으로 매일 가볍게 마무리합니다.", SUN30, R.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL),
    ("자외선으로부터 피부를 보호합니다(SPF30, PA+++).", SUN30, R.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL),
    ("SPF50+ 선크림입니다.", f"{PROTECTS}(SPF50, PA+++)", R.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL),
    # A grade or water resistance the official index does not hold.
    ("SPF30 PA++ 자외선 차단 기능성 화장품입니다.", SUN30_NO_GRADE, R.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL),
    ("SPF50+ PA++++ 지속내수성 선크림입니다.", SUN50, R.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL),
    ("SPF30 PA++ 지속내수성 선크림입니다.", SUN30_RESISTANT, R.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL),
    ("땀과 물에 강한 워터프루프 SPF50+ 선크림입니다.", SUN50, R.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL),
    # Stronger than the official sentence.
    ("자외선을 100% 차단합니다.", SUN50, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("자외선을 완벽하게 막아 주는 SPF50+ PA++++ 선크림.", SUN50, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    # Medical wording stays outside what a cosmetic may claim.
    ("자외선으로 생긴 기미를 치료하는 SPF50+ 선크림.", SUN50, R.MEDICAL_CLAIM_BEYOND_COSMETIC_SCOPE),
])
def test_sunscreen_claims_beyond_the_official_efficacy_are_mismatches(
    ad: str, document: str, reason: CosmeticVerdictReason,
) -> None:
    decision = _decide(ad, document)
    assert decision.verdict is Verdict.MISMATCH and decision.reason is reason
    assert decision.official_sentences == ()


@pytest.mark.parametrize(("ad", "document", "reason"), [
    # A lower index is no overstatement, but it is not what the record says either.
    ("SPF30 PA++ 자외선 차단 기능성 화장품입니다.", SUN50, R.SUNSCREEN_INDEX_DIFFERS_FROM_OFFICIAL),
    ("SPF50+ PA+++ 자외선 차단 기능성 화장품입니다.", SUN50, R.SUNSCREEN_INDEX_DIFFERS_FROM_OFFICIAL),
    # The official sentence has no index to compare with.
    ("SPF50+ PA++++ 자외선 차단 기능성 화장품입니다.", PROTECTS, R.OFFICIAL_SUNSCREEN_INDEX_MISSING),
    ("SPF50+ 선크림입니다.", PROTECTS, R.OFFICIAL_SUNSCREEN_INDEX_MISSING),
    # Two values in one sentence: which one is claimed is not known.
    ("SPF30에서 SPF50+로 달라진 선크림입니다.", SUN50, R.SUNSCREEN_INDEX_UNCLEAR),
    ("SPF50+ PA++++ 선크림과 SPF30 PA++ 선로션 세트.", SUN30, R.SUNSCREEN_INDEX_UNCLEAR),
    # "Waterproof" beside an official water resistance is not one of its two grades.
    ("워터프루프 SPF30 PA++ 선크림입니다.", SUN30_RESISTANT, R.CLAIM_SCOPE_UNRESOLVED),
    # The same index in a sentence that was not read completely.
    ("가볍게 발리는 SPF50+ PA++++ 선크림으로 하루를 시작합니다.", SUN50, R.CLAIM_SCOPE_UNRESOLVED),
    # A product kind alone claims nothing that can be compared.
    ("선크림 전 단계에 가볍게 발라 주세요.", WHITENING, R.CLAIM_STRENGTH_UNCLEAR),
    ("선크림 전 단계에 가볍게 발라 주세요.", SUN50, R.CLAIM_STRENGTH_UNCLEAR),
    # Wording that was not read, a missing statement: nothing is taken from them.
    ("SPF50+ PA++++ 선크림입니다.", f"{PROTECTS} (SFP40, PA+++)", R.OFFICIAL_EFFICACY_UNRECOGNIZED),
    ("자외선 차단에 도움을 줍니다.", "", R.OFFICIAL_EFFICACY_MISSING),
])
def test_sunscreen_claims_that_cannot_be_compared_are_unverifiable(
    ad: str, document: str, reason: CosmeticVerdictReason,
) -> None:
    decision = _decide(ad, document)
    assert decision.verdict is Verdict.UNVERIFIABLE and decision.reason is reason


def test_the_separate_index_items_of_the_record_must_agree_with_the_sentence() -> None:
    same = _decide("SPF50+ PA++++ 자외선 차단 기능성 화장품입니다.", SUN50, spf="SPF50+", pa="4")
    assert same.verdict is Verdict.CONFIRMED

    # The record's own items disagree with its sentence: the index is not confirmed against either.
    for fields in ({"spf": "45", "pa": "4"}, {"spf": "50+", "pa": "3"}):
        held = _decide("SPF50+ PA++++ 자외선 차단 기능성 화장품입니다.", SUN50, **fields)
        assert held.verdict is Verdict.UNVERIFIABLE and held.reason is R.OFFICIAL_SUNSCREEN_INDEX_CONFLICTING
    # … and only an index above both is an overstatement.
    above_both = _decide("SPF50+ 선크림입니다.", f"{PROTECTS}(SPF47, PA+++)", spf="40", pa="3")
    assert above_both.verdict is Verdict.MISMATCH and above_both.reason is R.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL
    between = _decide("SPF45 선크림입니다.", f"{PROTECTS}(SPF47, PA+++)", spf="40", pa="3")
    assert between.verdict is Verdict.UNVERIFIABLE and between.reason is R.OFFICIAL_SUNSCREEN_INDEX_CONFLICTING
    # A claim without an index does not depend on the items.
    function_only = _decide("자외선 차단 기능성 화장품입니다.", SUN50, spf="45", pa="4")
    assert function_only.verdict is Verdict.CONFIRMED


def test_an_unread_neighbour_withholds_a_sunscreen_confirmation() -> None:
    decisions = _decide_all("단 하루. SPF50+ PA++++ 자외선 차단 기능성 화장품입니다.", _product(SUN50))
    assert [decision.reason for decision in decisions] == [R.AD_TEXT_NOT_FULLY_READ]


def test_the_receipt_shows_the_index_read_from_the_advertisement() -> None:
    ad = "SPF50+ PA++++ 자외선 차단 기능성 화장품입니다."
    product = _product(SUN30)
    receipt = build_cosmetic_receipt(ad, product, _decide_all(ad, product), AT)

    (claim,) = receipt.claims
    assert claim.verdict is Verdict.MISMATCH and claim.reason_code is R.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL
    assert claim.index_cues == ("SPF50+", "PA++++") and claim.functions == ("자외선 차단",)
    assert "지수" in claim.reason_message
