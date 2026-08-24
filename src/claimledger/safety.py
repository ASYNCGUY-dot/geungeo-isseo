from collections.abc import Sequence

from claimledger.domain import (
    ConfirmedProduct,
    InteractionEvidence,
    OfficialFieldStatus,
    OfficialProductCaution,
    SafetySignal,
    classify_general_caution,
)


def build_safety_signals(
    product: ConfirmedProduct,
    product_cautions: Sequence[OfficialProductCaution],
    interaction_evidence: Sequence[InteractionEvidence],
) -> tuple[SafetySignal, ...]:
    product_signals: list[SafetySignal] = []
    for caution in product_cautions:
        category = classify_general_caution(caution.original_text)
        if caution.status is not OfficialFieldStatus.VERIFIED or category is None:
            continue
        product_signals.append(
            SafetySignal(
                kind="official_product_caution",
                message=caution.original_text,
                source_id=product.product.source_id,
                official_identifier=product.product.report_no,
                retrieved_at=product.product.retrieved_at,
                source_text=caution.original_text,
                caution_category=category,
            )
        )

    report_no = product.product.report_no
    interaction_signals: list[SafetySignal] = []
    for evidence in interaction_evidence:
        if evidence.product_report_no is not None and evidence.product_report_no != report_no:
            raise ValueError("interaction evidence product report number does not match confirmed product")
        interaction_signals.append(
            SafetySignal(
                kind="official_interaction_caution",
                message=evidence.source_text,
                source_id=evidence.source_id,
                source_url=evidence.source_url,
                official_identifier=evidence.official_identifier,
                retrieved_at=evidence.retrieved_at,
                source_text=evidence.source_text,
                caution_category=evidence.caution_category,
            )
        )

    return tuple(product_signals) + tuple(interaction_signals)
