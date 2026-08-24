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
CONSULT_PROFESSIONAL = "consult_professional"
OFFICIAL_INGREDIENT_GUIDANCE = "official_ingredient_guidance"


def test_safety_signal_can_never_express_clearance() -> None:
    signal = SafetySignal(
        kind="official_product_caution",
        message=CAUTION_TEXT,
        source_id="C003",
        source_url="https://example.test/official/TEST-SAFETY-001",
        retrieved_at=NOW,
        source_text=CAUTION_TEXT,
        caution_category=CONSULT_PROFESSIONAL,
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
            caution_category=CONSULT_PROFESSIONAL,
            is_safety_clearance=True,
        )


@pytest.mark.parametrize(
    "message",
    [
        "안전합니다",
        "상호작용 없음",
        "복용해도 됩니다",
        "부작용이 없습니다",
        "함께 복용해도 문제 없습니다",
        "상호작용이 없습니다",
        "부작용 없다",
        "안전한 제품입니다",
        "효과가 있습니다",
        "복용량을 줄이십시오",
    ],
)
def test_safety_signal_rejects_clearance_claim_and_recommendation_equivalents(message: str) -> None:
    with pytest.raises(ValidationError):
        SafetySignal(
            kind="official_product_caution",
            message=message,
            source_id="C003",
            official_identifier="TEST-SAFETY-001",
            retrieved_at=NOW,
            source_text=message,
            caution_category=CONSULT_PROFESSIONAL,
        )


def test_safety_signal_requires_traceable_source_and_literal_source_text() -> None:
    with pytest.raises(ValidationError):
        SafetySignal(
            kind="official_product_caution",
            message=CAUTION_TEXT,
            source_id="C003",
            retrieved_at=NOW,
            source_text=CAUTION_TEXT,
            caution_category=CONSULT_PROFESSIONAL,
        )

    with pytest.raises(ValidationError):
        SafetySignal(
            kind="official_product_caution",
            message=CAUTION_TEXT,
            source_id="C003",
            official_identifier="TEST-SAFETY-001",
            retrieved_at=NOW,
            source_text=" ",
            caution_category=CONSULT_PROFESSIONAL,
        )


def test_safety_signal_requires_a_recognized_literal_caution_category() -> None:
    with pytest.raises(ValidationError):
        SafetySignal(
            kind="official_product_caution",
            message=CAUTION_TEXT,
            source_id="C003",
            official_identifier="TEST-SAFETY-001",
            retrieved_at=NOW,
            source_text=CAUTION_TEXT,
            caution_category="free_form_caution",
        )


def test_legitimate_general_caution_remains_accepted() -> None:
    signal = SafetySignal(
        kind="official_product_caution",
        message=CAUTION_TEXT,
        source_id="C003",
        official_identifier="TEST-SAFETY-001",
        retrieved_at=NOW,
        source_text=CAUTION_TEXT,
        caution_category=CONSULT_PROFESSIONAL,
    )

    assert signal.message == CAUTION_TEXT
    assert signal.is_safety_clearance is False


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
            caution_category=CONSULT_PROFESSIONAL,
        ),
    )


def test_unverified_official_caution_is_not_rewritten_into_a_signal() -> None:
    caution = OfficialProductCaution(
        status=OfficialFieldStatus.UNVERIFIABLE,
        source_field="intake_method",
        original_text="맛있게 드십시오.",
    )

    assert build_safety_signals(CONFIRMED_PRODUCT, [caution], []) == ()


def test_registered_official_interaction_evidence_becomes_general_signal() -> None:
    evidence = InteractionEvidence(
        source_id="MFDS",
        source_url="https://www.foodsafetykorea.go.kr/ingredient/omega3",
        retrieved_at=NOW,
        source_text=CAUTION_TEXT,
        official_source_category=OFFICIAL_INGREDIENT_GUIDANCE,
        official_source_verified=True,
        caution_category=CONSULT_PROFESSIONAL,
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
            caution_category=CONSULT_PROFESSIONAL,
        ),
    )


def test_interaction_evidence_rejects_arbitrary_unverified_source_identity() -> None:
    with pytest.raises(ValidationError):
        InteractionEvidence(
            source_id="blog",
            source_url="https://example.test/blog-post",
            retrieved_at=NOW,
            source_text=CAUTION_TEXT,
            official_source_category=OFFICIAL_INGREDIENT_GUIDANCE,
            official_source_verified=True,
            caution_category=CONSULT_PROFESSIONAL,
        )


def test_interaction_evidence_rejects_a_url_outside_its_registered_official_source() -> None:
    with pytest.raises(ValidationError):
        InteractionEvidence(
            source_id="MFDS",
            source_url="https://example.test/blog-post",
            retrieved_at=NOW,
            source_text=CAUTION_TEXT,
            official_source_category=OFFICIAL_INGREDIENT_GUIDANCE,
            official_source_verified=True,
            caution_category=CONSULT_PROFESSIONAL,
        )


def test_interaction_evidence_rejects_copied_text_that_does_not_match_its_caution_category() -> None:
    with pytest.raises(ValidationError):
        InteractionEvidence(
            source_id="MFDS",
            official_identifier="MFDS-INGREDIENT-OMEGA3",
            retrieved_at=NOW,
            source_text="함께 복용해도 문제 없습니다",
            official_source_category=OFFICIAL_INGREDIENT_GUIDANCE,
            official_source_verified=True,
            caution_category=CONSULT_PROFESSIONAL,
        )


def test_product_specific_interaction_evidence_for_another_product_is_rejected() -> None:
    evidence = InteractionEvidence(
        source_id="MFDS",
        official_identifier="OTHER-PRODUCT-001",
        product_report_no="OTHER-PRODUCT-001",
        retrieved_at=NOW,
        source_text=CAUTION_TEXT,
        official_source_category=OFFICIAL_INGREDIENT_GUIDANCE,
        official_source_verified=True,
        caution_category=CONSULT_PROFESSIONAL,
    )

    with pytest.raises(ValueError, match="does not match confirmed product"):
        build_safety_signals(CONFIRMED_PRODUCT, [], [evidence])
