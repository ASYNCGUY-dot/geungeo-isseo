import hashlib
import json
from collections.abc import Iterable

from pydantic import ValidationError

from claimledger.domain import (
    CLAIM_FINGERPRINT_VERSION,
    Claim,
    ClaimSupportRecord,
    ConfirmedProduct,
    Verdict,
)
from claimledger.errors import DecisionInvariantError
from claimledger.identity import require_confirmed_product
from claimledger.product_evidence import (
    ProductEvidenceBundle,
    ProductSourceSnapshot,
    require_product_evidence_ready,
)


def claim_fingerprint(claim: Claim) -> str:
    payload = json.dumps(
        (
            CLAIM_FINGERPRINT_VERSION,
            claim.original_text,
            claim.normalized_subject,
        ),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{CLAIM_FINGERPRINT_VERSION}:{hashlib.sha256(payload).hexdigest()}"


def decide_supported_claim(
    claim: Claim,
    product: ConfirmedProduct | None,
    evidence: Iterable[ClaimSupportRecord],
    product_evidence: ProductEvidenceBundle,
) -> Verdict:
    confirmed_product = require_confirmed_product(product)
    report_no = confirmed_product.product.report_no

    try:
        validated_claim = Claim.model_validate(claim.model_dump(warnings=False))
        support_records = tuple(
            ClaimSupportRecord.model_validate(record.model_dump(warnings=False))
            for record in evidence
        )
    except (AttributeError, TypeError, ValueError, ValidationError):
        return Verdict.UNVERIFIABLE
    if not support_records:
        return Verdict.UNVERIFIABLE

    fingerprint = claim_fingerprint(validated_claim)
    if any(
        record.claim_fingerprint != fingerprint
        or record.confirmed_product_report_no != report_no
        for record in support_records
    ):
        return Verdict.UNVERIFIABLE

    require_product_evidence_ready(product_evidence)
    confirmed_snapshot = ProductSourceSnapshot.from_candidate(confirmed_product.product)
    if product_evidence.product_snapshot.report_no != confirmed_snapshot.report_no:
        raise DecisionInvariantError("product evidence is not ready: REPORT_NUMBER_CONFLICT")
    if product_evidence.product_snapshot != confirmed_snapshot:
        raise DecisionInvariantError("product evidence is not ready: PRODUCT_SNAPSHOT_CONFLICT")
    return Verdict.CONFIRMED
