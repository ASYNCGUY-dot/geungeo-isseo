"""Synthetic regressions for review finding P2 (step 2): another ingredient's official statement
joined under a target header. Not an accuracy benchmark."""

from datetime import UTC, datetime

import pytest

from claimledger.carriers import foreign_statements
from claimledger.claims_v1 import confirm_claims, extract_claims
from claimledger.domain import ConfirmedProduct, IngredientGroup, ProductCandidate, Verdict
from claimledger.receipt import build_receipt
from claimledger.verdict_v1 import VerdictReason, decide_claim

AT = datetime(2026, 9, 30, tzinfo=UTC)
EPA = "[EPA 및 DHA 함유 유지] 혈중 중성지질 개선·혈행 개선에 도움을 줄 수 있음"
GINKGO = "기억력 개선·혈행 개선에 도움을 줄 수 있음"
MEMORY_AD = "오메가3는 기억력 개선에 도움을 줄 수 있어요."
RAW_WITH_GINKGO = "EPA 및 DHA 함유 유지, 은행잎추출물(고시형), 비타민E"


def _decide(ad: str, official: str, raw: str):
    claims = confirm_claims(extract_claims(ad), "all")
    assert len(claims) == 1
    product = ProductCandidate(
        report_no="SYNTHETIC-P2", name="합성 테스트 제품", company="합성 테스트 업체",
        primary_function=official, raw_materials=raw, intake_method="합성 fixture",
        source_id="C003", retrieved_at=AT,
    )
    return decide_claim(claims[0], ConfirmedProduct(product=product, confirmed_by_user=True))


@pytest.mark.parametrize("joiner", [", ", " / ", ". ", "\n"])
def test_other_ingredients_statement_under_the_header_is_held(joiner: str) -> None:
    decision = _decide(MEMORY_AD, EPA + joiner + GINKGO, RAW_WITH_GINKGO)
    assert decision.verdict is Verdict.UNVERIFIABLE
    assert decision.reason is VerdictReason.OFFICIAL_STATEMENT_OF_OTHER_INGREDIENT
    assert decision.official_effect is None


# v2.10 reads U+2024 as a middle dot; the borrowed-statement check must read it the same way, or
# "기억력 개선․혈행 개선…" slips past it (found while building headerless attribution, 2026-10-01).
@pytest.mark.parametrize("official", [
    "[EPA 및 DHA 함유 유지] 기억력 개선․혈행 개선에 도움을 줄 수 있음",
    EPA + ", 기억력 개선․혈행 개선에 도움을 줄 수 있음",
    "[EPA 및 DHA 함유 유지] 혈중 중성지질 개선․혈행 개선에 도움을 줄 수 있음 / 기억력 개선․ 혈행 개선에 도움을 줄 수 있음",
])
def test_one_dot_leader_does_not_hide_another_ingredients_statement(official: str) -> None:
    decision = _decide(MEMORY_AD, official, RAW_WITH_GINKGO)
    assert decision.verdict is Verdict.UNVERIFIABLE
    assert decision.reason is VerdictReason.OFFICIAL_STATEMENT_OF_OTHER_INGREDIENT


@pytest.mark.parametrize(("official", "raw", "ad"), [
    (EPA + ", " + GINKGO, "EPA 및 DHA 함유 유지, 비타민E", MEMORY_AD),
    (EPA + ", " + GINKGO + "\n[은행잎추출물] " + GINKGO, RAW_WITH_GINKGO, MEMORY_AD),
    (EPA + ", " + GINKGO, RAW_WITH_GINKGO, "오메가3는 혈행 개선에 도움을 줄 수 있어요."),
    (
        "[프로바이오틱스] ① 유산균 증식 및 유해균 억제에 도움을 줄 수 있음 ② 배변활동 원활에 도움을 줄 수 있음",
        "프로바이오틱스, 차전자피식이섬유",
        "배변활동 원활에 도움을 줄 수 있어요.",
    ),
])
def test_header_ingredients_own_statements_stay_confirmed(official: str, raw: str, ad: str) -> None:
    assert _decide(ad, official, raw).verdict is Verdict.CONFIRMED


def test_only_distinctive_statements_of_other_notified_ingredients_are_listed() -> None:
    omega = {(item.name, item.statement) for item in foreign_statements(IngredientGroup.OMEGA3)}
    probiotics = {item.statement for item in foreign_statements(IngredientGroup.PROBIOTICS)}

    assert ("은행잎 추출물", "기억력개선·혈행개선에도움을줄수있음") in omega
    assert "배변활동원활에도움을줄수있음" not in probiotics


def test_receipt_explains_the_hold() -> None:
    official = EPA + ", " + GINKGO
    decision = _decide(MEMORY_AD, official, RAW_WITH_GINKGO)
    product = ConfirmedProduct(
        product=ProductCandidate(
            report_no="SYNTHETIC-P2", name="합성 테스트 제품", company="합성 테스트 업체",
            primary_function=official, raw_materials=RAW_WITH_GINKGO, intake_method="합성 fixture",
            source_id="C003", retrieved_at=AT,
        ),
        confirmed_by_user=True,
    )
    receipt = build_receipt(MEMORY_AD, product, [decision], AT)
    assert receipt.claims[0].verdict_label == "검증 불가"
    assert "다른" in receipt.claims[0].reason_message
    assert receipt.rule_versions[-1] == "claim-verdict-v1.4"
