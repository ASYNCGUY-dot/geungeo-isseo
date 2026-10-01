"""Attribute target statements in official function fields that have no ingredient header at all.

Without a header, the only question is which raw material a statement belongs to. A statement is
attributed to a target group only when
- the whole field passes the same gates as header attribution (reviewed clauses, no negative words),
- its line is entirely target support statements,
- C003 shows the same statement under that group's headers in at least two companies,
- the raw materials name the target group, and
- no other ingredient that C003 shows with the same statement is in the raw materials.
A single-effect statement can belong to many ingredients, so it is also held when the raw materials
name any notified ingredient with that effect, any known carrier keyword of that effect (name
variants such as 알로에베라, 보라지유, 영지, 나토), or any marked functional ingredient ("(고시형)", an
approval number) that is not identified as the target, a vitamin or mineral, or an ingredient
whose notified functions lack the effect.
Other ingredients are matched to raw materials generously (name parts and cores), so a doubtful
match holds. A notified ingredient whose notified functions lack the statement's effects is not an
owner (its rows are layout errors). This is inference from the raw materials, not a header, and
results carry attribution_basis="headerless_owner" so verdicts and receipts can say so.
v2 (independent review of v1): the carrier keywords and marked-ingredient hold, and Latin word
boundaries for EPA/DHA (ashwagandha, preparations are not omega-3; Bacillus natto is not a probiotic).
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

HEADERLESS_ATTRIBUTION_VERSION = "headerless-attribution-v2"
STATEMENT_OWNERS_VERSION = "official-statement-owners-v1"
MIN_COMPANIES = 2
_OWNERS_PATH = Path(__file__).with_name("reference") / "official_statement_owners_v1.json"
_NOTICE_PATH = Path(__file__).with_name("reference") / "notice_functions_2026_43.json"
# Notified items that are the target groups themselves (고시 제3. 2. 기능성 원료).
_TARGET_NOTICE_ITEMS = frozenset({"2-26", "2-16", "2-51"})
# Bacillus subtilis (natto) is not a probiotic; only B. coagulans (now Weizmannia) is.
_GENERA = (
    "lactobacillus|bifidobacterium|lactiplantibacillus|lacticaseibacillus|limosilactobacillus"
    "|ligilactobacillus|lactococcus|streptococcus|enterococcus|pediococcus|leuconostoc"
    "|bacilluscoagulans|weizmannia"
)
# EPA/DHA as words: "ashwagandha" or "preparations" contain the letters but are not omega-3.
_OMEGA3_NAME = (
    r"(?<![a-z])(?:epa|dha)(?:(?:및|와|과|/|\+|,|&)?(?:epa|dha))?(?![a-z])|오메가-?3|(?<![a-z])omega-?3"
)
# Header names of a target group's family, including individually approved strains and extracts.
_HEADER_FAMILY: dict[IngredientGroup, re.Pattern[str]] = {
    IngredientGroup.PROBIOTICS: re.compile(rf"프로바이오틱스|probiotic|^(?:{_GENERA})"),
    IngredientGroup.OMEGA3: re.compile(_OMEGA3_NAME),
    IngredientGroup.LUTEIN_ZEAXANTHIN: re.compile(r"루테인|지아잔틴|마리골드|lutein|zeaxanthin"),
}
# Raw-material names that put the target group in the product (strict).
_RAW_TARGET: dict[IngredientGroup, re.Pattern[str]] = {
    IngredientGroup.PROBIOTICS: re.compile(r"프로바이오틱스|probiotic"),
    IngredientGroup.OMEGA3: re.compile(rf"{_OMEGA3_NAME}|어유"),
    IngredientGroup.LUTEIN_ZEAXANTHIN: re.compile(r"루테인|지아잔틴|마리골드|lutein|zeaxanthin"),
}
# Raw-material names that put a family in the product when it is another owner (generous).
_RAW_FAMILY: dict[IngredientGroup, re.Pattern[str]] = {
    IngredientGroup.PROBIOTICS: re.compile(rf"프로바이오틱스|probiotic|유산균|{_GENERA}"),
    IngredientGroup.OMEGA3: re.compile(rf"{_OMEGA3_NAME}|어유|크릴"),
    IngredientGroup.LUTEIN_ZEAXANTHIN: _RAW_TARGET[IngredientGroup.LUTEIN_ZEAXANTHIN],
}
# Effects each target family can carry, to judge it as another owner of a single-effect statement.
_FAMILY_EFFECTS: dict[IngredientGroup, frozenset[EffectKey]] = {
    IngredientGroup.LUTEIN_ZEAXANTHIN: frozenset(
        {EffectKey.MACULAR_PIGMENT_EYE_HEALTH, EffectKey.DRY_EYE_EYE_HEALTH}
    ),
    IngredientGroup.OMEGA3: frozenset({
        EffectKey.BLOOD_TRIGLYCERIDE, EffectKey.BLOOD_CIRCULATION, EffectKey.MEMORY,
        EffectKey.DRY_EYE_EYE_HEALTH,
    }),
    IngredientGroup.PROBIOTICS: frozenset({
        EffectKey.PROBIOTIC_GROWTH_HARMFUL_INHIBITION, EffectKey.BOWEL_MOVEMENT, EffectKey.GUT_HEALTH,
    }),
}
# Other carriers of a single effect under the names raw materials actually use (generous on purpose).
_EFFECT_CARRIERS: dict[EffectKey, re.Pattern[str] | None] = {
    EffectKey.BLOOD_CIRCULATION: re.compile(
        r"은행|홍삼|인삼|영지|불로초|감마리놀렌|보라지|달맞이꽃|까막까치밥|블랙커런트|나토|natto|아르기닌"
    ),
    EffectKey.MEMORY: re.compile(r"은행|홍삼|인삼|원지|피브로인|포스파티딜세린|바코파|아쉬와간다|ashwagandha"),
    EffectKey.BLOOD_TRIGLYCERIDE: re.compile(r"난소화성|식이섬유|글로빈"),
    EffectKey.BOWEL_MOVEMENT: re.compile(
        r"알로에|차전자|질경이|한천|이눌린|치커리|올리고당|식이섬유|난소화성|폴리덱스트로스|구아검|글루코만난"
        r"|곤약|아카시아검|아라비아검|호로파|목이버섯|라피노스|락추로스|귀리|보리|밀기울|키토산"
    ),
    EffectKey.GUT_HEALTH: re.compile(r"알로에|올리고당|식이섬유|이눌린|치커리"),
    EffectKey.PROBIOTIC_GROWTH_HARMFUL_INHIBITION: re.compile(r"올리고당|이눌린|치커리|식이섬유|락추로스"),
    EffectKey.DRY_EYE_EYE_HEALTH: re.compile(r"루테인|지아잔틴|마리골드|빌베리|감잎|헤마토코쿠스"),
    EffectKey.MACULAR_PIGMENT_EYE_HEALTH: None,
}
# A raw material declared as a functional ingredient in this product.
_FUNCTIONAL_MARK = re.compile(r"고시형|기능성원료|개별인정|인정번호|제\d{4}-\d{1,3}호")
# Vitamins and minerals (and their usual chemical forms): none carries a target effect.
_NUTRIENT = re.compile(
    r"비타민|토코페롤|레티놀|카로틴|칼시페롤|아스코르브|티아민|리보플라빈|니코틴|나이아신|판토텐|피리독신"
    r"|비오틴|엽산|폴산|코발라민|칼슘|마그네슘|아연|구리|셀렌|셀레늄|망간|요오드|크롬|몰리브덴|칼륨|철|효모"
)
_NAME_SUFFIXES = (
    "주정추출분말", "열수추출분말", "열수추출물", "추출분말", "추출물", "농축분말", "농축액", "건조분말",
    "분말", "식이섬유", "가수분해물", "복합물", "제품", "엑스", "함유유지",
)
# Words that name no ingredient on their own ("밀크씨슬(…) 추출물" must not make "추출물" a key that
# identifies every extract as milk thistle).
_GENERIC_NAMES = frozenset({*_NAME_SUFFIXES, "함유유지", "함유", "유지"})
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
    number: str
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
            if run in _GENERIC_NAMES:
                continue
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
    if payload["table_version"] != STATEMENT_OWNERS_VERSION or payload["min_companies"] != MIN_COMPANIES:
        raise ValueError("statement owner table does not match this attribution rule")
    return StatementOwners(
        version=payload["table_version"],
        source_id=payload["source"]["source_id"],
        source_sha256=payload["source"]["sha256"],
        source_retrieved_at=payload["source"]["retrieved_at"],
        min_companies=payload["min_companies"],
        statements=payload["statements"],
    )


@cache
def _all_notice_items() -> tuple[_NoticeItem, ...]:
    items = json.loads(_NOTICE_PATH.read_text(encoding="utf-8"))["items"]
    return tuple(
        _NoticeItem(
            number=item["number"],
            keys=_name_keys(item["name"]),
            names=frozenset(
                part for part in (_squash(p) for p in re.split(r"[/(),]", item["name"])) if len(part) >= 2
            ) | {_squash(item["name"])},
            effects=frozenset(EffectKey(e) for e in (*item["effects"], *item["mentioned_effects"])),
        )
        for item in items
    )


def _notice_items() -> tuple[_NoticeItem, ...]:
    """Notified items other than the target groups themselves."""
    return tuple(item for item in _all_notice_items() if item.number not in _TARGET_NOTICE_ITEMS)


def _known_non_carrier(owner: str, effects: Iterable[EffectKey]) -> bool:
    """A notified ingredient whose notified functions lack these effects cannot own the statement."""
    if owner.startswith(_GROUP_PREFIX):
        return False
    wanted = set(effects)
    matches = [item for item in _notice_items() if owner in item.names]
    return bool(matches) and all(not wanted & item.effects for item in matches)


def _raw_items(raw_materials: str) -> list[str]:
    """Raw-material entries split at top-level commas (commas inside parentheses stay)."""
    items: list[str] = []
    current: list[str] = []
    depth = 0
    for character in unicodedata.normalize("NFKC", raw_materials):
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth = max(0, depth - 1)
        if character == "," and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(character)
    items.append("".join(current))
    return [_squash(item) for item in items if item.strip()]


def _unidentified_marked_ingredient(items: Iterable[str], group: IngredientGroup, effect: EffectKey) -> bool:
    """A declared functional ingredient that could carry the effect or is not identified at all."""
    for item in items:
        if not _FUNCTIONAL_MARK.search(item) or _RAW_FAMILY[group].search(item) or _NUTRIENT.search(item):
            continue
        families = [g for g, pattern in _RAW_FAMILY.items() if g is not group and pattern.search(item)]
        if families:
            if any(effect in _FAMILY_EFFECTS[g] for g in families):
                return True
            continue
        notified = [notice for notice in _all_notice_items() if any(key in item for key in notice.keys)]
        if not notified or any(effect in notice.effects for notice in notified):
            return True
    return False


def _raw_has_owner(raw: str, owner: str) -> bool:
    if owner.startswith(_GROUP_PREFIX):
        return _RAW_FAMILY[IngredientGroup(owner.removeprefix(_GROUP_PREFIX))].search(raw) is not None
    return any(key in raw for key in _name_keys(owner))


def _owned(
    statement: str,
    group: IngredientGroup,
    owners: Mapping[str, Mapping[str, int]],
    raw: str,
    items: Iterable[str],
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
        effect = effects[0]
        carriers = (item for item in _notice_items() if effect in item.effects)
        if any(key in raw for item in carriers for key in item.keys):
            return False
        keywords = _EFFECT_CARRIERS[effect]
        if keywords is not None and keywords.search(raw):
            return False
        if _unidentified_marked_ingredient(items, group, effect):
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
    items = _raw_items(raw_materials)
    found: list[OfficialEffect] = []
    for start, end in spans:
        if not line_supported(function_text, start, end):
            continue
        for effect in span_effects(function_text, start, end):
            statement = effect_statement(effect)
            if statement is not None and _owned(statement, effect.effect_group, table, raw, items):
                found.append(
                    effect.model_copy(
                        update={
                            "attributed_groups": (effect.effect_group,),
                            "attribution_basis": "headerless_owner",
                        }
                    )
                )
    return tuple(found)


def headerless_references() -> tuple[str, ...]:
    """Versions (with source hash prefixes) of the tables a headerless attribution depends on."""
    table = known_statement_owners()
    notice = json.loads(_NOTICE_PATH.read_text(encoding="utf-8"))
    return (
        f"{table.version}@{table.source_sha256[:12]}",
        str(notice["reference_version"]),
    )


__all__ = [
    "HEADERLESS_ATTRIBUTION_VERSION",
    "MIN_COMPANIES",
    "STATEMENT_OWNERS_VERSION",
    "StatementOwners",
    "headerless_effects",
    "headerless_references",
    "known_statement_owners",
    "owner_key",
]
