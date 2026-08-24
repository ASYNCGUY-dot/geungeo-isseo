import re

from claimledger.domain import (
    IngredientGroup,
    IngredientMapping,
    IngredientMatchEvidence,
    IngredientSourceField,
    MappingStatus,
    ProductCandidate,
)

RULE_VERSION = "ingredient-map-v1"
_SOURCE_FIELDS: tuple[IngredientSourceField, ...] = (
    "name",
    "primary_function",
    "raw_materials",
)
_REQUIRED_OFFICIAL_FIELDS = ("primary_function", "raw_materials")
_FLAVOR_SUFFIXES = ("맛", "향", "flavor", "flavour")
_ALIASES: dict[IngredientGroup, tuple[str, ...]] = {
    IngredientGroup.LUTEIN_ZEAXANTHIN: (
        "루테인지아잔틴복합추출물",
        "lutein zeaxanthin complex extract",
        "지아잔틴",
        "zeaxanthin",
        "루테인",
        "lutein",
    ),
    IngredientGroup.OMEGA3: (
        "EPA 및 DHA 함유 유지",
        "epa and dha containing oil",
        "오메가-3",
        "omega-3",
        "오메가3",
        "omega 3",
        "omega3",
    ),
    IngredientGroup.PROBIOTICS: ("프로바이오틱스", "probiotics", "probiotic"),
    IngredientGroup.MILK_THISTLE: ("밀크씨슬", "milk thistle"),
    IngredientGroup.VITAMIN_D: ("비타민 D", "비타민D", "vitamin d"),
    IngredientGroup.RED_GINSENG: ("red ginseng", "홍삼"),
    IngredientGroup.COENZYME_Q10: ("코엔자임 Q10", "코엔자임Q10", "coenzyme q10", "coq10"),
    IngredientGroup.MAGNESIUM: ("마그네슘", "magnesium"),
}


def _alias_pattern(alias: str) -> re.Pattern[str]:
    return re.compile(re.escape(alias), re.IGNORECASE)


def _is_flavor_context(text: str, match_end: int) -> bool:
    following_text = text[match_end:].lstrip(" -").casefold()
    return following_text.startswith(_FLAVOR_SUFFIXES)


def _find_matches(
    group: IngredientGroup, source_field: IngredientSourceField, text: str
) -> tuple[IngredientMatchEvidence, ...]:
    matches: list[IngredientMatchEvidence] = []
    occupied_spans: list[tuple[int, int]] = []
    for alias in _ALIASES[group]:
        for match in _alias_pattern(alias).finditer(text):
            span = match.span()
            if _is_flavor_context(text, match.end()) or any(
                start < span[1] and span[0] < end for start, end in occupied_spans
            ):
                continue
            occupied_spans.append(span)
            matches.append(
                IngredientMatchEvidence(
                    group=group,
                    source_field=source_field,
                    matched_text=match.group(),
                )
            )
    return tuple(matches)


def map_ingredients(product: ProductCandidate) -> IngredientMapping:
    if not any(getattr(product, field).strip() for field in _REQUIRED_OFFICIAL_FIELDS):
        return IngredientMapping(
            status=MappingStatus.UNVERIFIABLE,
            groups=(),
            evidence=(),
            rule_version=RULE_VERSION,
        )

    evidence: list[IngredientMatchEvidence] = []
    groups: list[IngredientGroup] = []
    for group in IngredientGroup:
        group_evidence = tuple(
            match
            for source_field in _SOURCE_FIELDS
            for match in _find_matches(group, source_field, getattr(product, source_field))
        )
        if group_evidence:
            groups.append(group)
            evidence.extend(group_evidence)

    status = MappingStatus.VERIFIED if len(groups) == 1 else MappingStatus.AMBIGUOUS
    return IngredientMapping(
        status=status,
        groups=tuple(groups),
        evidence=tuple(evidence),
        rule_version=RULE_VERSION,
    )
