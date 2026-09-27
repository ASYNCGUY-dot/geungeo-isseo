import re
from collections.abc import Iterable, Sequence
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from claimledger.official_v2 import EffectKey, _compact

CLAIM_EXTRACTION_VERSION = "claim-extract-v1"


class ExpressionStrength(StrEnum):
    POSSIBILITY = "possibility"
    SUPPORT = "support"
    IMPROVEMENT = "improvement"
    GUARANTEE = "guarantee"
    TREATMENT_PREVENTION = "treatment_prevention"


STRENGTH_RANK: dict[ExpressionStrength, int] = {
    strength: rank for rank, strength in enumerate(ExpressionStrength)
}

# Advertisement cues matched on whitespace-free NFKC text. Longer official-like phrases come
# first so the recorded cue keeps the most specific literal wording.
_EFFECT_CUES: tuple[tuple[EffectKey, re.Pattern[str]], ...] = (
    (EffectKey.MACULAR_PIGMENT_EYE_HEALTH, re.compile(r"황반색소밀도|황반")),
    (EffectKey.BLOOD_TRIGLYCERIDE, re.compile(r"혈중중성지질|중성지질|중성지방")),
    (EffectKey.BLOOD_CIRCULATION, re.compile(r"혈행개선|혈행|혈액순환|혈액흐름")),
    (EffectKey.MEMORY, re.compile(r"기억력개선|기억력")),
    (EffectKey.DRY_EYE_EYE_HEALTH, re.compile(r"건조한눈|안구건조|눈건조|눈의건조")),
    (
        EffectKey.PROBIOTIC_GROWTH_HARMFUL_INHIBITION,
        re.compile(r"유산균증식및유해균억제|유산균증식|유해균억제|유익균"),
    ),
    (EffectKey.BOWEL_MOVEMENT, re.compile(r"배변활동원활|배변활동|배변")),
    (EffectKey.GUT_HEALTH, re.compile(r"(?<![성신심간])장건강|장내환경")),
)
_GENERIC_EYE_CUE = re.compile(r"눈건강|눈의건강")
_EYE_EFFECTS = (EffectKey.MACULAR_PIGMENT_EYE_HEALTH, EffectKey.DRY_EYE_EYE_HEALTH)

_STRENGTH_CUES: tuple[tuple[ExpressionStrength, re.Pattern[str]], ...] = (
    (
        ExpressionStrength.TREATMENT_PREVENTION,
        re.compile(
            r"치료|예방|완치|특효|낫게|낫는|낫습|질병|질환|고혈압|고지혈증|당뇨|치매|백내장|녹내장"
            r"|황반변성|항암|암을|암이|암세포"
        ),
    ),
    (
        ExpressionStrength.GUARANTEE,
        re.compile(r"보장|100%|100퍼|백퍼|확실|반드시|무조건|즉시|즉각|완벽|단번에|하루만에|기적"),
    ),
    (ExpressionStrength.SUPPORT, re.compile(r"도움")),
    (
        ExpressionStrength.IMPROVEMENT,
        re.compile(
            r"개선|향상|좋아|회복|되살|강화|튼튼|해결|해소|쑥쑥|낮춰|낮춥|낮아|떨어뜨|젊어"
            r"|사라지|사라집|없애|높여|높이|높아"
        ),
    ),
    (ExpressionStrength.POSSIBILITY, re.compile(r"수있")),
)
_NEGATED_ENDING = re.compile(r"(아닙니다|아니에요|아니다|아님|않습니다|않아요|않음|없습니다|없어요|없음)[.!?…]*$")
_SENTENCE = re.compile(r"[^\n]+?(?:[.!?。…]+(?=\s|$)|$)", re.MULTILINE)


class AdClaim(BaseModel):
    model_config = {"frozen": True}

    claim_id: str
    text: str
    span: tuple[int, int]
    effect_candidates: tuple[EffectKey, ...]
    effect_cues: tuple[str, ...]
    strength: ExpressionStrength | None
    strength_cues: tuple[str, ...]
    confirmed_by_user: bool = False
    extraction_version: Literal["claim-extract-v1"] = CLAIM_EXTRACTION_VERSION


def _literal(text: str, positions: list[int], match: re.Match[str]) -> str:
    return text[positions[match.start()] : positions[match.end() - 1] + 1]


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for match in _SENTENCE.finditer(text):
        start, end = match.span()
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end:
            spans.append((start, end))
    return spans


def _classify(sentence: str) -> tuple[
    tuple[EffectKey, ...], tuple[str, ...], ExpressionStrength | None, tuple[str, ...]
]:
    compact, positions = _compact(sentence)
    effects: list[EffectKey] = []
    effect_cues: list[str] = []
    for effect, pattern in _EFFECT_CUES:
        for match in pattern.finditer(compact):
            if effect not in effects:
                effects.append(effect)
            effect_cues.append(_literal(sentence, positions, match))
    generic = list(_GENERIC_EYE_CUE.finditer(compact))
    if generic and not any(effect in effects for effect in _EYE_EFFECTS):
        effects.extend(_EYE_EFFECTS)
        effect_cues.extend(_literal(sentence, positions, match) for match in generic)
    ordered_effects = tuple(effect for effect in EffectKey if effect in effects)

    strength: ExpressionStrength | None = None
    strength_cues: list[str] = []
    for candidate, pattern in _STRENGTH_CUES:
        matches = list(pattern.finditer(compact))
        if matches:
            strength = candidate
            strength_cues = [_literal(sentence, positions, match) for match in matches]
            break
    return ordered_effects, tuple(dict.fromkeys(effect_cues)), strength, tuple(strength_cues)


def extract_claims(text: str) -> tuple[AdClaim, ...]:
    claims: list[AdClaim] = []
    for start, end in _sentence_spans(text):
        sentence = text[start:end]
        compact, _ = _compact(sentence)
        if _NEGATED_ENDING.search(compact):
            continue
        effects, effect_cues, strength, strength_cues = _classify(sentence)
        strong = strength is not None and STRENGTH_RANK[strength] >= STRENGTH_RANK[
            ExpressionStrength.IMPROVEMENT
        ]
        if not effects and not strong:
            continue
        claims.append(
            AdClaim(
                claim_id=f"C{len(claims) + 1}",
                text=sentence,
                span=(start, end),
                effect_candidates=effects,
                effect_cues=effect_cues,
                strength=strength,
                strength_cues=strength_cues,
            )
        )
    return tuple(claims)


def confirm_claims(
    claims: Sequence[AdClaim], claim_ids: Iterable[str] | Literal["all"]
) -> tuple[AdClaim, ...]:
    known = {claim.claim_id for claim in claims}
    selected = known if claim_ids == "all" else set(claim_ids)
    unknown = selected - known
    if unknown:
        raise ValueError(f"unknown claim id: {', '.join(sorted(unknown))}")
    return tuple(
        claim.model_copy(update={"confirmed_by_user": claim.claim_id in selected})
        for claim in claims
    )


__all__ = [
    "CLAIM_EXTRACTION_VERSION",
    "STRENGTH_RANK",
    "AdClaim",
    "ExpressionStrength",
    "confirm_claims",
    "extract_claims",
]
