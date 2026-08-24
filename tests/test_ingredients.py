from datetime import UTC, datetime

import pytest

from claimledger.domain import IngredientGroup, MappingStatus, ProductCandidate
from claimledger.ingredients import map_ingredients

NOW = datetime(2026, 8, 24, tzinfo=UTC)


def product(**updates: str) -> ProductCandidate:
    values = {
        "report_no": "TEST-INGREDIENT-001",
        "name": "성분 테스트 제품",
        "company": "테스트 제조사",
        "primary_function": "공식 기능성 문구",
        "raw_materials": "원재료명",
        "intake_method": "1일 1회",
        "source_id": "C003",
        "retrieved_at": NOW,
    }
    values.update(updates)
    return ProductCandidate(**values)


LUTEIN_PRODUCT = product(raw_materials="루테인지아잔틴복합추출물")
MIXED_PRODUCT = product(raw_materials="루테인지아잔틴복합추출물, EPA 및 DHA 함유 유지")
MISSING_PRODUCT = product(primary_function="", raw_materials="")


def test_mapping_records_exact_source_field_text_and_rule_version() -> None:
    mapping = map_ingredients(LUTEIN_PRODUCT)

    assert mapping.status is MappingStatus.VERIFIED
    assert mapping.groups == (IngredientGroup.LUTEIN_ZEAXANTHIN,)
    assert mapping.evidence[0].source_field == "raw_materials"
    assert mapping.evidence[0].matched_text == "루테인지아잔틴복합추출물"
    assert mapping.rule_version == "ingredient-map-v1"


def test_multiple_incompatible_groups_are_ambiguous_not_inferred() -> None:
    mapping = map_ingredients(MIXED_PRODUCT)

    assert mapping.status is MappingStatus.AMBIGUOUS
    assert mapping.groups == (IngredientGroup.LUTEIN_ZEAXANTHIN, IngredientGroup.OMEGA3)


def test_missing_required_source_fields_are_unverifiable() -> None:
    mapping = map_ingredients(MISSING_PRODUCT)

    assert mapping.status is MappingStatus.UNVERIFIABLE
    assert mapping.groups == ()
    assert mapping.evidence == ()


def test_dha_in_unrelated_prose_does_not_map_omega3() -> None:
    mapping = map_ingredients(
        product(
            primary_function="DHA라는 약어가 안내 문구에만 포함됩니다.",
            raw_materials="식물성 향료",
        )
    )

    assert mapping.status is MappingStatus.AMBIGUOUS
    assert mapping.groups == ()
    assert mapping.evidence == ()


def test_generic_lactic_acid_bacteria_is_not_a_probiotic_alias() -> None:
    mapping = map_ingredients(product(raw_materials="유산균 혼합분말"))

    assert mapping.status is MappingStatus.AMBIGUOUS
    assert mapping.groups == ()


def test_explicit_probiotics_alias_is_verifiable() -> None:
    mapping = map_ingredients(product(raw_materials="프로바이오틱스"))

    assert mapping.status is MappingStatus.VERIFIED
    assert mapping.groups == (IngredientGroup.PROBIOTICS,)
    assert mapping.evidence[0].matched_text == "프로바이오틱스"


def test_red_ginseng_flavor_is_not_a_red_ginseng_ingredient_alias() -> None:
    mapping = map_ingredients(product(raw_materials="홍삼맛 향료"))

    assert mapping.status is MappingStatus.AMBIGUOUS
    assert mapping.groups == ()


def test_english_flavor_prose_is_not_an_ingredient_alias() -> None:
    mapping = map_ingredients(product(raw_materials="red ginseng flavor"))

    assert mapping.status is MappingStatus.AMBIGUOUS
    assert mapping.groups == ()


@pytest.mark.parametrize("raw_materials", ["luteinase", "omega30", "coq10ase"])
def test_english_alias_substrings_do_not_map_compound_words(raw_materials: str) -> None:
    mapping = map_ingredients(product(raw_materials=raw_materials))

    assert mapping.status is MappingStatus.AMBIGUOUS
    assert mapping.groups == ()
    assert mapping.evidence == ()


def test_probiotic_free_is_not_positive_ingredient_evidence() -> None:
    mapping = map_ingredients(product(raw_materials="probiotic-free"))

    assert mapping.status is MappingStatus.AMBIGUOUS
    assert mapping.groups == ()
    assert mapping.evidence == ()


@pytest.mark.parametrize("raw_materials", ["non-lutein", "without lutein"])
def test_english_absence_prefix_is_not_positive_ingredient_evidence(raw_materials: str) -> None:
    mapping = map_ingredients(product(raw_materials=raw_materials))

    assert mapping.status is MappingStatus.AMBIGUOUS
    assert mapping.groups == ()
    assert mapping.evidence == ()


@pytest.mark.parametrize("raw_materials", ["cinnamon lutein", "cannon lutein"])
def test_english_word_ending_in_non_does_not_suppress_lutein(raw_materials: str) -> None:
    mapping = map_ingredients(product(raw_materials=raw_materials))

    assert mapping.status is MappingStatus.VERIFIED
    assert mapping.groups == (IngredientGroup.LUTEIN_ZEAXANTHIN,)
    assert mapping.evidence[0].matched_text == "lutein"


@pytest.mark.parametrize(
    ("raw_materials", "group"),
    [
        ("루테인지아잔틴복합추출물", IngredientGroup.LUTEIN_ZEAXANTHIN),
        ("EPA 및 DHA 함유 유지", IngredientGroup.OMEGA3),
        ("probiotics", IngredientGroup.PROBIOTICS),
        ("milk thistle extract", IngredientGroup.MILK_THISTLE),
        ("vitamin D", IngredientGroup.VITAMIN_D),
        ("red ginseng concentrate", IngredientGroup.RED_GINSENG),
        ("coenzyme Q10", IngredientGroup.COENZYME_Q10),
        ("magnesium", IngredientGroup.MAGNESIUM),
    ],
)
def test_each_reviewed_group_has_an_explicit_korean_or_english_alias(
    raw_materials: str, group: IngredientGroup
) -> None:
    mapping = map_ingredients(product(raw_materials=raw_materials))

    assert mapping.status is MappingStatus.VERIFIED
    assert mapping.groups == (group,)
