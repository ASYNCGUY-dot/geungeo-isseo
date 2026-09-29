import json
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from claimledger.domain import IngredientGroup

OFFICIAL_FUNCTION_V2_VERSION = "official-function-v2.5"
_HEADER_VOCABULARY_PATH = (
    Path(__file__).with_name("reference") / "official_header_vocabulary_v1.json"
)
_CLAUSE_VOCABULARY_PATH = (
    Path(__file__).with_name("reference") / "official_clause_vocabulary_v1.json"
)


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

# Full matches on the normalized header only: a core name inside an unknown/composite name is
# not attribution.
_HEADER_NAMES: dict[IngredientGroup, str] = {
    IngredientGroup.LUTEIN_ZEAXANTHIN: (
        r"(?:루테인|지아잔틴|루테인지아잔틴(?:복합추출물|추출복합물)?|마리골드꽃(?:주정)?추출물"
        r"|lutein|zeaxanthin)"
    ),
    IngredientGroup.OMEGA3: r"(?:epa(?:및|와|/)dha함유유지|오메가-?3(?:지방산함유유지)?|omega-?3)",
    IngredientGroup.PROBIOTICS: r"(?:프로바이오틱스|probiotics?)",
}
# Korean list letters only; "[가-하]" would be every syllable, so "(안)" or "(미)" would vanish.
_LIST_LETTERS = "가나다라마바사아자차카타파하"
_HEADER_LIST_MARKER = re.compile(
    rf"(?:[*\-•·◦▪]+|\d{{1,2}}[).]|\(\d{{1,2}}\)|\([{_LIST_LETTERS}]\))"
)
# NFKC turns circled numbers into plain digits, so they are removed before compaction.
_CIRCLED_MARKER = re.compile(r"\s*[①-⑳]")
# Only decorations that keep naming the same ingredient are removed: approval numbers, the
# notification type and the zeaxanthin note. Any other parenthetical stays part of the name.
_HEADER_DECORATION = re.compile(
    r"\((?:(?:기능성원료)?인정(?:번호)?[:：]?)?제?\d{4}-\d{1,3}호?\)"
    r"|\((?:고시형|개별인정형(?:원료)?|지아잔틴함유)\)"
)
_OFFICIAL_SUPPORT_END = re.compile(r"도움(?:을줄수있음|을줌)?[.。]*$")
# Attribute only a fully consumed list of supported effects sharing an explicit predicate.
# Detection below can still retain an unattributed keyword for review; it is not evidence.
_SUPPORT_FUNCTION = (
    r"(?:(?:노화로인해감소될수있는)?황반색소밀도를유지하여눈건강|"
    r"혈중중성지질개선|혈행개선|기억력개선|건조한눈을개선하여눈건강|"
    r"유산균증식및유해균억제|배변활동원활|장건강)"
)
_LIST_MARKER = rf"(?:\(\d{{1,2}}\)|\([{_LIST_LETTERS}]\)|\d{{1,2}}[).]?|[*•·◦▪-])"
# Effect lists inside one clause share its predicate; complete clauses (each with its own
# predicate) may be joined by a period, list marker, comma or slash.
_SUPPORT_CLAUSE = (
    _SUPPORT_FUNCTION
    + r"(?:(?:[·・,•⋅ᆞ∙]|및)" + _SUPPORT_FUNCTION + r")*"
    + r"에도움(?:을줄수있음|을줌)?"
)
_SUPPORTED_STATEMENT = re.compile(
    rf"(?:{_LIST_MARKER})?{_SUPPORT_CLAUSE}"
    rf"(?:(?:[.。]+(?:{_LIST_MARKER})?|[,/](?:{_LIST_MARKER})?|{_LIST_MARKER})"
    rf"{_SUPPORT_CLAUSE})*[.。]*"
)
_KOREAN_LABEL = "(국문)"
# Clause boundaries for the vocabulary gate, applied after circled numbers became newlines.
_CLAUSE_BREAK = re.compile(
    rf"\n|\(\d{{1,2}}\)|\([{_LIST_LETTERS}]\)|(?:^|(?<=\s))\d{{1,2}}[.)](?!\d)|[.。](?=\s|$)"
)
_CLAUSE_LEAD = re.compile(r"^(?:[*\-•·◦▪]+|\((?:국문|영문)\))+")
_DOT_VARIANTS = re.compile(r"[・•⋅ᆞ∙]")
# Only complete known statements may be chained; fragments such as "가" or "기억력개선" may not.
_CLAUSE_PREDICATE = re.compile(r"(?:도움을줄수있음|도움을줄수있습니다|도움을줌|도움이될수있음|필요|관여)$")
_NEGATIVE_STATEMENT = re.compile(
    r"않|없|아님|아니|못|안됨|안됩니다|제외|대신|삭제|미인정"
)
_FUNCTION_WORDS = (
    "도움", "필요", "개선", "억제", "원활", "증진", "감소", "보호", "관여", "형성", "help", "necessary",
)
_NON_HEADER_NAMES = ("기능성내용", "기능성", "국문", "영문")

_BRACKET_HEADER = re.compile(r"\[([^\[\]\n]{1,80})\]")
# Used with match(text, pos): no "^", which would only match at the start of the whole field.
_LINE_PREFIX = re.compile(
    rf"(?:[*\-•·◦▪]|\d{{1,2}}\s*[).]|\(\d{{1,2}}\)|[①-⑳]|\([{_LIST_LETTERS}]\))\s*"
)
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
    parser_version: Literal["official-function-v2.5"] = OFFICIAL_FUNCTION_V2_VERSION


@dataclass(frozen=True)
class ReviewedVocabulary:
    version: str
    source_id: str
    source_sha256: str
    source_retrieved_at: str
    min_companies: int
    names: frozenset[str]
    excluded: dict[str, str]


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


def normalize_header_name(header: str) -> str:
    """Compact a header and drop one list marker and allowlisted same-ingredient decorations."""
    text = header.strip().strip("[]")
    circled = _CIRCLED_MARKER.match(text)
    compact = _compact(text[circled.end():] if circled else text)[0].strip("[]")
    marker = None if circled else _HEADER_LIST_MARKER.match(compact)
    if marker:
        compact = compact[marker.end():]
    return _HEADER_DECORATION.sub("", compact).removesuffix("제품")


def _load_vocabulary(path: Path) -> ReviewedVocabulary:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ReviewedVocabulary(
        version=payload["vocabulary_version"],
        source_id=payload["source"]["source_id"],
        source_sha256=payload["source"]["sha256"],
        source_retrieved_at=payload["source"]["retrieved_at"],
        min_companies=payload["min_companies"],
        names=frozenset(payload["names"]),
        excluded=dict(payload["excluded"]),
    )


@cache
def known_header_vocabulary() -> ReviewedVocabulary:
    """Reviewed ingredient header names; any other header next to evidence is unresolved."""
    return _load_vocabulary(_HEADER_VOCABULARY_PATH)


@cache
def known_clause_vocabulary() -> ReviewedVocabulary:
    """Reviewed official clauses; any other body clause in the field holds attribution."""
    return _load_vocabulary(_CLAUSE_VOCABULARY_PATH)


def segment_header_names(text: str) -> tuple[str, ...]:
    """Raw header names in the order the parser segments them (no vocabulary needed)."""
    return tuple(block.header for block in _segment_blocks(text) if block.header is not None)


def _clause_key(piece: str) -> str:
    key = _CLAUSE_LEAD.sub("", _compact(piece)[0])
    return _DOT_VARIANTS.sub("·", key).rstrip(".,;/·")


def segment_body_clauses(text: str) -> tuple[str, ...]:
    """Normalized clauses of every body span, headerless preface included (no vocabulary)."""
    clauses: list[str] = []
    for block in _segment_blocks(text):
        for start, end in block.body_spans:
            span = unicodedata.normalize("NFKC", re.sub(r"[①-⑳]", "\n", text[start:end]))
            clauses.extend(
                key for piece in _CLAUSE_BREAK.split(span) if (key := _clause_key(piece))
            )
    return tuple(clauses)


def _clause_accepted(clause: str, vocabulary: frozenset[str]) -> bool:
    """A reviewed clause, a fully supported target statement, or a chain of known statements."""
    if clause in vocabulary or _SUPPORTED_STATEMENT.fullmatch(clause):
        return True
    # Statements written back to back without list markers ("…필요피부와…필요"). Every
    # character must belong to a known complete statement or a single separator between two.
    reachable = [True] + [False] * len(clause)
    for start in range(len(clause)):
        if not reachable[start]:
            continue
        for end in range(start + 1, len(clause) + 1):
            piece = clause[start:end]
            if piece in vocabulary and _CLAUSE_PREDICATE.search(piece):
                reachable[end] = True
                if end < len(clause) and clause[end] in ",./·":
                    reachable[end + 1] = True
    return reachable[-1]


def _header_groups(header: str) -> tuple[IngredientGroup, ...]:
    normalized = normalize_header_name(header)
    return tuple(
        group for group, pattern in _HEADER_NAMES.items() if re.fullmatch(pattern, normalized)
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
        blocks.append(block)
        blocks.extend(_line_blocks(text, match.end(), body_end, block))
    return blocks


def _block_effects(
    text: str, block: _Block, *, allow_attribution: bool,
) -> list[OfficialEffect]:
    header_groups = _header_groups(block.header) if block.header is not None else ()
    # Every line in the ingredient block must be understood before a fragment can be evidence.
    # In particular, do not drop a tentative continuation just because it has no help predicate.
    block_supported = all(
        _SUPPORTED_STATEMENT.fullmatch(_compact(text[start:end])[0].removeprefix(_KOREAN_LABEL))
        for start, end in block.body_spans
    )
    effects: list[tuple[int, OfficialEffect]] = []
    for span_start, span_end in block.body_spans:
        statement_start, statement_end = _trimmed_span(text, span_start, span_end)
        compact, positions = _compact(text[statement_start:statement_end])
        # A remaining colon signals an unparsed inline header; do not inherit the old header.
        if (
            ":" in compact
            or not _OFFICIAL_SUPPORT_END.search(compact)
            or _NEGATIVE_STATEMENT.search(compact)
        ):
            continue
        groups = (
            header_groups if allow_attribution and block_supported else ()
        )
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
    # A flattened C003 field cannot prove the scope of a negative section/continuation.
    # Do not let a subsequent ingredient header silently reset that uncertainty. A header that is
    # neither a target nor a reviewed ingredient name (e.g. "[검토 중]") may qualify neighbouring
    # evidence even when it has a body, so it holds the whole field as well.
    vocabulary = known_header_vocabulary().names
    unresolved_header = any(
        block.header is not None
        and not _header_groups(block.header)
        and (not block.body_spans or normalize_header_name(block.header) not in vocabulary)
        for block in raw_blocks
    )
    # Annotations can also sit in a body: another ingredient's block, a headerless preface or a
    # second target block. Every body clause of the field must be a reviewed official clause.
    clauses = known_clause_vocabulary().names
    unknown_clause = not all(
        _clause_accepted(clause, clauses) for clause in segment_body_clauses(text)
    )
    allow_attribution = (
        not unresolved_header
        and not unknown_clause
        and _NEGATIVE_STATEMENT.search(_compact(text)[0]) is None
    )
    blocks = tuple(
        OfficialFunctionBlock(
            header=block.header,
            header_span=block.header_span,
            attributed_groups=(
                _header_groups(block.header)
                if allow_attribution and block.header is not None else ()
            ),
            body_spans=tuple(block.body_spans),
        )
        for block in raw_blocks
    )
    effects = tuple(
        effect for block in raw_blocks
        for effect in _block_effects(text, block, allow_attribution=allow_attribution)
    )
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
    "ReviewedVocabulary",
    "effect_mentioned",
    "known_clause_vocabulary",
    "known_header_vocabulary",
    "normalize_header_name",
    "parse_official_function_v2",
    "segment_body_clauses",
    "segment_header_names",
]
