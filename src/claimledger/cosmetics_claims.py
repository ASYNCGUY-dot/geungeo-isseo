"""Advertisement claims about functional cosmetics: extraction and the wording that may be confirmed.

Keyword cues only propose what a sentence is about. A claim can be confirmed only when the whole
sentence is one of a few allowlisted forms about whitening or wrinkle improvement, with no subject
other than the product itself: the official efficacy belongs to the product, not to an ingredient.
The medical and guarantee cues are a conservative development policy, not a legal determination.

A sentence that is neither a claim nor a recognized disclaimer is kept as unread text: nothing in
it was judged, and a confirmation is withheld while such text stands beside a recognized sentence.
A cue that stands before a denial, a caution to the reader or a question mark is set aside: Korean
puts what is denied before the denial, so that cue may be the thing denied.
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from typing import Literal, NamedTuple

from pydantic import BaseModel

from claimledger.claims_v1 import ExpressionStrength, _literal, _sentence_spans
from claimledger.cosmetics_official import CosmeticFunction
from claimledger.official_v2 import _compact

COSMETIC_CLAIM_VERSION = "cosmetic-claim-v1.2"
# The sentence splitter is quadratic on long runs of one character.
MAX_AD_TEXT_LENGTH = 5000

# Cues on whitespace-free NFKC, casefolded text. A wrinkle cue after "입술" is the lip function,
# and "선크림" inside "주름개선크림" is not a sunscreen.
_FUNCTION_CUES: tuple[tuple[CosmeticFunction, re.Pattern[str]], ...] = (
    (CosmeticFunction.WHITENING, re.compile(r"미백|화이트닝|멜라닌|기미|주근깨")),
    (CosmeticFunction.WRINKLE, re.compile(r"(?<!입술)(?<!입술의)주름|링클")),
    (CosmeticFunction.LIP_WRINKLE, re.compile(r"입술(?:의)?주름")),
    (CosmeticFunction.SUNSCREEN, re.compile(r"자외선|spf|(?<!개)선크림|(?<!개)선블록|썬크림|썬블록")),
    (CosmeticFunction.HAIR_DYE, re.compile(r"염모|염색")),
    (CosmeticFunction.HAIR_BLEACH, re.compile(r"탈색")),
    (CosmeticFunction.HAIR_REMOVAL, re.compile(r"제모")),
    (CosmeticFunction.HAIR_LOSS, re.compile(r"탈모")),
    (CosmeticFunction.ACNE, re.compile(r"여드름")),
    (CosmeticFunction.SKIN_BARRIER, re.compile(r"피부장벽|가려움")),
    (CosmeticFunction.STRETCH_MARK, re.compile(r"튼살")),
)
# Words with an everyday sense count only in their medical or absolute one: "저자극 처방" is a
# formulation, "재생 플라스틱" a material, "링클 필러 크림" a product type, "부작용이 있으면" a caution,
# "향이 좋아요" a liking, and "즉시 흡수" is not an effect.
_PRESCRIBER = r"(?:의사|전문의|피부과|병원|의원|약사|약국|한의사|한의원)"
_REGROWN = r"(?:피부|세포|진피|조직|상처|모발|모근|콜라겐)"
# "개선" is a strength only as a verb: "주름개선" and "주름 개선 효과" name the function.
_VERBAL = (
    r"(?:합니다|한다|해요|해줍|해주|해드|해서|했|하는|하고|하며|하여|하세요"
    r"|됩니다|된다|돼요|됐|되는|되고|되며|되어|시켜|시킵|시키)"
)
_STRENGTH_CUES: tuple[tuple[ExpressionStrength, re.Pattern[str]], ...] = (
    (
        ExpressionStrength.TREATMENT_PREVENTION,
        re.compile(
            r"치료|완치|특효|낫게|낫는|낫습|질병|질환|항염|염증|아토피|피부염|습진|건선|흉터"
            r"|약효|보톡스|시술|필러(?:를|을)?(?:맞|시술|주사|효과|대신)"
            rf"|{_PRESCRIBER}(?:의|가|이|에서)?처방|처방받"
            rf"|{_REGROWN}(?:의|을|를)?재생|재생(?:크림|효과|력|케어|시켜|시킵|시키)"
        ),
    ),
    (
        ExpressionStrength.GUARANTEE,
        re.compile(
            r"보장|100%|100퍼|백퍼|확실|반드시|무조건|완벽|단번에|하루만에|기적|영구"
            r"|\d+(?:일|주|개월)만에|부작용(?:이|은|도|걱정)?(?:전혀|하나도|일절)?(?:없|제로)|무부작용"
        ),
    ),
    (ExpressionStrength.SUPPORT, re.compile(r"도움|기능성")),
    (
        ExpressionStrength.IMPROVEMENT,
        re.compile(
            rf"개선(?={_VERBAL})|향상|좋아(?:지|집|져|졌)|회복|되살|강화|해결|해소|없애|사라지|사라집|제거"
            r"|지워|펴주|펴줍|펴집|하얗게|하얘|밝아|환해|엷게|옅게|완화|줄여|줄어|감소"
        ),
    ),
    (ExpressionStrength.POSSIBILITY, re.compile(r"수있")),
)
_STRONG = frozenset({
    ExpressionStrength.IMPROVEMENT, ExpressionStrength.GUARANTEE, ExpressionStrength.TREATMENT_PREVENTION,
})

# A denial ("아닙니다", "않는", "없는", "못합니다"), a prohibition or caution to the reader ("마세요",
# "사용을 중지", "상담", "…이 있는 부위") or a question mark. A cue before one of these is not asserted.
# "없애다" and "없어지다" are effects, not denials.
_NON_ASSERTION = re.compile(
    r"\?"
    r"|않|아니|아닌|아닙|아님|못(?:하|해|한|함|합)|없(?!애|앨|앱|앴|어지|어집|어져|어졌)"
    r"|말것|마세요|마십시오|금지|다릅니다|달라요|다르다"
    r"|사용을?(?:중지|중단|자제|삼가|피하|피해)|피해주|피하세|피하십|상담|상의"
    r"|있(?:는|으신|을)(?:분|경우|부위)|있으면|생기면"
)
# The disclaimer every cosmetic may carry; one closing mark at most, like the claim forms.
_DISCLAIMER = re.compile(
    r"(?:본제품은|이제품은)?(?:질병의예방및치료를위한)?의약품이(?:아닙니다|아니에요|아니다|아님)[.!。]?"
)
_DOT = "[ᆞ·・‧⋅∙]"
_SUBJECT = r"(?:(?:본제품|이제품|본품)(?:은|는|이|가))?"
_EFFECT: dict[CosmeticFunction, str] = {
    CosmeticFunction.WHITENING: r"(?:피부(?:의)?)?미백",
    CosmeticFunction.WRINKLE: r"(?:피부(?:의)?)?주름개선",
}
_JOIN = rf"(?:과|와|및|[,/]|{_DOT})"
_HELP = r"에도움(?:을(?:줄수(?:있음|있습니다|있어요)|줌|줍니다|준다))?"
_CATEGORY = r"기능성(?:화장품)?(?:입니다|이에요|예요)?"
# One closing mark at most: "…" and "..." announce a continuation.
_END = r"[.!。]?"
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
    # Cue words before a denial, a caution or a question: they propose nothing.
    set_aside_cues: tuple[str, ...] = ()
    confirmed_by_user: bool = False
    extraction_version: Literal["cosmetic-claim-v1.2"] = COSMETIC_CLAIM_VERSION


class UnreadSentence(BaseModel):
    model_config = {"frozen": True}

    text: str
    span: tuple[int, int]


class _Reading(NamedTuple):
    functions: tuple[CosmeticFunction, ...]
    function_cues: tuple[str, ...]
    strength: ExpressionStrength | None
    strength_cues: tuple[str, ...]
    set_aside: tuple[str, ...]
    # A function word or a strong word was set aside, so the sentence stays visible as a claim.
    substance_set_aside: bool


def normalize_ad_text(text: str) -> str:
    """Drop a leading byte order mark and compose decomposed Hangul (NFD); spans index the result."""
    return unicodedata.normalize("NFC", text.removeprefix("﻿"))


def asserted_functions(claim: CosmeticClaim) -> frozenset[CosmeticFunction] | None:
    """Functions asserted by a fully recognized sentence, or None when any part of it is unread."""
    compact, _ = _compact(claim.text)
    for functions, pattern in _CONFIRMABLE:
        if pattern.fullmatch(compact):
            return functions
    return None


def _classify(sentence: str) -> _Reading:
    compact, positions = _compact(sentence)
    function_matches = [
        (function, match) for function, pattern in _FUNCTION_CUES for match in pattern.finditer(compact)
    ]
    strength_matches = [
        (level, match) for level, pattern in _STRENGTH_CUES for match in pattern.finditer(compact)
    ]
    cue_spans = [match.span() for _, match in (*function_matches, *strength_matches)]
    # A denial inside a cue ("부작용 없는") belongs to that cue.
    markers = [
        marker.start() for marker in _NON_ASSERTION.finditer(compact)
        if not any(start < marker.end() and marker.start() < end for start, end in cue_spans)
    ]
    last_marker = max(markers, default=-1)

    def asserted(match: re.Match[str]) -> bool:
        return match.end() > last_marker

    functions = {function for function, match in function_matches if asserted(match)}
    function_cues = [_literal(sentence, positions, match) for _, match in function_matches if asserted(match)]
    strength: ExpressionStrength | None = None
    strength_cues: list[str] = []
    for level, _ in _STRENGTH_CUES:
        found = [match for candidate, match in strength_matches if candidate is level and asserted(match)]
        if found:
            strength, strength_cues = level, [_literal(sentence, positions, match) for match in found]
            break
    denied = [
        (match.start(), _literal(sentence, positions, match), kind)
        for kind, match in (*function_matches, *strength_matches) if not asserted(match)
    ]
    return _Reading(
        functions=tuple(function for function in CosmeticFunction if function in functions),
        function_cues=tuple(dict.fromkeys(function_cues)),
        strength=strength,
        strength_cues=tuple(strength_cues),
        set_aside=tuple(dict.fromkeys(literal for _, literal, _ in sorted(denied, key=lambda item: item[0]))),
        substance_set_aside=any(isinstance(kind, CosmeticFunction) or kind in _STRONG for _, _, kind in denied),
    )


def _read(text: str) -> tuple[tuple[CosmeticClaim, ...], tuple[UnreadSentence, ...]]:
    text = normalize_ad_text(text)
    if len(text) > MAX_AD_TEXT_LENGTH:
        raise ValueError(f"the advertisement text is longer than {MAX_AD_TEXT_LENGTH} characters")
    claims: list[CosmeticClaim] = []
    unread: list[UnreadSentence] = []
    for start, end in _sentence_spans(text):
        sentence = text[start:end]
        if _DISCLAIMER.fullmatch(_compact(sentence)[0]):
            continue
        reading = _classify(sentence)
        if not reading.functions and reading.strength not in _STRONG and not reading.substance_set_aside:
            unread.append(UnreadSentence(text=sentence, span=(start, end)))
            continue
        claims.append(
            CosmeticClaim(
                claim_id=f"C{len(claims) + 1}",
                text=sentence,
                span=(start, end),
                function_candidates=reading.functions,
                function_cues=reading.function_cues,
                strength=reading.strength,
                strength_cues=reading.strength_cues,
                set_aside_cues=reading.set_aside,
            )
        )
    return tuple(claims), tuple(unread)


def extract_cosmetic_claims(text: str) -> tuple[CosmeticClaim, ...]:
    return _read(text)[0]


def unread_sentences(text: str) -> tuple[UnreadSentence, ...]:
    """Sentences that are neither a claim nor a recognized disclaimer: nothing in them was judged."""
    return _read(text)[1]


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
    "MAX_AD_TEXT_LENGTH",
    "CosmeticClaim",
    "UnreadSentence",
    "asserted_functions",
    "confirm_cosmetic_claims",
    "extract_cosmetic_claims",
    "normalize_ad_text",
    "unread_sentences",
]
