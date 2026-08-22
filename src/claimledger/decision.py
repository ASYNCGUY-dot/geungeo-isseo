from collections.abc import Sequence

from claimledger.domain import Claim, ConfirmedProduct, EvidenceRecord, Verdict
from claimledger.identity import require_confirmed_product


def decide_supported_claim(
    claim: Claim,
    product: ConfirmedProduct | None,
    evidence: Sequence[EvidenceRecord],
) -> Verdict:
    del claim
    confirmed_product = require_confirmed_product(product)
    if not evidence:
        return Verdict.UNVERIFIABLE

    supporting_evidence = [record for record in evidence if record.supports_claim]
    if not supporting_evidence:
        return Verdict.UNVERIFIABLE

    report_no = confirmed_product.product.report_no
    if any(
        record.product_report_no is not None and record.product_report_no != report_no
        for record in supporting_evidence
    ):
        return Verdict.UNVERIFIABLE
    return Verdict.CONFIRMED
