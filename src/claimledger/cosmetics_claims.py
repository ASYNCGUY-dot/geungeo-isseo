"""Advertisement claims about functional cosmetics: extraction and the wording that may be confirmed.

Keyword cues only propose what a sentence is about. A claim can be confirmed only when the whole
sentence is one of a few allowlisted forms about whitening or wrinkle improvement, with no subject
other than the product itself: the official efficacy belongs to the product, not to an ingredient.
The medical and guarantee cues are a conservative development policy, not a legal determination.

A sentence that is neither a claim nor a recognized disclaimer is kept as unread text: nothing in
it was judged, and a confirmation is withheld while such text stands beside a recognized sentence.
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel

from claimledger.claims_v1 import _DISCLAIMER, ExpressionStrength, _literal, _sentence_spans
from claimledger.cosmetics_official import CosmeticFunction
from claimledger.official_v2 import _compact

COSMETIC_CLAIM_VERSION = "cosmetic-claim-v1.1"

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
# and "즉시 흡수" is not an effect.
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
            rf"개선(?={_VERBAL})|향상|좋아|회복|되살|강화|해결|해소|없애|사라지|사라집|제거|지워|펴주|펴줍|펴집"
            r"|하얗게|하얘|밝아|환해|엷게|옅게|완화|줄여|줄어|감소"
        ),
    ),
    (ExpressionStrength.POSSIBILITY, re.compile(r"수있")),
)

# A sentence that denies an effect ("치료 목적의 제품이 아닙니다", "없애지는 못합니다") is not that
# claim. Only predicate forms count: "끈적이지 않고" and "뿐 아니라" deny nothing about the effect.
_DENIAL = re.compile(
    r"아닙니다|아니에요|아니예요|아니다|아님|않습니다|않아요|않는다|않음|않지만"
    r"|못합니다|못해요|못한다|못함|못하지만|수없|수는없|수도없"
)
# A caution to the reader ("전문의와 상담하세요", "사용을 중지할 것") names a condition without claiming
# to treat it.
_CAUTION = re.compile(r"상담하세요|상담하십시오|상담하시기|상담할것|사용을(?:중지|중단|자제|삼가)|사용하지마")
_DOT = "[ᆞ·・‧⋅∙]"
_SUBJECT = r"(?:(?:본제품|이제품|본품)(?:은|는|이|가))?"
_EFFECT: dict[CosmeticFunction, str] = {
    CosmeticFunction.WHITENING: r"(?:피부(?:의)?)?미백",
    CosmeticFunction.WRINKLE: r"(?:피부(?:의)?)?주름개선",
}
_JOIN = rf"(?:과|와|및|[,/]|{_DOT})"
_HELP = r"에도움(?:을(?:줄수(?:있음|있습니다|있어요)|줌|줍니다|준다))?"
_CATEGORY = r"기능성(?:화장품)?(?:입니다|이에요|예요)?"
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
    confirmed_by_user: bool = False
    extraction_version: Literal["cosmetic-claim-v1.1"] = COSMETIC_CLAIM_VERSION


class UnreadSentence(BaseModel):
    model_config = {"frozen": True}

    text: str
    span: tuple[int, int]


def normalize_ad_text(text: str) -> str:
    """Compose decomposed Hangul (NFD) so that cues match; spans index the returned text."""
    return unicodedata.normalize("NFC", text)


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


def asks(claim: CosmeticClaim) -> bool:
    """Whether the sentence is a question: it asserts nothing."""
    return "?" in _compact(claim.text)[0]


def cautions(claim: CosmeticClaim) -> bool:
    """Whether the sentence tells the reader when to stop or seek advice."""
    return _CAUTION.search(_compact(claim.text)[0]) is not None


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


def _read(text: str) -> tuple[tuple[CosmeticClaim, ...], tuple[UnreadSentence, ...]]:
    text = normalize_ad_text(text)
    claims: list[CosmeticClaim] = []
    unread: list[UnreadSentence] = []
    for start, end in _sentence_spans(text):
        sentence = text[start:end]
        if _DISCLAIMER.fullmatch(_compact(sentence)[0]):
            continue
        functions, function_cues, strength, strength_cues = _classify(sentence)
        strong = strength is not None and strength in {
            ExpressionStrength.IMPROVEMENT, ExpressionStrength.GUARANTEE, ExpressionStrength.TREATMENT_PREVENTION,
        }
        if not functions and not strong:
            unread.append(UnreadSentence(text=sentence, span=(start, end)))
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
    "CosmeticClaim",
    "UnreadSentence",
    "asks",
    "asserted_functions",
    "cautions",
    "confirm_cosmetic_claims",
    "denies",
    "extract_cosmetic_claims",
    "normalize_ad_text",
    "unread_sentences",
]
