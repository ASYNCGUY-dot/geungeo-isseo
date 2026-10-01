"""Attribute target statements in official function fields that have no ingredient header at all.

Without a header, the only question is which raw material a statement belongs to. A statement is
attributed to a target group only when
- the whole field passes the same gates as header attribution (reviewed clauses, no negative words),
- its line is entirely target support statements,
- C003 shows the same statement under that group's headers in at least two companies,
- the raw materials name the target group, and
- no other ingredient that C003 shows with the same statement is in the raw materials; for a
  single-effect statement any other notified ingredient with that effect counts as well.
Other ingredients are matched to raw materials generously (name parts and cores), so a doubtful
match holds. A notified ingredient whose notified functions lack the statement's effects is not an
owner (its rows are layout errors). This is inference from the raw materials, not a header, and
results carry attribution_basis="headerless_owner" so verdicts and receipts can say so.
"""

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from claimledger.domain import IngredientGroup
from claimledger.official_v2 import (
    EFFECT_GROUP,
    EffectKey,
    OfficialEffect,
    effect_statement,
    field_allows_attribution,
    headerless_body_spans,
    line_supported,
    normalize_header_name,
    official_effect_keys,
    span_effects,
)

HEADERLESS_ATTRIBUTION_VERSION = "headerless-attribution-v1"
STATEMENT_OWNERS_VERSION = "official-statement-owners-v1"
MIN_COMPANIES = 2
_OWNERS_PATH = Path(__file__).with_name("reference") / "official_statement_owners_v1.json"
_NOTICE_PATH = Path(__file__).with_name("reference") / "notice_functions_2026_43.json"
# Notified items that are the target groups themselves (고시 제3. 2. 기능성 원료).
_TARGET_NOTICE_ITEMS = frozenset({"2-26", "2-16", "2-51"})
_GENERA = (
    "lactobacillus|bifidobacterium|lactiplantibacillus|lacticaseibacillus|limosilactobacillus"
    "|ligilactobacillus|lactococcus|streptococcus|enterococcus|pediococcus|leuconostoc|bacillus|weizmannia"
)
# Header names of a target group's family, including individually approved strains and extracts.
_HEADER_FAMILY: dict[IngredientGroup, re.Pattern[str]] = {
    IngredientGroup.PROBIOTICS: re.compile(rf"프로바이오틱스|probiotic|^(?:{_GENERA})"),
    IngredientGroup.OMEGA3: re.compile(r"epa|dha|오메가-?3|omega-?3"),
    IngredientGroup.LUTEIN_ZEAXANTHIN: re.compile(r"루테인|지아잔틴|마리골드|lutein|zeaxanthin"),
}
# Raw-material names that put the target group in the product (strict).
_RAW_TARGET: dict[IngredientGroup, re.Pattern[str]] = {
    IngredientGroup.PROBIOTICS: re.compile(r"프로바이오틱스|probiotic"),
    IngredientGroup.OMEGA3: re.compile(r"epa|dha|오메가-?3|omega-?3|어유"),
    IngredientGroup.LUTEIN_ZEAXANTHIN: re.compile(r"루테인|지아잔틴|마리골드|lutein|zeaxanthin"),
}
# Raw-material names that put a family in the product when it is another owner (generous).
_RAW_FAMILY: dict[IngredientGroup, re.Pattern[str]] = {
    IngredientGroup.PROBIOTICS: re.compile(rf"프로바이오틱스|probiotic|유산균|{_GENERA}"),
    IngredientGroup.OMEGA3: re.compile(r"epa|dha|오메가-?3|omega-?3|어유|크릴"),
    IngredientGroup.LUTEIN_ZEAXANTHIN: _RAW_TARGET[IngredientGroup.LUTEIN_ZEAXANTHIN],
}
_NAME_SUFFIXES = (
    "주정추출분말", "열수추출분말", "열수추출물", "추출분말", "추출물", "농축분말", "농축액", "건조분말",
    "분말", "식이섬유", "가수분해물", "복합물", "제품", "엑스",
)
_GROUP_PREFIX = "group:"


@dataclass(frozen=True)
class StatementOwners:
    version: str
    source_id: str
    source_sha256: str
    source_retrieved_at: str
    min_companies: int
    statements: Mapping[str, Mapping[str, int]]


@dataclass(frozen=True)
class _NoticeItem:
    keys: frozenset[str]
    names: frozenset[str]
    effects: frozenset[EffectKey]


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()


def owner_key(header: str) -> str:
    """'group:<target>' for a target family header, otherwise the normalized header name."""
    name = normalize_header_name(header)
    families = [group for group, pattern in _HEADER_FAMILY.items() if pattern.search(name)]
    return f"{_GROUP_PREFIX}{families[0].value}" if len(families) == 1 else name


def _name_keys(name: str) -> frozenset[str]:
    """Parts and cores of an ingredient name, so "차전자피식이섬유" also matches raw "차전자피"."""
    keys: set[str] = set()
    for part in re.split(r"[/(),·+\[\]<>]", _squash(name)):
        for run in re.findall(r"[가-힣]{2,}|[a-z0-9\-]{4,}", part):
            core = run
            stripped = True
            while stripped:
                stripped = False
                for suffix in _NAME_SUFFIXES:
                    if core.endswith(suffix) and len(core) > len(suffix):
                        core, stripped = core[: -len(suffix)], True
            if len(core) >= 2:
                keys.add(core)
    return frozenset(keys)


@cache
def known_statement_owners() -> StatementOwners:
    """Reviewed-snapshot table: support statement -> owner -> number of companies (C003 headers)."""
    payload = json.loads(_OWNERS_PATH.read_text(encoding="utf-8"))
    return StatementOwners(
        version=payload["table_version"],
        source_id=payload["source"]["source_id"],
        source_sha256=payload["source"]["sha256"],
        source_retrieved_at=payload["source"]["retrieved_at"],
        min_companies=payload["min_companies"],
        statements=payload["statements"],
    )


@cache
def _notice_items() -> tuple[_NoticeItem, ...]:
    items = json.loads(_NOTICE_PATH.read_text(encoding="utf-8"))["items"]
    return tuple(
        _NoticeItem(
            keys=_name_keys(item["name"]),
            names=frozenset(
                part for part in (_squash(p) for p in re.split(r"[/(),]", item["name"])) if len(part) >= 2
            ) | {_squash(item["name"])},
            effects=frozenset(EffectKey(e) for e in (*item["effects"], *item["mentioned_effects"])),
        )
        for item in items
        if item["number"] not in _TARGET_NOTICE_ITEMS
    )


def _known_non_carrier(owner: str, effects: Iterable[EffectKey]) -> bool:
    """A notified ingredient whose notified functions lack these effects cannot own the statement."""
    if owner.startswith(_GROUP_PREFIX):
        return False
    wanted = set(effects)
    matches = [item for item in _notice_items() if owner in item.names]
    return bool(matches) and all(not wanted & item.effects for item in matches)


def _raw_has_owner(raw: str, owner: str) -> bool:
    if owner.startswith(_GROUP_PREFIX):
        return _RAW_FAMILY[IngredientGroup(owner.removeprefix(_GROUP_PREFIX))].search(raw) is not None
    return any(key in raw for key in _name_keys(owner))


def _owned(
    statement: str, group: IngredientGroup, owners: Mapping[str, Mapping[str, int]], raw: str,
) -> bool:
    effects = official_effect_keys(statement)
    if not effects or any(EFFECT_GROUP[effect] is not group for effect in effects):
        return False
    by_owner = owners.get(statement, {})
    own = f"{_GROUP_PREFIX}{group.value}"
    if by_owner.get(own, 0) < MIN_COMPANIES or _RAW_TARGET[group].search(raw) is None:
        return False
    if any(
        _raw_has_owner(raw, owner)
        for owner in by_owner
        if owner != own and not _known_non_carrier(owner, effects)
    ):
        return False
    if len(effects) == 1:
        carriers = (item for item in _notice_items() if effects[0] in item.effects)
        if any(key in raw for item in carriers for key in item.keys):
            return False
    return True


def headerless_effects(
    function_text: str,
    raw_materials: str,
    owners: Mapping[str, Mapping[str, int]] | None = None,
) -> tuple[OfficialEffect, ...]:
    """Target effects attributed in a field without any header, by statement owner and raw materials."""
    spans = headerless_body_spans(function_text) if function_text.strip() else None
    if not spans or not field_allows_attribution(function_text):
        return ()
    table = known_statement_owners().statements if owners is None else owners
    raw = _squash(raw_materials)
    found: list[OfficialEffect] = []
    for start, end in spans:
        if not line_supported(function_text, start, end):
            continue
        for effect in span_effects(function_text, start, end):
            statement = effect_statement(effect)
            if statement is not None and _owned(statement, effect.effect_group, table, raw):
                found.append(
                    effect.model_copy(
                        update={
                            "attributed_groups": (effect.effect_group,),
                            "attribution_basis": "headerless_owner",
                        }
                    )
                )
    return tuple(found)


__all__ = [
    "HEADERLESS_ATTRIBUTION_VERSION",
    "MIN_COMPANIES",
    "STATEMENT_OWNERS_VERSION",
    "StatementOwners",
    "headerless_effects",
    "known_statement_owners",
    "owner_key",
]
