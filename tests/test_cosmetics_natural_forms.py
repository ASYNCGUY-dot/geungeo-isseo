"""Natural advertisement sentences: a recognized claim with an invitation around it (synthetic products).

The claim itself stays an allowlisted form. What may stand around it is an invitation to the reader
or a fixed statement by the seller, built from role-bound word lists: when, where, what, and an
action. The lists hold no subject, so a sentence cannot bring in a third party or another product,
and no noun that a time, an amount or an effect could attach to.
"""

import time
from datetime import UTC, datetime

import pytest

from claimledger.cosmetics_claims import (
    confirm_cosmetic_claims,
    extract_cosmetic_claims,
    neutral_sentences,
    unread_sentences,
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
    ("미백 케어에 도움을 드리는 제품", WHITENING),
    ("해당 제품은 미백과 주름개선에 도움을 줄 수 있습니다.", BOTH),
    # "도움이 되다" says the same as "도움을 주다".
    ("주름개선에 도움이 됩니다.", WRINKLE),
    # The claim, then an invitation to the reader: when, where, what, and an action.
    ("피부 미백에 도움을 주는 제품으로 저녁 루틴을 마무리해 보세요.", WHITENING),
    ("피부 미백에 도움을 줄 수 있는 제품, 지금 장바구니에 담아 보세요.", WHITENING),
    ("주름개선에 도움을 주는 제품으로 스킨케어루틴을 시작해보세요", WRINKLE),
    ("미백에 도움을 주는 기능성 화장품, 이제 온라인에서 편하게 구매하세요.", WHITENING),
    ("피부의 미백에 도움을 줄 수 있는 기능성 화장품으로 화장대를 채워 보세요", WHITENING),
    ("주름개선에 도움을 주는 기능성 화장품, 무료배송으로 받아 보세요", WRINKLE),
    ("주름개선에 도움을 주는 기능성 화장품은 여기에서 확인하세요", WRINKLE),
    ("주름개선에 도움을 주는 제품 구경하러 오세요", WRINKLE),
    ("미백과 주름개선에 도움을 주는 기능성 화장품, 둘러보세요.", BOTH),
    ("미백 기능성 화장품, 지금 만나 보세요", WHITENING),
    # A complete claim joined to an invitation by a comma, in either order.
    ("미백에 도움을 줍니다, 지금 바로 만나 보세요!", WHITENING),
    ("이 제품 한 번 써 보세요, 피부 미백에 도움을 줄 수 있습니다.", WHITENING),
    ("피부 미백에 도움을 줍니다, 자세한 내용은 상세 페이지에서 확인하세요", WHITENING),
    ("피부의 주름개선에 도움을 줍니다, 구매 전 상세 페이지를 천천히 읽어 보세요", WRINKLE),
    # A fixed statement by the seller about the product.
    ("미백에 도움을 주는 기능성 화장품 판매 중", WHITENING),
    ("피부의 주름개선에 도움을 주는 기능성 화장품을 소개합니다.", WRINKLE),
    ("미백에 도움을 주는 기능성 화장품이 재입고되었습니다!", WHITENING),
    ("미백에 도움을 주는 기능성 화장품, 오늘 매장에 입고되었습니다.", WHITENING),
    ("미백에 도움을 주는 제품, 상세 정보를 살펴주세요.", WHITENING),
    # How the product got to the shop, said before it.
    ("드디어 입고된 미백에 도움을 주는 기능성 화장품을 만나보세요", WHITENING),
    ("지금 이 페이지에서 만나는 주름개선에 도움을 주는 기능성 화장품", WRINKLE),
    ("새로 나온 미백 주름개선 기능성 화장품 보러 오세요", BOTH),
])
def test_a_claim_with_an_invitation_around_it_is_confirmed(ad: str, official: str) -> None:
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
    "효과가 입증된 미백에 도움을 주는 기능성 화장품을 만나보세요",
    "피부과에서 소개하는 미백에 도움을 주는 기능성 화장품을 만나보세요",
    "오늘 입고된 민감 피부 미백에 도움을 주는 제품입니다",
    "드디어 입고된 미백에 도움을 줍니다",
    # The claim is altered or reported, not stated.
    "미백에 큰 도움을 주는 제품입니다.",
    "미백에 도움을 준다는 이 제품, 요즘 저의 필수템이에요.",
    "미백에 도움을 주는 유일한 제품입니다.",
    "미백에 도움을 주는 제품 1위입니다.",
    "미백에 도움을 주는 제품입니다만 개인차가 있습니다.",
    "미백 이중 기능성 화장품입니다.",
    "주름개선 2중 기능성",
    "미백에 도움이 되지 않는 제품입니다.",
    # The product named is not necessarily this one, or is a kind the record does not show.
    "미백에 도움을 주는 제품과 함께 써 보세요.",
    "미백에 도움을 주는 제품보다 좋습니다.",
    "미백에 도움을 주는 제품을 골라 보세요.",
    "미백에 도움을 주는 제품만 있습니다.",
    "미백에 도움을 주는 기능성 화장품을 찾으시나요?",
    "미백에 도움을 주는 크림을 찾으신다면 고객센터로 문의해 주세요.",
    "미백에 도움을 주는 토너입니다.",
    # A word outside the role lists follows the claim.
    "미백에 도움을 주는 제품, 피부과 추천합니다.",
    "미백에 도움을 주는 제품으로 새로운 피부를 만나 보세요.",
    "미백에 도움을 주는 제품으로 2주 관리를 시작해 보세요.",
    "미백에 도움을 주는 제품으로 탄력 관리도 시작해 보세요.",
    "미백에 도움을 주는 제품으로 관리하면 좋습니다.",
    "미백에 도움을 주는 제품으로 저녁 루틴을 마무리해 보세요...",
    "미백에 도움을 주는 제품으로 저녁 루틴을 마무리해 볼까요?",
    "미백에 도움을 주는 기능성 화장품은 아닙니다",
    "미백에 도움을 주는 기능성 화장품 효과 안내",
    "미백에 도움을 주는 기능성 화장품, 사용 후 달라진 피부를 확인하세요",
    "미백에 도움을 주는 기능성 화장품, 1+1 행사",
    "미백에 도움을 주는 기능성 화장품, 지금 바로",
    "미백에 도움이 되는 기능성 화장품, 주름 관리도 가능합니다.",
])
def test_anything_outside_the_role_lists_keeps_the_sentence_unconfirmed(ad: str) -> None:
    decisions = _decide_all(ad, BOTH)
    assert decisions and all(decision.verdict is not Verdict.CONFIRMED for decision in decisions)
    assert all(decision.official_sentences == () for decision in decisions)


@pytest.mark.parametrize(("ad", "official"), [
    # Independent review of the first shop-language grammar (9db94c1): its words could be combined
    # into a time or frequency of the effect …
    ("미백에 도움을 주는 제품, 한번 사용으로 관리 완료입니다.", WHITENING),
    ("주름개선에 도움을 주는 제품, 밤 사용으로 아침에 확인해 보세요.", WRINKLE),
    ("미백에 도움을 주는 제품, 하루 사용으로 관리를 완성합니다.", WHITENING),
    ("주름개선에 도움을 주는 제품, 첫 사용부터 기능성을 경험해 보세요.", WRINKLE),
    ("미백 기능성 화장품, 사용 순간부터 기능성을 경험해 보실 수 있습니다.", WHITENING),
    ("미백에 도움을 주는 제품, 아침부터 밤까지 관리해 드립니다.", WHITENING),
    ("주름개선에 도움을 줍니다, 하루 사용으로 관리 완료입니다.", WRINKLE),
    # … into a claim about other products …
    ("미백에 도움을 주는 제품을 모았습니다.", WHITENING),
    ("미백에 도움을 주는 제품은 사은품입니다.", WHITENING),
    ("미백에 도움을 주는 제품은 전 제품입니다.", WHITENING),
    ("미백 기능성 화장품은 전 상품입니다.", WHITENING),
    ("사은품으로 준비한 미백에 도움을 주는 제품입니다.", WHITENING),
    ("주름개선에 도움을 주는 제품도 샘플로 드립니다.", WRINKLE),
    ("주름개선 기능성 화장품 기획전입니다.", WRINKLE),
    ("미백에 도움을 주는 제품 목록입니다.", WHITENING),
    ("사은품 샘플도 드립니다, 미백에 도움을 줍니다.", WHITENING),
    # … into an endorsement or evidence from a third party …
    ("미백에 도움을 주는 제품, 회원이 추천합니다.", WHITENING),
    ("주름개선에 도움을 주는 제품, 후기가 추천합니다.", WRINKLE),
    ("미백에 도움을 주는 제품이라서 회원이 추천합니다.", WHITENING),
    ("미백에 도움을 주는 제품, 회원이 다시 구매합니다.", WHITENING),
    ("미백에 도움을 주는 제품, 사용 전 사진을 후기에서 확인해 보세요.", WHITENING),
    ("주름개선에 도움을 주는 제품, 후기 사진으로 직접 확인해 보세요.", WRINKLE),
    ("회원이 소개하는 미백에 도움을 주는 제품입니다.", WHITENING),
    ("리뷰에 올라온 주름개선에 도움을 주는 제품입니다.", WRINKLE),
    ("방송에 나온 미백에 도움을 주는 기능성 화장품", WHITENING),
    ("미백에 도움을 주는 기능성 화장품, 많은 후기가 있습니다", WHITENING),
    # … and into a degree, a completion or a suitability.
    ("미백에 도움을 주는 제품, 한 단계 더 기능성을 경험해 보세요.", WHITENING),
    ("주름개선에 도움을 주는 제품, 더 꼼꼼한 기능성 케어를 경험해 보세요.", WRINKLE),
    ("미백에 도움을 주며, 피부관리를 완성합니다.", WHITENING),
    ("미백에 도움을 주는 제품, 꼭 관리를 완성해 드립니다.", WHITENING),
    ("미백에 도움을 주는 제품, 여러분께 알맞습니다.", WHITENING),
    # Second review (90f96ce): "check" with nothing to check, after "apply once", promises a result
    # at once; a seller statement with an argument becomes a claim of its own; "도" adds a product.
    ("주름개선에 도움을 주는 제품, 한 번 바로 확인해 보세요.", WRINKLE),
    ("한 번 발라 보세요, 주름개선에 도움을 줍니다, 바로 확인해 보세요.", WRINKLE),
    ("오늘 발라 보세요, 주름개선에 도움을 줍니다, 오늘 바로 확인하세요.", WRINKLE),
    ("이 제품 한 번 써 보세요, 미백에 도움을 줍니다, 지금 장바구니에 담아 보세요.", WHITENING),
    ("미백에 도움을 주는 제품, 온라인에서 추천합니다.", WHITENING),
    ("미백에 도움을 주는 제품, 꾸준히 판매 중입니다.", WHITENING),
    ("꾸준히 판매 중인 미백 기능성 화장품입니다.", WHITENING),
    ("먼저 출시된 미백 기능성 화장품입니다.", WHITENING),
    ("미백에 도움을 주는 제품, 일상을 추천합니다.", WHITENING),
    ("미백에 도움을 주는 제품도 판매합니다.", WHITENING),
    ("미백에 도움을 주는 제품, 살펴보세요.", WHITENING),
    # Third pass (f2936f9): a place in the reader's life or a store is where one looks at one's face.
    ("주름개선에 도움을 주는 제품, 화장대에서 한 번 바로 확인해 보세요.", WRINKLE),
    ("주름개선에 도움을 주는 제품, 매장에서 바로 확인해 보세요.", WRINKLE),
    # Fourth pass (3a8cf89): "구경하다" is a look as well.
    ("주름개선에 도움을 주는 제품, 화장대에서 한 번 바로 구경해 보세요.", WRINKLE),
    ("주름개선에 도움을 주는 제품, 일상에서 바로 둘러보세요.", WRINKLE),
])
def test_words_cannot_be_combined_into_content_of_their_own(ad: str, official: str) -> None:
    decisions = _decide_all(ad, official)
    assert decisions and all(decision.verdict is not Verdict.CONFIRMED for decision in decisions)


def test_a_fully_read_natural_sentence_can_show_a_missing_function() -> None:
    ad = "피부 미백과 주름개선에 도움을 주는 이 제품으로 스킨케어를 시작해 보세요."
    (decision,) = _decide_all(ad, WRINKLE)
    assert decision.verdict is Verdict.MISMATCH and decision.reason is R.FUNCTION_NOT_IN_OFFICIAL_EFFICACY


@pytest.mark.parametrize("ad", [
    # "Apply once. Check right away." beside a claim reads as a result at once. Each reviewed
    # grammar still let some pair through, so an advertisement gets one invitation, not several.
    "주름개선에 도움을 줍니다. 한 번 발라 보세요. 바로 확인해 보세요.",
    "주름개선에 도움을 줍니다. 사용 전 확인해 보세요. 한 번 써 보세요. 다시 확인해 보세요.",
    "주름개선에 도움을 줍니다. 한 번 발라 보세요. 화장대에서 바로 확인해 보세요.",
    "주름개선에 도움을 줍니다. 사용 전 화장대에서 확인해 보세요. 한 번 써 보세요. 화장대에서 다시 확인해 보세요.",
    "주름개선에 도움을 줍니다. 여기에 한 번 발라 보세요. 여기에서 바로 확인해 보세요.",
    "주름개선에 도움을 줍니다. 이곳에 한 번 발라 보세요. 이곳에서 지금 바로 확인하세요.",
    "주름개선에 도움을 줍니다. 한 번 발라 보세요. 화장대에서 바로 구경해 보세요.",
    "주름개선에 도움을 줍니다. 한 번 발라 보세요. 상세 페이지에서 확인해 보세요.",
    "주름개선에 도움을 줍니다. 한 번 발라 보세요. 바로 완성해 보세요.",
    # One inside the claim sentence and one beside it are two as well.
    "주름개선에 도움을 주는 제품, 지금 만나 보세요. 장바구니에 담아 보세요.",
    "장바구니에 담아 보세요. 한 번 써 보세요, 주름개선에 도움을 줍니다.",
])
def test_several_invitations_cannot_add_up_to_a_promise(ad: str) -> None:
    decisions = _decide_all(ad, WRINKLE)
    assert [decision.reason for decision in decisions] == [R.AD_TEXT_NOT_FULLY_READ]


def test_an_invitation_sentence_is_read_and_does_not_block_a_confirmation() -> None:
    ad = "미백에 도움을 줍니다.\n지금 장바구니에 담아 보세요!"
    decisions = _decide_all(ad, WHITENING)

    assert [decision.verdict for decision in decisions] == [Verdict.CONFIRMED]
    assert [item.text for item in neutral_sentences(ad)] == ["지금 장바구니에 담아 보세요!"]
    assert [ad[slice(*item.span)] for item in neutral_sentences(ad)] == [item.text for item in neutral_sentences(ad)]
    assert unread_sentences(ad) == ()
    assert [d.verdict for d in _decide_all("미백에 도움을 줍니다. 상세 페이지에서 확인해 보세요.", WHITENING)] == [
        Verdict.CONFIRMED
    ]
    # A second invitation is still shown as read text, but the confirmation is withheld.
    twice = ad + "\n매일 저녁 루틴에 더해 보세요."
    assert [decision.reason for decision in _decide_all(twice, WHITENING)] == [R.AD_TEXT_NOT_FULLY_READ]
    assert len(neutral_sentences(twice)) == 2 and unread_sentences(twice) == ()


@pytest.mark.parametrize("neighbour", [
    # A fragment without an action attaches to the claim beside it.
    "매일 저녁.",
    "꾸준히.",
    "지금 바로.",
    # Words outside the role lists.
    "단 2주면 충분합니다.",
    "피부과 추천합니다.",
    "촉촉한 사용감.",
    "지금 만나 볼까요?",
    "지금 만나 보세요...",
    # Sentences the first shop-language grammar read as claiming nothing.
    "한번 사용으로 관리 완료입니다.",
    "밤 사용으로 아침에 확인해 보세요.",
    "사은품 안내입니다.",
    "전 제품 기능성 화장품입니다.",
    "그 제품 이야기입니다.",
    "회원 후기입니다.",
    "회원이 추천합니다.",
    # "Check" needs something to check: the page or its information.
    "바로 확인해 보세요.",
    "사용 전 확인해 보세요.",
    "다시 확인해 보세요.",
    "꾸준히 판매 중입니다.",
    "화장대에서 바로 확인해 보세요.",
    "일상에서 바로 확인해 보세요.",
    "저녁 루틴에서 바로 확인하세요.",
    "매장에서 바로 살펴보세요.",
])
def test_other_text_beside_a_claim_still_blocks_the_confirmation(neighbour: str) -> None:
    for ad in (f"미백에 도움을 줍니다. {neighbour}", f"{neighbour} 미백에 도움을 줍니다."):
        decisions = _decide_all(ad, WHITENING)
        plain = [decision for decision in decisions if decision.claim.text == "미백에 도움을 줍니다."]
        assert [decision.reason for decision in plain] == [R.AD_TEXT_NOT_FULLY_READ]
        assert all(decision.verdict is not Verdict.CONFIRMED for decision in decisions)
        assert neutral_sentences(ad) == ()


@pytest.mark.parametrize("ad", [
    "미백" * 1250 + "," + "않" * 2499,
    "기미" * 1666 + "," + "않" * 1667,
    "미백에 도움을 주는 제품, " + "지금 " * 400 + "효과",
    "…" * 4999 + "a",
    "미백 도움 " + "." * 4990 + "a",
    "." * 4999 + "a",
    "1" * 5000,
])
def test_long_runs_are_read_in_linear_time(ad: str) -> None:
    product = _product(WHITENING)
    started = time.perf_counter()
    claims = confirm_cosmetic_claims(extract_cosmetic_claims(ad), "all")
    decisions = decide_cosmetic_ad(ad, claims, product)
    build_cosmetic_receipt(ad, product, decisions, AT)
    # The splitter and the word reading were quadratic or worse on these (about two seconds).
    assert time.perf_counter() - started < 1.0
    assert all(decision.verdict is not Verdict.CONFIRMED for decision in decisions)
