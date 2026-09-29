"""Synthetic developer regressions, not a human-labeled accuracy benchmark."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from claimledger.api import create_app
from claimledger.claims_v1 import confirm_claims, extract_claims
from claimledger.domain import ConfirmedProduct, ProductCandidate, Verdict
from claimledger.receipt import build_receipt, render_markdown
from claimledger.verdict_v1 import decide_claim

AT = datetime(2026, 9, 28, tzinfo=UTC)
CIRCULATION = "[EPA 및 DHA 함유 유지] 혈행 개선에 도움을 줄 수 있음"
EYE = "[루테인] 노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음"


def _product(text: str = CIRCULATION, report_no: str = "SYNTHETIC-1") -> ProductCandidate:
    return ProductCandidate(
        report_no=report_no, name="합성 테스트 제품", company="합성 테스트 업체",
        primary_function=text, raw_materials="합성 fixture", intake_method="합성 fixture",
        source_id="C003", retrieved_at=AT,
    )


def _decide(ad: str, official: str = CIRCULATION):
    claims = confirm_claims(extract_claims(ad), "all")
    assert len(claims) == 1, "A risky sentence must remain visible for review"
    product = ConfirmedProduct(product=_product(official), confirmed_by_user=True)
    return decide_claim(claims[0], product)


@pytest.mark.parametrize("ad", [
    "혈행과 기억력 개선에 도움을 줄 수 있어요.",
    "혈행과 면역력 개선에 도움을 줄 수 있어요.",
    "혈행 개선에 도움을 주고 혈액순환이 좋아집니다.",
    "혈행 개선에 도움이 안 됩니다.",
    "혈행 개선에 도움을 줄 수 없습니다.",
    "혈행 개선에 도움을 줄 수 있나요?",
    "루테인이 혈행 개선에 도움을 줄 수 있어요.",
    "혈행 개선에 도움을 주며 체중도 줄여줍니다.",
    "혈행 개선에 도움을 주고 부작용이 없습니다.",
    "혈행 개선에 3배 도움을 줄 수 있어요.",
    "어린이의 혈행 개선에 도움을 줄 수 있어요.",
])
def test_partial_keyword_match_cannot_clear_the_whole_sentence(ad: str) -> None:
    decision = _decide(ad)
    assert decision.verdict is Verdict.UNVERIFIABLE
    assert decision.official_effect is None
    assert decision.claim.text == ad
    assert ad[slice(*decision.claim.span)] == ad


def test_disclaimer_suffix_does_not_hide_strong_claim() -> None:
    decision = _decide("혈행을 확실히 개선하며 부작용이 없습니다.")
    assert decision.verdict is not Verdict.CONFIRMED


@pytest.mark.parametrize("official", [
    CIRCULATION + "\n은행잎추출물: 기억력 개선에 도움을 줄 수 있음",
    CIRCULATION + "\n은행잎추출물\n기억력 개선에 도움을 줄 수 있음",
    CIRCULATION + " 은행잎추출물: 기억력 개선에 도움을 줄 수 있음",
    "[오메가3 및 은행잎추출물] 기억력 개선에 도움을 줄 수 있음",
    "[오메가3 + 프로바이오틱스] 기억력 개선에 도움을 줄 수 있음",
    "[오메가3아님] 기억력 개선에 도움을 줄 수 있음",
    "[notomega3] 기억력 개선에 도움을 줄 수 있음",
    "[EPA 및 DHA 함유 유지] 기억력 개선에 도움이 되지 않음",
    "[EPA 및 DHA 함유 유지] 기억력 개선",
    "[EPA 및 DHA 함유 유지] 기억력 개선은 제외, 혈행 개선에 도움을 줄 수 있음",
    "[EPA 및 DHA 함유 유지] 기억력 개선 대신 혈행 개선에 도움을 줄 수 있음",
    "[EPA 및 DHA 함유 유지] 기억력 개선 삭제, 혈행 개선에 도움을 줄 수 있음",
    "[EPA 및 DHA 함유 유지] 기억력 개선 미인정, 혈행 개선에 도움을 줄 수 있음",
])
def test_ambiguous_or_negative_official_evidence_is_not_positive(official: str) -> None:
    decision = _decide("기억력 개선에 도움을 줄 수 있어요.", official)
    assert decision.verdict is Verdict.UNVERIFIABLE
    assert decision.official_effect is None


@pytest.mark.parametrize(("ad", "official"), [
    ("혈행 개선에 도움을 줄 수 있어요.", CIRCULATION),
    ("오메가3가 혈행 개선에 도움을 줄 수 있습니다.", CIRCULATION),
    ("혈행 개선에 도움을 줄 수 있음", "EPA 및 DHA 함유 유지 : 혈행 개선에 도움을 줄 수 있음"),
    ("눈 건강에 도움을 줄 수 있어요.", EYE),
    ("루테인이 눈 건강에 도움을 줄 수 있어요.", EYE),
    ("황반색소밀도를 유지해 눈 건강에 도움을 줍니다.", EYE),
    ("배변활동 원활에 도움을 줄 수 있어요.", "[프로바이오틱스 제품] 배변활동 원활에 도움을 줄 수 있음"),
])
def test_single_supported_claim_still_has_literal_evidence(ad: str, official: str) -> None:
    decision = _decide(ad, official)
    assert decision.verdict is Verdict.CONFIRMED
    assert decision.official_effect is not None
    evidence = decision.official_effect
    assert official[slice(*evidence.matched_span)] == evidence.matched_text
    assert official[slice(*evidence.statement_span)] == evidence.statement_text


def test_two_separate_sentences_do_not_share_confirmation() -> None:
    ad = "혈행 개선에 도움을 줄 수 있어요. 기억력 개선에 도움을 줄 수 있어요."
    product = ConfirmedProduct(product=_product(), confirmed_by_user=True)
    decisions = [decide_claim(c, product) for c in confirm_claims(extract_claims(ad), "all")]
    assert [d.verdict for d in decisions] == [Verdict.CONFIRMED, Verdict.MISMATCH]


def test_compound_claim_receipt_explains_abstention() -> None:
    ad = "혈행과 기억력 개선에 도움을 줄 수 있어요."
    product = ConfirmedProduct(product=_product(), confirmed_by_user=True)
    receipt = build_receipt(ad, product, [_decide(ad)], AT)
    assert receipt.claims[0].verdict_label == "검증 불가"
    assert "문장 전체" in receipt.claims[0].reason_message
    assert "검증 불가" in render_markdown(receipt)


def test_api_confirmation_revocation_and_product_change_cannot_reuse_clearance() -> None:
    client = TestClient(create_app([_product(), _product("", "SYNTHETIC-2")], source_retrieved_at=AT))
    result = client.post("/api/v1/analyses", json={"ad_text": "혈행 개선에 도움을 줄 수 있어요."})
    assert result.status_code == 201
    path = f"/api/v1/analyses/{result.json()['analysis_id']}"
    assert client.post(path + "/evaluate", json={"verdict": "confirmed"}).status_code == 409
    client.put(path + "/product-confirmation", json={"report_no": "SYNTHETIC-1"})
    client.put(path + "/claims/confirmation", json={"claim_ids": ["C1"]})
    assert client.post(path + "/evaluate").json()["claims"][0]["verdict"] == "confirmed"
    client.put(path + "/claims/confirmation", json={"claim_ids": []})
    assert client.get(path + "/receipt").status_code == 404
    assert client.post(path + "/evaluate").json()["claims"][0]["reason_code"] == "CLAIM_UNCONFIRMED"
    client.put(path + "/claims/confirmation", json={"claim_ids": ["C1"]})
    client.put(path + "/product-confirmation", json={"report_no": "SYNTHETIC-2"})
    assert client.get(path + "/receipt").status_code == 404
    receipt = client.post(path + "/evaluate", json={"verdict": "confirmed"}).json()
    assert receipt["claims"][0]["verdict"] == "unverifiable"


def test_api_does_not_turn_partial_support_into_a_confirmed_receipt() -> None:
    client = TestClient(create_app([_product()], source_retrieved_at=AT))
    ad = "혈행과 기억력 개선에 도움을 줄 수 있어요."
    response = client.post("/api/v1/analyses", json={"ad_text": ad})
    path = f"/api/v1/analyses/{response.json()['analysis_id']}"
    client.put(path + "/product-confirmation", json={"report_no": "SYNTHETIC-1"})
    client.put(path + "/claims/confirmation", json={"claim_ids": ["C1"]})
    response = client.post(path + "/evaluate")
    assert response.status_code == 200
    assert response.json()["claims"][0]["verdict"] == "unverifiable"
    assert response.json()["claims"][0]["official_quote"] is None


# Official wording as notified; since v2.5 an official clause never seen in C003 is held.
SINGLE_FUNCTIONS = [
    ("루테인", "노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강", "눈 건강"),
    ("EPA 및 DHA 함유 유지", "혈중 중성지질 개선", "혈중 중성지질 개선"),
    ("EPA 및 DHA 함유 유지", "혈행 개선", "혈행 개선"),
    ("EPA 및 DHA 함유 유지", "기억력 개선", "기억력 개선"),
    ("EPA 및 DHA 함유 유지", "건조한 눈을 개선하여 눈 건강", "건조한 눈 개선"),
    ("프로바이오틱스", "유산균 증식 및 유해균 억제", "유산균 증식 및 유해균 억제"),
    ("프로바이오틱스", "배변활동 원활", "배변활동 원활"),
    ("프로바이오틱스", "장 건강", "장 건강"),
]


@pytest.mark.parametrize(("header", "official_effect", "ad_effect"), SINGLE_FUNCTIONS)
def test_each_supported_effect_remains_confirmable(
    header: str, official_effect: str, ad_effect: str,
) -> None:
    decision = _decide(
        f"{ad_effect}에 도움을 줄 수 있음",
        f"[{header}] {official_effect}에 도움을 줄 수 있음",
    )
    assert decision.verdict is Verdict.CONFIRMED


@pytest.mark.parametrize(("header", "official_effect", "ad_effect"), SINGLE_FUNCTIONS)
@pytest.mark.parametrize(("prefix", "ending"), [
    ("", "에 도움을 줄 수 있나요?"),
    ("", "에 도움이 안 됩니다."),
    ("", "에 도움을 줄 수 없어요."),
    ("", "에 도움을 주며 체중도 줄여줍니다."),
    ("임산부의 ", "에 도움을 줄 수 있음"),
    ("", "에 2배 도움을 줄 수 있음"),
])
def test_extra_scope_never_inherits_a_supported_effect_clearance(
    header: str, official_effect: str, ad_effect: str, prefix: str, ending: str,
) -> None:
    decision = _decide(
        f"{prefix}{ad_effect}{ending}",
        f"[{header}] {official_effect}에 도움을 줄 수 있음",
    )
    assert decision.verdict is Verdict.UNVERIFIABLE


@pytest.mark.parametrize("section", ["미인정", "삭제"])
@pytest.mark.parametrize("header", [
    "EPA 및 DHA 함유 유지:", "EPA 및 DHA 함유 유지 -", "[EPA 및 DHA 함유 유지]",
])
def test_negative_section_cannot_be_reset_by_a_nested_ingredient_header(
    section: str, header: str,
) -> None:
    official = f"[{section}]\n{header} 기억력 개선에 도움을 줄 수 있음"
    assert _decide("기억력 개선에 도움을 줄 수 있어요.", official).verdict is Verdict.UNVERIFIABLE


@pytest.mark.parametrize("ad", [
    "루테인이\n혈행 개선에 도움을 줄 수 있어요.",
    "어린이의\n혈행 개선에 도움을 줄 수 있어요.",
    "혈행 개선에 도움을 줄 수 있음\n이라는 주장은 사실이 아닙니다.",
    "혈행 개선에 도움을 줄 수 있음\n은 미확인 주장입니다.",
])
def test_line_wrap_cannot_discard_subject_or_qualification(ad: str) -> None:
    decision = _decide(ad)
    assert decision.verdict is Verdict.UNVERIFIABLE
    assert decision.claim.text == ad
    assert ad[slice(*decision.claim.span)] == ad


@pytest.mark.parametrize("body", [
    "기억력 개선은 검토 중이며 혈행 개선에 도움을 줄 수 있음",
    "기억력 개선은 확인 중, 혈행 개선에 도움을 줄 수 있음",
    "기억력 개선은 가설이고 혈행 개선에 도움을 줄 수 있음",
    "기억력 개선은 연구 대상이며 혈행 개선에 도움을 줄 수 있음",
    "혈행 개선에 도움을 줄 수 있음 은행잎추출물 - 기억력 개선에 도움을 줄 수 있음",
    "혈행 개선에 도움을 줄 수 있음 은행잎추출물 – 기억력 개선에 도움을 줄 수 있음",
])
def test_support_predicate_must_bind_to_the_whole_official_clause(body: str) -> None:
    official = "[EPA 및 DHA 함유 유지] " + body
    decision = _decide("기억력 개선에 도움을 줄 수 있어요.", official)
    assert decision.verdict is Verdict.UNVERIFIABLE
    assert decision.official_effect is None


def test_wrapped_supported_subject_preserves_literal_span() -> None:
    ad = "오메가3가\n혈행 개선에 도움을 줄 수 있어요."
    decision = _decide(ad)
    assert decision.verdict is Verdict.CONFIRMED
    assert decision.claim.text == ad
    assert ad[slice(*decision.claim.span)] == ad


@pytest.mark.parametrize(("official", "ad"), [
    (
        ("[EPA 및 DHA 함유 유지] 혈중 중성지질 개선·혈행 개선에 도움을 줄 수 있음. "
         "건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음."),
        "혈행 개선에 도움을 줄 수 있어요.",
    ),
    (
        ("[EPA 및 DHA 함유 유지] 혈행 개선에 도움을 줄 수 있음. "
         "건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음"),
        "건조한 눈 개선에 도움을 줄 수 있어요.",
    ),
    (
        ("[프로바이오틱스]①유산균 증식 및 유해균 억제에 도움을 줄 수 있음 "
         "②배변활동 원활에 도움을 줄 수 있음"),
        "배변활동 원활에 도움을 줄 수 있어요.",
    ),
    (
        ("[프로바이오틱스](1)유산균 증식 및 유해균 억제에 도움을 줄 수 있음 "
         "(2)배변활동 원활에 도움을 줄 수 있음."),
        "유산균 증식 및 유해균 억제에 도움을 줄 수 있어요.",
    ),
])
def test_complete_positive_sentences_and_numbered_lists_keep_evidence(
    official: str, ad: str,
) -> None:
    decision = _decide(ad, official)
    assert decision.verdict is Verdict.CONFIRMED
    assert decision.official_effect is not None
    assert official[slice(*decision.official_effect.statement_span)] == (
        decision.official_effect.statement_text
    )


@pytest.mark.parametrize("body", [
    "혈행 개선에 도움을 줄 수 있음. 기억력 개선은 검토 중",
    "혈행 개선에 도움을 줄 수 있음. 은행잎추출물 - 기억력 개선에 도움을 줄 수 있음",
    "①혈행 개선에 도움을 줄 수 있음 ②기억력 개선은 검토 중",
    "혈행 개선에 도움을 줄 수 있음\n이 문구는 미인정",
])
def test_positive_clause_does_not_erase_unresolved_following_clause(body: str) -> None:
    assert _decide(
        "혈행 개선에 도움을 줄 수 있어요.", "[EPA 및 DHA 함유 유지] " + body,
    ).verdict is Verdict.UNVERIFIABLE


@pytest.mark.parametrize("suffix", [
    "\n이라는 문구는 검토 중",
    "\n기억력 개선 문구는 검토 중",
    "\n[검토 중]",
    " [검토 중]",
])
def test_official_unresolved_continuation_cannot_disappear_at_a_boundary(suffix: str) -> None:
    official = "[EPA 및 DHA 함유 유지] 기억력 개선에 도움을 줄 수 있음" + suffix
    decision = _decide("기억력 개선에 도움을 줄 수 있어요.", official)
    assert decision.verdict is Verdict.UNVERIFIABLE
    assert decision.official_effect is None


@pytest.mark.parametrize("separator", [". ", "․", "．", ".\n"])
def test_separate_or_ambiguous_sentences_cannot_share_the_support_predicate(
    separator: str,
) -> None:
    official = (
        "[EPA 및 DHA 함유 유지] 기억력 개선" + separator + "혈행 개선에 도움을 줄 수 있음"
    )
    decision = _decide("기억력 개선에 도움을 줄 수 있어요.", official)
    assert decision.verdict is Verdict.UNVERIFIABLE
    assert decision.official_effect is None
