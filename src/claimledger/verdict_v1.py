from collections.abc import Sequence
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from claimledger.carriers import borrowed_statement
from claimledger.claims_v1 import (
    CLAIM_EXTRACTION_VERSION,
    STRENGTH_RANK,
    AdClaim,
    ExpressionStrength,
    extract_claims,
    supports_confirmation,
    unread_sentences,
)
from claimledger.domain import ConfirmedProduct, Verdict
from claimledger.errors import IdentityRequiredError
from claimledger.headerless import headerless_effects
from claimledger.identity import require_confirmed_product
from claimledger.official_v2 import (
    EFFECT_GROUP,
    OFFICIAL_FUNCTION_V2_VERSION,
    EffectKey,
    OfficialEffect,
    effect_mentioned,
    parse_official_function_v2,
)

CLAIM_VERDICT_VERSION = "claim-verdict-v1.4"
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
    OFFICIAL_STATEMENT_OF_OTHER_INGREDIENT = "OFFICIAL_STATEMENT_OF_OTHER_INGREDIENT"
    EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL = "EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL"
    MATCHES_OFFICIAL_FUNCTION = "MATCHES_OFFICIAL_FUNCTION"
    MATCHES_UNLABELED_OFFICIAL_FUNCTION = "MATCHES_UNLABELED_OFFICIAL_FUNCTION"
    AD_TEXT_NOT_FULLY_READ = "AD_TEXT_NOT_FULLY_READ"


class ClaimDecision(BaseModel):
    model_config = {"frozen": True}

    claim: AdClaim
    verdict: Verdict
    reason: VerdictReason
    official_effect: OfficialEffect | None = None
    rule_version: Literal["claim-verdict-v1.4"] = CLAIM_VERDICT_VERSION
    extraction_version: Literal["claim-extract-v1.4"] = CLAIM_EXTRACTION_VERSION
    official_parser_version: Literal["official-function-v2.11"] = OFFICIAL_FUNCTION_V2_VERSION


def _decision(
    claim: AdClaim,
    verdict: Verdict,
    reason: VerdictReason,
    official_effect: OfficialEffect | None = None,
) -> ClaimDecision:
    return ClaimDecision(claim=claim, verdict=verdict, reason=reason, official_effect=official_effect)


def _attributed(effects: tuple[OfficialEffect, ...], candidates: tuple[EffectKey, ...]) -> list[OfficialEffect]:
    return [
        official
        for official in effects
        if official.effect in candidates and EFFECT_GROUP[official.effect] in official.attributed_groups
    ]


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
    attributed = _attributed(parsed.effects, claim.effect_candidates)
    # A statement that is word for word another notified ingredient's official statement, with
    # that ingredient in the raw materials and no header of its own, is not the header's evidence.
    own = [
        item
        for item in attributed
        if borrowed_statement(item, confirmed.product.raw_materials, function_text) is None
    ]
    if attributed and not own:
        return _decision(claim, Verdict.UNVERIFIABLE, VerdictReason.OFFICIAL_STATEMENT_OF_OTHER_INGREDIENT)
    official = own[0] if own else None
    match_reason = VerdictReason.MATCHES_OFFICIAL_FUNCTION
    if official is None:
        # No header anywhere: the statement's owner is inferred from C003 wording and raw materials.
        unlabeled = [
            item
            for item in headerless_effects(function_text, confirmed.product.raw_materials)
            if item.effect in claim.effect_candidates
            and borrowed_statement(item, confirmed.product.raw_materials, function_text) is None
        ]
        if unlabeled:
            official = unlabeled[0]
            match_reason = VerdictReason.MATCHES_UNLABELED_OFFICIAL_FUNCTION
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
    return _decision(claim, Verdict.CONFIRMED, match_reason, official)


def _fully_read(claim: AdClaim) -> bool:
    return any(supports_confirmation(claim, effect) for effect in claim.effect_candidates)


def decide_ad(text: str, claims: Sequence[AdClaim], product: ConfirmedProduct | None) -> tuple[ClaimDecision, ...]:
    """Decide every claim of one advertisement.

    A claim is confirmed only when every other sentence of the advertisement is a fully read support
    statement or the recognized disclaimer. Anything else beside it may change what it says ("단 2주.",
    "아래 문구는 사실이 아닙니다.", "하루 3캡슐이면 충분합니다."), and a keyword verdict on that neighbour
    ("(병원 치료 병행 시)" is flagged for "치료") does not show that it was understood.
    """
    unconfirmed = [claim.model_copy(update={"confirmed_by_user": False}) for claim in claims]
    if unconfirmed != list(extract_claims(text)):
        raise ValueError("the claims are not the ones extracted from this advertisement text")
    decisions = tuple(decide_claim(claim, product) for claim in claims)
    if not unread_sentences(text) and all(_fully_read(claim) for claim in claims):
        return decisions
    return tuple(
        _decision(decision.claim, Verdict.UNVERIFIABLE, VerdictReason.AD_TEXT_NOT_FULLY_READ)
        if decision.verdict is Verdict.CONFIRMED else decision
        for decision in decisions
    )


__all__ = ["CLAIM_VERDICT_VERSION", "ClaimDecision", "VerdictReason", "decide_ad", "decide_claim"]
