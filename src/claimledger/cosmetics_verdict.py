"""Verdicts for advertisement claims about a confirmed functional cosmetic.

Only whitening and wrinkle improvement are judged. `confirmed` requires a user-confirmed product
whose official efficacy was read completely, a sentence that is one of the allowlisted forms, a
strength no higher than the official "도움을 준다", and an advertisement in which every other
sentence is an allowlisted form, the recognized disclaimer or an invitation in the closed vocabulary.
General cosmetics are not in the MFDS lists and can never be confirmed here.
"""

from collections.abc import Sequence
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from claimledger.claims_v1 import STRENGTH_RANK, ExpressionStrength
from claimledger.cosmetics_claims import (
    COSMETIC_CLAIM_VERSION,
    CosmeticClaim,
    asserted_functions,
    extract_cosmetic_claims,
    unread_sentences,
)
from claimledger.cosmetics_official import (
    COSMETIC_EFFICACY_VERSION,
    CosmeticFunction,
    EfficacyStatus,
    OfficialSentence,
    parse_cosmetic_efficacy,
)
from claimledger.domain import Verdict
from claimledger.sources.functional_cosmetics import FunctionalCosmetic

COSMETIC_VERDICT_VERSION = "cosmetic-verdict-v1.2"
JUDGED_FUNCTIONS = frozenset({CosmeticFunction.WHITENING, CosmeticFunction.WRINKLE})
_OFFICIAL_STRENGTH = ExpressionStrength.SUPPORT
# An official function on a narrower scope neither confirms nor contradicts the general claim.
_NARROWER = {CosmeticFunction.WRINKLE: frozenset({CosmeticFunction.LIP_WRINKLE})}


class CosmeticVerdictReason(StrEnum):
    PRODUCT_IDENTITY_UNCONFIRMED = "PRODUCT_IDENTITY_UNCONFIRMED"
    CLAIM_UNCONFIRMED = "CLAIM_UNCONFIRMED"
    CLAIM_NOT_PLAINLY_ASSERTED = "CLAIM_NOT_PLAINLY_ASSERTED"
    MEDICAL_CLAIM_BEYOND_COSMETIC_SCOPE = "MEDICAL_CLAIM_BEYOND_COSMETIC_SCOPE"
    CLAIM_OUTSIDE_RULE_SCOPE = "CLAIM_OUTSIDE_RULE_SCOPE"
    FUNCTION_RULE_NOT_READY = "FUNCTION_RULE_NOT_READY"
    CLAIM_STRENGTH_UNCLEAR = "CLAIM_STRENGTH_UNCLEAR"
    OFFICIAL_RECORD_WITHDRAWN = "OFFICIAL_RECORD_WITHDRAWN"
    OFFICIAL_EFFICACY_MISSING = "OFFICIAL_EFFICACY_MISSING"
    OFFICIAL_EFFICACY_TEMPLATE_REMNANT = "OFFICIAL_EFFICACY_TEMPLATE_REMNANT"
    OFFICIAL_EFFICACY_CONFLICTING = "OFFICIAL_EFFICACY_CONFLICTING"
    OFFICIAL_EFFICACY_UNRECOGNIZED = "OFFICIAL_EFFICACY_UNRECOGNIZED"
    FUNCTION_NOT_IN_OFFICIAL_EFFICACY = "FUNCTION_NOT_IN_OFFICIAL_EFFICACY"
    EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL = "EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL"
    CLAIM_SCOPE_UNRESOLVED = "CLAIM_SCOPE_UNRESOLVED"
    AD_TEXT_NOT_FULLY_READ = "AD_TEXT_NOT_FULLY_READ"
    MATCHES_OFFICIAL_EFFICACY = "MATCHES_OFFICIAL_EFFICACY"


_HELD = {
    EfficacyStatus.MISSING: CosmeticVerdictReason.OFFICIAL_EFFICACY_MISSING,
    EfficacyStatus.TEMPLATE_REMNANT: CosmeticVerdictReason.OFFICIAL_EFFICACY_TEMPLATE_REMNANT,
    EfficacyStatus.CONFLICTING_FIELDS: CosmeticVerdictReason.OFFICIAL_EFFICACY_CONFLICTING,
    EfficacyStatus.UNRECOGNIZED_WORDING: CosmeticVerdictReason.OFFICIAL_EFFICACY_UNRECOGNIZED,
}


class ConfirmedCosmetic(BaseModel):
    model_config = {"frozen": True}

    product: FunctionalCosmetic
    confirmed_by_user: bool


class CosmeticDecision(BaseModel):
    model_config = {"frozen": True}

    claim: CosmeticClaim
    verdict: Verdict
    reason: CosmeticVerdictReason
    official_sentences: tuple[OfficialSentence, ...] = ()
    efficacy_version: Literal["cosmetic-efficacy-v1.0"] = COSMETIC_EFFICACY_VERSION
    extraction_version: Literal["cosmetic-claim-v1.6"] = COSMETIC_CLAIM_VERSION
    verdict_version: Literal["cosmetic-verdict-v1.2"] = COSMETIC_VERDICT_VERSION


def _decision(
    claim: CosmeticClaim,
    verdict: Verdict,
    reason: CosmeticVerdictReason,
    official_sentences: tuple[OfficialSentence, ...] = (),
) -> CosmeticDecision:
    return CosmeticDecision(claim=claim, verdict=verdict, reason=reason, official_sentences=official_sentences)


def _decide_sentence(claim: CosmeticClaim, product: ConfirmedCosmetic | None) -> CosmeticDecision:
    """Decide one sentence on its own; rules apply in a fixed fail-closed order and the first match wins."""
    unverifiable, mismatch = Verdict.UNVERIFIABLE, Verdict.MISMATCH
    reason = CosmeticVerdictReason
    if product is None or not product.confirmed_by_user:
        return _decision(claim, unverifiable, reason.PRODUCT_IDENTITY_UNCONFIRMED)
    if not claim.confirmed_by_user:
        return _decision(claim, unverifiable, reason.CLAIM_UNCONFIRMED)
    if claim.strength is ExpressionStrength.TREATMENT_PREVENTION:
        return _decision(claim, mismatch, reason.MEDICAL_CLAIM_BEYOND_COSMETIC_SCOPE)
    candidates = frozenset(claim.function_candidates)
    if not candidates:
        # With cues set aside, every function word stood before a denial, a caution or a question.
        held = reason.CLAIM_NOT_PLAINLY_ASSERTED if claim.set_aside_cues else reason.CLAIM_OUTSIDE_RULE_SCOPE
        return _decision(claim, unverifiable, held)
    if not candidates <= JUDGED_FUNCTIONS:
        return _decision(claim, unverifiable, reason.FUNCTION_RULE_NOT_READY)
    if claim.strength is None:
        return _decision(claim, unverifiable, reason.CLAIM_STRENGTH_UNCLEAR)

    row = product.product
    if row.withdrawn:
        return _decision(claim, unverifiable, reason.OFFICIAL_RECORD_WITHDRAWN)
    if row.effect_doc_unreadable:
        # The sentence beside a document that could not be read cannot be checked against it.
        return _decision(claim, unverifiable, reason.OFFICIAL_EFFICACY_UNRECOGNIZED)
    efficacy = parse_cosmetic_efficacy(row.effect_text, row.effect_name)
    if efficacy.status is not EfficacyStatus.READABLE:
        return _decision(claim, unverifiable, _HELD[efficacy.status])

    official = efficacy.functions
    asserted = asserted_functions(claim)
    exceeds = STRENGTH_RANK[claim.strength] > STRENGTH_RANK[_OFFICIAL_STRENGTH]
    # A sentence that was not fully read is judged on its keywords only when none of them is official.
    absent = (asserted if asserted is not None else candidates) - official
    if absent and (asserted is not None or not candidates & official):
        if any(not _NARROWER.get(function, frozenset()) & official for function in absent):
            # A function word with "수 있" alone does not say that the product has the function.
            if asserted is None and STRENGTH_RANK[claim.strength] < STRENGTH_RANK[_OFFICIAL_STRENGTH]:
                return _decision(claim, unverifiable, reason.CLAIM_SCOPE_UNRESOLVED)
            return _decision(claim, mismatch, reason.FUNCTION_NOT_IN_OFFICIAL_EFFICACY)
        if not exceeds:
            return _decision(claim, unverifiable, reason.CLAIM_SCOPE_UNRESOLVED)
    if exceeds:
        return _decision(claim, mismatch, reason.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL)
    if asserted is None:
        return _decision(claim, unverifiable, reason.CLAIM_SCOPE_UNRESOLVED)
    quoted = tuple(sentence for sentence in efficacy.sentences if sentence.function in asserted)
    return _decision(claim, Verdict.CONFIRMED, reason.MATCHES_OFFICIAL_EFFICACY, quoted)


def decide_cosmetic_ad(
    text: str, claims: Sequence[CosmeticClaim], product: ConfirmedCosmetic | None,
) -> tuple[CosmeticDecision, ...]:
    """Decide every claim of one advertisement.

    A sentence is confirmed only when every other sentence of the advertisement is an allowlisted
    form, the recognized disclaimer or an invitation to use or buy read in the closed vocabulary
    (those are not listed as unread). Anything else beside it may change what it says, and a
    keyword verdict on that neighbour ("(피부과 시술 병행 시)" is flagged for "시술") does not show
    that it was understood.
    """
    unconfirmed = [claim.model_copy(update={"confirmed_by_user": False}) for claim in claims]
    if unconfirmed != list(extract_cosmetic_claims(text)):
        raise ValueError("the claims are not the ones extracted from this advertisement text")
    decisions = tuple(_decide_sentence(claim, product) for claim in claims)
    if not unread_sentences(text) and all(asserted_functions(claim) is not None for claim in claims):
        return decisions
    return tuple(
        _decision(decision.claim, Verdict.UNVERIFIABLE, CosmeticVerdictReason.AD_TEXT_NOT_FULLY_READ)
        if decision.verdict is Verdict.CONFIRMED else decision
        for decision in decisions
    )


__all__ = [
    "COSMETIC_VERDICT_VERSION",
    "JUDGED_FUNCTIONS",
    "ConfirmedCosmetic",
    "CosmeticDecision",
    "CosmeticVerdictReason",
    "decide_cosmetic_ad",
]
