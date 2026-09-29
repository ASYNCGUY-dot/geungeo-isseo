from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from claimledger.claims_v1 import (
    CLAIM_EXTRACTION_VERSION,
    STRENGTH_RANK,
    AdClaim,
    ExpressionStrength,
    supports_confirmation,
)
from claimledger.domain import ConfirmedProduct, Verdict
from claimledger.errors import IdentityRequiredError
from claimledger.identity import require_confirmed_product
from claimledger.official_v2 import (
    EFFECT_GROUP,
    OFFICIAL_FUNCTION_V2_VERSION,
    EffectKey,
    OfficialEffect,
    effect_mentioned,
    parse_official_function_v2,
)

CLAIM_VERDICT_VERSION = "claim-verdict-v1.1"
_OFFICIAL_STRENGTH = ExpressionStrength.SUPPORT


class VerdictReason(StrEnum):
    PRODUCT_IDENTITY_UNCONFIRMED = "PRODUCT_IDENTITY_UNCONFIRMED"
    CLAIM_UNCONFIRMED = "CLAIM_UNCONFIRMED"
    DISEASE_CLAIM_BEYOND_FUNCTIONAL_SCOPE = "DISEASE_CLAIM_BEYOND_FUNCTIONAL_SCOPE"
    CLAIM_OUTSIDE_RULE_SCOPE = "CLAIM_OUTSIDE_RULE_SCOPE"
    CLAIM_STRENGTH_UNCLEAR = "CLAIM_STRENGTH_UNCLEAR"
    CLAIM_SCOPE_UNRESOLVED = "CLAIM_SCOPE_UNRESOLVED"
    OFFICIAL_FUNCTION_MISSING = "OFFICIAL_FUNCTION_MISSING"
    EFFECT_NOT_IN_OFFICIAL_FUNCTIONS = "EFFECT_NOT_IN_OFFICIAL_FUNCTIONS"
    OFFICIAL_ATTRIBUTION_AMBIGUOUS = "OFFICIAL_ATTRIBUTION_AMBIGUOUS"
    EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL = "EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL"
    MATCHES_OFFICIAL_FUNCTION = "MATCHES_OFFICIAL_FUNCTION"


class ClaimDecision(BaseModel):
    model_config = {"frozen": True}

    claim: AdClaim
    verdict: Verdict
    reason: VerdictReason
    official_effect: OfficialEffect | None = None
    rule_version: Literal["claim-verdict-v1.1"] = CLAIM_VERDICT_VERSION
    extraction_version: Literal["claim-extract-v1.2"] = CLAIM_EXTRACTION_VERSION
    official_parser_version: Literal["official-function-v2.4"] = OFFICIAL_FUNCTION_V2_VERSION


def _decision(
    claim: AdClaim,
    verdict: Verdict,
    reason: VerdictReason,
    official_effect: OfficialEffect | None = None,
) -> ClaimDecision:
    return ClaimDecision(claim=claim, verdict=verdict, reason=reason, official_effect=official_effect)


def _attributed(effects: tuple[OfficialEffect, ...], candidates: tuple[EffectKey, ...]) -> OfficialEffect | None:
    for official in effects:
        if official.effect in candidates and EFFECT_GROUP[official.effect] in official.attributed_groups:
            return official
    return None


def decide_claim(claim: AdClaim, product: ConfirmedProduct | None) -> ClaimDecision:
    """Decide one advertisement claim against the confirmed product's official function text.

    Rules are applied in a fixed fail-closed order; the first matching rule wins.
    """
    try:
        confirmed = require_confirmed_product(product)
    except IdentityRequiredError:
        return _decision(claim, Verdict.UNVERIFIABLE, VerdictReason.PRODUCT_IDENTITY_UNCONFIRMED)
    if not claim.confirmed_by_user:
        return _decision(claim, Verdict.UNVERIFIABLE, VerdictReason.CLAIM_UNCONFIRMED)
    if claim.strength is ExpressionStrength.TREATMENT_PREVENTION:
        return _decision(claim, Verdict.MISMATCH, VerdictReason.DISEASE_CLAIM_BEYOND_FUNCTIONAL_SCOPE)
    if not claim.effect_candidates:
        return _decision(claim, Verdict.UNVERIFIABLE, VerdictReason.CLAIM_OUTSIDE_RULE_SCOPE)
    if claim.strength is None:
        return _decision(claim, Verdict.UNVERIFIABLE, VerdictReason.CLAIM_STRENGTH_UNCLEAR)

    function_text = confirmed.product.primary_function
    if not function_text.strip():
        return _decision(claim, Verdict.UNVERIFIABLE, VerdictReason.OFFICIAL_FUNCTION_MISSING)

    parsed = parse_official_function_v2(function_text)
    official = _attributed(parsed.effects, claim.effect_candidates)
    if official is None:
        mentioned = any(effect_mentioned(function_text, effect) for effect in claim.effect_candidates) or any(
            item.effect in claim.effect_candidates for item in parsed.effects
        )
        reason = (
            VerdictReason.OFFICIAL_ATTRIBUTION_AMBIGUOUS
            if mentioned
            else VerdictReason.EFFECT_NOT_IN_OFFICIAL_FUNCTIONS
        )
        verdict = Verdict.UNVERIFIABLE if mentioned else Verdict.MISMATCH
        return _decision(claim, verdict, reason)

    if STRENGTH_RANK[claim.strength] > STRENGTH_RANK[_OFFICIAL_STRENGTH]:
        return _decision(claim, Verdict.MISMATCH, VerdictReason.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL, official)
    if not supports_confirmation(claim, official.effect):
        return _decision(claim, Verdict.UNVERIFIABLE, VerdictReason.CLAIM_SCOPE_UNRESOLVED)
    return _decision(claim, Verdict.CONFIRMED, VerdictReason.MATCHES_OFFICIAL_FUNCTION, official)


__all__ = ["CLAIM_VERDICT_VERSION", "ClaimDecision", "VerdictReason", "decide_claim"]
