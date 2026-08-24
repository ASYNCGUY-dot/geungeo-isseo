from datetime import UTC, datetime

import pytest

from claimledger.decision import decide_supported_claim
from claimledger.domain import Claim, ConfirmedProduct, EvidenceRecord, ProductCandidate, Verdict
from claimledger.errors import DecisionInvariantError, IdentityRequiredError
from claimledger.product_evidence import build_product_evidence

NOW = datetime(2026, 8, 22, tzinfo=UTC)
CLAIM = Claim(original_text="눈 건강에 도움을 줍니다", normalized_subject="눈 건강")
PRODUCT = ProductCandidate(
    report_no="TEST-0001",
    name="루테인 테스트 제품",
    company="테스트 제조사",
    primary_function="눈 건강에 도움을 줄 수 있음",
    raw_materials="루테인지아잔틴복합추출물",
    intake_method="1일 1회, 1회 1캡슐을 섭취하십시오.",
    source_id="C003",
    retrieved_at=NOW,
)
CONFIRMED_PRODUCT = ConfirmedProduct(product=PRODUCT, confirmed_by_user=True)
READY_BUNDLE = build_product_evidence(CONFIRMED_PRODUCT)
SUPPORTING_EVIDENCE = EvidenceRecord(
    evidence_id="EVIDENCE-0001",
    source_url="https://example.test/evidence/0001",
    retrieved_at=NOW,
    product_report_no="TEST-0001",
    supports_claim=True,
)


def test_missing_confirmed_product_cannot_clear_claim() -> None:
    with pytest.raises(IdentityRequiredError):
        decide_supported_claim(CLAIM, None, [SUPPORTING_EVIDENCE], READY_BUNDLE)


def test_empty_evidence_cannot_clear_claim() -> None:
    assert (
        decide_supported_claim(CLAIM, CONFIRMED_PRODUCT, [], READY_BUNDLE)
        is Verdict.UNVERIFIABLE
    )


def test_evidence_without_claim_support_cannot_clear_claim() -> None:
    non_supporting_evidence = SUPPORTING_EVIDENCE.model_copy(update={"supports_claim": False})

    assert (
        decide_supported_claim(
            CLAIM,
            CONFIRMED_PRODUCT,
            [non_supporting_evidence],
            READY_BUNDLE,
        )
        is Verdict.UNVERIFIABLE
    )


def test_product_specific_evidence_must_match_report_number() -> None:
    other_product_evidence = SUPPORTING_EVIDENCE.model_copy(
        update={"product_report_no": "TEST-9999"}
    )
    assert (
        decide_supported_claim(
            CLAIM,
            CONFIRMED_PRODUCT,
            [other_product_evidence],
            READY_BUNDLE,
        )
        is Verdict.UNVERIFIABLE
    )


def test_mismatched_non_supporting_product_evidence_prevents_confirmation() -> None:
    mismatched_non_supporting = SUPPORTING_EVIDENCE.model_copy(
        update={"product_report_no": "TEST-9999", "supports_claim": False}
    )

    assert (
        decide_supported_claim(
            CLAIM,
            CONFIRMED_PRODUCT,
            [SUPPORTING_EVIDENCE, mismatched_non_supporting],
            READY_BUNDLE,
        )
        is Verdict.UNVERIFIABLE
    )


def test_ready_bundle_must_match_confirmed_product_report_number() -> None:
    conflicting_bundle = READY_BUNDLE.model_copy(update={"report_no": "TEST-9999"})

    with pytest.raises(DecisionInvariantError, match="REPORT_NUMBER_CONFLICT"):
        decide_supported_claim(
            CLAIM,
            CONFIRMED_PRODUCT,
            [SUPPORTING_EVIDENCE],
            conflicting_bundle,
        )


def test_rebadged_bundle_for_another_report_cannot_confirm() -> None:
    other_product = PRODUCT.model_copy(
        update={
            "report_no": "TEST-0002",
            "name": "다른 루테인 제품",
            "company": "다른 제조사",
        }
    )
    other_confirmed_product = ConfirmedProduct(
        product=other_product,
        confirmed_by_user=True,
    )
    other_supporting_evidence = SUPPORTING_EVIDENCE.model_copy(
        update={"product_report_no": "TEST-0002"}
    )
    rebadged_bundle = READY_BUNDLE.model_copy(update={"report_no": "TEST-0002"})

    with pytest.raises(DecisionInvariantError, match="REPORT_NUMBER_CONFLICT"):
        decide_supported_claim(
            CLAIM,
            other_confirmed_product,
            [other_supporting_evidence],
            rebadged_bundle,
        )


def test_bundle_snapshot_must_match_every_confirmed_product_source_field() -> None:
    altered_product = PRODUCT.model_copy(update={"company": "다른 제조사"})
    altered_bundle = build_product_evidence(
        ConfirmedProduct(product=altered_product, confirmed_by_user=True)
    )

    with pytest.raises(DecisionInvariantError, match="PRODUCT_SNAPSHOT_CONFLICT"):
        decide_supported_claim(
            CLAIM,
            CONFIRMED_PRODUCT,
            [SUPPORTING_EVIDENCE],
            altered_bundle,
        )


def test_genuine_other_report_bundle_uses_report_conflict_precedence() -> None:
    other_product = PRODUCT.model_copy(
        update={
            "report_no": "TEST-0002",
            "name": "다른 루테인 제품",
            "company": "다른 제조사",
        }
    )
    other_bundle = build_product_evidence(
        ConfirmedProduct(product=other_product, confirmed_by_user=True)
    )

    with pytest.raises(DecisionInvariantError, match="REPORT_NUMBER_CONFLICT"):
        decide_supported_claim(
            CLAIM,
            CONFIRMED_PRODUCT,
            [SUPPORTING_EVIDENCE],
            other_bundle,
        )


def test_non_ready_product_evidence_cannot_clear_claim() -> None:
    incomplete_product = CONFIRMED_PRODUCT.model_copy(
        update={"product": PRODUCT.model_copy(update={"raw_materials": ""})}
    )
    non_ready_bundle = build_product_evidence(incomplete_product)

    with pytest.raises(DecisionInvariantError, match="MISSING_RAW_MATERIALS"):
        decide_supported_claim(
            CLAIM,
            incomplete_product,
            [SUPPORTING_EVIDENCE],
            non_ready_bundle,
        )


def test_traceable_matching_support_can_confirm() -> None:
    assert (
        decide_supported_claim(
            CLAIM,
            CONFIRMED_PRODUCT,
            [SUPPORTING_EVIDENCE],
            READY_BUNDLE,
        )
        is Verdict.CONFIRMED
    )
