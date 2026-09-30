"""Other notified ingredients' official statements that could be written under a target header.

Review finding P2: a header's block is attributed as a whole, so another ingredient's official
statement joined under it (e.g. 은행잎 추출물 "기억력 개선·혈행 개선에 도움을 줄 수 있음" under
[EPA 및 DHA 함유 유지]) would lend its effects to the header ingredient. Only statements that the
header ingredient's own notified statement cannot produce (effects not in the same order) are kept,
so shared single-effect statements such as "배변활동 원활에 도움을 줄 수 있음" are not listed.
"""

import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from claimledger.domain import IngredientGroup
from claimledger.official_v2 import (
    EFFECT_GROUP,
    OfficialEffect,
    effect_statement,
    normalize_header_name,
    official_effect_keys,
    segment_header_names,
    support_statements,
)

_NOTICE_PATH = Path(__file__).with_name("reference") / "notice_functions_2026_43.json"
# Notified item that is the target group itself (고시 제3. 2. 기능성 원료).
_TARGET_ITEMS = {
    IngredientGroup.LUTEIN_ZEAXANTHIN: "2-26",
    IngredientGroup.OMEGA3: "2-16",
    IngredientGroup.PROBIOTICS: "2-51",
}


@dataclass(frozen=True)
class ForeignStatement:
    number: str
    name: str
    aliases: tuple[str, ...]
    statement: str


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()


def _aliases(name: str) -> tuple[str, ...]:
    parts = (_squash(part) for part in re.split(r"[/(),]", name))
    return tuple(part for part in parts if len(part) >= 2)


def _is_subsequence(effects: Sequence, order: Sequence) -> bool:
    remaining = iter(order)
    return all(effect in remaining for effect in effects)


@cache
def foreign_statements(group: IngredientGroup) -> tuple[ForeignStatement, ...]:
    items = json.loads(_NOTICE_PATH.read_text(encoding="utf-8"))["items"]
    own = next(item for item in items if item["number"] == _TARGET_ITEMS[group])
    own_order = official_effect_keys(own["function_text"])
    found: list[ForeignStatement] = []
    for item in items:
        if item["number"] == own["number"]:
            continue
        for statement in support_statements(item["function_text"]):
            effects = official_effect_keys(statement)
            if any(EFFECT_GROUP[effect] is group for effect in effects) and not _is_subsequence(
                effects, own_order
            ):
                found.append(
                    ForeignStatement(item["number"], item["name"], _aliases(item["name"]), statement)
                )
    return tuple(found)


def borrowed_statement(
    effect: OfficialEffect, raw_materials: str, function_text: str,
) -> ForeignStatement | None:
    """The other ingredient whose statement carries this effect, if it is in the raw materials
    without a header of its own in the official function text."""
    statement = effect_statement(effect)
    if statement is None:
        return None
    raw = _squash(raw_materials)
    headers = [normalize_header_name(header) for header in segment_header_names(function_text)]
    for foreign in foreign_statements(EFFECT_GROUP[effect.effect]):
        if foreign.statement != statement or not any(alias in raw for alias in foreign.aliases):
            continue
        if not any(alias in header for alias in foreign.aliases for header in headers):
            return foreign
    return None


__all__ = ["ForeignStatement", "borrowed_statement", "foreign_statements"]
