from datetime import UTC, datetime

import pytest

from claimledger.decision import decide_supported_claim
from claimledger.domain import Claim, ConfirmedProduct, EvidenceRecord, ProductCandidate, Verdict
from claimledger.errors import IdentityRequiredError

NOW = datetime(2026, 8, 22, tzinfo=UTC)
CLAIM = Claim(original_text="눈 건강에 도움을 줍니다", normalized_subject="눈 건강")
PRODUCT = ProductCandidate(
    report_no="TEST-0001",
    name="루테인 테스트 제품",
    company="테스트 제조사",
    source_id="C003",
    retrieved_at=NOW,
)
CONFIRMED_PRODUCT = ConfirmedProduct(product=PRODUCT, confirmed_by_user=True)
SUPPORTING_EVIDENCE = EvidenceRecord(
    evidence_id="EVIDENCE-0001",
    source_url="https://example.test/evidence/0001",
    retrieved_at=NOW,
    product_report_no="TEST-0001",
    supports_claim=True,
)


def test_missing_confirmed_product_cannot_clear_claim() -> None:
    with pytest.raises(IdentityRequiredError):
        decide_supported_claim(CLAIM, None, [SUPPORTING_EVIDENCE])


def test_empty_evidence_cannot_clear_claim() -> None:
    assert decide_supported_claim(CLAIM, CONFIRMED_PRODUCT, []) is Verdict.UNVERIFIABLE


def test_product_specific_evidence_must_match_report_number() -> None:
    other_product_evidence = SUPPORTING_EVIDENCE.model_copy(
        update={"product_report_no": "TEST-9999"}
    )
    assert (
        decide_supported_claim(CLAIM, CONFIRMED_PRODUCT, [other_product_evidence])
        is Verdict.UNVERIFIABLE
    )


def test_traceable_matching_support_can_confirm() -> None:
    assert (
        decide_supported_claim(CLAIM, CONFIRMED_PRODUCT, [SUPPORTING_EVIDENCE])
        is Verdict.CONFIRMED
    )
