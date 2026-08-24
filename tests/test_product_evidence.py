from datetime import UTC, datetime

import pytest

from claimledger.domain import (
    ConfirmedProduct,
    MappingStatus,
    OfficialFieldStatus,
    ProductCandidate,
)
from claimledger.errors import DecisionInvariantError
from claimledger.product_evidence import (
    ProductEvidenceStatus,
    build_product_evidence,
    require_product_evidence_ready,
)

NOW = datetime(2026, 8, 24, tzinfo=UTC)
CORE_PRODUCT = ProductCandidate(
    report_no="TEST-EVIDENCE-001",
    name="루테인 지아잔틴 테스트 제품",
    company="테스트 제조사",
    primary_function="눈 건강에 도움을 줄 수 있음",
    raw_materials="루테인지아잔틴복합추출물",
    intake_method="의약품 복용 시 전문가와 상담하십시오.",
    source_id="C003",
    retrieved_at=NOW,
)
CONFIRMED_CORE_PRODUCT = ConfirmedProduct(product=CORE_PRODUCT, confirmed_by_user=True)


def test_confirmed_product_with_complete_official_data_builds_ready_bundle() -> None:
    bundle = build_product_evidence(CONFIRMED_CORE_PRODUCT)

    assert bundle.status is ProductEvidenceStatus.READY
    assert bundle.report_no == CONFIRMED_CORE_PRODUCT.product.report_no
    assert bundle.ingredient_mapping.status is MappingStatus.VERIFIED
    assert all(
        statement.status is OfficialFieldStatus.VERIFIED
        for statement in bundle.official_functions
    )
    assert bundle.rule_versions == (
        "ingredient-map-v1",
        "official-function-v1",
    )
    assert bundle.source_ids == ("C003",)
    assert bundle.source_timestamps == (NOW,)
    assert bundle.reason_codes == ()
    assert len(bundle.official_cautions) == 2
    assert len(bundle.safety_signals) == 1
    assert bundle.safety_signals[0].is_safety_clearance is False


@pytest.mark.parametrize("field", ["primary_function", "raw_materials", "intake_method"])
def test_missing_required_official_field_fails_closed(field: str) -> None:
    product = CONFIRMED_CORE_PRODUCT.model_copy(
        update={"product": CONFIRMED_CORE_PRODUCT.product.model_copy(update={field: ""})}
    )

    bundle = build_product_evidence(product)

    assert bundle.status is ProductEvidenceStatus.UNVERIFIABLE
    assert f"MISSING_{field.upper()}" in bundle.reason_codes


def test_ambiguous_ingredient_mapping_is_not_ready() -> None:
    product = CONFIRMED_CORE_PRODUCT.model_copy(
        update={
            "product": CONFIRMED_CORE_PRODUCT.product.model_copy(
                update={
                    "raw_materials": "루테인지아잔틴복합추출물, EPA 및 DHA 함유 유지"
                }
            )
        }
    )

    bundle = build_product_evidence(product)

    assert bundle.status is ProductEvidenceStatus.AMBIGUOUS
    assert bundle.reason_codes == ("AMBIGUOUS_INGREDIENT_MAPPING",)


def test_unparsed_official_function_is_not_ready() -> None:
    product = CONFIRMED_CORE_PRODUCT.model_copy(
        update={
            "product": CONFIRMED_CORE_PRODUCT.product.model_copy(
                update={"primary_function": "눈 건강이 놀랍게 달라집니다"}
            )
        }
    )

    bundle = build_product_evidence(product)

    assert bundle.status is ProductEvidenceStatus.UNVERIFIABLE
    assert "UNPARSED_OFFICIAL_FUNCTION" in bundle.reason_codes


def test_unverifiable_mapping_has_its_own_stable_reason_code() -> None:
    product = CONFIRMED_CORE_PRODUCT.model_copy(
        update={
            "product": CONFIRMED_CORE_PRODUCT.product.model_copy(
                update={"primary_function": "", "raw_materials": ""}
            )
        }
    )

    bundle = build_product_evidence(product)

    assert bundle.status is ProductEvidenceStatus.UNVERIFIABLE
    assert "UNVERIFIABLE_INGREDIENT_MAPPING" in bundle.reason_codes


def test_readiness_guard_raises_domain_error_with_stable_reason_codes() -> None:
    product = CONFIRMED_CORE_PRODUCT.model_copy(
        update={
            "product": CONFIRMED_CORE_PRODUCT.product.model_copy(
                update={"raw_materials": ""}
            )
        }
    )
    bundle = build_product_evidence(product)

    with pytest.raises(DecisionInvariantError, match="MISSING_RAW_MATERIALS"):
        require_product_evidence_ready(bundle)


def test_readiness_guard_recomputes_structural_readiness() -> None:
    ready_bundle = build_product_evidence(CONFIRMED_CORE_PRODUCT)
    ambiguous_product = CONFIRMED_CORE_PRODUCT.model_copy(
        update={
            "product": CONFIRMED_CORE_PRODUCT.product.model_copy(
                update={
                    "raw_materials": "루테인지아잔틴복합추출물, EPA 및 DHA 함유 유지"
                }
            )
        }
    )
    ambiguous_mapping = build_product_evidence(ambiguous_product).ingredient_mapping
    forged_ready_bundle = ready_bundle.model_copy(
        update={"ingredient_mapping": ambiguous_mapping}
    )

    with pytest.raises(DecisionInvariantError, match="AMBIGUOUS_INGREDIENT_MAPPING"):
        require_product_evidence_ready(forged_ready_bundle)


def test_readiness_guard_accepts_only_a_ready_bundle() -> None:
    bundle = build_product_evidence(CONFIRMED_CORE_PRODUCT)

    assert require_product_evidence_ready(bundle) is bundle
