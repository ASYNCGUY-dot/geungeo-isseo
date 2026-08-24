from collections.abc import Sequence

from claimledger.domain import Claim, ConfirmedProduct, EvidenceRecord, Verdict
from claimledger.errors import DecisionInvariantError
from claimledger.identity import require_confirmed_product
from claimledger.product_evidence import (
    ProductEvidenceBundle,
    ProductSourceSnapshot,
    require_product_evidence_ready,
)


def decide_supported_claim(
    claim: Claim,
    product: ConfirmedProduct | None,
    evidence: Sequence[EvidenceRecord],
    product_evidence: ProductEvidenceBundle,
) -> Verdict:
    del claim
    confirmed_product = require_confirmed_product(product)
    report_no = confirmed_product.product.report_no
    if any(
        record.product_report_no is not None and record.product_report_no != report_no
        for record in evidence
    ):
        return Verdict.UNVERIFIABLE
    if not evidence:
        return Verdict.UNVERIFIABLE

    supporting_evidence = [record for record in evidence if record.supports_claim]
    if not supporting_evidence:
        return Verdict.UNVERIFIABLE

    require_product_evidence_ready(product_evidence)
    confirmed_snapshot = ProductSourceSnapshot.from_candidate(confirmed_product.product)
    if product_evidence.product_snapshot != confirmed_snapshot:
        raise DecisionInvariantError("product evidence is not ready: PRODUCT_SNAPSHOT_CONFLICT")
    return Verdict.CONFIRMED
