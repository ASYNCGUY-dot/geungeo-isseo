import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from claimledger.domain import IngredientGroup

OFFICIAL_FUNCTION_V2_VERSION = "official-function-v2"


class EffectKey(StrEnum):
    MACULAR_PIGMENT_EYE_HEALTH = "macular_pigment_eye_health"
    BLOOD_TRIGLYCERIDE = "blood_triglyceride"
    BLOOD_CIRCULATION = "blood_circulation"
    MEMORY = "memory"
    DRY_EYE_EYE_HEALTH = "dry_eye_eye_health"
    PROBIOTIC_GROWTH_HARMFUL_INHIBITION = "probiotic_growth_harmful_inhibition"
    BOWEL_MOVEMENT = "bowel_movement"
    GUT_HEALTH = "gut_health"


EFFECT_GROUP: dict[EffectKey, IngredientGroup] = {
    EffectKey.MACULAR_PIGMENT_EYE_HEALTH: IngredientGroup.LUTEIN_ZEAXANTHIN,
    EffectKey.BLOOD_TRIGLYCERIDE: IngredientGroup.OMEGA3,
    EffectKey.BLOOD_CIRCULATION: IngredientGroup.OMEGA3,
    EffectKey.MEMORY: IngredientGroup.OMEGA3,
    EffectKey.DRY_EYE_EYE_HEALTH: IngredientGroup.OMEGA3,
    EffectKey.PROBIOTIC_GROWTH_HARMFUL_INHIBITION: IngredientGroup.PROBIOTICS,
    EffectKey.BOWEL_MOVEMENT: IngredientGroup.PROBIOTICS,
    EffectKey.GUT_HEALTH: IngredientGroup.PROBIOTICS,
}

# Official statement fragments, matched on whitespace-free NFKC text. The notified wording for
# these effects is regular; only separators, spacing and sentence endings vary in C003.
_EFFECT_PATTERNS: tuple[tuple[EffectKey, re.Pattern[str]], ...] = (
    (EffectKey.MACULAR_PIGMENT_EYE_HEALTH, re.compile(r"황반색소밀도를유지하여눈건강에도움")),
    (EffectKey.BLOOD_TRIGLYCERIDE, re.compile(r"혈중중성지질개선")),
    (EffectKey.BLOOD_CIRCULATION, re.compile(r"혈행개선")),
    (EffectKey.MEMORY, re.compile(r"기억력개선")),
    (EffectKey.DRY_EYE_EYE_HEALTH, re.compile(r"건조한눈을개선하여눈건강")),
    (EffectKey.PROBIOTIC_GROWTH_HARMFUL_INHIBITION, re.compile(r"유산균증식및유해균억제")),
    (EffectKey.BOWEL_MOVEMENT, re.compile(r"배변활동원활")),
    (EffectKey.GUT_HEALTH, re.compile(r"(?<![성신심간])장건강")),
)

# Broad keywords used only to decide whether an effect is mentioned anywhere in the text.
_MENTION_PATTERNS: dict[EffectKey, re.Pattern[str]] = {
    EffectKey.MACULAR_PIGMENT_EYE_HEALTH: re.compile(r"황반|눈건강|눈의건강"),
    EffectKey.BLOOD_TRIGLYCERIDE: re.compile(r"중성지질"),
    EffectKey.BLOOD_CIRCULATION: re.compile(r"혈행|혈액흐름|혈액순환"),
    EffectKey.MEMORY: re.compile(r"기억력"),
    EffectKey.DRY_EYE_EYE_HEALTH: re.compile(r"건조한눈|안구건조|눈건조|눈의건조"),
    EffectKey.PROBIOTIC_GROWTH_HARMFUL_INHIBITION: re.compile(r"유산균증식|유해균억제|유익균"),
    EffectKey.BOWEL_MOVEMENT: re.compile(r"배변"),
    EffectKey.GUT_HEALTH: re.compile(r"(?<![성신심간])장건강|장내"),
}

# Header names that identify a core ingredient source. Marigold flower extract is the notified
# lutein source material, so its header attributes lutein statements.
_HEADER_ALIASES: dict[IngredientGroup, tuple[str, ...]] = {
    IngredientGroup.LUTEIN_ZEAXANTHIN: ("루테인", "지아잔틴", "마리골드", "lutein", "zeaxanthin", "marigold"),
    IngredientGroup.OMEGA3: ("epa", "dha", "오메가", "omega"),
    IngredientGroup.PROBIOTICS: ("프로바이오틱스", "probiotic"),
}
_FUNCTION_WORDS = (
    "도움", "필요", "개선", "억제", "원활", "증진", "감소", "보호", "관여", "형성", "help", "necessary",
)
_NON_HEADER_NAMES = ("기능성내용", "기능성", "국문", "영문")

_BRACKET_HEADER = re.compile(r"\[([^\[\]\n]{1,80})\]")
_LINE_PREFIX = re.compile(r"^(?:[*\-•·◦▪]|\d{1,2}\s*[).]|\(\d{1,2}\)|[①-⑳]|\([가-하]\))\s*")
_COLON_HEADER = re.compile(r"^(?P<name>[^:：\n]{1,60}?)\s*[:：]\s*(?P<rest>.*)$")
_DASH_HEADER = re.compile(r"^(?P<name>[^\-–\n]{1,40}?)\s*[-–]\s*(?P<rest>.+)$")


class OfficialFunctionBlock(BaseModel):
    model_config = {"frozen": True}

    header: str | None
    header_span: tuple[int, int] | None
    attributed_groups: tuple[IngredientGroup, ...]
    body_spans: tuple[tuple[int, int], ...]


class OfficialEffect(BaseModel):
    model_config = {"frozen": True}

    effect: EffectKey
    effect_group: IngredientGroup
    matched_text: str
    matched_span: tuple[int, int]
    statement_text: str
    statement_span: tuple[int, int]
    block_header: str | None
    attributed_groups: tuple[IngredientGroup, ...]
    official_strength: Literal["support"] = "support"


class OfficialFunctionParse(BaseModel):
    model_config = {"frozen": True}

    source_text: str
    blocks: tuple[OfficialFunctionBlock, ...]
    effects: tuple[OfficialEffect, ...]
    parser_version: Literal["official-function-v2"] = OFFICIAL_FUNCTION_V2_VERSION


@dataclass
class _Block:
    header: str | None
    header_span: tuple[int, int] | None
    body_spans: list[tuple[int, int]]


def _compact(text: str) -> tuple[str, list[int]]:
    """Return NFKC, casefolded text without whitespace and the source index of each character."""
    characters: list[str] = []
    positions: list[int] = []
    for index, character in enumerate(text):
        for normalized in unicodedata.normalize("NFKC", character).casefold():
            if normalized.isspace():
                continue
            characters.append(normalized)
            positions.append(index)
    return "".join(characters), positions


def _header_groups(header: str) -> tuple[IngredientGroup, ...]:
    compact, _ = _compact(header)
    return tuple(
        group
        for group in IngredientGroup
        if any(alias in compact for alias in _HEADER_ALIASES.get(group, ()))
    )


def _is_header_name(name: str) -> bool:
    compact, _ = _compact(name)
    if not compact or len(compact) > 40:
        return False
    if any(word in compact for word in _FUNCTION_WORDS):
        return False
    stripped = compact.strip("()")
    return not any(stripped.startswith(stop) for stop in _NON_HEADER_NAMES)


def _trimmed_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _line_spans(text: str, start: int, end: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = start
    while cursor <= end:
        newline = text.find("\n", cursor, end)
        line_end = end if newline == -1 else newline
        spans.append((cursor, line_end))
        if newline == -1:
            break
        cursor = newline + 1
    return spans


def _line_blocks(text: str, start: int, end: int, current: _Block | None) -> list[_Block]:
    blocks: list[_Block] = []
    for line_start, line_end in _line_spans(text, start, end):
        content_start, content_end = _trimmed_span(text, line_start, line_end)
        if content_start >= content_end:
            continue
        prefix = _LINE_PREFIX.match(text, content_start, content_end)
        body_start = prefix.end() if prefix else content_start
        line = text[body_start:content_end]
        header: str | None = None
        header_span: tuple[int, int] | None = None
        rest_start = content_end
        for pattern in (_COLON_HEADER, _DASH_HEADER):
            match = pattern.match(line)
            if match and _is_header_name(match.group("name")):
                name_start, name_end = _trimmed_span(
                    text, body_start + match.start("name"), body_start + match.end("name")
                )
                header, header_span = text[name_start:name_end], (name_start, name_end)
                rest_start = body_start + match.start("rest")
                break
        if header is None and _is_header_name(line):
            header, header_span = line.strip(), _trimmed_span(text, body_start, content_end)
        if header is not None:
            current = _Block(header=header, header_span=header_span, body_spans=[])
            blocks.append(current)
            if rest_start < content_end:
                current.body_spans.append((rest_start, content_end))
            continue
        if current is None:
            current = _Block(header=None, header_span=None, body_spans=[])
            blocks.append(current)
        current.body_spans.append((content_start, content_end))
    return blocks


def _segment_blocks(text: str) -> list[_Block]:
    brackets = list(_BRACKET_HEADER.finditer(text))
    if not brackets:
        return _line_blocks(text, 0, len(text), None)
    blocks = _line_blocks(text, 0, brackets[0].start(), None)
    for position, match in enumerate(brackets):
        body_end = brackets[position + 1].start() if position + 1 < len(brackets) else len(text)
        header_start, header_end = _trimmed_span(text, match.start(1), match.end(1))
        block = _Block(
            header=text[header_start:header_end],
            header_span=(header_start, header_end),
            body_spans=[],
        )
        for line_start, line_end in _line_spans(text, match.end(), body_end):
            span = _trimmed_span(text, line_start, line_end)
            if span[0] < span[1]:
                block.body_spans.append(span)
        blocks.append(block)
    return blocks


def _block_effects(text: str, block: _Block) -> list[OfficialEffect]:
    groups = _header_groups(block.header) if block.header is not None else ()
    effects: list[tuple[int, OfficialEffect]] = []
    for span_start, span_end in block.body_spans:
        statement_start, statement_end = _trimmed_span(text, span_start, span_end)
        compact, positions = _compact(text[statement_start:statement_end])
        for effect, pattern in _EFFECT_PATTERNS:
            for match in pattern.finditer(compact):
                matched_start = statement_start + positions[match.start()]
                matched_end = statement_start + positions[match.end() - 1] + 1
                effects.append(
                    (
                        matched_start,
                        OfficialEffect(
                            effect=effect,
                            effect_group=EFFECT_GROUP[effect],
                            matched_text=text[matched_start:matched_end],
                            matched_span=(matched_start, matched_end),
                            statement_text=text[statement_start:statement_end],
                            statement_span=(statement_start, statement_end),
                            block_header=block.header,
                            attributed_groups=groups,
                        ),
                    )
                )
    return [effect for _, effect in sorted(effects, key=lambda item: item[0])]


def parse_official_function_v2(text: str) -> OfficialFunctionParse:
    if not text.strip():
        return OfficialFunctionParse(source_text=text, blocks=(), effects=())
    raw_blocks = _segment_blocks(text)
    blocks = tuple(
        OfficialFunctionBlock(
            header=block.header,
            header_span=block.header_span,
            attributed_groups=_header_groups(block.header) if block.header is not None else (),
            body_spans=tuple(block.body_spans),
        )
        for block in raw_blocks
    )
    effects = tuple(effect for block in raw_blocks for effect in _block_effects(text, block))
    return OfficialFunctionParse(source_text=text, blocks=blocks, effects=effects)


def effect_mentioned(text: str, effect: EffectKey) -> bool:
    compact, _ = _compact(text)
    return _MENTION_PATTERNS[effect].search(compact) is not None


__all__ = [
    "EFFECT_GROUP",
    "OFFICIAL_FUNCTION_V2_VERSION",
    "EffectKey",
    "OfficialEffect",
    "OfficialFunctionBlock",
    "OfficialFunctionParse",
    "effect_mentioned",
    "parse_official_function_v2",
]
