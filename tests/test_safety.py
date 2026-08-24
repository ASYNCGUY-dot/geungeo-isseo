from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from claimledger.domain import (
    ConfirmedProduct,
    InteractionEvidence,
    OfficialFieldStatus,
    OfficialProductCaution,
    ProductCandidate,
    SafetySignal,
)
from claimledger.safety import build_safety_signals

NOW = datetime(2026, 8, 24, tzinfo=UTC)
PRODUCT = ProductCandidate(
    report_no="TEST-SAFETY-001",
    name="안전 신호 테스트 제품",
    company="테스트 제조사",
    primary_function="눈 건강에 도움을 줄 수 있음",
    raw_materials="루테인지아잔틴복합추출물",
    intake_method="의약품 복용 시 전문가와 상담하십시오.",
    source_id="C003",
    retrieved_at=NOW,
)
CONFIRMED_PRODUCT = ConfirmedProduct(product=PRODUCT, confirmed_by_user=True)
CAUTION_TEXT = "의약품 복용 시 전문가와 상담하십시오."


def test_safety_signal_can_never_express_clearance() -> None:
    signal = SafetySignal(
        kind="official_product_caution",
        message=CAUTION_TEXT,
        source_id="C003",
        source_url="https://example.test/official/TEST-SAFETY-001",
        retrieved_at=NOW,
        source_text=CAUTION_TEXT,
    )

    assert signal.is_safety_clearance is False

    with pytest.raises(ValidationError):
        SafetySignal(
            kind="official_product_caution",
            message=CAUTION_TEXT,
            source_id="C003",
            source_url="https://example.test/official/TEST-SAFETY-001",
            retrieved_at=NOW,
            source_text=CAUTION_TEXT,
            is_safety_clearance=True,
        )


@pytest.mark.parametrize("message", ["안전합니다", "상호작용 없음", "복용해도 됩니다", "부작용이 없습니다"])
def test_safety_signal_rejects_prohibited_clearance_phrases(message: str) -> None:
    with pytest.raises(ValidationError):
        SafetySignal(
            kind="official_product_caution",
            message=message,
            source_id="C003",
            official_identifier="TEST-SAFETY-001",
            retrieved_at=NOW,
            source_text=CAUTION_TEXT,
        )


def test_safety_signal_requires_traceable_source_and_literal_source_text() -> None:
    with pytest.raises(ValidationError):
        SafetySignal(
            kind="official_product_caution",
            message=CAUTION_TEXT,
            source_id="C003",
            retrieved_at=NOW,
            source_text=CAUTION_TEXT,
        )

    with pytest.raises(ValidationError):
        SafetySignal(
            kind="official_product_caution",
            message=CAUTION_TEXT,
            source_id="C003",
            official_identifier="TEST-SAFETY-001",
            retrieved_at=NOW,
            source_text=" ",
        )


def test_absent_interaction_evidence_does_not_create_no_interaction_message() -> None:
    assert build_safety_signals(CONFIRMED_PRODUCT, [], []) == ()


def test_verified_official_product_caution_becomes_source_backed_general_signal() -> None:
    caution = OfficialProductCaution(
        status=OfficialFieldStatus.VERIFIED,
        source_field="intake_method",
        original_text=CAUTION_TEXT,
    )

    signals = build_safety_signals(CONFIRMED_PRODUCT, [caution], [])

    assert signals == (
        SafetySignal(
            kind="official_product_caution",
            message=CAUTION_TEXT,
            source_id="C003",
            official_identifier="TEST-SAFETY-001",
            retrieved_at=NOW,
            source_text=CAUTION_TEXT,
        ),
    )


def test_unverified_official_caution_is_not_rewritten_into_a_signal() -> None:
    caution = OfficialProductCaution(
        status=OfficialFieldStatus.UNVERIFIABLE,
        source_field="intake_method",
        original_text="맛있게 드십시오.",
    )

    assert build_safety_signals(CONFIRMED_PRODUCT, [caution], []) == ()


def test_source_backed_interaction_evidence_becomes_general_signal() -> None:
    evidence = InteractionEvidence(
        source_id="OFFICIAL-INGREDIENT",
        source_url="https://example.test/ingredient/omega3",
        retrieved_at=NOW,
        source_text="의약품 복용 시 전문가와 상담하십시오.",
    )

    signals = build_safety_signals(CONFIRMED_PRODUCT, [], [evidence])

    assert signals == (
        SafetySignal(
            kind="official_interaction_caution",
            message=evidence.source_text,
            source_id=evidence.source_id,
            source_url=evidence.source_url,
            retrieved_at=NOW,
            source_text=evidence.source_text,
        ),
    )


def test_product_specific_interaction_evidence_for_another_product_is_rejected() -> None:
    evidence = InteractionEvidence(
        source_id="OFFICIAL-INGREDIENT",
        official_identifier="OTHER-PRODUCT-001",
        product_report_no="OTHER-PRODUCT-001",
        retrieved_at=NOW,
        source_text=CAUTION_TEXT,
    )

    with pytest.raises(ValueError, match="does not match confirmed product"):
        build_safety_signals(CONFIRMED_PRODUCT, [], [evidence])
