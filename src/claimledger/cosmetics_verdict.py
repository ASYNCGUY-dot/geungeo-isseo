"""Verdicts for advertisement claims about a confirmed functional cosmetic.

Whitening, wrinkle improvement and sun protection are judged. `confirmed` requires a user-confirmed
product whose official efficacy was read completely, a sentence that is one of the allowlisted forms,
a strength no higher than the official wording, and an advertisement in which every other sentence
is an allowlisted form, the recognized disclaimer or an invitation in the closed vocabulary.
A mismatch for a function the product lacks needs less: it is enough that the sentence names that
function as what is helped.

A sunscreen index is compared part by part with the official one, and only in a sentence that was
read completely or where a short phrase binds it to this product ("SPF50+ 표기의 이 제품"):
elsewhere it may belong to a comparison, a recommendation or another product. A bound index in a
sentence not read completely gives a mismatch or a hold, never a confirmation. A
higher SPF or PA grade, or a water resistance the record does not hold, is a mismatch; a lower one
is no overstatement but not what the record says either, and is held. The reported list also carries
the SPF and the PA grade as separate items: where one is filled and disagrees with the sentence, or
cannot be read, the index is confirmed against neither, and only a value above both is a mismatch.

Outside the forms a sunscreen word is a claim only as what is helped or with an absolute word on
the blocking itself, and effect verbs ("지워", "밝아") say nothing about sun protection. A record
whose own name or index items speak of sun protection is not called a product without it.
General cosmetics are not in the MFDS lists and can never be confirmed here.
"""

import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from claimledger.claims_v1 import STRENGTH_RANK, ExpressionStrength
from claimledger.cosmetics_claims import (
    COSMETIC_CLAIM_VERSION,
    CosmeticClaim,
    asserted_functions,
    binds_index,
    blocks_absolutely,
    extract_cosmetic_claims,
    form_index,
    helped_functions,
    invitation_count,
    unread_sentences,
)
from claimledger.cosmetics_official import (
    COSMETIC_EFFICACY_VERSION,
    CosmeticFunction,
    EfficacyStatus,
    OfficialSentence,
    SunscreenIndex,
    parse_cosmetic_efficacy,
)
from claimledger.domain import Verdict
from claimledger.sources.functional_cosmetics import FunctionalCosmetic

COSMETIC_VERDICT_VERSION = "cosmetic-verdict-v1.11"
JUDGED_FUNCTIONS = frozenset({CosmeticFunction.WHITENING, CosmeticFunction.WRINKLE, CosmeticFunction.SUNSCREEN})
_OFFICIAL_STRENGTH = ExpressionStrength.SUPPORT
_WATER_RANK = {"": 0, "내수성": 1, "지속내수성": 2}
_SPF_ITEM = re.compile(r"(?:spf)?(\d{1,3})(\+?)")
_SUN_IN_NAME = re.compile(r"spf|자외선|[선썬](?:크림|블록|스틱|쿠션|로션|젤|밤)|(?<![a-z])sun(?:screen|block|cream|stick)?(?![a-z])")
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
    SUNSCREEN_INDEX_EXCEEDS_OFFICIAL = "SUNSCREEN_INDEX_EXCEEDS_OFFICIAL"
    SUNSCREEN_INDEX_DIFFERS_FROM_OFFICIAL = "SUNSCREEN_INDEX_DIFFERS_FROM_OFFICIAL"
    SUNSCREEN_INDEX_UNCLEAR = "SUNSCREEN_INDEX_UNCLEAR"
    OFFICIAL_SUNSCREEN_INDEX_MISSING = "OFFICIAL_SUNSCREEN_INDEX_MISSING"
    OFFICIAL_SUNSCREEN_INDEX_CONFLICTING = "OFFICIAL_SUNSCREEN_INDEX_CONFLICTING"
    OFFICIAL_SUNSCREEN_RECORD_CONFLICTING = "OFFICIAL_SUNSCREEN_RECORD_CONFLICTING"
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
    efficacy_version: Literal["cosmetic-efficacy-v1.3"] = COSMETIC_EFFICACY_VERSION
    extraction_version: Literal["cosmetic-claim-v1.16"] = COSMETIC_CLAIM_VERSION
    verdict_version: Literal["cosmetic-verdict-v1.11"] = COSMETIC_VERDICT_VERSION


def _decision(
    claim: CosmeticClaim,
    verdict: Verdict,
    reason: CosmeticVerdictReason,
    official_sentences: tuple[OfficialSentence, ...] = (),
) -> CosmeticDecision:
    return CosmeticDecision(claim=claim, verdict=verdict, reason=reason, official_sentences=official_sentences)


def _part(stated: tuple[int, ...], official: set[tuple[int, ...] | None]) -> str:
    """One part of a stated index against the official values of that part; None is a value that was not read."""
    known = official - {None}
    if all(stated > value for value in known):
        return "exceeds"
    if len(official) > 1:
        return "conflicting"
    return "same" if {stated} == official else "differs"


def _index_reason(
    claim: CosmeticClaim, index: SunscreenIndex | None, row: FunctionalCosmetic,
) -> CosmeticVerdictReason | None:
    """Why the index a sentence states is not the official one; None when every stated part is."""
    reason = CosmeticVerdictReason
    stated = (*claim.spf, *claim.pa, *claim.water)
    # The words and the form must read the same index: a space inside it ("지속 내수성") leaves
    # the claimed value unknown.
    if max(len(claim.spf), len(claim.pa), len(claim.water)) > 1 or "?" in stated:
        return reason.SUNSCREEN_INDEX_UNCLEAR
    if form_index(claim) != (claim.spf, claim.pa, claim.water):
        return reason.SUNSCREEN_INDEX_UNCLEAR
    if index is None:
        return reason.OFFICIAL_SUNSCREEN_INDEX_MISSING
    parts = []
    if claim.spf:
        official: set[tuple[int, ...] | None] = {(index.spf, int(index.plus))}
        # A filled item that is no plain value was not read: it cannot agree with the sentence.
        if item := "".join(row.spf.casefold().split()):
            read = _SPF_ITEM.fullmatch(item)
            official.add((int(read.group(1)), int(bool(read.group(2)))) if read else None)
        parts.append(_part((int(claim.spf[0].rstrip("+")), int(claim.spf[0].endswith("+"))), official))
    if claim.pa:
        official = {(index.pa,)}
        if item := row.pa.strip():
            official.add((int(item),) if item in {"0", "1", "2", "3", "4"} else None)
        parts.append(_part((len(claim.pa[0]),), official))
    if claim.water:
        parts.append(_part((_WATER_RANK[claim.water[0]],), {(_WATER_RANK[index.water],)}))
    for outcome, found in (
        ("exceeds", reason.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL),
        ("conflicting", reason.OFFICIAL_SUNSCREEN_INDEX_CONFLICTING),
        ("differs", reason.SUNSCREEN_INDEX_DIFFERS_FROM_OFFICIAL),
    ):
        if outcome in parts:
            return found
    return None


def _names_sun_protection(row: FunctionalCosmetic) -> bool:
    """Whether the record speaks of sun protection outside its efficacy statement."""
    return bool(
        row.sunscreen or row.spf.strip() or row.pa.strip() not in {"", "0"}
        or _SUN_IN_NAME.search("".join(row.item_name.casefold().split()))
    )


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
    asserted = asserted_functions(claim)
    sun = CosmeticFunction.SUNSCREEN
    stated_index = bool(claim.spf or claim.pa or claim.water or any(form_index(claim)))
    absolute = sun in candidates and claim.strength is ExpressionStrength.GUARANTEE and blocks_absolutely(claim)
    bound = sun in candidates and binds_index(claim)
    helped = helped_functions(claim)
    strength = claim.strength
    if candidates == {sun} and strength in {ExpressionStrength.IMPROVEMENT, ExpressionStrength.GUARANTEE}:
        # Effect verbs and absolute words are about whitening and wrinkles ("지워", "밝아", "100%
        # 무기자차"); for sun protection only an absolute word on the blocking itself counts. A help
        # phrase beside such a word keeps its own strength.
        strength = (
            ExpressionStrength.GUARANTEE if absolute else ExpressionStrength.SUPPORT if sun in helped else None
        )
    # The official sunscreen sentence is a plain statement, and a sentence with an index is held
    # for its scope, not for its strength: such sentences need no strength word.
    if strength is None and not (sun in candidates and (stated_index or asserted is not None)):
        return _decision(claim, unverifiable, reason.CLAIM_STRENGTH_UNCLEAR)
    rank = STRENGTH_RANK[strength or _OFFICIAL_STRENGTH]

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
    exceeds = rank > STRENGTH_RANK[_OFFICIAL_STRENGTH]
    # A sentence that was not fully read is judged on its keywords when none of them is official,
    # and otherwise on the functions its one phrase names as what is helped ("미백과 주름개선에
    # 도움을 …"); a function named any other way beside an official one may be another product's.
    if asserted is not None:
        claimed = asserted
    elif not candidates & official:
        # Whitening and wrinkle words with a strength word; a sunscreen word only as what is helped,
        # with an absolute word on the blocking, or with an index bound to this product ("자외선
        # 차단제를 함께 사용하세요" is advice).
        claimed = (candidates - {sun} if strength is not None else frozenset()) | (
            {sun} if sun in helped or absolute or bound else frozenset()
        )
    else:
        claimed = helped
    absent = claimed - official
    if absent == {sun} and _names_sun_protection(row):
        return _decision(claim, unverifiable, reason.OFFICIAL_SUNSCREEN_RECORD_CONFLICTING)
    if absent:
        if any(not _NARROWER.get(function, frozenset()) & official for function in absent):
            # A function word with "수 있" alone does not say that the product has the function.
            if asserted is None and rank < STRENGTH_RANK[_OFFICIAL_STRENGTH]:
                return _decision(claim, unverifiable, reason.CLAIM_SCOPE_UNRESOLVED)
            return _decision(claim, mismatch, reason.FUNCTION_NOT_IN_OFFICIAL_EFFICACY)
        if not exceeds:
            return _decision(claim, unverifiable, reason.CLAIM_SCOPE_UNRESOLVED)
    if exceeds:
        return _decision(claim, mismatch, reason.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL)
    if asserted is None and not bound:
        return _decision(claim, unverifiable, reason.CLAIM_SCOPE_UNRESOLVED)
    if stated_index:
        found = _index_reason(claim, efficacy.sunscreen_index, row)
        if found is reason.SUNSCREEN_INDEX_EXCEEDS_OFFICIAL:
            return _decision(claim, mismatch, found)
        if found is not None:
            return _decision(claim, unverifiable, found)
    if asserted is None:
        # A bound index equal to the official one says no more, but the rest was not read.
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
    that it was understood. The advertisement may hold one invitation: each is harmless alone, but
    two can add up to a promise ("한 번 발라 보세요. 바로 확인해 보세요.").
    """
    unconfirmed = [claim.model_copy(update={"confirmed_by_user": False}) for claim in claims]
    if unconfirmed != list(extract_cosmetic_claims(text)):
        raise ValueError("the claims are not the ones extracted from this advertisement text")
    decisions = tuple(_decide_sentence(claim, product) for claim in claims)
    read = not unread_sentences(text) and all(asserted_functions(claim) is not None for claim in claims)
    if read and invitation_count(text, claims) <= 1:
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
