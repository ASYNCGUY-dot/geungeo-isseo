"""Stratify (product, ingredient group, effect) pairs by the parser path for attribution evaluation.

The question labelled for each pair is whether the product's official function text says that the
ingredient group has the effect. Strata follow the parser outcome so that each path added in steps
1-2 (header variants, extended statement formats) and each kind of hold can be measured separately.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from claimledger.domain import IngredientGroup
from claimledger.headerless import headerless_effects
from claimledger.official_v2 import (
    EFFECT_GROUP,
    EffectKey,
    OfficialEffect,
    OfficialFunctionParse,
    effect_mentioned,
    normalize_header_name,
    parse_official_function_v2,
    segment_header_names,
    support_statements,
)

TARGET_GROUPS = (
    IngredientGroup.LUTEIN_ZEAXANTHIN,
    IngredientGroup.OMEGA3,
    IngredientGroup.PROBIOTICS,
)
# Target header names as recognised before step 1 (official-function-v2.2), on compact text.
_V22_HEADER_NAMES = {
    IngredientGroup.LUTEIN_ZEAXANTHIN: (
        r"(?:루테인|지아잔틴|루테인지아잔틴(?:복합추출물)?|마리골드꽃추출물|lutein|zeaxanthin)"
    ),
    IngredientGroup.OMEGA3: r"(?:epa및dha함유유지|epa/dha함유유지|오메가-?3|omega-?3)",
    IngredientGroup.PROBIOTICS: r"(?:프로바이오틱스|probiotics?)",
}
# Raw-material names that put a target group in the sampling frame (not attribution).
_RAW_NAMES = {
    IngredientGroup.LUTEIN_ZEAXANTHIN: re.compile(r"마리골드|루테인|지아잔틴|lutein|zeaxanthin"),
    IngredientGroup.OMEGA3: re.compile(r"epa|dha|오메가-?3|omega-?3|어유"),
    IngredientGroup.PROBIOTICS: re.compile(r"프로바이오틱스|probiotic"),
}
# Formats accepted from step 2 on: (가) markers, bullet separators, the (국문) label.
_EXTENDED_MARK = re.compile(r"\([가나다라마바사아자차카타파하]\)|[•ᆞ⋅∙‧]|^\(국문\)")
# Formats first accepted in official-function-v2.7/v2.8 (translations, the function-content label,
# grade 2 notes, "[name] :", "(or" headers, separators inside a parenthesis of a name line). On the
# C003 snapshot this marks all 509 pairs gained over v2.6 and 3 pairs v2.6 already attributed.
_NEW_BLOCK_MARK = re.compile(r"\(영문\)|생리활성기능2등급")
_PAREN_SEPARATOR = re.compile(r"\([^()]*[-:][^()]*\)")


class Stratum(StrEnum):
    ATTRIBUTED_CANONICAL = "attributed_canonical"
    ATTRIBUTED_VARIANT_HEADER = "attributed_variant_header"
    ATTRIBUTED_EXTENDED_FORMAT = "attributed_extended_format"
    ATTRIBUTED_NEW_FORMAT = "attributed_new_format"
    ATTRIBUTED_HEADERLESS = "attributed_headerless"
    HELD_UNDER_TARGET_HEADER = "held_under_target_header"
    HELD_HEADERLESS = "held_headerless"
    HELD_OTHER = "held_other"


ATTRIBUTED_STRATA = (
    Stratum.ATTRIBUTED_CANONICAL,
    Stratum.ATTRIBUTED_VARIANT_HEADER,
    Stratum.ATTRIBUTED_EXTENDED_FORMAT,
    Stratum.ATTRIBUTED_NEW_FORMAT,
    Stratum.ATTRIBUTED_HEADERLESS,
)


@dataclass(frozen=True)
class EvalPair:
    report_no: str
    group: IngredientGroup
    effect: EffectKey
    stratum: Stratum


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()


def _extended_format(effect: OfficialEffect) -> bool:
    compact = _squash(effect.statement_text)
    joined = len(support_statements(effect.statement_text)) > 1 and re.search(r"(?:있음|줌)[,/]", compact)
    return bool(_EXTENDED_MARK.search(compact) or joined)


def _bracketed(text: str, span: tuple[int, int]) -> bool:
    return span[0] > 0 and text[span[0] - 1] == "["


def _new_format(text: str, parse: OfficialFunctionParse, effect: OfficialEffect) -> bool:
    block = next(
        (
            block for block in parse.blocks
            if block.header == effect.block_header
            and any(start <= effect.statement_span[0] < end for start, end in block.body_spans)
        ),
        None,
    )
    if block is None or block.header_span is None:
        return False
    body = _squash(unicodedata.normalize("NFKC", " ".join(text[s:e] for s, e in block.body_spans)))
    if _NEW_BLOCK_MARK.search(body) or "기능성내용:" in _squash(unicodedata.normalize("NFKC", effect.statement_text)):
        return True
    if _bracketed(text, block.header_span) and re.match(r"\s*\][ \t]*[:：]", text[block.header_span[1]:]):
        return True
    for other in parse.blocks:
        if other.header is None or other.header_span is None:
            continue
        header = _squash(unicodedata.normalize("NFKC", other.header))
        if "(or" in header:
            return True
        if (
            not _bracketed(text, other.header_span)
            and _PAREN_SEPARATOR.search(header)
            and re.match(r"[ \t]*(?:\n|$)", text[other.header_span[1]:])
        ):
            return True
    return False


def _v22_header(header: str | None, group: IngredientGroup) -> bool:
    compact = _squash(header or "").strip("[]")
    return re.fullmatch(_V22_HEADER_NAMES[group] + r"(?:제품)?(?:\(고시형\))?", compact) is not None


def classify_pair(
    function_text: str, group: IngredientGroup, effect: EffectKey, raw_materials: str = "",
) -> Stratum:
    """Parser path of the pair; headerless attribution needs the raw materials (none: never)."""
    parse = parse_official_function_v2(function_text)
    attributed = [
        item for item in parse.effects if item.effect is effect and group in item.attributed_groups
    ]
    if attributed:
        first = attributed[0]
        if _new_format(function_text, parse, first):
            return Stratum.ATTRIBUTED_NEW_FORMAT
        if _extended_format(first):
            return Stratum.ATTRIBUTED_EXTENDED_FORMAT
        if not _v22_header(first.block_header, group):
            return Stratum.ATTRIBUTED_VARIANT_HEADER
        return Stratum.ATTRIBUTED_CANONICAL
    if raw_materials and any(
        item.effect is effect and group in item.attributed_groups
        for item in headerless_effects(function_text, raw_materials)
    ):
        return Stratum.ATTRIBUTED_HEADERLESS
    headers = segment_header_names(function_text)
    if not headers:
        return Stratum.HELD_HEADERLESS
    target_names = _V22_HEADER_NAMES[group]
    if any(re.search(target_names, normalize_header_name(header)) for header in headers):
        return Stratum.HELD_UNDER_TARGET_HEADER
    return Stratum.HELD_OTHER


def candidate_pairs(rows: Iterable[Mapping[str, str]]) -> list[EvalPair]:
    """Pairs whose effect is mentioned and whose group is in the raw materials or attributed."""
    pairs: list[EvalPair] = []
    for row in rows:
        text = row.get("primary_function") or ""
        if not text.strip():
            continue
        raw_materials = row.get("raw_materials") or ""
        raw = _squash(raw_materials)
        attributed_groups = {
            group
            for item in parse_official_function_v2(text).effects
            for group in item.attributed_groups
            if EFFECT_GROUP[item.effect] is group
        }
        for group in TARGET_GROUPS:
            if not (_RAW_NAMES[group].search(raw) or group in attributed_groups):
                continue
            for effect in EffectKey:
                if EFFECT_GROUP[effect] is group and effect_mentioned(text, effect):
                    stratum = classify_pair(text, group, effect, raw_materials)
                    pairs.append(EvalPair(row["report_no"], group, effect, stratum))
    return pairs


__all__ = [
    "ATTRIBUTED_STRATA",
    "TARGET_GROUPS",
    "EvalPair",
    "Stratum",
    "candidate_pairs",
    "classify_pair",
]
