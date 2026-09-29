"""Synthetic developer regressions for the official clause gate, not an accuracy benchmark.

The P1-A cases reproduce the independent review of 688b9d4: annotations placed in a body (another
ingredient's block, a headerless preface, a second target block) were never checked.
"""

import time
from datetime import UTC, datetime

import pytest

from claimledger.claims_v1 import confirm_claims, extract_claims
from claimledger.domain import ConfirmedProduct, ProductCandidate, Verdict
from claimledger.official_v2 import known_clause_vocabulary, segment_body_clauses
from claimledger.verdict_v1 import decide_claim

AT = datetime(2026, 9, 29, tzinfo=UTC)
MEM = "[EPA 및 DHA 함유 유지] 기억력 개선에 도움을 줄 수 있음"
MEM_AD = "기억력 개선에 도움을 줄 수 있어요."
EYE = "노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음"


def _decide(ad: str, official: str):
    claims = confirm_claims(extract_claims(ad), "all")
    assert len(claims) == 1
    product = ProductCandidate(
        report_no="SYNTHETIC-C", name="합성 테스트 제품", company="합성 테스트 업체",
        primary_function=official, raw_materials="합성 fixture", intake_method="합성 fixture",
        source_id="C003", retrieved_at=AT,
    )
    return decide_claim(claims[0], ConfirmedProduct(product=product, confirmed_by_user=True))


@pytest.mark.parametrize("official", [
    MEM + "\n[아연] 정상적인 면역기능에 필요. 검토 중: 기억력 개선",
    MEM + "\n아연: 정상적인 면역기능에 필요 검토 중: 기억력 개선",
    MEM + " [비타민E] 기억력 개선 검토 중",
    MEM + "\n[은행잎추출물] 상기 기억력 개선 기능성은 재평가 중",
    MEM + "\n[아연] 기억력 개선 기능성 인정 취소",
    "기억력 개선 기능 재검토 중\n" + MEM,
    "(국문) 기억력 개선 재검토 대상\n" + MEM,
    "기능성 검토 중\n" + MEM,
    "[EPA 및 DHA 함유 유지]\n기억력 개선 검토 중\nEPA 및 DHA 함유 유지: 기억력 개선에 도움을 줄 수 있음",
    "[EPA 및 DHA 함유 유지]\n기억력 개선 검토 중\n- EPA 및 DHA 함유 유지: 기억력 개선에 도움을 줄 수 있음",
    MEM + "\n[오메가-3] 기억력 개선 재검토 중",
    MEM + "\n[프로바이오틱스] 기억력 개선 재검토 중",
    MEM + "\n[아연] 정상적인 면역기능에 필요\n【검토 중】 기억력 개선",
    MEM + "\n[아연] 정상적인 면역기능에 필요. 위 EPA 및 DHA 함유 유지 기능성 재평가 중",
    MEM + "\n[은행잎추출물] 기억력 개선은 검토 중이며 혈행 개선에 도움을 줄 수 있음",
])
def test_annotation_in_any_body_holds_the_field(official: str) -> None:
    decision = _decide(MEM_AD, official)
    assert decision.verdict is Verdict.UNVERIFIABLE
    assert decision.official_effect is None


@pytest.mark.parametrize("official", [
    MEM + "\n[아연] 정상적인 면역기능에 필요",
    "[비타민E] 항산화 작용을 하여 유해산소로부터 세포를 보호하는데 필요\n" + MEM,
    MEM + "\n[은행잎추출물] 기억력 개선·혈행 개선에 도움을 줄 수 있음",
])
def test_known_official_neighbour_clauses_keep_the_target_evidence(official: str) -> None:
    assert _decide(MEM_AD, official).verdict is Verdict.CONFIRMED


@pytest.mark.parametrize(("official", "ad"), [
    (
        (
            "[EPA 및 DHA 함유 유지] (가) 혈중 중성지질 개선·혈행 개선에 도움을 줄 수 있음 "
            "(나) 건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음"
        ),
        "건조한 눈 개선에 도움을 줄 수 있어요.",
    ),
    (
        (
            "[EPA 및 DHA 함유 유지] 혈중 중성지질 개선·혈행 개선에 도움을 줄 수 있음, "
            "건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음"
        ),
        "혈행 개선에 도움을 줄 수 있어요.",
    ),
    (
        "[프로바이오틱스] 유산균 증식 및 유해균 억제•배변활동 원활•장 건강에 도움을 줄 수 있음",
        "배변활동 원활에 도움을 줄 수 있어요.",
    ),
    (
        "[프로바이오틱스] 유산균 증식 및 유해균 억제ᆞ배변활동 원활에 도움을 줄 수 있음",
        "배변활동 원활에 도움을 줄 수 있어요.",
    ),
    (f"[마리골드꽃추출물] (국문) {EYE}", "눈 건강에 도움을 줄 수 있어요."),
])
def test_additional_official_statement_formats_are_supported(official: str, ad: str) -> None:
    decision = _decide(ad, official)
    assert decision.verdict is Verdict.CONFIRMED
    assert official[slice(*decision.official_effect.statement_span)] == (
        decision.official_effect.statement_text
    )


@pytest.mark.parametrize("official", [
    "[EPA 및 DHA 함유 유지] (가) 기억력 개선 검토 중 (나) 혈행 개선에 도움을 줄 수 있음",
    "[EPA 및 DHA 함유 유지] 혈행 개선에 도움을 줄 수 있음, 기억력 개선 검토 중",
    "[EPA 및 DHA 함유 유지] 기억력 개선, 혈행 개선에 도움을 줄 수 있음 / 검토 중",
    "[EPA 및 DHA 함유 유지] (국문) 기억력 개선 검토 중",
])
def test_new_formats_do_not_open_a_path_for_annotations(official: str) -> None:
    decision = _decide(MEM_AD, official)
    assert decision.verdict is not Verdict.CONFIRMED
    assert decision.official_effect is None


VITAMIN_A = (
    "[비타민A] 어두운 곳에서 시각 적응을 위해 필요 피부와 점막을 형성하고 기능을 유지하는데 필요 "
    "상피세포의 성장과 발달에 필요"
)


@pytest.mark.parametrize(("official", "ad"), [
    (
        (
            "[EPA 및 DHA 함유 유지] 혈중 중성지질 개선, 혈행 개선, "
            "건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음"
        ),
        "혈행 개선에 도움을 줄 수 있어요.",
    ),
    (MEM + "\n" + VITAMIN_A, MEM_AD),
])
def test_unseen_clause_is_accepted_only_when_fully_explained(official: str, ad: str) -> None:
    assert _decide(ad, official).verdict is Verdict.CONFIRMED


@pytest.mark.parametrize("official", [
    MEM + "\n" + VITAMIN_A + " 기억력 개선 재검토 중",
    MEM + "\n" + VITAMIN_A + " 보류",
    MEM + "\n[아연] 정상적인 면역기능에 필요 가 검토",
    "[EPA 및 DHA 함유 유지] 기억력 개선, 혈행 개선, 검토 중에 도움을 줄 수 있음",
])
def test_known_pieces_cannot_carry_unexplained_text(official: str) -> None:
    decision = _decide(MEM_AD, official)
    assert decision.verdict is not Verdict.CONFIRMED
    assert decision.official_effect is None


def test_hyphenation_point_is_an_effect_list_separator() -> None:
    official = "[EPA 및 DHA 함유 유지] 혈중 중성지질 개선‧혈행 개선에 도움을 줄 수 있음"
    assert _decide("혈행 개선에 도움을 줄 수 있어요.", official).verdict is Verdict.CONFIRMED
    assert segment_body_clauses(official) == ("혈중중성지질개선·혈행개선에도움을줄수있음",)


def test_long_unexplained_clause_is_rejected_quickly() -> None:
    official = MEM + "\n[아연] " + "필요" * 2000 + "X"
    start = time.perf_counter()
    decision = _decide(MEM_AD, official)
    assert time.perf_counter() - start < 1.0
    assert decision.verdict is Verdict.UNVERIFIABLE


def test_clause_segmentation_covers_every_body_span() -> None:
    text = (
        "기능성 안내\n"
        "[비타민E] ①항산화 작용을 하여 유해산소로부터 세포를 보호하는데 필요"
        "②정상적인 면역기능에 필요\n"
        "- 아연: (1) 정상적인 세포분열에 필요. (2) 1.5 mg 기준\n"
        "[프로바이오틱스] (국문) 유산균 증식 및 유해균 억제･배변활동 원활에 도움을 줄 수 있음."
    )
    assert segment_body_clauses(text) == (
        "기능성안내",
        "항산화작용을하여유해산소로부터세포를보호하는데필요",
        "정상적인면역기능에필요",
        "정상적인세포분열에필요",
        "1.5mg기준",
        "유산균증식및유해균억제·배변활동원활에도움을줄수있음",
    )


def test_clause_vocabulary_is_bound_to_its_source_and_review() -> None:
    vocabulary = known_clause_vocabulary()
    assert vocabulary.version == "official-clause-vocabulary-v1"
    assert vocabulary.source_id == "C003"
    assert len(vocabulary.source_sha256) == 64
    assert vocabulary.min_companies >= 2
    assert "정상적인면역기능에필요" in vocabulary.names
    assert not vocabulary.names & set(vocabulary.excluded)
    assert all(name and not any(ch.isspace() for ch in name) for name in vocabulary.names)
