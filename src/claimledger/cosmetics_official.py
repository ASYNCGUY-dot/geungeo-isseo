"""Official efficacy of a functional cosmetic, read from the MFDS reported and reviewed lists.

The efficacy is product-level: a row says which functions that product was reported or reviewed
for. A statement is read only when every sentence in it is an allowlisted form (the forms cover
the wording measured on 2026-10-11); one unknown sentence holds the whole product, because a
half-read statement could hide a limitation. Misspelt or merged sentences are not repaired.

Three kinds of official data never count as evidence:

- no efficacy text at all (old registrations),
- a document that still carries the reporting form's instruction ("해당하는 효능효과 이외에는 모두
  삭제하시기 바랍니다"): the listed functions may be the unedited form,
- an efficacy sentence and a document that name different functions.

A sunscreen sentence carries its index in brackets (SPF, PA grade, water resistance). The index is
kept as written in an allowlisted form; a misspelt label ("SFP40") leaves the statement unread.
Two fields that give the same function with different indexes conflict like two different functions.
"""

import re
from collections import Counter
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from claimledger.official_v2 import _compact

COSMETIC_EFFICACY_VERSION = "cosmetic-efficacy-v1.3"


class CosmeticFunction(StrEnum):
    WHITENING = "whitening"
    WRINKLE = "wrinkle"
    LIP_WRINKLE = "lip_wrinkle"
    SUNSCREEN = "sunscreen"
    HAIR_DYE = "hair_dye"
    HAIR_BLEACH = "hair_bleach"
    HAIR_REMOVAL = "hair_removal"
    HAIR_LOSS = "hair_loss"
    ACNE = "acne"
    SKIN_BARRIER = "skin_barrier"
    STRETCH_MARK = "stretch_mark"
    DYE_OXIDANT = "dye_oxidant"
    DYE_OXIDANT_AID = "dye_oxidant_aid"


class EfficacyStatus(StrEnum):
    READABLE = "readable"
    MISSING = "missing"
    TEMPLATE_REMNANT = "template_remnant"
    CONFLICTING_FIELDS = "conflicting_fields"
    UNRECOGNIZED_WORDING = "unrecognized_wording"


class SunscreenIndex(BaseModel):
    """The index after an official sunscreen sentence."""

    model_config = {"frozen": True}

    spf: int
    # "50+": the value is 50 or more.
    plus: bool = False
    # Plus signs of the PA grade; 0 when the sentence gives none.
    pa: int = 0
    water: Literal["", "내수성", "지속내수성"] = ""


class OfficialSentence(BaseModel):
    model_config = {"frozen": True}

    function: CosmeticFunction
    text: str
    source: Literal["document", "effect_name"]
    index: SunscreenIndex | None = None


class CosmeticEfficacy(BaseModel):
    model_config = {"frozen": True}

    status: EfficacyStatus
    sentences: tuple[OfficialSentence, ...] = ()
    version: Literal["cosmetic-efficacy-v1.3"] = COSMETIC_EFFICACY_VERSION

    @property
    def functions(self) -> frozenset[CosmeticFunction]:
        return frozenset(sentence.function for sentence in self.sentences)

    @property
    def sunscreen_index(self) -> SunscreenIndex | None:
        """The index of the sunscreen sentences; None when there is none or they differ."""
        indexes = {
            sentence.index for sentence in self.sentences if sentence.function is CosmeticFunction.SUNSCREEN
        }
        return next(iter(indexes)) if len(indexes) == 1 else None


# Patterns match whitespace-free, NFKC, casefolded text. NFKC turns "ㆍ" into "ᆞ".
_DOT = "[ᆞ·・‧⋅∙]"
# Sunscreen index after the sentence: SPF, optional PA and optional water resistance only. The
# separator before PA varies (comma, slash, period, middle dot or nothing); misspelt labels hold.
_INDEX = (
    rf"\(spf:?(?P<spf>\d{{1,3}})(?P<plus>\+?)(?:(?:[,/.]|{_DOT})?pa:?(?P<pa>\+{{1,4}}))?"
    r"(?:,?(?P<water>(?:지속)?내수성))?\)"
)
_SENTENCES: tuple[tuple[CosmeticFunction, re.Pattern[str]], ...] = (
    (CosmeticFunction.WHITENING, re.compile(r"피부(?:의)?미백에도움을(?:준다|줍니다)")),
    (CosmeticFunction.WRINKLE, re.compile(r"피부(?:의)?주름개선에도움을(?:준다|줍니다)")),
    (CosmeticFunction.LIP_WRINKLE, re.compile(r"입술(?:의)?주름개선에도움을준다")),
    (
        CosmeticFunction.SUNSCREEN,
        re.compile(
            r"자외선으로부터피부를(?:보호한다|보호합니다|보호해준다|보호해줍니다|보호하는데도움을준다)"
            rf"(?:\.?{_INDEX})?"
        ),
    ),
    (CosmeticFunction.HAIR_DYE, re.compile(r"모발(?:\(백모\))?의염모(?:\([^()]{1,40}\))?")),
    (CosmeticFunction.HAIR_BLEACH, re.compile(r"모발의탈색")),
    (CosmeticFunction.HAIR_REMOVAL, re.compile(r"제모(?:\(체모의제거\))?")),
    (CosmeticFunction.HAIR_LOSS, re.compile(r"탈모증상(?:의)?완화에도움을(?:준다|줍니다)")),
    (CosmeticFunction.ACNE, re.compile(r"여드름성피부를완화하는데도움을(?:준다|줍니다)")),
    (CosmeticFunction.SKIN_BARRIER, re.compile(r"피부장벽의기능을회복하여가려움등의개선에도움을준다")),
    (CosmeticFunction.STRETCH_MARK, re.compile(r"튼살로인한붉은선을엷게하는데도움을준다")),
    (CosmeticFunction.DYE_OXIDANT, re.compile(rf"염모제의산화제또는탈색(?:제)?{_DOT}탈염제의산화제")),
    (
        CosmeticFunction.DYE_OXIDANT_AID,
        re.compile(rf"염모제의산화보조제또는탈색(?:제)?{_DOT}탈염제의산화보조제"),
    ),
)
_LIST_MARKER = re.compile(rf"(?:[-–*•]\.?|{_DOT}|\(?\d{{1,2}}[.)]|[①-⑳])")
_SENTENCE_END = re.compile(r"[.。]*")
_TEMPLATE_NOTE = "삭제하시기바랍니다"


def _read(text: str, source: Literal["document", "effect_name"]) -> tuple[OfficialSentence, ...] | None:
    """Every sentence of the text, or None when any part of it is not an allowlisted form."""
    sentences: list[OfficialSentence] = []
    for line in text.split("\n"):
        compact, positions = _compact(line)
        if not compact:
            continue
        marker = _LIST_MARKER.match(compact)
        cursor = marker.end() if marker else 0
        if cursor == len(compact):
            return None
        while cursor < len(compact):
            for function, pattern in _SENTENCES:
                if match := pattern.match(compact, cursor):
                    break
            else:
                return None
            end = _SENTENCE_END.match(compact, match.end()).end()
            literal = line[positions[cursor] : positions[end - 1] + 1]
            index = None
            if function is CosmeticFunction.SUNSCREEN and match.group("spf"):
                index = SunscreenIndex(
                    spf=int(match.group("spf")), plus=bool(match.group("plus")),
                    pa=len(match.group("pa") or ""), water=match.group("water") or "",
                )
            sentences.append(OfficialSentence(function=function, text=literal, source=source, index=index))
            cursor = end
    return tuple(sentences) or None


def parse_cosmetic_efficacy(effect_text: str, effect_name: str) -> CosmeticEfficacy:
    """Read a row's efficacy document (`effect_text`) and efficacy sentence (`effect_name`)."""
    document, sentence = effect_text.strip(), effect_name.strip()
    if not document and not sentence:
        return CosmeticEfficacy(status=EfficacyStatus.MISSING)
    if _TEMPLATE_NOTE in _compact(document + sentence)[0]:
        return CosmeticEfficacy(status=EfficacyStatus.TEMPLATE_REMNANT)
    read = {
        source: _read(text, source)
        for source, text in (("document", document), ("effect_name", sentence))
        if text
    }
    if any(sentences is None for sentences in read.values()):
        return CosmeticEfficacy(status=EfficacyStatus.UNRECOGNIZED_WORDING)
    if len(read) == 2 and Counter((item.function, item.index) for item in read["document"]) != Counter(
        (item.function, item.index) for item in read["effect_name"]
    ):
        return CosmeticEfficacy(status=EfficacyStatus.CONFLICTING_FIELDS)
    return CosmeticEfficacy(
        status=EfficacyStatus.READABLE, sentences=read.get("document") or read["effect_name"]
    )


__all__ = [
    "COSMETIC_EFFICACY_VERSION",
    "CosmeticEfficacy",
    "CosmeticFunction",
    "EfficacyStatus",
    "OfficialSentence",
    "SunscreenIndex",
    "parse_cosmetic_efficacy",
]
