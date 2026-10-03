"""Advertisement wording accepted for confirmation (claim-extract-v1.3); synthetic developer cases.

claim-eval-v1 showed that common wording inside the official scope fell to unverifiable. The grammar
is widened by an allowlist; dose, frequency, population, comparison and extra content stay held.
"""

from datetime import UTC, datetime

import pytest

from claimledger.claims_v1 import confirm_claims, extract_claims
from claimledger.domain import ConfirmedProduct, ProductCandidate, Verdict
from claimledger.verdict_v1 import VerdictReason, decide_claim

AT = datetime(2026, 10, 4, tzinfo=UTC)
EYE = "[루테인] 노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음"
OMEGA = "[EPA 및 DHA 함유 유지] 혈중 중성지질 개선·혈행 개선·기억력 개선·건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음"
PROBIOTIC = "[프로바이오틱스] 유산균 증식 및 유해균 억제·배변활동 원활·장 건강에 도움을 줄 수 있음"


def _decide(ad: str, official: str):
    claims = confirm_claims(extract_claims(ad), "all")
    assert len(claims) == 1, "A risky sentence must remain visible for review"
    product = ProductCandidate(
        report_no="SYNTHETIC-G", name="합성 테스트 제품", company="합성 테스트 업체",
        primary_function=official, raw_materials="합성 fixture", intake_method="합성 fixture",
        source_id="C003", retrieved_at=AT,
    )
    return decide_claim(claims[0], ConfirmedProduct(product=product, confirmed_by_user=True))


@pytest.mark.parametrize(("ad", "official"), [
    ("오메가3는 혈중 중성지질을 개선하는 데 도움을 줄 수 있습니다.", OMEGA),
    ("오메가3는 혈행을 개선하는 데 도움을 줄 수 있어요.", OMEGA),
    ("오메가3는 기억력 개선에 도움을 줄 수 있는 기능성 원료입니다.", OMEGA),
    ("오메가3는 혈행 개선에 도움을 줄 수 있는 원료예요.", OMEGA),
    ("꾸준히 섭취하는 오메가3는 기억력 개선에 도움을 줄 수 있습니다.", OMEGA),
    ("매일 챙기는 오메가3는 혈중 중성지질 개선에 도움이 될 수 있습니다.", OMEGA),
    ("오메가3는 건조한 눈 개선으로 눈 건강에 도움을 줄 수 있습니다.", OMEGA),
    ("오메가3는 건조한 눈을 개선해 눈 건강 관리에 도움을 줄 수 있습니다.", OMEGA),
    ("루테인은 황반색소밀도 유지에 도움을 줄 수 있습니다.", EYE),
    ("루테인은 황반색소밀도의 유지로 눈 건강 관리에 도움을 줄 수 있습니다.", EYE),
    ("루테인은 황반색소밀도 유지를 통해 눈 건강을 챙기는 데 도움을 줄 수 있습니다.", EYE),
    ("루테인은 황반색소밀도를 유지하는 데 도움을 줄 수 있습니다.", EYE),
    ("프로바이오틱스는 유산균의 증식과 유해균의 억제에 도움을 줄 수 있습니다.", PROBIOTIC),
    ("프로바이오틱스는 유해균 억제와 유산균 증식에 도움이 될 수 있어요.", PROBIOTIC),
    ("프로바이오틱스는 원활한 배변활동에 도움을 줄 수 있습니다.", PROBIOTIC),
    ("매일 먹는 프로바이오틱스는 배변활동을 원활하게 하는 데 도움을 줄 수 있습니다.", PROBIOTIC),
    ("프로바이오틱스는 장 건강 관리에 도움을 줄 수 있습니다.", PROBIOTIC),
])
def test_common_wording_inside_the_official_scope_is_confirmed(ad: str, official: str) -> None:
    decision = _decide(ad, official)
    assert decision.verdict is Verdict.CONFIRMED
    assert decision.official_effect is not None


@pytest.mark.parametrize(("ad", "official"), [
    # Dose and frequency: efficacy is recognised at the product's daily intake, which is not checked.
    ("하루 한 번 루테인은 황반색소밀도 유지로 눈 건강에 도움을 줄 수 있습니다.", EYE),
    ("매일 오메가3 한 알은 혈행 개선에 도움을 줄 수 있습니다.", OMEGA),
    ("하루 두 알 섭취하는 오메가3는 혈행 개선에 도움을 줄 수 있습니다.", OMEGA),
    ("매일 한 포 프로바이오틱스는 장 건강에 도움을 줄 수 있습니다.", PROBIOTIC),
    # Population, comparison, extra content and other wording outside the allowlist.
    ("어린이가 매일 먹는 오메가3는 기억력 개선에 도움을 줄 수 있습니다.", OMEGA),
    ("임산부가 꾸준히 섭취하는 오메가3는 혈행 개선에 도움을 줄 수 있습니다.", OMEGA),
    ("오메가3는 다른 원료보다 혈행 개선에 더 도움을 줄 수 있습니다.", OMEGA),
    ("오메가3는 혈행 개선에 도움을 줄 수 있는 유일한 원료입니다.", OMEGA),
    ("오메가3는 혈행 개선에 도움을 줄 수 있는 원료이자 면역 원료입니다.", OMEGA),
    ("건강한 식습관과 함께하는 오메가3는 혈중 중성지질 개선에 도움을 줄 수 있습니다.", OMEGA),
    ("눈 건강을 위한 루테인은 황반색소밀도 유지에 도움을 줄 수 있습니다.", EYE),
    ("규칙적인 배변활동이 원활하도록 프로바이오틱스가 도움을 줄 수 있습니다.", PROBIOTIC),
    # Negation, questions and the wrong subject in the new forms.
    ("오메가3는 혈행을 개선하는 데 도움을 줄 수 없습니다.", OMEGA),
    ("오메가3는 혈행 개선에 도움이 될 수 있을까요?", OMEGA),
    ("오메가3는 혈행 개선에 도움이 되지 않습니다.", OMEGA),
    ("루테인은 혈중 중성지질을 개선하는 데 도움을 줄 수 있습니다.", OMEGA),
    ("프로바이오틱스는 혈행 개선에 도움을 줄 수 있는 원료입니다.", OMEGA),
])
def test_wording_outside_the_allowlist_is_not_confirmed(ad: str, official: str) -> None:
    assert _decide(ad, official).verdict is not Verdict.CONFIRMED


@pytest.mark.parametrize(("ad", "official"), [
    ("오메가3는 혈행 개선을 통해 혈전과 뇌졸중 위험을 낮추는 데 도움을 줍니다.", OMEGA),
    ("혈전을 막는 오메가3는 혈행 개선에 도움을 줄 수 있습니다.", OMEGA),
    ("오메가3는 동맥경화 걱정을 덜어 줍니다.", OMEGA),
    ("오메가3는 안구건조증에 도움을 줄 수 있습니다.", OMEGA),
    ("오메가3는 기억력 개선으로 알츠하이머를 막아 줍니다.", OMEGA),
    ("루테인은 노안 걱정을 줄여 줍니다.", EYE),
    ("프로바이오틱스는 유해균 억제로 장염을 완화합니다.", PROBIOTIC),
    ("프로바이오틱스는 배변활동 원활로 변비를 완화합니다.", PROBIOTIC),
    ("프로바이오틱스는 설사를 멈추게 합니다.", PROBIOTIC),
    ("프로바이오틱스는 과민성대장증후군에 도움을 줄 수 있습니다.", PROBIOTIC),
])
def test_disease_and_symptom_names_are_disease_claims(ad: str, official: str) -> None:
    decision = _decide(ad, official)
    assert decision.verdict is Verdict.MISMATCH
    assert decision.reason is VerdictReason.DISEASE_CLAIM_BEYOND_FUNCTIONAL_SCOPE
