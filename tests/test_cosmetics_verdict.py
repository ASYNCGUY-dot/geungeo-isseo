"""Whitening and wrinkle claims against a functional cosmetic's official efficacy (synthetic products)."""

import unicodedata
from datetime import UTC, datetime

import pytest

from claimledger.claims_v1 import ExpressionStrength
from claimledger.cosmetics_claims import (
    MAX_AD_TEXT_LENGTH,
    asserted_functions,
    confirm_cosmetic_claims,
    extract_cosmetic_claims,
    unread_sentences,
)
from claimledger.cosmetics_official import CosmeticFunction
from claimledger.cosmetics_verdict import (
    COSMETIC_VERDICT_VERSION,
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
BOTH = f"{WHITENING} {WRINKLE}"
SUN = "자외선으로부터 피부를 보호한다.(SPF50+, PA++++)"
LIP = "입술의 주름개선에 도움을 준다."


def _product(sentence: str = "", document: str = "", **fields: object) -> ConfirmedCosmetic:
    product = FunctionalCosmetic(
        record_id="SYNTHETIC-1", item_name="합성 테스트 크림", company="합성 테스트 업체",
        registered_on="20250102", effect_text=document, effect_name=sentence,
        source_id="data.go.kr:15095680", retrieved_at=AT, **fields,
    )
    return ConfirmedCosmetic(product=product, confirmed_by_user=True)


def _official(text: str) -> ConfirmedCosmetic:
    # Sunscreen and lip-wrinkle wording exists only in the document form.
    return _product(document=text) if text in (SUN, LIP) else _product(sentence=text)


def _decide_all(ad: str, product: ConfirmedCosmetic | None) -> tuple[CosmeticDecision, ...]:
    claims = confirm_cosmetic_claims(extract_cosmetic_claims(ad), "all")
    return decide_cosmetic_ad(ad, claims, product)


def _decide(ad: str, product: ConfirmedCosmetic | None) -> CosmeticDecision:
    decisions = _decide_all(ad, product)
    assert len(decisions) == 1, "A risky sentence must remain visible for review"
    return decisions[0]


def test_extraction_reads_functions_and_strength_with_literal_spans() -> None:
    text = "피부 미백에 도움을 줍니다.\n주름을 확실하게 없애줍니다!\n본 제품은 의약품이 아닙니다.\n촉촉한 사용감."
    claims = extract_cosmetic_claims(text)

    assert [claim.claim_id for claim in claims] == ["C1", "C2"]
    assert claims[0].function_candidates == (F.WHITENING,) and claims[0].strength is ExpressionStrength.SUPPORT
    assert claims[1].function_candidates == (F.WRINKLE,) and claims[1].strength is ExpressionStrength.GUARANTEE
    assert text[slice(*claims[1].span)] == "주름을 확실하게 없애줍니다!"
    assert claims[0].function_cues == ("미백",) and not claims[0].confirmed_by_user
    assert claims[0].set_aside_cues == ()


def test_sentences_without_a_claim_stay_visible_as_unread_text() -> None:
    text = "단 2주. 미백에 도움을 줍니다.\n본 제품은 의약품이 아닙니다.\n촉촉한 사용감."
    unread = unread_sentences(text)

    # The disclaimer is a recognized form; the other two were not read at all.
    assert [item.text for item in unread] == ["단 2주.", "촉촉한 사용감."]
    assert [text[slice(*item.span)] for item in unread] == ["단 2주.", "촉촉한 사용감."]
    assert unread_sentences("미백에 도움을 줍니다. 본 제품은 의약품이 아닙니다.") == ()


def test_words_before_a_denial_caution_or_question_are_set_aside() -> None:
    def read(ad: str) -> tuple[tuple[F, ...], ExpressionStrength | None, tuple[str, ...]]:
        (claim,) = extract_cosmetic_claims(ad)
        return claim.function_candidates, claim.strength, claim.set_aside_cues

    # What stands before the denial is what is denied; what follows it is still said.
    assert read("주름 완화가 아니라 주름 제거입니다.") == ((F.WRINKLE,), ExpressionStrength.IMPROVEMENT, ("주름", "완화"))
    assert read("끈적이지 않고 주름을 100% 없애줍니다.") == ((F.WRINKLE,), ExpressionStrength.GUARANTEE, ())
    assert read("미백 효과를 100% 보장하지는 않습니다.") == ((), None, ("미백", "100%", "보장"))
    assert read("주름개선 되나요?") == ((), None, ("주름",))
    # The denial inside "부작용 없는" is the assurance itself.
    assert read("부작용 없는 미백 크림") == ((F.WHITENING,), ExpressionStrength.GUARANTEE, ())
    # A weak word alone does not make a claim of a sentence.
    assert extract_cosmetic_claims("도움이 되지 않습니다.") == ()


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
    ("눈가 주름 케어에 도움을 드립니다.", WHITENING, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    # A lip-wrinkle product does not cover whitening at all.
    ("미백과 주름개선에 도움을 줍니다.", LIP, R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY),
    # Stronger than "도움을 준다".
    ("주름을 개선합니다.", WRINKLE, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("주름 개선해 줍니다.", WRINKLE, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("주름개선됩니다.", WRINKLE, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("주름이 좋아집니다.", WRINKLE, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("즉시 주름이 사라집니다.", WRINKLE, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("피부가 하얗게 밝아지는 미백 크림", WHITENING, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("미백 효과 100% 보장", WHITENING, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("7일 만에 주름개선에 도움을 줍니다.", WRINKLE, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("부작용 없는 미백 크림", WHITENING, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("주름을 완벽하게 없애줍니다.", LIP, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    # A denial of something else leaves the claim after it standing.
    ("끈적이지 않고 주름을 100% 없애줍니다.", WRINKLE, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("미백뿐 아니라 주름까지 완벽하게 제거", WRINKLE, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("주름 완화가 아니라 주름 제거입니다.", WRINKLE, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    ("시술 없이도 주름이 사라집니다.", WRINKLE, R.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL),
    # Medical wording is outside what a cosmetic may claim, whatever the product.
    ("기미를 치료하는 미백 크림", WHITENING, R.MEDICAL_CLAIM_BEYOND_COSMETIC_SCOPE),
    ("피부 재생으로 주름개선에 도움을 줍니다.", WRINKLE, R.MEDICAL_CLAIM_BEYOND_COSMETIC_SCOPE),
    ("세포 재생 크림", WRINKLE, R.MEDICAL_CLAIM_BEYOND_COSMETIC_SCOPE),
    ("의사가 처방한 미백 크림", WHITENING, R.MEDICAL_CLAIM_BEYOND_COSMETIC_SCOPE),
    ("피부과 처방 그대로 담았습니다.", WHITENING, R.MEDICAL_CLAIM_BEYOND_COSMETIC_SCOPE),
    ("보톡스 맞은 듯한 주름개선", WRINKLE, R.MEDICAL_CLAIM_BEYOND_COSMETIC_SCOPE),
    ("필러 맞은 듯한 주름개선", WRINKLE, R.MEDICAL_CLAIM_BEYOND_COSMETIC_SCOPE),
])
def test_claims_beyond_the_official_efficacy_are_mismatches(
    ad: str, official: str, reason: CosmeticVerdictReason,
) -> None:
    decision = _decide(ad, _official(official))
    assert decision.verdict is Verdict.MISMATCH and decision.reason is reason
    assert decision.official_sentences == ()


@pytest.mark.parametrize("ad", [
    # Subjects, conditions and extra content the rules cannot read stay unresolved.
    "나이아신아마이드가 피부 미백에 도움을 줍니다.",
    "미백에 도움을 주고 피부결도 매끄럽게 가꿔 줍니다.",
    "민감한 피부의 미백에 도움을 줍니다.",
    "미백에 3배 도움을 줍니다.",
    "화이트닝에 도움을 줍니다.",
    "미백과 주름개선, 탄력에 도움을 줍니다.",
    "미백 기능성 인증을 받은 유일한 화장품입니다.",
    # "필러" in a product type is not the injection.
    "링클 필러 크림은 주름개선 기능성화장품입니다.",
    # A trailing continuation is not a complete sentence.
    "미백에 도움을 줍니다…",
    "미백에 도움을 줍니다...",
    "미백에 도움을 줍니다!!",
])
def test_unreadable_claims_are_not_confirmed(ad: str) -> None:
    decision = _decide(ad, _product(sentence=BOTH))
    assert decision.verdict is Verdict.UNVERIFIABLE and decision.official_sentences == ()
    assert decision.reason is R.CLAIM_SCOPE_UNRESOLVED


@pytest.mark.parametrize(("ad", "official"), [
    # A fragment or sentence the rules did not read can change what the recognized sentence says.
    ("단 2주. 미백에 도움을 줍니다.", BOTH),
    ("아래 문구는 사실이 아닙니다. 미백에 도움을 줍니다.", BOTH),
    ("미백에 도움을 줍니다. 라고는 할 수 없습니다.", BOTH),
    ("미백에 도움을 줍니다.\n촉촉한 사용감.", BOTH),
    ("미백에 도움을 줍니다. 의약품이 아닙니다...", BOTH),
    # The neighbour is extracted but held.
    ("단 2주 만에. 미백에 도움을 줍니다.", BOTH),
    ("미백에 도움을 줍니다. 부작용이 전혀 없습니다.", BOTH),
    ("미백에 도움을 줍니다. 자외선 차단에 도움을 줍니다.", BOTH),
    ("미백에 도움을 줍니다. 정말 100% 미백이 될까요?", WHITENING),
    # The neighbour is flagged, for a reason that says nothing about the recognized sentence: a
    # condition, a subject or a denial of it hides behind the cue word (independent review, P1).
    ("미백에 도움을 줍니다. 주름을 완벽하게 제거합니다.", BOTH),
    ("미백에 도움을 줍니다. (피부과 시술 병행 시)", BOTH),
    ("미백에 도움을 줍니다. (아토피 피부에 한함)", BOTH),
    ("미백에 도움을 줍니다. 단, 피부과 시술을 받은 분에 한합니다.", WHITENING),
    ("주름개선에 도움을 줍니다. *보톡스 시술 병행 기준", BOTH),
    ("보톡스 성분이. 미백에 도움을 줍니다.", WHITENING),
    ("미백에 도움을 줍니다. 는 미백을 과장한 100% 거짓.", BOTH),
    ("미백에 도움을 줍니다. 정말 100% 미백이 될까요.", WHITENING),
    ("단 2주 만에 미백. 미백에 도움을 줍니다.", BOTH),
    ("미백에 도움을 줍니다. 단, 주름이 없는 피부에서만 그럴 수 있음.", WHITENING),
    ("주름개선에 도움을 줍니다. 단, 기미가 없는 피부에 한해 도움이 될 수 있음.", WRINKLE),
    ("미백에 도움을 줍니다. 습진, 피부염이 있는 부위에는 사용하지 말 것", BOTH),
])
def test_nothing_is_confirmed_beside_a_sentence_that_was_not_read_completely(ad: str, official: str) -> None:
    decisions = _decide_all(ad, _official(official))

    assert all(decision.verdict is not Verdict.CONFIRMED for decision in decisions)
    assert all(decision.official_sentences == () for decision in decisions)
    recognized = [decision for decision in decisions if asserted_functions(decision.claim) is not None]
    assert len(recognized) == 1 and recognized[0].reason is R.AD_TEXT_NOT_FULLY_READ


@pytest.mark.parametrize("ad", [
    "미백에 도움을 줍니다... 라고는 할 수 없습니다.",
    "미백에 도움을 줍니다… 라고는 할 수 없습니다.",
])
def test_an_ellipsis_before_a_denial_leaves_nothing_to_confirm(ad: str) -> None:
    decisions = _decide_all(ad, _product(sentence=BOTH))

    assert [decision.reason for decision in decisions] == [R.CLAIM_SCOPE_UNRESOLVED]
    assert [item.text for item in unread_sentences(ad)] == ["라고는 할 수 없습니다."]


def test_recognized_neighbours_do_not_block_a_confirmation() -> None:
    both, whitening = _product(sentence=BOTH), _product(sentence=WHITENING)

    def verdicts(ad: str, product: ConfirmedCosmetic) -> list[Verdict]:
        return [decision.verdict for decision in _decide_all(ad, product)]

    # Each sentence is a recognized form on its own, so one cannot quietly change the other.
    assert verdicts("미백에 도움을 줍니다. 주름개선에 도움을 줍니다.", whitening) == [Verdict.CONFIRMED, Verdict.MISMATCH]
    assert verdicts("미백 기능성화장품입니다. 주름개선 기능성화장품입니다.", both) == [Verdict.CONFIRMED, Verdict.CONFIRMED]
    assert verdicts("미백에 도움을 줍니다. 본 제품은 의약품이 아닙니다.", both) == [Verdict.CONFIRMED]
    # A recognized sentence the user left out is still a sentence the rules read completely.
    ad = "미백에 도움을 줍니다. 주름개선에 도움을 줍니다."
    partly = decide_cosmetic_ad(ad, confirm_cosmetic_claims(extract_cosmetic_claims(ad), ["C2"]), both)
    assert [decision.reason for decision in partly] == [R.CLAIM_UNCONFIRMED, R.MATCHES_OFFICIAL_EFFICACY]


def test_claims_must_be_the_ones_extracted_from_the_same_text() -> None:
    product = _product(sentence=BOTH)
    claims = confirm_cosmetic_claims(extract_cosmetic_claims("미백에 도움을 줍니다."), "all")

    with pytest.raises(ValueError):
        decide_cosmetic_ad("단 2주. 미백에 도움을 줍니다.", claims, product)
    with pytest.raises(ValueError):
        decide_cosmetic_ad("미백에 도움을 줍니다. 주름을 완벽하게 제거합니다.", claims, product)
    # A claim whose reading was altered after extraction is refused as well.
    ad = "미백에 도움을 줍니다. 부작용이 전혀 없습니다."
    honest = confirm_cosmetic_claims(extract_cosmetic_claims(ad), "all")
    altered = (honest[0], honest[1].model_copy(update={"strength": ExpressionStrength.TREATMENT_PREVENTION}))
    with pytest.raises(ValueError):
        decide_cosmetic_ad(ad, altered, product)
    with pytest.raises(ValueError):
        extract_cosmetic_claims("가" * (MAX_AD_TEXT_LENGTH + 1))


@pytest.mark.parametrize(("product", "reason"), [
    (_product(), R.OFFICIAL_EFFICACY_MISSING),
    (_product(document=f"{WHITENING}\n※ 해당하는 효능효과 이외에는 모두 삭제하시기 바랍니다."), R.OFFICIAL_EFFICACY_TEMPLATE_REMNANT),
    (_product(sentence=WHITENING, document=SUN), R.OFFICIAL_EFFICACY_CONFLICTING),
    (_product(document="피부의 미백에 도움은 준다."), R.OFFICIAL_EFFICACY_UNRECOGNIZED),
    # A document that could not be read is not replaced by the sentence beside it.
    (_product(sentence=WHITENING, effect_doc="<DOC><TABLE/></DOC>", effect_doc_unreadable=True), R.OFFICIAL_EFFICACY_UNRECOGNIZED),
    (_product(sentence=WHITENING, withdrawn=True), R.OFFICIAL_RECORD_WITHDRAWN),
])
def test_official_data_that_cannot_be_trusted_never_clears_or_condemns(
    product: ConfirmedCosmetic, reason: CosmeticVerdictReason,
) -> None:
    for ad in ("미백에 도움을 줍니다.", "주름개선에 도움을 줍니다.", "미백 효과 100% 보장"):
        decision = _decide(ad, product)
        assert decision.verdict is Verdict.UNVERIFIABLE and decision.reason is reason


def test_identity_and_claim_confirmation_gates() -> None:
    ad = "미백에 도움을 줍니다."
    claims = extract_cosmetic_claims(ad)
    product = _product(sentence=WHITENING)

    assert decide_cosmetic_ad(ad, claims, product)[0].reason is R.CLAIM_UNCONFIRMED
    confirmed = confirm_cosmetic_claims(claims, ["C1"])
    assert decide_cosmetic_ad(ad, confirmed, None)[0].reason is R.PRODUCT_IDENTITY_UNCONFIRMED
    unconfirmed = ConfirmedCosmetic(product=product.product, confirmed_by_user=False)
    assert decide_cosmetic_ad(ad, confirmed, unconfirmed)[0].reason is R.PRODUCT_IDENTITY_UNCONFIRMED
    assert decide_cosmetic_ad(ad, confirmed, product)[0].verdict is Verdict.CONFIRMED
    with pytest.raises(ValueError):
        confirm_cosmetic_claims(claims, ["C9"])


@pytest.mark.parametrize(("ad", "reason"), [
    ("자외선 차단에 도움을 줍니다.", R.FUNCTION_RULE_NOT_READY),
    ("미백과 자외선 차단에 도움을 줍니다.", R.FUNCTION_RULE_NOT_READY),
    ("주름개선 선크림", R.FUNCTION_RULE_NOT_READY),
    ("입술 주름개선에 도움을 줍니다.", R.FUNCTION_RULE_NOT_READY),
    ("탈모 증상 완화에 도움을 줍니다.", R.FUNCTION_RULE_NOT_READY),
    ("피부 탄력을 확실하게 높여 줍니다.", R.CLAIM_OUTSIDE_RULE_SCOPE),
    ("미백 크림", R.CLAIM_STRENGTH_UNCLEAR),
    # "주름개선" names the function: on its own it is neither a strength nor a sunscreen ("선크림").
    ("주름개선 화장품", R.CLAIM_STRENGTH_UNCLEAR),
    ("주름개선 크림", R.CLAIM_STRENGTH_UNCLEAR),
    ("주름 개선 효과", R.CLAIM_STRENGTH_UNCLEAR),
    # Words with an everyday meaning do not condemn a sentence about something else.
    ("미백 크림이 즉시 흡수됩니다.", R.CLAIM_STRENGTH_UNCLEAR),
    ("미백 크림, 향이 좋아요.", R.CLAIM_STRENGTH_UNCLEAR),
    ("미백 제품 사용 중 부작용이 있을 수 있습니다.", R.CLAIM_SCOPE_UNRESOLVED),
    ("저자극 처방의 미백 크림", R.CLAIM_STRENGTH_UNCLEAR),
    ("재생 플라스틱 용기에 담은 미백 크림", R.CLAIM_STRENGTH_UNCLEAR),
])
def test_claims_outside_the_first_two_functions_are_unverifiable(
    ad: str, reason: CosmeticVerdictReason,
) -> None:
    document = f"{WHITENING}\n{WRINKLE}\n{SUN}\n{LIP}"
    decision = _decide(ad, _product(document=document))
    assert decision.verdict is Verdict.UNVERIFIABLE and decision.reason is reason


@pytest.mark.parametrize("ad", ["저자극 처방으로 만들었습니다.", "재생 플라스틱 용기를 사용했습니다."])
def test_a_sentence_about_formulation_or_packaging_is_not_a_claim(ad: str) -> None:
    assert extract_cosmetic_claims(ad) == ()
    assert [item.text for item in unread_sentences(ad)] == [ad]


@pytest.mark.parametrize(("ad", "official"), [
    # A caution to the reader names a condition; it does not claim to treat it.
    ("피부 질환이 있는 분은 사용 전 전문의와 상담하세요.", BOTH),
    ("염증이 있는 부위에는 사용하지 마세요.", BOTH),
    ("미백 제품 사용 중 부작용이 있으면 사용을 중지하세요.", BOTH),
    ("주름 시술 직후 이상이 있으면 사용을 중지할 것", WRINKLE),
    ("피부 질환이 있는 부위에는 사용을 피하세요.", BOTH),
    ("습진 및 피부염 등의 이상이 있는 부위에는 사용하지 말 것", BOTH),
    ("아토피가 있으신 분은 패치 테스트 후 사용하세요.", BOTH),
    ("염증 부위 사용 금지", BOTH),
    ("피부염이 생기면 사용 중단", BOTH),
    ("질환이 있는 경우 전문의 상담 필요", BOTH),
    ("피부과 시술 후에는 사용 전 의사와 상의하세요.", BOTH),
    ("상처나 흉터가 있는 부위에는 바르지 마세요.", BOTH),
    ("흉터가 남을 수 있으니 상처 부위는 피해 주세요.", BOTH),
    # A denied or questioned effect is not that claim, whatever the cue words say.
    ("질병 치료 목적의 제품이 아닙니다.", BOTH),
    ("이 제품은 피부 질환을 치료하지 않습니다.", BOTH),
    ("의약품처럼 염증을 없애는 제품은 아니에요.", BOTH),
    ("질병 치료용이 아닌 화장품입니다.", BOTH),
    ("본 제품은 질병을 치료하는 의약품이 아니라 화장품입니다.", BOTH),
    ("치료 효과는 없습니다.", BOTH),
    ("피부과 전문의가 처방하는 의약품과는 다릅니다.", BOTH),
    ("병원 처방 없이 구매할 수 있는 화장품입니다.", BOTH),
    ("보톡스 시술이 아닌 바르는 화장품", BOTH),
    ("주름을 완전히 없애주지는 않습니다.", WRINKLE),
    ("주름을 완전히 없애지는 못합니다.", WRINKLE),
    ("주름을 100% 없앨 수는 없습니다.", WRINKLE),
    ("주름이 100% 사라지는 것은 아니며 개인차가 있습니다.", WRINKLE),
    ("주름을 완벽하게 없애준다는 광고는 믿지 마세요.", WRINKLE),
    ("주름을 없애주는 제품은 아니지만 꾸준히 사용해 보세요.", WRINKLE),
    ("미백 효과를 100% 보장하지는 않습니다.", WHITENING),
    ("미백 효과를 보장하지 않으며 개인차가 있습니다.", WHITENING),
    ("미백 효과를 100% 보장하는 화장품은 없습니다.", WHITENING),
    ("미백에 도움이 되지 않습니다.", BOTH),
    ("미백 기능성화장품이 아닙니다.", SUN),
    ("주름개선에 도움을 주지 않습니다.", SUN),
    ("미백에는 도움을 주지 않는 제품입니다.", WRINKLE),
    ("미백, 주름개선 기능성은 없는 제품입니다.", SUN),
    ("주름이 사라질까요?", WRINKLE),
    ("주름개선 되나요?", SUN),
    ("미백에 도움을 줄 수 있나요?", BOTH),
])
def test_a_denied_or_questioned_effect_is_neither_cleared_nor_condemned(ad: str, official: str) -> None:
    decision = _decide(ad, _official(official))
    assert decision.verdict is Verdict.UNVERIFIABLE and decision.reason is R.CLAIM_NOT_PLAINLY_ASSERTED
    assert decision.claim.set_aside_cues


@pytest.mark.parametrize(("ad", "official"), [
    # Naming a function the product lacks is not a claim to it: "수 있" alone says too little.
    ("미백 제품과 함께 사용할 수 있습니다.", WRINKLE),
    ("주름이 생기기 쉬운 눈가에도 사용할 수 있습니다.", WHITENING),
    ("기미는 호르몬 변화로 생길 수 있습니다.", WRINKLE),
    ("주름은 나이가 들면 누구에게나 생길 수 있습니다.", WHITENING),
    ("기미, 주근깨가 걱정되는 분도 사용할 수 있습니다.", WRINKLE),
    # What is left after the denial does not claim the function either.
    ("주름개선 기능성 화장품은 아니며 보습 크림입니다.", WHITENING),
])
def test_a_function_word_without_a_claim_does_not_condemn(ad: str, official: str) -> None:
    decisions = _decide_all(ad, _official(official))
    assert all(decision.verdict is Verdict.UNVERIFIABLE for decision in decisions)


def test_a_safety_assurance_stays_visible_as_an_unverified_claim() -> None:
    decisions = _decide_all("미백에 도움을 줍니다. 부작용이 전혀 없습니다.", _product(sentence=BOTH))
    assert [decision.reason for decision in decisions] == [R.AD_TEXT_NOT_FULLY_READ, R.CLAIM_OUTSIDE_RULE_SCOPE]
    # In one sentence the assurance blocks the confirmation as well.
    joined = _decide("미백에 도움을 주며 부작용이 없습니다.", _product(sentence=BOTH))
    assert joined.verdict is Verdict.MISMATCH and joined.claim.set_aside_cues == ()


def test_a_lip_wrinkle_product_does_not_clear_or_condemn_a_skin_wrinkle_claim() -> None:
    decision = _decide("주름개선에 도움을 줍니다.", _product(document=LIP))
    assert decision.verdict is Verdict.UNVERIFIABLE and decision.reason is R.CLAIM_SCOPE_UNRESOLVED


def test_decomposed_hangul_is_read_like_composed_text() -> None:
    # Text copied from some systems arrives as separate jamo (NFD), and files may start with a BOM.
    ad = unicodedata.normalize("NFD", "주름을 확실하게 없애줍니다.")
    decision = _decide(ad, _product(sentence=WRINKLE))

    assert decision.verdict is Verdict.MISMATCH and decision.claim.text == "주름을 확실하게 없애줍니다."
    plain = "\ufeff" + unicodedata.normalize("NFD", "미백에 도움을 줍니다.")
    assert _decide(plain, _product(sentence=WHITENING)).verdict is Verdict.CONFIRMED
