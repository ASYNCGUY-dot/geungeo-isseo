"""Synthetic developer regressions for headerless attribution (headerless-attribution-v1).

A field without any ingredient header attributes a target statement only when C003 shows that wording
under the target group's headers (>= 2 companies) and no other ingredient that C003 shows with the
same wording (or, for a single-effect statement, any notified ingredient with that effect) is in the
raw materials. Not an accuracy benchmark.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from claimledger.claims_v1 import confirm_claims, extract_claims
from claimledger.domain import ConfirmedProduct, IngredientGroup, ProductCandidate, Verdict
from claimledger.headerless import (
    HEADERLESS_ATTRIBUTION_VERSION,
    headerless_effects,
    known_statement_owners,
    owner_key,
)
from claimledger.official_v2 import EffectKey
from claimledger.receipt import REASON_MESSAGES
from claimledger.verdict_v1 import VerdictReason, decide_claim
from scripts import build_statement_owners

AT = datetime(2026, 10, 1, tzinfo=UTC)
LUTEIN = IngredientGroup.LUTEIN_ZEAXANTHIN
OMEGA3 = IngredientGroup.OMEGA3
PROBIOTICS = IngredientGroup.PROBIOTICS
PROBIOTIC_STATEMENT = "유산균 증식 및 유해균 억제･배변활동 원활･장 건강에 도움을 줄 수 있음"
OMEGA_STATEMENT = "혈중 중성지질 개선･혈행 개선에 도움을 줄 수 있음"
MEMORY_STATEMENT = "기억력 개선에 도움을 줄 수 있음"
BOWEL_STATEMENT = "배변활동 원활에 도움을 줄 수 있음"
VITAMIN_E = "항산화 작용을 하여 유해산소로부터 세포를 보호하는데 필요"
OWNERS = {
    "유산균증식및유해균억제·배변활동원활·장건강에도움을줄수있음": {"group:probiotics": 105},
    "혈중중성지질개선·혈행개선에도움을줄수있음": {"group:omega3": 50},
    "기억력개선에도움을줄수있음": {"group:omega3": 25, "홍삼": 98, "은행잎추출물": 28},
    "배변활동원활에도움을줄수있음": {"group:probiotics": 47, "차전자피식이섬유": 63, "이눌린/치커리추출물": 13},
    "건조한눈을개선하여눈건강에도움을줄수있음": {"group:omega3": 45, "group:lutein_zeaxanthin": 14},
    "장건강에도움을줄수있음": {"group:probiotics": 1},
}


def _pairs(text: str, raw: str, owners=OWNERS) -> set[tuple[IngredientGroup, EffectKey]]:
    return {
        (group, effect.effect)
        for effect in headerless_effects(text, raw, owners)
        for group in effect.attributed_groups
    }


def test_owned_statement_is_attributed_when_the_target_is_in_the_raw_materials() -> None:
    pairs = _pairs(PROBIOTIC_STATEMENT + "\n" + VITAMIN_E, "프로바이오틱스(고시형), 결정셀룰로스, 비타민E")
    assert pairs == {
        (PROBIOTICS, EffectKey.PROBIOTIC_GROWTH_HARMFUL_INHIBITION),
        (PROBIOTICS, EffectKey.BOWEL_MOVEMENT),
        (PROBIOTICS, EffectKey.GUT_HEALTH),
    }
    assert _pairs(OMEGA_STATEMENT, "EPA 및 DHA 함유 유지(고시형), 비타민E") == {
        (OMEGA3, EffectKey.BLOOD_TRIGLYCERIDE), (OMEGA3, EffectKey.BLOOD_CIRCULATION),
    }
    assert _pairs("혈중 중성지질 개선․혈행 개선에 도움을 줄 수 있음", "정제어유") == {
        (OMEGA3, EffectKey.BLOOD_TRIGLYCERIDE), (OMEGA3, EffectKey.BLOOD_CIRCULATION),
    }


def test_effects_carry_the_headerless_basis() -> None:
    effects = headerless_effects(OMEGA_STATEMENT, "EPA 및 DHA 함유 유지", OWNERS)
    assert effects and all(effect.attribution_basis == "headerless_owner" for effect in effects)
    assert all(effect.block_header is None for effect in effects)
    assert effects[0].statement_text == OMEGA_STATEMENT


def test_shared_statement_is_attributed_only_without_another_owner_in_the_raw_materials() -> None:
    assert _pairs(MEMORY_STATEMENT, "EPA 및 DHA 함유 유지, 비타민E") == {(OMEGA3, EffectKey.MEMORY)}
    assert not _pairs(MEMORY_STATEMENT, "EPA 및 DHA 함유 유지, 홍삼농축액")
    assert not _pairs(MEMORY_STATEMENT, "정제어유, 은행잎추출물")


@pytest.mark.parametrize("raw", [
    "프로바이오틱스, 차전자피",
    "프로바이오틱스, 차전자피 식이섬유",
    "프로바이오틱스, 치커리추출물",
    "프로바이오틱스, 이눌린",
])
def test_other_owner_names_match_raw_materials_generously(raw: str) -> None:
    assert not _pairs(BOWEL_STATEMENT, raw)


def test_single_effect_statement_also_checks_notified_carriers_of_that_effect() -> None:
    owners = {"배변활동원활에도움을줄수있음": {"group:probiotics": 47}}
    assert _pairs(BOWEL_STATEMENT, "프로바이오틱스(고시형)", owners) == {(PROBIOTICS, EffectKey.BOWEL_MOVEMENT)}
    assert not _pairs(BOWEL_STATEMENT, "프로바이오틱스(고시형), 프락토올리고당", owners)
    assert not _pairs(BOWEL_STATEMENT, "프로바이오틱스(고시형), 난소화성말토덱스트린", owners)


def test_another_target_group_owner_in_the_raw_materials_holds() -> None:
    statement = "건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음"
    assert _pairs(statement, "EPA 및 DHA 함유 유지") == {(OMEGA3, EffectKey.DRY_EYE_EYE_HEALTH)}
    assert not _pairs(statement, "EPA 및 DHA 함유 유지, 루테인지아잔틴복합추출물")


@pytest.mark.parametrize(("text", "raw"), [
    ("장 건강에 도움을 줄 수 있음", "프로바이오틱스"),
    ("혈중 중성지질 개선에 도움을 줄 수 있음", "EPA 및 DHA 함유 유지"),
    (PROBIOTIC_STATEMENT, "결정셀룰로스, 스테아린산마그네슘"),
    ("[프로바이오틱스] " + PROBIOTIC_STATEMENT, "프로바이오틱스"),
    ("비타민E : " + VITAMIN_E + "\n" + PROBIOTIC_STATEMENT, "프로바이오틱스, 비타민E"),
    (PROBIOTIC_STATEMENT + "\n기능성 재검토 중", "프로바이오틱스"),
    (PROBIOTIC_STATEMENT + " (일부 제품 미적용)", "프로바이오틱스"),
    ("유산균 증식 및 유해균 억제. 배변활동 원활･장 건강에 도움을 줄 수 있음", "프로바이오틱스"),
    ("노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강･혈행 개선에 도움을 줄 수 있음", "마리골드꽃추출물, 정제어유"),
])
def test_unowned_unsupported_or_annotated_fields_are_held(text: str, raw: str) -> None:
    assert not _pairs(text, raw)


# Independent review of headerless-attribution-v1 (P1-1, P1-2): name variants defeated the other-owner
# match (알로에베라 vs 알로에겔/알로에전잎, 보라지유 vs 감마리놀렌산 함유 유지, ...). Single-effect statements now
# also check known carrier keywords and hold on any marked functional ingredient that is not identified.
SINGLE_OWNERS = {
    "배변활동원활에도움을줄수있음": {"group:probiotics": 47},
    "장건강에도움을줄수있음": {"group:probiotics": 32},
    "혈행개선에도움을줄수있음": {"group:omega3": 30},
    "혈중중성지질개선에도움을줄수있음": {"group:omega3": 27},
    "기억력개선에도움을줄수있음": {"group:omega3": 25},
}
CIRCULATION = "혈행 개선에 도움을 줄 수 있음"


@pytest.mark.parametrize(("text", "raw"), [
    ("①배변활동 원활에 도움을 줄 수 있음", "알로에베라(고시형), 강황가루, 프로바이오틱스분말(고시형)"),
    ("장 건강에 도움을 줄 수 있음", "프로바이오틱스(고시형), 알로에베라겔동결건조분말"),
    (BOWEL_STATEMENT, "프로바이오틱스, 한천"),
    (BOWEL_STATEMENT, "프로바이오틱스, 질경이씨앗껍질분말"),
    (CIRCULATION, "EPA 및 DHA 함유 유지(고시형), 보라지유(고시형)"),
    (CIRCULATION, "정제어유, 달맞이꽃종자유"),
    (CIRCULATION, "정제어유, 영지농축액"),
    (CIRCULATION, "정제어유, 불로초자실체"),
    (CIRCULATION, "정제어유, HK나토배양물(제2009-50호)"),
    (CIRCULATION, "정제어유, Bacillus natto"),
    (CIRCULATION, "정제어유, 은행추출물"),
    (MEMORY_STATEMENT, "정제어유, 바코파추출물"),
])
def test_known_carrier_name_variants_hold_single_effect_statements(text: str, raw: str) -> None:
    assert not _pairs(text, raw, SINGLE_OWNERS)


@pytest.mark.parametrize("raw", [
    "EPA 및 DHA 함유 유지(고시형), 동충하초추출물(제2020-12호)",
    "EPA 및 DHA 함유 유지(고시형), 미지추출물(제2020-12호)",
    "EPA 및 DHA 함유 유지(고시형), 미지추출분말(고시형)",
    "EPA 및 DHA 함유 유지, 미지추출물(기능성원료인정 제2020-12호)",
])
def test_unidentified_marked_functional_ingredient_holds_single_effect_statements(raw: str) -> None:
    assert not _pairs(CIRCULATION, raw, SINGLE_OWNERS)


@pytest.mark.parametrize("raw", [
    "EPA 및 DHA 함유 유지(고시형), 레티닐 팔미트산염(고시형), 황산동(고시형), 글루콘산동(고시형)",
    "EPA 및 DHA 함유 유지(고시형), 아스코르빈산(고시형), d-α-토코페릴호박산(고시형)",
    "EPA 및 DHA 함유 유지(고시형), 산화아연(고시형), D-α-토코페롤(고시형), 비타민D3혼합제제(고시형)",
    "EPA 및 DHA 함유 유지(고시형), 밀크씨슬(카르두스 마리아누스) 추출물(고시형)",
    "EPA 및 DHA 함유 유지(고시형), 결정셀룰로스, 젤라틴",
])
def test_nutrients_and_known_non_carriers_do_not_hold(raw: str) -> None:
    assert _pairs(CIRCULATION, raw, SINGLE_OWNERS) == {(OMEGA3, EffectKey.BLOOD_CIRCULATION)}


def test_generic_words_are_not_name_keys() -> None:
    from claimledger.headerless import _name_keys

    assert "추출물" not in _name_keys("밀크씨슬(카르두스 마리아누스) 추출물")
    assert "함유유지" not in _name_keys("EPA 및 DHA 함유 유지")
    assert "감마리놀렌산" in _name_keys("감마리놀렌산 함유 유지")


# Residual risk (2026-10-02): a raw list without any functional mark cannot use the marked-ingredient
# hold, so a single-effect statement there needs every other entry to be the target, a nutrient or
# a common excipient.
@pytest.mark.parametrize(("text", "raw"), [
    (CIRCULATION, "정제어유, 젤라틴, 글리세린, 아마씨앗유"),
    (MEMORY_STATEMENT, "정제어유, 산화아연, 젤라틴, 미르틸루스산앵도추출물분말"),
    ("혈중 중성지질 개선에 도움을 줄 수 있음", "EPA 및 DHA 함유 유지, 글리세린, 크릴새우오일"),
    (CIRCULATION, "정제어유, 젤라틴, 비수리추출분말, 홍국 분말"),
])
def test_unmarked_list_with_an_unknown_entry_holds_single_effect_statements(text: str, raw: str) -> None:
    assert not _pairs(text, raw, SINGLE_OWNERS)


@pytest.mark.parametrize("raw", [
    "정제어유, 젤라틴, 글리세린, D-소르비톨액",
    "정제어유, d-α-토코페롤",
    "오메가-3지방산함유유지(정제어유(EPA와 DHA의 합-30%이상)), 젤라틴, 글리세린, D-α-토코페롤(식물성유지(대두유 50%))",
    "EPA 및 DHA 함유 유지, 프탈산히드록시프로필메틸셀룰로오스, 카라기난, 변성전분, 에틸바닐린, 안나토색소",
])
def test_unmarked_list_of_target_nutrients_and_excipients_attributes(raw: str) -> None:
    assert _pairs(CIRCULATION, raw, SINGLE_OWNERS) == {(OMEGA3, EffectKey.BLOOD_CIRCULATION)}


def test_marked_probiotic_strains_are_the_target_itself() -> None:
    raw = (
        "프로바이오틱스분말(고시형), Bifidobacterium animalis ssp. lactis(고시형), "
        "Lactiplantibacillus plantarum(고시형), 결정셀룰로스"
    )
    assert _pairs(BOWEL_STATEMENT, raw, SINGLE_OWNERS) == {(PROBIOTICS, EffectKey.BOWEL_MOVEMENT)}
    assert _pairs(BOWEL_STATEMENT, "Lactobacillus gasseri, 프로바이오틱스, 결정셀룰로스", SINGLE_OWNERS) == {
        (PROBIOTICS, EffectKey.BOWEL_MOVEMENT)
    }


def test_owned_multi_effect_statement_ignores_unidentified_marked_ingredients() -> None:
    raw = "프로바이오틱스(고시형), 미지추출물(제2020-12호), 알로에베라(고시형)"
    assert (PROBIOTICS, EffectKey.BOWEL_MOVEMENT) in _pairs(PROBIOTIC_STATEMENT, raw)


# Review P1-3: "epa"/"dha" inside Latin words (ashwagandha, preparations) is not EPA or DHA.
@pytest.mark.parametrize("raw", [
    "아쉬와간다추출물(Ashwagandha), 결정셀룰로스",
    "바코파추출물, 천연향료(natural flavouring preparations)",
])
def test_latin_substrings_are_not_omega3(raw: str) -> None:
    assert not _pairs(MEMORY_STATEMENT, raw, SINGLE_OWNERS)


@pytest.mark.parametrize("raw", ["EPA+DHA 함유 유지", "EPADHA 오일", "dha 함유 유지", "정제어유(EPA, DHA)"])
def test_epa_and_dha_as_words_are_omega3(raw: str) -> None:
    assert _pairs(OMEGA_STATEMENT, raw) == {
        (OMEGA3, EffectKey.BLOOD_TRIGLYCERIDE), (OMEGA3, EffectKey.BLOOD_CIRCULATION),
    }


# Re-review of v2 (headerless-attribution-v3).
MULTI_OWNERS = {
    **SINGLE_OWNERS,
    "배변활동원활·장건강에도움을줄수있음": {"group:probiotics": 5},
    "혈중중성지질개선·혈행개선에도움을줄수있음": {"group:omega3": 50},
    "유산균증식및유해균억제·배변활동원활·장건강에도움을줄수있음": {"group:probiotics": 105},
    "노화로인해감소될수있는황반색소밀도를유지하여눈건강에도움을줄수있음": {"group:lutein_zeaxanthin": 73},
}
EYE_STATEMENT = "노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음"


# P1-A: a multi-effect statement without a target-only phrase gets the single-effect holds per effect.
@pytest.mark.parametrize(("text", "raw", "held"), [
    ("배변활동 원활·장 건강에 도움을 줄 수 있음", "프로바이오틱스, 알로에겔(고시형), 차전자피식이섬유(고시형)",
     {EffectKey.BOWEL_MOVEMENT, EffectKey.GUT_HEALTH}),
    (OMEGA_STATEMENT, "정제어유, 난소화성말토덱스트린(고시형), 영지버섯자실체추출물(고시형)",
     {EffectKey.BLOOD_TRIGLYCERIDE, EffectKey.BLOOD_CIRCULATION}),
    ("①유산균 증식 및 유해균 억제에 도움을 줄 수 있음\n②배변활동 원활· 장건강에 도움을 줄 수 있음",
     "프로바이오틱스(고시형), 프락토올리고당, 이눌린/치커리추출물(고시형)",
     {EffectKey.BOWEL_MOVEMENT, EffectKey.GUT_HEALTH}),
])
def test_multi_effect_statement_without_target_only_phrase_is_checked_per_effect(text, raw, held) -> None:
    owners = {**MULTI_OWNERS, "유산균증식및유해균억제에도움을줄수있음": {"group:probiotics": 46}}
    assert not {effect for _, effect in _pairs(text, raw, owners)} & held


@pytest.mark.parametrize("raw", [
    "정제어유, 미지추출물",
    "정제어유, L-아르지닌(기능성원료인정제2015-19호)",
    "정제어유, 난소화성말토덱스트린(고시형)",
])
def test_target_specific_combination_holds_only_when_known_carriers_cover_every_effect(raw: str) -> None:
    # 혈중 중성지질 개선 + 혈행 개선 together is only the EPA/DHA combination.
    assert _pairs(OMEGA_STATEMENT, raw, MULTI_OWNERS) == {
        (OMEGA3, EffectKey.BLOOD_TRIGLYCERIDE), (OMEGA3, EffectKey.BLOOD_CIRCULATION),
    }


def test_shared_combination_is_checked_per_effect() -> None:
    # 기억력 개선 + 혈행 개선 is also the 은행잎 combination, so an unknown entry holds it.
    owners = {"기억력개선·혈행개선에도움을줄수있음": {"group:omega3": 5}}
    assert not _pairs("기억력 개선·혈행 개선에 도움을 줄 수 있음", "정제어유, 미지추출물", owners)


def test_target_only_phrases_keep_the_statement_with_other_carriers_present() -> None:
    raw = "프로바이오틱스(고시형), 프락토올리고당(고시형), 난소화성말토덱스트린(고시형)"
    assert (PROBIOTICS, EffectKey.BOWEL_MOVEMENT) in _pairs(PROBIOTIC_STATEMENT, raw, MULTI_OWNERS)
    assert _pairs(EYE_STATEMENT, "마리골드꽃추출물(고시형), 미지추출물", MULTI_OWNERS) == {
        (LUTEIN, EffectKey.MACULAR_PIGMENT_EYE_HEALTH)
    }


# P1-B and P3-3: spellings C003 uses most (아르지닌, 락툴로즈).
@pytest.mark.parametrize(("text", "raw"), [
    (CIRCULATION, "EPA 및 DHA 함유 유지(고시형), L-아르지닌"),
    (BOWEL_STATEMENT, "프로바이오틱스, 락툴로즈"),
    (BOWEL_STATEMENT, "프로바이오틱스, 락툴로오스분말"),
])
def test_common_spelling_variants_of_carriers_hold(text: str, raw: str) -> None:
    assert not _pairs(text, raw, SINGLE_OWNERS)


# P2-C: marks are not reliable; an unknown unmarked entry holds even when other entries are marked.
@pytest.mark.parametrize("raw", [
    "EPA 및 DHA 함유 유지(고시형), 미지추출물",
    "정제어유, 미지추출물, 비타민E(고시형)",
    "EPA 및 DHA 함유 유지(고시형), 젤라틴, 아마씨앗유",
])
def test_unknown_unmarked_entries_hold_even_in_marked_lists(raw: str) -> None:
    assert not _pairs(CIRCULATION, raw, SINGLE_OWNERS)


# P2-D and P3-2: an individually approved entry is never identified by a notified name.
@pytest.mark.parametrize("raw", [
    "EPA 및 DHA 함유 유지(고시형), 녹차추출물(열처리)(제2022-34호)",
    "EPA 및 DHA 함유 유지(고시형), 녹차추출물(개별인정형)",
    "EPA 및 DHA 함유 유지(고시형), 녹차추출물(인정형)",
    "EPA 및 DHA 함유 유지(고시형), 녹차추출물(2006-1)",
    "EPA 및 DHA 함유 유지(고시형), 녹차추출물(인증번호 제2006-1호)",
])
def test_individually_approved_entries_are_not_matched_to_notified_names(raw: str) -> None:
    assert not _pairs(MEMORY_STATEMENT, raw, SINGLE_OWNERS)


# P2-E: a probiotic genus inside another approved ingredient's name does not identify it.
def test_genus_inside_another_approved_ingredient_holds() -> None:
    raw = "EPA 및 DHA 함유 유지(고시형), Lactobacillus brevis 발효 다시마추출물(제2011-22호)"
    assert not _pairs(MEMORY_STATEMENT, raw, SINGLE_OWNERS)


# P2-F: nutrients and excipients are judged on the entry name, not on its composition in brackets.
@pytest.mark.parametrize(("text", "raw"), [
    (CIRCULATION, "정제어유, 미지추출분말(미지추출물 50%, 덱스트린 50%)"),
    (CIRCULATION, "EPA 및 DHA 함유 유지(고시형), 미지추출물(셀렌 0.1%)(제2020-12호)"),
    (BOWEL_STATEMENT, "프로바이오틱스, 저항성말토덱스트린"),
    (BOWEL_STATEMENT, "프로바이오틱스, 난소화말토덱스트린"),
    (CIRCULATION, "정제어유, 사철쑥추출물"),
])
def test_entry_names_not_compositions_decide_nutrients_and_excipients(text: str, raw: str) -> None:
    assert not _pairs(text, raw, SINGLE_OWNERS)


def test_notified_ingredients_lacking_the_effect_do_not_hold() -> None:
    # 마늘 and 홍국 are notified for blood cholesterol, not blood circulation.
    assert _pairs(CIRCULATION, "정제어유, 젤라틴, 마늘유지(Oil), 홍국 분말", SINGLE_OWNERS) == {
        (OMEGA3, EffectKey.BLOOD_CIRCULATION)
    }


def test_mineral_yeast_is_still_a_nutrient() -> None:
    assert _pairs(CIRCULATION, "정제어유, 건조효모(셀렌함유), 젤라틴", SINGLE_OWNERS) == {
        (OMEGA3, EffectKey.BLOOD_CIRCULATION)
    }


# P2-G and P3-7: an unbalanced raw list holds; HTML entities and other brackets are normalized.
def test_unbalanced_raw_list_holds_and_brackets_are_normalized() -> None:
    from claimledger.headerless import _raw_items

    assert not _pairs(CIRCULATION, "정제어유(EPA 18%, DHA 12%, 젤라틴, 미지추출물", SINGLE_OWNERS)
    assert _raw_items("정제어유&#40;EPA, DHA&#41;, 젤라틴【소】; 글리세린")[0] == [
        "정제어유(epa,dha)", "젤라틴(소)", "글리세린",
    ]


# P3-1: shark liver oil and plant omega-3 are not EPA/DHA oil.
@pytest.mark.parametrize("raw", ["상어유, 젤라틴", "철갑상어유지, 젤라틴", "식물성오메가3, 젤라틴"])
def test_other_oils_are_not_the_omega3_target(raw: str) -> None:
    assert not _pairs(CIRCULATION, raw, SINGLE_OWNERS)


def test_owner_keys_group_target_families_and_keep_other_names() -> None:
    assert owner_key("프로바이오틱스") == "group:probiotics"
    assert owner_key("Lactiplantibacillus plantarum HAC01 프로바이오틱스") == "group:probiotics"
    assert owner_key("Bifidobacterium breve B-3") == "group:probiotics"
    assert owner_key("EPA 및 DHA의 함유유지") == "group:omega3"
    assert owner_key("루테인지아잔틴복합추출물20%") == "group:lutein_zeaxanthin"
    assert owner_key("은행잎 추출물") == "은행잎추출물"
    assert owner_key("유산균발효홍삼") == "유산균발효홍삼"
    assert owner_key("아쉬와간다(Ashwagandha)") == "아쉬와간다(ashwagandha)"
    assert owner_key("Bacillus subtilis natto 배양분말") == "bacillussubtilisnatto배양분말"
    assert owner_key("Bacillus coagulans SNZ1969 프로바이오틱스") == "group:probiotics"
    assert owner_key("Weizmannia coagulans") == "group:probiotics"


def test_reference_owner_table_is_bound_to_the_snapshot() -> None:
    table = known_statement_owners()
    assert table.source_id == "C003" and len(table.source_sha256) == 64
    assert table.min_companies == 2
    probiotic = table.statements["유산균증식및유해균억제·배변활동원활·장건강에도움을줄수있음"]
    assert probiotic["group:probiotics"] >= 2
    assert "홍삼" in table.statements["기억력개선에도움을줄수있음"]


def _decide(ad: str, official: str, raw: str):
    claims = confirm_claims(extract_claims(ad), "all")
    assert len(claims) == 1
    product = ProductCandidate(
        report_no="SYNTHETIC-HL", name="합성 테스트 제품", company="합성 테스트 업체",
        primary_function=official, raw_materials=raw, intake_method="합성 fixture",
        source_id="C003", retrieved_at=AT,
    )
    return decide_claim(claims[0], ConfirmedProduct(product=product, confirmed_by_user=True))


def test_verdict_confirms_with_its_own_reason_and_keeps_strength_rules() -> None:
    decision = _decide("배변활동 원활에 도움을 줄 수 있어요.", PROBIOTIC_STATEMENT, "프로바이오틱스(고시형), 결정셀룰로스")
    assert decision.verdict is Verdict.CONFIRMED
    assert decision.reason is VerdictReason.MATCHES_UNLABELED_OFFICIAL_FUNCTION
    assert decision.official_effect is not None
    assert decision.official_effect.attribution_basis == "headerless_owner"
    message = REASON_MESSAGES[VerdictReason.MATCHES_UNLABELED_OFFICIAL_FUNCTION]
    # Review P2-2: the message states what was checked, not that no other owner exists.
    assert "원료명" in message and "C003" in message and "개별인정" in message
    assert "다른 원료가 없습니다" not in message
    strong = _decide("배변활동을 확실히 개선합니다.", PROBIOTIC_STATEMENT, "프로바이오틱스(고시형)")
    assert strong.verdict is Verdict.MISMATCH
    held = _decide("배변활동 원활에 도움을 줄 수 있어요.", PROBIOTIC_STATEMENT, "결정셀룰로스")
    assert held.verdict is Verdict.UNVERIFIABLE


def test_receipt_records_the_basis_and_the_owner_table() -> None:
    from claimledger.receipt import build_receipt

    ad = "배변활동 원활에 도움을 줄 수 있어요."
    decision = _decide(ad, PROBIOTIC_STATEMENT, "프로바이오틱스(고시형)")
    product = ConfirmedProduct(
        product=ProductCandidate(
            report_no="SYNTHETIC-HL", name="합성 테스트 제품", company="합성 테스트 업체",
            primary_function=PROBIOTIC_STATEMENT, raw_materials="프로바이오틱스(고시형)",
            intake_method="합성 fixture", source_id="C003", retrieved_at=AT,
        ),
        confirmed_by_user=True,
    )
    receipt = build_receipt(ad, product, [decision], AT)
    quote = receipt.claims[0].official_quote
    assert quote is not None and quote.attribution_basis == "headerless_owner"
    table = known_statement_owners()
    assert f"{table.version}@{table.source_sha256[:12]}" in receipt.rule_versions


def test_build_script_counts_companies_per_owner(tmp_path: Path) -> None:
    rows = [
        {"report_no": "1", "company": "A", "primary_function": "[프로바이오틱스] " + PROBIOTIC_STATEMENT},
        {"report_no": "2", "company": "B", "primary_function": "[Bifidobacterium breve B-3] " + PROBIOTIC_STATEMENT},
        {"report_no": "3", "company": "B", "primary_function": "[프로바이오틱스] " + PROBIOTIC_STATEMENT},
        {"report_no": "4", "company": "C", "primary_function": "[홍삼] " + MEMORY_STATEMENT},
        {"report_no": "5", "company": "D", "primary_function": PROBIOTIC_STATEMENT},
    ]
    export = tmp_path / "c003.jsonl"
    export.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    output = tmp_path / "owners.json"
    code = build_statement_owners.main([
        "--source-export", str(export), "--source-retrieved-at", "2026-08-27T12:42:29+00:00",
        "--output", str(output),
    ])
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["table_version"] == "official-statement-owners-v1"
    assert payload["attribution_version"] == HEADERLESS_ATTRIBUTION_VERSION
    statements = payload["statements"]
    assert statements["유산균증식및유해균억제·배변활동원활·장건강에도움을줄수있음"] == {"group:probiotics": 2}
    assert statements["기억력개선에도움을줄수있음"] == {"홍삼": 1}
    assert len(payload["source"]["sha256"]) == 64
