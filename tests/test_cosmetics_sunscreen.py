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


def _product(document: str, sentence: str = "", item_name: str = "합성 테스트 크림", **fields: object) -> ConfirmedCosmetic:
    product = FunctionalCosmetic(
        record_id="SYNTHETIC-1", item_name=item_name, company="합성 테스트 업체",
        registered_on="20250102", effect_text=document, effect_name=sentence,
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


def test_official_fields_with_different_indexes_hold_the_product() -> None:
    # The same function in both fields, but 50+ in one and 30 in the other (independent review, P1).
    efficacy = parse_cosmetic_efficacy(SUN50, SUN30)
    assert efficacy.status is EfficacyStatus.CONFLICTING_FIELDS and efficacy.sunscreen_index is None
    assert parse_cosmetic_efficacy(SUN50, PROTECTS).status is EfficacyStatus.CONFLICTING_FIELDS
    assert parse_cosmetic_efficacy(SUN50, f"{PROTECTS} (SPF50+, PA++++)").status is EfficacyStatus.READABLE

    held = _decide("SPF50+ PA++++ 자외선 차단 기능성 화장품입니다.", SUN50, sentence=SUN30)
    assert held.verdict is Verdict.UNVERIFIABLE and held.reason is R.OFFICIAL_EFFICACY_CONFLICTING


def test_the_index_of_an_advertisement_is_read_word_by_word() -> None:
    def index(ad: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        (claim,) = extract_cosmetic_claims(ad)
        return claim.spf, claim.pa, claim.water

    assert index("SPF50+ PA++++ 지속내수성 선크림입니다.") == (("50+",), ("++++",), ("지속내수성",))
    assert index("자외선 차단 지수 SPF 30, PA ++ 제품입니다.") == (("30",), ("++",), ())
    assert index("(SPF50+/PA+++) 자외선 차단 기능성 화장품입니다.") == (("50+",), ("+++",), ())
    # A number or a plus sign of the next word is not part of the index (independent review).
    assert index("데일리 선크림 SPF30 50ml.") == (("30",), (), ())
    assert index("SPF35 01호 화사한 베이지 쿠션, 자외선 차단.") == (("35",), (), ())
    # A lone "+" or digit in the next word may belong to the value ("SPF50 +", "SPF 5 0"): the
    # value is not known, so it is kept as unread.
    assert index("선크림 SPF50+ PA+++ + 선스틱 증정.") == (("50+",), ("?",), ())
    assert index("SPF30 + 수분크림 세트, 자외선 차단.") == (("?",), (), ())
    assert index("SPF 5 0 + 자외선 차단.") == (("?",), (), ())
    assert index("UVA PA++++ 차단 선크림.") == ((), ("++++",), ())
    # A label whose value cannot be read is kept as unread, so nothing is compared.
    assert index("비비크림 SPF47+++ 자외선 차단.") == (("?",), (), ())
    assert index("PA+++++ 선크림.") == ((), ("?",), ())
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
    # The same index as the official one, before or after the claim, or with the kind of product.
    ("자외선으로부터 피부를 보호합니다(SPF50+, PA++++).", SUN50),
    ("SPF50+ PA++++ 자외선 차단 기능성 화장품입니다.", SUN50),
    ("SPF30 PA++ 자외선 차단 기능성 화장품입니다.", SUN30),
    ("SPF 30 자외선 차단 기능성 화장품입니다.", SUN30_NO_GRADE),
    ("자외선 차단 기능성 화장품입니다 (SPF30/PA++, 내수성).", SUN30_RESISTANT),
    ("SPF50+ PA++++ 선크림입니다.", SUN50),
    ("자외선 차단 지수 SPF50+ PA++++", SUN50),
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
    # The product was not reported for sun protection: a fully read sentence says it has it.
    ("자외선 차단에 도움을 줍니다.", WHITENING, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    ("자외선으로부터 피부를 보호합니다.", f"{WHITENING}\n{WRINKLE}", R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    ("SPF50+ PA++++ 선크림입니다.", WHITENING, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    ("미백·주름개선·자외선 차단 3중 기능성 화장품입니다.", WHITENING_SUN, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    # … or names sun protection as what is helped, or blocks "100%".
    ("자외선 차단에 도움을 주는 크림으로 하루를 시작하세요.", WHITENING, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    ("미백과 자외선 차단에 도움을 주는 제품으로 매일 가볍게 관리하세요.", WHITENING, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    ("자외선을 100% 차단합니다.", WHITENING, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    # A sunscreen advertised for a function it was not reported for.
    ("미백과 주름개선에 도움을 주는 선크림입니다.", SUN50, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    ("미백에 도움을 주는 SPF50+ 선크림으로 하루를 시작합니다.", SUN50, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    ("미백·주름개선 기능성 선크림으로 하루를 시작합니다.", SUN50, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    # A higher index than the official one, in a sentence that was read completely.
    ("SPF50+ PA++++ 자외선 차단 기능성 화장품입니다.", SUN30, R.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL),
    ("자외선으로부터 피부를 보호합니다(SPF30, PA+++).", SUN30, R.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL),
    ("SPF50+ 선크림입니다.", f"{PROTECTS}(SPF50, PA+++)", R.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL),
    ("SPF50+ PA++++", SUN30, R.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL),
    # A grade or water resistance the official index does not hold.
    ("SPF30 PA++ 자외선 차단 기능성 화장품입니다.", SUN30_NO_GRADE, R.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL),
    ("SPF50+ PA++++ 지속내수성 선크림입니다.", SUN50, R.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL),
    ("SPF30 PA++ 지속내수성 선크림입니다.", SUN30_RESISTANT, R.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL),
    # Stronger than the official sentence: an absolute word on the blocking itself.
    ("자외선을 100% 차단합니다.", SUN50, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("자외선을 완벽하게 막아 주는 SPF50+ PA++++ 선크림.", SUN50, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("자외선으로부터 피부를 완벽하게 보호합니다.", SUN50, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("자외선 차단율 100%.", SUN50, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
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
    # A space inside the index: the form reads one value, the words another (independent review, P1).
    ("SPF50+ PA++++ 지속 내수성 선크림입니다.", f"{PROTECTS}(SPF50+, PA++++, 내수성)", R.SUNSCREEN_INDEX_UNCLEAR),
    ("SPF50+ PA++++ 지속내수 성 자외선 차단에 도움을 줄 수 있습니다.", SUN50, R.SUNSCREEN_INDEX_UNCLEAR),
    ("SPF50+ PA++++ 내수 성.", SUN50, R.SUNSCREEN_INDEX_UNCLEAR),
    ("S PF100 선크림입니다.", SUN30, R.SUNSCREEN_INDEX_UNCLEAR),
    ("S PF50+ 내수성 본 제품은 자외선으로부터 피부를 보호해 줍니다.", SUN30_RESISTANT, R.SUNSCREEN_INDEX_UNCLEAR),
    ("이 제품은 자외선 차단에 도움을 주는기능성 화장품 S PF50!", PROTECTS, R.SUNSCREEN_INDEX_UNCLEAR),
    ("SPF7 0+ 선크림입니다.", f"{PROTECTS}(SPF7)", R.SUNSCREEN_INDEX_UNCLEAR),
    ("SPF50 +.", f"{PROTECTS}(SPF 50)", R.SUNSCREEN_INDEX_UNCLEAR),
    ("SPF50 +PA++++.", f"{PROTECTS}(SPF50, PA++++)", R.SUNSCREEN_INDEX_UNCLEAR),
    # "SPF50 +" may be 50 or 50+: it confirms neither.
    ("SPF50 + PA++++ 자외선 차단 기능성 화장품입니다.", SUN50, R.SUNSCREEN_INDEX_UNCLEAR),
    ("SPF50 + PA++++ 자외선 차단 기능성 화장품입니다.", f"{PROTECTS}(SPF50, PA++++)", R.SUNSCREEN_INDEX_UNCLEAR),
    # The official sentence has no index to compare with.
    ("SPF50+ PA++++ 자외선 차단 기능성 화장품입니다.", PROTECTS, R.OFFICIAL_SUNSCREEN_INDEX_MISSING),
    ("SPF50+ 선크림입니다.", PROTECTS, R.OFFICIAL_SUNSCREEN_INDEX_MISSING),
    # Two values in one sentence: which one is claimed is not known.
    ("SPF30 PA++ 자외선 차단 기능성 화장품입니다 (SPF50+, PA++++).", SUN50, R.SUNSCREEN_INDEX_UNCLEAR),
    # An index in a sentence that was not read completely is not compared: it may belong to a
    # comparison, a recommendation or another product.
    ("가볍게 발리는 SPF50+ PA++++ 선크림으로 하루를 시작합니다.", SUN50, R.CLAIM_SCOPE_UNRESOLVED),
    ("SPF50 선크림으로 매일 가볍게 마무리합니다.", SUN30, R.CLAIM_SCOPE_UNRESOLVED),
    ("땀과 물에 강한 워터프루프 SPF50+ 선크림입니다.", SUN50, R.CLAIM_SCOPE_UNRESOLVED),
    ("SPF30에서 SPF50+로 달라진 선크림입니다.", SUN50, R.CLAIM_SCOPE_UNRESOLVED),
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


@pytest.mark.parametrize(("ad", "document"), [
    # Advice to use a sunscreen with a product that is none (retinol and whitening care).
    ("낮에는 SPF30 이상의 자외선 차단제를 함께 사용하세요.", WRINKLE),
    ("아침에는 SPF50+ 선크림과 함께 사용하세요.", WHITENING),
    ("SPF50+ 선크림 전 단계에 사용하세요.", WHITENING),
    ("PA++++는 가장 높은 등급입니다.", WHITENING),
    ("자외선 차단제를 반드시 함께 사용하세요.", WHITENING),
    ("자외선 차단제와 함께 사용하면 도움이 됩니다.", WHITENING),
    ("자외선이 강한 여름철 피부 보습에 도움을 줍니다.", WHITENING),
    ("자외선 차단 용기로 성분 보존에 도움을 줍니다.", WRINKLE),
    ("선크림 전 단계에 사용하면 흡수에 도움이 됩니다.", WHITENING),
    # A comparison, a recommendation or another product's index.
    ("SPF50+ 제품보다 순한 데일리 선크림입니다.", SUN30),
    ("SPF50+보다 낮지만 매일 쓰기에는 충분합니다.", SUN30),
    ("야외에서는 SPF50+ 제품을, 실내에서는 이 제품을 쓰세요.", SUN30),
    ("SPF50+ PA++++ 선스틱과 함께 쓰면 좋은 데일리 선크림.", SUN30),
    ("야외 활동에는 PA+++ 이상 제품을 권장합니다.", SUN30),
    ("SPF50+ PA++++ 선크림을 덧바르면 자외선 차단에 도움이 됩니다.", SUN30),
    # The volume, the shade number or a gift after the index.
    ("데일리 선크림 SPF30 50ml.", SUN30),
    ("SPF30 24시간 촉촉한 선크림.", SUN30),
    ("선크림 SPF50+ PA+++ + 선스틱 증정.", f"{PROTECTS}(SPF50+, PA+++)"),
    # Water resistance of something else, in a sentence about another function.
    ("워터프루프 마스카라와 함께 써도 좋은 미백 기능성 아이크림.", TRIPLE),
    ("내수성 좋은 파우치에 담아 드리는 미백 기능성 크림.", TRIPLE),
    ("내수성이 뛰어난 용기에 담은 SPF50+ 선크림.", SUN50),
    # Effect verbs and absolute words that are not about the sun protection.
    ("자외선 차단제를 반드시 함께 사용하세요.", SUN50),
    ("이지워시 선크림.", SUN50),
    ("세안제로 쉽게 지워지는 이지워시 선크림.", SUN50),
    ("밀림 현상을 개선했습니다, 데일리 선크림.", SUN50),
    ("피부 톤이 밝아 보이는 톤업 선크림.", SUN50),
    ("눈시림 걱정을 줄여 주는 순한 선크림.", SUN50),
    ("동백 퍼펙트 내추럴 썬크림.", SUN50),
    ("100% 무기자차 선크림입니다.", SUN50),
    ("완벽한 밀착력의 SPF50+ PA++++ 선크림.", SUN50),
    # A help phrase that belongs to another product beside the sunscreen.
    ("미백에 도움을 주는 세럼 다음에 바르는 SPF50+ 선크림.", SUN50),
    ("미백 기능성 토너 증정, SPF50+ PA++++ 선크림.", SUN50),
    ("미백·주름개선 기능성 앰플과 함께 쓰는 선크림.", SUN50),
    # An absolute word on what something else blocks or protects (independent review).
    ("자외선 100% 차단 용기에 담아 신선하게 보관했습니다.", WHITENING),
    ("자외선 100% 차단 용기에 담아 신선하게 보관했습니다.", SUN50),
    ("자외선 차단 100% 파우치에 담아 드립니다.", WRINKLE),
    ("자외선을 완벽 차단하는 선글라스와 함께 쓰세요.", WHITENING),
    ("자외선을 확실하게 막아 주는 모자를 함께 쓰세요.", SUN50),
    ("자외선 차단율 100% 양산과 함께 쓰면 좋아요.", WHITENING),
    ("피부를 완벽하게 보호하는 보습막, 외출 전에는 자외선 차단제도 함께 바르세요.", WHITENING),
    # The sunscreen a help phrase describes is another product.
    ("주름개선에 도움을 주는 선크림과 함께 쓰는 수분 크림.", SUN50),
    ("미백에 도움을 주는 선크림 전용 클렌저.", SUN50),
    # The letters of a product kind inside another word.
    ("생선젤라틴 콜라겐으로 탄력에 도움을 줍니다.", WHITENING),
    ("우선크림부터 바르면 흡수에 도움이 됩니다.", WRINKLE),
])
def test_a_sunscreen_word_without_a_claim_does_not_condemn(ad: str, document: str) -> None:
    decisions = _decide_all(ad, _product(document))
    assert all(decision.verdict is Verdict.UNVERIFIABLE for decision in decisions)


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


@pytest.mark.parametrize("fields", [
    # Items seen in the export that are no plain value (independent review, P1): nothing is taken
    # from an item that was not read, so it cannot agree with the sentence either.
    {"spf": "SPF38,PA++", "pa": "2"},
    {"spf": "54.1", "pa": "2"},
    {"spf": "33-41", "pa": "2"},
    {"spf": "SPF+", "pa": "2"},
    {"spf": "47", "pa": "²"},
    {"spf": "47", "pa": "++"},
])
def test_an_index_item_that_was_not_read_withholds_the_confirmation(fields: dict[str, str]) -> None:
    held = _decide("SPF47 PA++ 자외선 차단 기능성 화장품입니다.", f"{PROTECTS}(SPF47, PA ++)", **fields)
    assert held.verdict is Verdict.UNVERIFIABLE and held.reason is R.OFFICIAL_SUNSCREEN_INDEX_CONFLICTING


@pytest.mark.parametrize("fields", [
    {"spf": "50+", "pa": "3"},
    {"spf": "", "pa": "2"},
    {"item_name": "합성 마일드 선크림 SPF50+ PA++++"},
    {"sunscreen": True},
])
def test_a_record_that_names_sun_protection_elsewhere_is_not_called_without_it(fields: dict[str, object]) -> None:
    # The efficacy sentence has no sun protection, but the record's own items or name say otherwise.
    held = _decide("자외선 차단 기능성 화장품입니다.", WHITENING, **fields)
    assert held.verdict is Verdict.UNVERIFIABLE and held.reason is R.OFFICIAL_SUNSCREEN_RECORD_CONFLICTING
    # A PA item of 0 says "no grade", and other functions are judged as before.
    plain = _decide("자외선 차단 기능성 화장품입니다.", WHITENING, pa="0")
    assert plain.verdict is Verdict.MISMATCH and plain.reason is R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY
    other = _decide("주름개선에 도움을 줍니다.", WHITENING, **fields)
    assert other.verdict is Verdict.MISMATCH and other.reason is R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY


def test_a_form_whose_functions_are_not_its_cue_words_is_not_confirmed() -> None:
    # "자 외선" is no cue word, but the form without spaces reads sun protection.
    decision = _decide("주름개선과 자 외선 차단 기능성 화장품입니다.", TRIPLE)
    assert decision.verdict is Verdict.UNVERIFIABLE and decision.reason is R.CLAIM_SCOPE_UNRESOLVED


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
