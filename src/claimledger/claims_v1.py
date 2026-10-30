import re
from collections.abc import Iterable, Sequence
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from claimledger.domain import IngredientGroup
from claimledger.official_v2 import EFFECT_GROUP, EffectKey, _compact

CLAIM_EXTRACTION_VERSION = "claim-extract-v1.8"


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
        re.compile(r"유산균증식및유해균억제|유산균(?:의)?증식|유해균(?:의)?억제|유익균"),
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
            # Disease and symptom names near the three core functions (claim-extract-v1.3).
            r"|혈전|뇌졸중|중풍|동맥경화|심근경색|협심증|이상지질혈증|고콜레스테롤|알츠하이머"
            r"|안구건조증|노안|장염|대장염|과민성대장|변비|설사|크론병"
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
# The notice that the product is no medicine. 건강기능식품의 표시기준 제4조 제10호 asks for its content, not
# one wording, so a closed set of subjects, purposes and endings is read, with at most one leading mark
# and one pair of brackets (claim-extract-v1.7). Any other word keeps the sentence from being the notice.
_NOTICE_SUBJECT = r"(?:(?:본|이|해당)제품은|본품은)(?:건강기능식품(?:이며|으로서|으로),?)?|건강기능식품은"
# Matching runs on NFKC text: "ㆍ" (U+318D) arrives as U+119E and "･" (U+FF65) as "・" (U+30FB).
_NOTICE_TREATMENT = "(?:질병의?)?예방(?:및|과|또는|[·ᆞ・,])?치료"
_NOTICE_BODY = (
    rf"(?:{_NOTICE_SUBJECT})?(?:"
    rf"(?:{_NOTICE_TREATMENT}(?:를위한|를목적으로하는|목적의))?의약품이(?:아닙니다|아니에요|아니예요|아니다|아님)"
    rf"|(?:{_NOTICE_TREATMENT}(?:를위한|를목적으로하는|목적의))?의약품이아닌(?:건강기능)?식품(?:입니다|이에요|임)"
    rf"|{_NOTICE_TREATMENT}를목적으로하지않습니다"
    r")"
)
# Closing marks are read once outside the brackets, so a failing match does not try every split of a run.
_DISCLAIMER = re.compile(
    "[※*•·ᆞ・\\-]?"
    rf"(?:\({_NOTICE_BODY}[.!。]*\)|\[{_NOTICE_BODY}[.!。]*\]|{_NOTICE_BODY})[.!。]*"
)
# Layout wrapping is not a sentence boundary: retain the subject and trailing qualifiers. Only the
# recognized notice filling whole lines at the start or end of a sentence is split off
# (claim-extract-v1.5, v1.6): joined to a claim without a period, its "질병의 예방 및 치료" read as a
# disease claim.
_SENTENCE = re.compile(r".+?(?:[.!?。…]+(?=\s|$)|$)", re.DOTALL)
# A notice candidate spans at most this many lines and compact characters; longer text is no notice.
_NOTICE_MAX_LINES = 8
_NOTICE_MAX_CHARS = 48

# Keyword extraction proposes candidates; only a fully consumed, single support statement
# may be cleared. Unparsed subjects, modifiers, quantities and conjunctions remain unresolved.
# The allowlist below (claim-extract-v1.3) adds common wording of the same proposition: noun
# forms end in "에", verb forms in "데", followed by the support predicate. The sentence may end in
# one plain mark (claim-extract-v1.4): an ellipsis or a run of marks may trail off into something else.
_HELP = (
    r"도움(?:을(?:줄수(?:있음|있습니다|있어요)|줌|줍니다)|이(?:될수(?:있음|있습니다|있어요)|됩니다)"
    r"|을줄수있는(?:기능성)?원료(?:입니다|예요|이에요))?"
)
_SUPPORT_ENDING = rf"에{_HELP}[.!。]?"
_VERB_ENDING = rf"데{_HELP}[.!。]?"
_EYE_HEALTH = r"눈(?:의)?건강(?:관리)?"
_MACULAR = (
    r"(?:노화로인해감소될수있는)?황반색소밀도(?:를|의)?유지"
    rf"(?:(?:하여|해|로|를통해|를도와){_EYE_HEALTH})?"
)
_SINGLE_EFFECT: dict[EffectKey, str] = {
    EffectKey.MACULAR_PIGMENT_EYE_HEALTH: rf"(?:{_EYE_HEALTH}|황반건강|{_MACULAR})",
    EffectKey.BLOOD_TRIGLYCERIDE: r"(?:혈중중성지질|중성지질|중성지방)(?:의)?개선",
    EffectKey.BLOOD_CIRCULATION: r"(?:혈행|혈액순환|혈액흐름)(?:의)?개선",
    EffectKey.MEMORY: r"기억력(?:의)?개선",
    EffectKey.DRY_EYE_EYE_HEALTH: (
        r"(?:(?:건조한눈|안구건조|눈건조|눈의건조)(?:의)?개선"
        rf"(?:(?:으로|을통해){_EYE_HEALTH})?"
        rf"|건조한눈을개선(?:하여|해){_EYE_HEALTH}|{_EYE_HEALTH})"
    ),
    EffectKey.PROBIOTIC_GROWTH_HARMFUL_INHIBITION: (
        r"(?:유산균(?:의)?증식(?:및|과)유해균(?:의)?억제|유해균(?:의)?억제(?:및|와)유산균(?:의)?증식)"
    ),
    EffectKey.BOWEL_MOVEMENT: r"(?:배변활동(?:원활)?|원활한배변활동)",
    EffectKey.GUT_HEALTH: r"장건강(?:관리)?",
}
# Verb forms, completed by _VERB_ENDING ("…하는 데 도움").
_SINGLE_EFFECT_VERB: dict[EffectKey, str] = {
    EffectKey.MACULAR_PIGMENT_EYE_HEALTH: (
        rf"(?:황반색소밀도를유지하는|(?:{_MACULAR}(?:하여|해|로|를통해|를도와))?눈(?:의)?건강을챙기는)"
    ),
    EffectKey.BLOOD_TRIGLYCERIDE: r"(?:혈중중성지질|중성지질|중성지방)을개선하는",
    EffectKey.BLOOD_CIRCULATION: r"(?:혈행|혈액순환|혈액흐름)을개선하는",
    EffectKey.MEMORY: r"기억력을개선하는",
    EffectKey.DRY_EYE_EYE_HEALTH: r"건조한눈을개선하는",
    EffectKey.BOWEL_MOVEMENT: r"배변활동을원활하게하는",
}
# Intake wording without dose or frequency numbers: efficacy is recognised at the daily intake,
# which is not checked, so "하루 한 번" or "한 알" stays unresolved.
_INTAKE = r"(?:(?:매일|꾸준히)(?:섭취하는|챙기는|먹는|드시는)?|섭취하는|챙기는|먹는|드시는)"
_SINGLE_SUBJECT: dict[IngredientGroup, str] = {
    IngredientGroup.LUTEIN_ZEAXANTHIN: r"(?:루테인|지아잔틴|마리골드꽃추출물)",
    IngredientGroup.OMEGA3: r"(?:오메가-?3|omega-?3|epa및dha함유유지)",
    IngredientGroup.PROBIOTICS: r"프로바이오틱스",
}


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
    extraction_version: Literal["claim-extract-v1.8"] = CLAIM_EXTRACTION_VERSION


def _support_match(claim: AdClaim, effect: EffectKey) -> re.Match[str] | None:
    compact, _ = _compact(claim.text)
    subject = _SINGLE_SUBJECT[EFFECT_GROUP[effect]]
    prefix = rf"(?:{_INTAKE}?(?P<subject>본제품|이제품|{subject})(?:은|는|이|가))?"
    body = rf"{_SINGLE_EFFECT[effect]}{_SUPPORT_ENDING}"
    if effect in _SINGLE_EFFECT_VERB:
        body = rf"(?:{body}|{_SINGLE_EFFECT_VERB[effect]}{_VERB_ENDING})"
    return re.fullmatch(prefix + body, compact)


def supports_confirmation(claim: AdClaim, effect: EffectKey) -> bool:
    """Recognize a whole affirmative proposition, not just a matching effect keyword."""
    return _support_match(claim, effect) is not None


def read_subjects(claim: AdClaim) -> frozenset[str | None]:
    """Subjects of the whole support statements the claim reads as: None where it names none.

    Empty when the claim is not read as a whole statement for any of its effect candidates.
    """
    matches = (_support_match(claim, effect) for effect in claim.effect_candidates)
    return frozenset(match["subject"] for match in matches if match)


def _literal(text: str, positions: list[int], match: re.Match[str]) -> str:
    return text[positions[match.start()] : positions[match.end() - 1] + 1]


def _notice_lines(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Split off the recognized notice where it fills whole lines at the start or end of a sentence.

    A notice between other lines stays in the sentence: split there, the lines around it became
    sentences of their own ("혈행 개선에" read as an improvement claim; claim-extract-v1.6). Blank lines
    are no other lines; counted as such, they put a notice at the end "between" lines (claim-extract-v1.8)."""
    if _DISCLAIMER.fullmatch(_compact(text[start:end])[0]):
        return [(start, end)]
    lines: list[tuple[int, int]] = []
    position = start
    for line in text[start:end].split("\n"):
        lines.append((position, position + len(line)))
        position += len(line) + 1
    pieces: list[tuple[tuple[int, int], bool]] = []
    index = 0
    while index < len(lines):
        last = None
        for stop in range(index, min(len(lines), index + _NOTICE_MAX_LINES)):
            compact = _compact(text[lines[index][0] : lines[stop][1]])[0]
            if len(compact) > _NOTICE_MAX_CHARS:
                break
            if _DISCLAIMER.fullmatch(compact):
                last = stop
        if last is None:
            pieces.append((lines[index], False))
            index += 1
            continue
        pieces.append(((lines[index][0], lines[last][1]), True))
        index = last + 1
    other = [
        number for number, ((first, last), notice) in enumerate(pieces) if not notice and text[first:last].strip()
    ]
    if not other:
        return [span for span, _ in pieces]
    first, last = other[0], other[-1]
    middle = (pieces[first][0][0], pieces[last][0][1])
    return [span for span, _ in pieces[:first]] + [middle] + [span for span, _ in pieces[last + 1 :]]


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for match in _SENTENCE.finditer(text):
        for start, end in _notice_lines(text, *match.span()):
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


def _is_claim(effects: tuple[EffectKey, ...], strength: ExpressionStrength | None) -> bool:
    strong = strength is not None and STRENGTH_RANK[strength] >= STRENGTH_RANK[ExpressionStrength.IMPROVEMENT]
    return bool(effects) or strong


def unread_sentences(text: str) -> tuple[tuple[int, int], ...]:
    """Spans of the sentences that are neither a claim nor the recognized disclaimer.

    Extraction drops them ("단 2주.", "아래 문구는 사실이 아닙니다."), so a claim beside them was not
    read with everything the advertisement says about it.
    """
    spans = []
    for start, end in _sentence_spans(text):
        sentence = text[start:end]
        if _DISCLAIMER.fullmatch(_compact(sentence)[0]):
            continue
        effects, _, strength, _ = _classify(sentence)
        if not _is_claim(effects, strength):
            spans.append((start, end))
    return tuple(spans)


def extract_claims(text: str) -> tuple[AdClaim, ...]:
    claims: list[AdClaim] = []
    for start, end in _sentence_spans(text):
        sentence = text[start:end]
        compact, _ = _compact(sentence)
        if _DISCLAIMER.fullmatch(compact):
            continue
        effects, effect_cues, strength, strength_cues = _classify(sentence)
        if not _is_claim(effects, strength):
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
    "read_subjects",
    "supports_confirmation",
    "unread_sentences",
]
