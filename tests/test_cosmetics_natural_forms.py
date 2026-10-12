"""Natural advertisement sentences: a recognized claim with selling language around it (synthetic products).

The claim itself stays an allowlisted form. What may stand around it is a closed vocabulary of
invitations to use or buy; any other word keeps the sentence unread.
"""

from datetime import UTC, datetime

import pytest

from claimledger.cosmetics_claims import (
    confirm_cosmetic_claims,
    extract_cosmetic_claims,
    neutral_sentences,
    unread_sentences,
)
from claimledger.cosmetics_verdict import (
    ConfirmedCosmetic,
    CosmeticDecision,
    CosmeticVerdictReason,
    decide_cosmetic_ad,
)
from claimledger.domain import Verdict
from claimledger.sources.functional_cosmetics import FunctionalCosmetic

AT = datetime(2026, 10, 12, tzinfo=UTC)
R = CosmeticVerdictReason
WHITENING = "피부의 미백에 도움을 준다."
WRINKLE = "피부의 주름개선에 도움을 준다."
BOTH = f"{WHITENING} {WRINKLE}"


def _product(sentence: str) -> ConfirmedCosmetic:
    product = FunctionalCosmetic(
        record_id="SYNTHETIC-1", item_name="합성 테스트 크림", company="합성 테스트 업체",
        registered_on="20250102", effect_text="", effect_name=sentence,
        source_id="data.go.kr:15095680", retrieved_at=AT,
    )
    return ConfirmedCosmetic(product=product, confirmed_by_user=True)


def _decide_all(ad: str, official: str) -> tuple[CosmeticDecision, ...]:
    claims = confirm_cosmetic_claims(extract_cosmetic_claims(ad), "all")
    return decide_cosmetic_ad(ad, claims, _product(official))


@pytest.mark.parametrize(("ad", "official"), [
    # The claim describes the product: "…에 도움을 주는 제품".
    ("미백에 도움을 주는 제품입니다.", WHITENING),
    ("피부 미백에 도움을 줄 수 있는 기능성 화장품입니다.", WHITENING),
    ("미백에 도움을 주는 데일리 케어 제품입니다.", WHITENING),
    ("주름개선에 도움을 줄 수 있는, 매일 쓰는 케어 제품입니다.", WRINKLE),
    ("피부 미백과 주름개선 모두에 도움을 줄 수 있는 기능성 제품입니다.", BOTH),
    ("이 제품은 피부 주름개선에 도움을 주는 크림이에요.", WRINKLE),
    ("미백 케어에 도움을 드리는 제품", WHITENING),
    # The claim, then an invitation to use or buy the product.
    ("피부 미백에 도움을 주는 제품으로 저녁 루틴을 마무리해 보세요.", WHITENING),
    ("피부 미백에 도움을 줄 수 있는 제품, 지금 장바구니에 담아 보세요.", WHITENING),
    ("미백에 도움을 줄 수 있는 이 제품을 일상 습관으로 만들어 보세요.", WHITENING),
    ("피부 미백 관리에 도움을 주는 제품으로 한 단계 더 신경 써 보세요.", WHITENING),
    ("피부 주름개선에 도움을 주는 제품이라 꾸준한 관리에 알맞습니다.", WRINKLE),
    ("주름개선에 도움을 주는 제품으로 스킨케어루틴을 시작해보세요", WRINKLE),
    # A complete claim joined to an invitation by a comma, in either order.
    ("미백에 도움을 줍니다, 지금 바로 만나 보세요!", WHITENING),
    ("이 제품 한 번 써 보세요, 피부 미백에 도움을 줄 수 있습니다.", WHITENING),
])
def test_a_claim_with_selling_language_around_it_is_confirmed(ad: str, official: str) -> None:
    (decision,) = _decide_all(ad, official)
    assert decision.verdict is Verdict.CONFIRMED and decision.reason is R.MATCHES_OFFICIAL_EFFICACY
    assert {item.function for item in decision.official_sentences} == set(decision.claim.function_candidates)


@pytest.mark.parametrize("ad", [
    # Something stands before the claim: a target, a condition, another subject.
    "민감한 피부의 미백에 도움을 주는 제품입니다.",
    "나이아신아마이드가 미백에 도움을 주는 제품입니다.",
    "매일 쓰면 미백에 도움을 주는 제품입니다.",
    "꾸준히 바르면 피부 미백에 도움을 줄 수 있습니다.",
    "루틴이 미백에 도움을 줍니다.",
    "매일 저녁 관리가 미백에 도움을 줍니다.",
    "지금 써 보세요 미백에 도움을 줍니다.",
    # "이중 기능성" needs both functions named.
    "미백 이중 기능성 화장품입니다.",
    "주름개선 2중 기능성",
    # The claim is altered or reported, not stated.
    "미백에 큰 도움을 주는 제품입니다.",
    "미백에 도움을 준다는 이 제품, 요즘 저의 필수템이에요.",
    "미백에 도움을 주는 유일한 제품입니다.",
    "미백에 도움을 주는 제품 1위입니다.",
    "미백에 도움을 주는 제품입니다만 개인차가 있습니다.",
    # The product named is not necessarily this one.
    "미백에 도움을 주는 제품과 함께 써 보세요.",
    "미백에 도움을 주는 제품보다 좋습니다.",
    "미백에 도움을 주는 제품을 골라 보세요.",
    "미백에 도움을 주는 제품만 있습니다.",
    # A word outside the closed vocabulary follows the claim.
    "미백에 도움을 주는 제품, 피부과 추천합니다.",
    "미백에 도움을 주는 제품으로 새로운 피부를 만나 보세요.",
    "미백에 도움을 주는 제품으로 2주 관리를 시작해 보세요.",
    "미백에 도움을 주는 제품으로 탄력 관리도 시작해 보세요.",
    "미백에 도움을 주는 제품으로 관리하면 좋습니다.",
    "미백에 도움을 주는 제품으로 저녁 루틴을 마무리해 보세요...",
    "미백에 도움을 주는 제품으로 저녁 루틴을 마무리해 볼까요?",
])
def test_anything_outside_the_closed_vocabulary_keeps_the_sentence_unconfirmed(ad: str) -> None:
    decisions = _decide_all(ad, BOTH)
    assert decisions and all(decision.verdict is not Verdict.CONFIRMED for decision in decisions)
    assert all(decision.official_sentences == () for decision in decisions)


def test_a_fully_read_natural_sentence_can_show_a_missing_function() -> None:
    ad = "피부 미백과 주름개선에 도움을 주는 이 제품으로 스킨케어를 시작해 보세요."
    (decision,) = _decide_all(ad, WRINKLE)
    assert decision.verdict is Verdict.MISMATCH and decision.reason is R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY


def test_an_invitation_sentence_is_read_and_does_not_block_a_confirmation() -> None:
    ad = "미백에 도움을 줍니다. 지금 장바구니에 담아 보세요!\n매일 저녁 루틴에 더해 보세요."
    decisions = _decide_all(ad, WHITENING)

    assert [decision.verdict for decision in decisions] == [Verdict.CONFIRMED]
    assert [item.text for item in neutral_sentences(ad)] == ["지금 장바구니에 담아 보세요!", "매일 저녁 루틴에 더해 보세요."]
    assert [ad[slice(*item.span)] for item in neutral_sentences(ad)] == [item.text for item in neutral_sentences(ad)]
    assert unread_sentences(ad) == ()


@pytest.mark.parametrize("neighbour", [
    # A fragment without a predicate attaches to the claim beside it.
    "매일 저녁.",
    "꾸준히.",
    "한 단계 더.",
    # Words outside the vocabulary.
    "단 2주면 충분합니다.",
    "피부과 추천합니다.",
    "촉촉한 사용감.",
    "지금 만나 볼까요?",
    "지금 만나 보세요...",
])
def test_other_text_beside_a_claim_still_blocks_the_confirmation(neighbour: str) -> None:
    for ad in (f"미백에 도움을 줍니다. {neighbour}", f"{neighbour} 미백에 도움을 줍니다."):
        decisions = _decide_all(ad, WHITENING)
        assert [decision.reason for decision in decisions] == [R.AD_TEXT_NOT_FULLY_READ]
        assert neutral_sentences(ad) == () and [item.text for item in unread_sentences(ad)] == [neighbour]


@pytest.mark.parametrize(("ad", "official"), [
    # Shop language after the product: the page, the purchase, the delivery.
    ("미백에 도움을 주는 기능성 화장품 판매 중", WHITENING),
    ("미백에 도움을 주는 기능성 화장품 입고 소식입니다", WHITENING),
    ("미백에 도움을 주는 기능성 화장품, 이제 온라인에서 편하게 구매하세요.", WHITENING),
    ("피부의 미백에 도움을 줄 수 있는 기능성 화장품으로 화장대를 채워 보세요", WHITENING),
    ("미백에 도움을 주는 기능성 화장품입니다, 많은 관심 부탁드립니다", WHITENING),
    ("피부 미백에 도움을 줍니다, 자세한 내용은 상세 페이지에서 확인하세요", WHITENING),
    ("피부의 주름개선에 도움을 주는 기능성 화장품을 소개합니다.", WRINKLE),
    ("피부의 주름개선에 도움을 줍니다, 구매 전 상세 페이지를 천천히 읽어 보세요", WRINKLE),
    ("주름개선에 도움을 주는 기능성 화장품, 무료배송으로 받아 보세요", WRINKLE),
    ("주름개선에 도움을 주는 기능성 화장품은 여기에서 확인하세요", WRINKLE),
    ("주름개선에 도움을 주는 제품입니다, 구매 전에 문의 환영합니다", WRINKLE),
    ("피부 주름개선에 도움을 줄 수 있는 기능성 화장품, 사진과 설명으로 만나 보세요", WRINKLE),
    ("미백과 주름개선에 도움을 주는 제품을 이번에 새롭게 선보입니다", BOTH),
    ("주름개선에 도움을 주는 기능성 화장품이 필요하다면 눌러 보세요", WRINKLE),
    ("미백에 도움을 주는 기능성 화장품 특가 행사 중입니다", WHITENING),
    # The official name of the kind of product, then an invitation.
    ("미백 기능성 화장품, 지금 만나 보세요", WHITENING),
    ("새로 나온 미백 주름개선 기능성 화장품 보러 오세요", BOTH),
    # "도움이 되다" says the same as "도움을 주다".
    ("주름개선에 도움이 됩니다.", WRINKLE),
    ("미백에 도움이 되는 기능성 화장품을 정성껏 준비했습니다.", WHITENING),
    ("미백에 도움을 주는 기능성 화장품이 재입고되었습니다!", WHITENING),
    ("피부 미백에 도움을 주는 기능성 화장품, 선물 포장도 가능합니다.", WHITENING),
    ("주름개선에 도움을 주는 제품 구경하러 오세요", WRINKLE),
    ("미백과 주름개선에 도움을 주는 기능성 화장품, 둘러보고 가세요.", BOTH),
    # Shop language before the product, describing how it got there.
    ("드디어 입고된 미백에 도움을 주는 기능성 화장품을 만나보세요", WHITENING),
    ("지금 이 페이지에서 만나는 주름개선에 도움을 주는 기능성 화장품", WRINKLE),
    ("신제품 출시 소식입니다, 피부의 주름개선에 도움을 주는 기능성 화장품이에요", WRINKLE),
    ("해당 제품은 미백과 주름개선에 도움을 줄 수 있습니다.", BOTH),
])
def test_shop_language_around_a_claim_is_read(ad: str, official: str) -> None:
    (decision,) = _decide_all(ad, official)
    assert decision.verdict is Verdict.CONFIRMED and decision.reason is R.MATCHES_OFFICIAL_EFFICACY


@pytest.mark.parametrize("ad", [
    # A word outside the vocabulary before the product.
    "효과가 입증된 미백에 도움을 주는 기능성 화장품을 만나보세요",
    "피부과에서 소개하는 미백에 도움을 주는 기능성 화장품을 만나보세요",
    "오늘 입고된 민감 피부 미백에 도움을 주는 제품입니다",
    "후기가 많은 미백에 도움을 주는 기능성 화장품",
    "고객님이 추천하는 미백에 도움을 주는 기능성 화장품",
    "꾸준히 관리한 미백에 도움을 주는 제품입니다",
    # The describing clause must describe a product, not the effect.
    "드디어 입고된 미백에 도움을 줍니다",
    # After the product: another product, a comparison, a denial, an effect, an endorsement.
    "미백에 도움을 주는 기능성 화장품과 함께 써 보세요",
    "미백에 도움을 주는 기능성 화장품보다 좋은 선택",
    "미백에 도움을 주는 기능성 화장품은 아닙니다",
    "미백에 도움을 주는 기능성 화장품 효과 안내",
    "미백에 도움을 주는 기능성 화장품, 후기가 증명합니다",
    "미백에 도움을 주는 기능성 화장품, 고객님이 추천합니다",
    # Appearing on television and the number of reviews are claims of their own.
    "방송에 나온 미백에 도움을 주는 기능성 화장품",
    "미백에 도움을 주는 기능성 화장품, 많은 후기가 있습니다",
    "미백에 도움을 주는 기능성 화장품, 방송에서 소개했습니다",
    "미백에 도움을 주는 기능성 화장품, 사용 후 달라진 피부를 확인하세요",
    "미백에 도움을 주는 기능성 화장품, 1+1 행사",
    "미백에 도움을 주는 기능성 화장품을 찾으시나요?",
    "미백에 도움을 주는 기능성 화장품, 지금 바로",
    "미백에 도움이 되지 않는 제품입니다.",
    "미백에 도움이 되는 기능성 화장품, 주름 관리도 가능합니다.",
    "미백에 도움이 되는 기능성 화장품, 탄력 관리도 가능합니다.",
])
def test_shop_language_does_not_carry_other_content(ad: str) -> None:
    decisions = _decide_all(ad, BOTH)
    assert decisions and all(decision.verdict is not Verdict.CONFIRMED for decision in decisions)


def test_a_long_run_of_vocabulary_words_is_read_in_linear_time() -> None:
    # Grouping nouns in every possible way would take exponential time on a sentence that fails.
    ad = "미백에 도움을 주는 제품, " + "제품 " * 400 + "효과"
    (decision,) = _decide_all(ad, WHITENING)
    assert decision.verdict is Verdict.UNVERIFIABLE
    assert unread_sentences("제품 " * 600 + "효과") != ()
