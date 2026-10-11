"""Advertisement claims about functional cosmetics: extraction and the wording that may be confirmed.

Keyword cues only propose what a sentence is about. A claim can be confirmed only when the whole
sentence is one of a few allowlisted forms about whitening or wrinkle improvement, with no subject
other than the product itself: the official efficacy belongs to the product, not to an ingredient.
The medical and guarantee cues are a conservative development policy, not a legal determination.
"""

import re
from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel

from claimledger.claims_v1 import _DISCLAIMER, ExpressionStrength, _literal, _sentence_spans
from claimledger.cosmetics_official import CosmeticFunction
from claimledger.official_v2 import _compact

COSMETIC_CLAIM_VERSION = "cosmetic-claim-v1.0"

# Cues on whitespace-free NFKC, casefolded text. A wrinkle cue after "입술" is the lip function.
_FUNCTION_CUES: tuple[tuple[CosmeticFunction, re.Pattern[str]], ...] = (
    (CosmeticFunction.WHITENING, re.compile(r"미백|화이트닝|멜라닌|기미|주근깨")),
    (CosmeticFunction.WRINKLE, re.compile(r"(?<!입술)(?<!입술의)주름|링클")),
    (CosmeticFunction.LIP_WRINKLE, re.compile(r"입술(?:의)?주름")),
    (CosmeticFunction.SUNSCREEN, re.compile(r"자외선|spf|선크림|선블록|썬크림|썬블록")),
    (CosmeticFunction.HAIR_DYE, re.compile(r"염모|염색")),
    (CosmeticFunction.HAIR_BLEACH, re.compile(r"탈색")),
    (CosmeticFunction.HAIR_REMOVAL, re.compile(r"제모")),
    (CosmeticFunction.HAIR_LOSS, re.compile(r"탈모")),
    (CosmeticFunction.ACNE, re.compile(r"여드름")),
    (CosmeticFunction.SKIN_BARRIER, re.compile(r"피부장벽|가려움")),
    (CosmeticFunction.STRETCH_MARK, re.compile(r"튼살")),
)
_STRENGTH_CUES: tuple[tuple[ExpressionStrength, re.Pattern[str]], ...] = (
    (
        ExpressionStrength.TREATMENT_PREVENTION,
        re.compile(
            r"치료|완치|특효|낫게|낫는|낫습|질병|질환|재생|항염|염증|아토피|피부염|습진|건선|흉터"
            r"|약효|처방|보톡스|필러|시술"
        ),
    ),
    (
        ExpressionStrength.GUARANTEE,
        re.compile(
            r"보장|100%|100퍼|백퍼|확실|반드시|무조건|즉시|즉각|완벽|단번에|하루만에|기적|영구"
            r"|\d+(?:일|주|개월)만에|부작용"
        ),
    ),
    (ExpressionStrength.SUPPORT, re.compile(r"도움|기능성")),
    (
        ExpressionStrength.IMPROVEMENT,
        re.compile(
            r"개선|향상|좋아|회복|되살|강화|해결|해소|없애|사라지|사라집|제거|지워|펴주|펴줍|펴집"
            r"|하얗게|하얘|밝아|환해|엷게|옅게|완화|줄여|줄어|감소"
        ),
    ),
    (ExpressionStrength.POSSIBILITY, re.compile(r"수있")),
)

# A sentence that denies an effect ("치료 목적의 제품이 아닙니다") is not that claim.
_DENIAL = re.compile(r"아닙니다|아니에요|아니다|아님|않습니다|않아요|않는다|않음")
_DOT = "[ᆞ·・‧⋅∙]"
_SUBJECT = r"(?:(?:본제품|이제품|본품)(?:은|는|이|가))?"
_EFFECT: dict[CosmeticFunction, str] = {
    CosmeticFunction.WHITENING: r"(?:피부(?:의)?)?미백",
    CosmeticFunction.WRINKLE: r"(?:피부(?:의)?)?주름개선",
}
_JOIN = rf"(?:과|와|및|[,/]|{_DOT})"
_HELP = r"에도움(?:을(?:줄수(?:있음|있습니다|있어요)|줌|줍니다|준다))?"
_CATEGORY = r"기능성(?:화장품)?(?:입니다|이에요|예요)?"
_END = r"[.!。]*"
_WHITENING, _WRINKLE = _EFFECT[CosmeticFunction.WHITENING], _EFFECT[CosmeticFunction.WRINKLE]
_BOTH = rf"(?:{_WHITENING}{_JOIN}{_WRINKLE}|{_WRINKLE}{_JOIN}{_WHITENING})"
# Whole-sentence forms and the functions each one asserts.
_CONFIRMABLE: tuple[tuple[frozenset[CosmeticFunction], re.Pattern[str]], ...] = (
    *(
        (frozenset({function}), re.compile(rf"{_SUBJECT}{effect}(?:{_HELP}|{_CATEGORY}){_END}"))
        for function, effect in _EFFECT.items()
    ),
    (
        frozenset(_EFFECT),
        re.compile(rf"{_SUBJECT}{_BOTH}(?:{_HELP}|(?:2중|이중)?{_CATEGORY}){_END}"),
    ),
)


class CosmeticClaim(BaseModel):
    model_config = {"frozen": True}

    claim_id: str
    text: str
    span: tuple[int, int]
    function_candidates: tuple[CosmeticFunction, ...]
    function_cues: tuple[str, ...]
    strength: ExpressionStrength | None
    strength_cues: tuple[str, ...]
    confirmed_by_user: bool = False
    extraction_version: Literal["cosmetic-claim-v1.0"] = COSMETIC_CLAIM_VERSION


def asserted_functions(claim: CosmeticClaim) -> frozenset[CosmeticFunction] | None:
    """Functions asserted by a fully recognized sentence, or None when any part of it is unread."""
    compact, _ = _compact(claim.text)
    for functions, pattern in _CONFIRMABLE:
        if pattern.fullmatch(compact):
            return functions
    return None


def denies(claim: CosmeticClaim) -> bool:
    """Whether the sentence contains a denial, so a cue in it may be what is being denied."""
    return _DENIAL.search(_compact(claim.text)[0]) is not None


def _classify(sentence: str) -> tuple[
    tuple[CosmeticFunction, ...], tuple[str, ...], ExpressionStrength | None, tuple[str, ...]
]:
    compact, positions = _compact(sentence)
    functions: list[CosmeticFunction] = []
    function_cues: list[str] = []
    for function, pattern in _FUNCTION_CUES:
        for match in pattern.finditer(compact):
            if function not in functions:
                functions.append(function)
            function_cues.append(_literal(sentence, positions, match))
    ordered = tuple(function for function in CosmeticFunction if function in functions)

    strength: ExpressionStrength | None = None
    strength_cues: list[str] = []
    for candidate, pattern in _STRENGTH_CUES:
        matches = list(pattern.finditer(compact))
        if matches:
            strength = candidate
            strength_cues = [_literal(sentence, positions, match) for match in matches]
            break
    return ordered, tuple(dict.fromkeys(function_cues)), strength, tuple(strength_cues)


def extract_cosmetic_claims(text: str) -> tuple[CosmeticClaim, ...]:
    claims: list[CosmeticClaim] = []
    for start, end in _sentence_spans(text):
        sentence = text[start:end]
        if _DISCLAIMER.fullmatch(_compact(sentence)[0]):
            continue
        functions, function_cues, strength, strength_cues = _classify(sentence)
        strong = strength is not None and strength in {
            ExpressionStrength.IMPROVEMENT, ExpressionStrength.GUARANTEE, ExpressionStrength.TREATMENT_PREVENTION,
        }
        if not functions and not strong:
            continue
        claims.append(
            CosmeticClaim(
                claim_id=f"C{len(claims) + 1}",
                text=sentence,
                span=(start, end),
                function_candidates=functions,
                function_cues=function_cues,
                strength=strength,
                strength_cues=strength_cues,
            )
        )
    return tuple(claims)


def confirm_cosmetic_claims(
    claims: Sequence[CosmeticClaim], claim_ids: Iterable[str] | Literal["all"]
) -> tuple[CosmeticClaim, ...]:
    known = {claim.claim_id for claim in claims}
    selected = known if claim_ids == "all" else set(claim_ids)
    unknown = selected - known
    if unknown:
        raise ValueError(f"unknown claim id: {', '.join(sorted(unknown))}")
    return tuple(
        claim.model_copy(update={"confirmed_by_user": claim.claim_id in selected}) for claim in claims
    )


__all__ = [
    "COSMETIC_CLAIM_VERSION",
    "CosmeticClaim",
    "asserted_functions",
    "confirm_cosmetic_claims",
    "denies",
    "extract_cosmetic_claims",
]
