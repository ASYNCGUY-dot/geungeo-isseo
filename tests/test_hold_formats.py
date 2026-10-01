"""Synthetic developer regressions for held official formats found by attribution-eval-v1.

Each accepted format has risky variants that must stay held. Not an accuracy benchmark.
"""

from datetime import UTC, datetime

import pytest

from claimledger.claims_v1 import confirm_claims, extract_claims
from claimledger.domain import ConfirmedProduct, IngredientGroup, ProductCandidate, Verdict
from claimledger.official_v2 import (
    EffectKey,
    normalize_header_name,
    parse_official_function_v2,
    segment_header_names,
)
from claimledger.verdict_v1 import decide_claim

AT = datetime(2026, 10, 1, tzinfo=UTC)
LUTEIN = IngredientGroup.LUTEIN_ZEAXANTHIN
OMEGA3 = IngredientGroup.OMEGA3
EYE = "노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음"
EYE_EN = (
    "May help the eye health by maintaining the density of macular pigments which can be "
    "decreased by aging"
)
OMEGA_ALL = "혈중 중성지질 개선･혈행 개선･기억력 개선･건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음"
VITAMIN_E = "항산화 작용을 하여 유해산소로부터 세포를 보호하는데 필요"
MEM_AD = "기억력 개선에 도움을 줄 수 있어요."


def _attributed(official: str, group: IngredientGroup, effect: EffectKey) -> bool:
    return any(
        item.effect is effect and group in item.attributed_groups
        for item in parse_official_function_v2(official).effects
    )


def _decide(ad: str, official: str):
    claims = confirm_claims(extract_claims(ad), "all")
    assert len(claims) == 1
    product = ProductCandidate(
        report_no="SYNTHETIC-H", name="합성 테스트 제품", company="합성 테스트 업체",
        primary_function=official, raw_materials="합성 fixture", intake_method="합성 fixture",
        source_id="C003", retrieved_at=AT,
    )
    return decide_claim(claims[0], ConfirmedProduct(product=product, confirmed_by_user=True))


# AE-016: the dash inside an approval number was read as a "name - body" header separator.
APPROVAL_DASH = (
    "나이아신\n체내 에너지 생성에 필요\n\n"
    "마리골드꽃주정추출물(지아잔틴함유)(제2025-70호)\n" + EYE + "\n\n"
    "비타민E\n" + VITAMIN_E
)


def test_dash_inside_an_approval_number_does_not_split_the_header() -> None:
    assert "마리골드꽃주정추출물(지아잔틴함유)(제2025-70호)" in segment_header_names(APPROVAL_DASH)
    assert _attributed(APPROVAL_DASH, LUTEIN, EffectKey.MACULAR_PIGMENT_EYE_HEALTH)


def test_colon_inside_an_approval_number_does_not_split_the_header() -> None:
    official = "마리골드꽃추출물(인정번호:제2019-26호)\n" + EYE + "\n비타민E\n" + VITAMIN_E
    assert _attributed(official, LUTEIN, EffectKey.MACULAR_PIGMENT_EYE_HEALTH)


@pytest.mark.parametrize("header", [
    "마리골드꽃추출물(검토 중-재평가)",
    "마리골드꽃추출물(제2025-70호 재평가 중)",
    "마리골드꽃추출물(기능성 삭제-2025)",
])
def test_unknown_parenthetical_with_a_dash_still_holds(header: str) -> None:
    official = header + "\n" + EYE + "\n비타민E\n" + VITAMIN_E
    assert not _attributed(official, LUTEIN, EffectKey.MACULAR_PIGMENT_EYE_HEALTH)


def test_real_dash_header_is_still_a_header() -> None:
    official = "- 마리골드꽃추출물 - " + EYE + "\n- 비타민E - " + VITAMIN_E
    assert _attributed(official, LUTEIN, EffectKey.MACULAR_PIGMENT_EYE_HEALTH)


# "[name] : statement" puts the header's colon after the closing bracket.
def test_colon_after_a_bracket_header_is_part_of_the_header() -> None:
    official = "[EPA 및 DHA 함유 유지] : " + OMEGA_ALL + "\n[비타민E] : " + VITAMIN_E
    assert _attributed(official, OMEGA3, EffectKey.MEMORY)
    assert _decide(MEM_AD, official).verdict is Verdict.CONFIRMED


@pytest.mark.parametrize("official", [
    "[EPA 및 DHA 함유 유지] : 검토 중 : " + OMEGA_ALL,
    "[EPA 및 DHA 함유 유지] : : " + OMEGA_ALL,
    "[EPA 및 DHA 함유 유지] : 기억력 개선 재평가 중\n" + OMEGA_ALL,
])
def test_bracket_colon_does_not_hide_a_second_label(official: str) -> None:
    assert not _attributed(official, OMEGA3, EffectKey.MEMORY)


# "(1) 기능성 내용 : ..." labels the statement; it is not an ingredient header.
def test_function_content_label_is_read_as_a_label() -> None:
    official = "[EPA 및 DHA 함유 유지]\n(1) 기능성 내용 : " + OMEGA_ALL + "\n\n[비타민E]\n(1) " + VITAMIN_E
    assert _attributed(official, OMEGA3, EffectKey.MEMORY)
    assert _decide(MEM_AD, official).verdict is Verdict.CONFIRMED


@pytest.mark.parametrize("official", [
    "[EPA 및 DHA 함유 유지]\n(1) 기능성 내용(재평가) : " + OMEGA_ALL,
    "[EPA 및 DHA 함유 유지]\n(1) 기능성 내용 : 검토 중 : " + OMEGA_ALL,
    "[EPA 및 DHA 함유 유지]\n(1) 삭제된 기능성 내용 : " + OMEGA_ALL,
    "(1) 기능성 내용 : " + OMEGA_ALL,
])
def test_function_content_label_variants_stay_held(official: str) -> None:
    assert not _attributed(official, OMEGA3, EffectKey.MEMORY)


# (영문) translations of a reviewed statement, on their own line or after the Korean text.
@pytest.mark.parametrize("official", [
    "[루테인지아잔틴복합추출물]\n(국문) " + EYE + "\n(영문) " + EYE_EN + "\n[비타민E] " + VITAMIN_E,
    "[루테인지아잔틴복합추출물]\n" + EYE + " (영문) " + EYE_EN + "\n[비타민E] " + VITAMIN_E,
    "[루테인지아잔틴복합추출물]\n" + EYE + ", (영문) " + EYE_EN + "\n[비타민E] " + VITAMIN_E,
])
def test_reviewed_english_translation_does_not_hold_the_target(official: str) -> None:
    assert _attributed(official, LUTEIN, EffectKey.MACULAR_PIGMENT_EYE_HEALTH)


@pytest.mark.parametrize("official", [
    "[루테인지아잔틴복합추출물]\n(국문) " + EYE + "\n(영문) May help the eye health (under re-evaluation)",
    "[루테인지아잔틴복합추출물]\n(국문) " + EYE + "\n(영문) " + EYE_EN + " 재평가 중",
    "[루테인지아잔틴복합추출물]\n" + EYE + " (영문) 기능성 재검토 중",
    "[루테인지아잔틴복합추출물]\n(영문) " + EYE_EN,
])
def test_unreviewed_or_korean_translation_text_stays_held(official: str) -> None:
    assert not _attributed(official, LUTEIN, EffectKey.MACULAR_PIGMENT_EYE_HEALTH)


def test_numbered_translations_of_target_statements_are_accepted() -> None:
    official = (
        "[루테인지아잔틴복합추출물(제2018-4호)]\n"
        "(국문) ① " + EYE + " ② 건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음\n"
        "(영문) ① " + EYE_EN + " ② May help to maintain eyes healthy by relieving dryness\n"
        "[비타민E] " + VITAMIN_E
    )
    assert _attributed(official, LUTEIN, EffectKey.MACULAR_PIGMENT_EYE_HEALTH)


# Review of v2.7 (P2-1): the clause gate checks pieces, so any reviewed English piece could ride
# along. Only English that the vocabulary pairs with a target statement may be set aside; any
# other English line is an unexplained line in the block, exactly like its Korean counterpart.
MEM_BLOCK = "[EPA 및 DHA 함유 유지]"
MEM_LINE = "기억력 개선에 도움을 줄 수 있음"


@pytest.mark.parametrize("official", [
    MEM_BLOCK + "\n(영문) May help to reduce body fat\n" + MEM_LINE + "\n[비타민E] " + VITAMIN_E,
    MEM_BLOCK + "\n" + MEM_LINE + "\n(영문) May help to reduce body fat\n[비타민E] " + VITAMIN_E,
    MEM_BLOCK + " " + MEM_LINE + ", (영문). May help to improve memory. May help to reduce body fat",
    MEM_BLOCK + " " + MEM_LINE + ", (영문). :. May help to improve memory",
    MEM_BLOCK + " " + MEM_LINE + " (영문) May help to improve memory (other function claim 2 grade)",
])
def test_english_outside_target_translations_holds_the_block(official: str) -> None:
    assert not _attributed(official, OMEGA3, EffectKey.MEMORY)
    assert _decide(MEM_AD, official).verdict is not Verdict.CONFIRMED


def test_reviewed_target_translation_of_the_same_statement_is_accepted() -> None:
    official = MEM_BLOCK + " " + MEM_LINE + " (영문) May help to improve memory\n[비타민E] " + VITAMIN_E
    assert _decide(MEM_AD, official).verdict is Verdict.CONFIRMED


# Review of v2.7 (P3-1): "[A] : B : statement" names a second ingredient on the same line.
@pytest.mark.parametrize(("official", "group", "effect"), [
    (
        "[프로바이오틱스] : EPA 및 DHA 함유 유지 : " + MEM_LINE + "\n[비타민E] " + VITAMIN_E,
        OMEGA3, EffectKey.MEMORY,
    ),
    (
        "[EPA 및 DHA 함유 유지] : 루테인 : " + EYE + "\n[비타민E] " + VITAMIN_E,
        LUTEIN, EffectKey.MACULAR_PIGMENT_EYE_HEALTH,
    ),
    (
        "[EPA 및 DHA 함유 유지] : 마리골드꽃추출물 - " + EYE + "\n[비타민E] " + VITAMIN_E,
        LUTEIN, EffectKey.MACULAR_PIGMENT_EYE_HEALTH,
    ),
])
def test_second_header_after_a_bracket_colon_holds(
    official: str, group: IngredientGroup, effect: EffectKey,
) -> None:
    assert not _attributed(official, group, effect)


def test_bracket_colon_with_a_header_on_the_next_line_is_unchanged() -> None:
    official = "[EPA 및 DHA 함유 유지] : " + OMEGA_ALL + "\n마리골드꽃추출물 : " + EYE + "\n[비타민E] " + VITAMIN_E
    assert _attributed(official, OMEGA3, EffectKey.MEMORY)
    assert _attributed(official, LUTEIN, EffectKey.MACULAR_PIGMENT_EYE_HEALTH)


# Review of v2.7 (P3-2): the label and translation formats are accepted only where the reviewed
# clause vocabulary holds that exact labelled or paired clause. These pin the narrower scope so a
# vocabulary rebuild that widens it shows up as a test change.
@pytest.mark.parametrize(("official", "group", "effect"), [
    (
        MEM_BLOCK + "\n(1) 기능성 내용 : " + MEM_LINE + "\n[비타민E]\n(1) " + VITAMIN_E,
        OMEGA3, EffectKey.MEMORY,
    ),
    (
        "[프로바이오틱스]\n(1) 기능성 내용 : 유산균 증식 및 유해균 억제에 도움을 줄 수 있음\n[비타민E]\n(1) " + VITAMIN_E,
        IngredientGroup.PROBIOTICS, EffectKey.PROBIOTIC_GROWTH_HARMFUL_INHIBITION,
    ),
    (
        MEM_BLOCK + " " + MEM_LINE + " (영문) May help improve memory\n[비타민E] " + VITAMIN_E,
        OMEGA3, EffectKey.MEMORY,
    ),
])
def test_label_and_translation_outside_the_vocabulary_stay_held(
    official: str, group: IngredientGroup, effect: EffectKey,
) -> None:
    assert not _attributed(official, group, effect)


# The former grade 2 wording is "도움을 줄 수 있음"; grades 1 and 3 name other strengths.
GRADED = (
    "[EPA 및 DHA 함유유지]①혈중 중성지질 개선·혈행 개선에 도움을 줄 수 있음 "
    "②건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음(생리활성기능 2등급) "
    "③기억력 개선에 도움을 줄 수 있음 (생리활성기능 2등급)\n"
    "[비타민E]①유해산소로부터 세포를 보호하는데 필요"
)


def test_grade_two_note_matching_the_wording_is_accepted() -> None:
    assert _attributed(GRADED, OMEGA3, EffectKey.MEMORY)
    assert _decide(MEM_AD, GRADED).verdict is Verdict.CONFIRMED


@pytest.mark.parametrize("note", ["(생리활성기능 3등급)", "(생리활성기능 1등급)", "(기능성 재평가 등급)"])
def test_other_grade_notes_stay_held(note: str) -> None:
    official = "[EPA 및 DHA 함유유지]①기억력 개선에 도움을 줄 수 있음" + note + "\n[비타민E]①" + VITAMIN_E
    assert not _attributed(official, OMEGA3, EffectKey.MEMORY)


def test_grade_two_note_after_a_stronger_wording_stays_held() -> None:
    official = "[EPA 및 DHA 함유유지]①기억력 개선에 도움을 줌(생리활성기능 2등급)\n[비타민E]①" + VITAMIN_E
    assert not _attributed(official, OMEGA3, EffectKey.MEMORY)


# "(or X)" in a header is the same as "(또는X)".
def test_english_or_in_a_header_reads_as_korean_or() -> None:
    assert normalize_header_name("셀레늄(or 셀렌)") == normalize_header_name("셀레늄(또는 셀렌)")
    official = (
        "* 셀레늄(or 셀렌)\n① 유해산소로부터 세포를 보호하는데 필요\n\n"
        "* 프로바이오틱스\n① 유산균 증식 및 유해균 억제에 도움을 줄 수 있음\n② 배변활동 원활에 도움을 줄 수 있음"
    )
    assert _attributed(official, IngredientGroup.PROBIOTICS, EffectKey.BOWEL_MOVEMENT)


def test_or_is_only_rewritten_before_a_korean_name() -> None:
    assert normalize_header_name("비타민C(orange)").endswith("(orange)")


# U+2024 ("․") is typed as a middle dot; NFKC turns it into ".", which is not an effect-list
# separator. From v2.10 (user decision 2026-10-01: minimise unverifiable) U+2024 itself reads as
# "·"; ASCII and full-width periods still end a sentence.
ONE_DOT = "․"


@pytest.mark.parametrize(("official", "effect"), [
    (
        MEM_BLOCK + "\n혈중 중성지질 개선" + ONE_DOT + "혈행 개선" + ONE_DOT + "기억력 개선" + ONE_DOT
        + "건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음\n[비타민E] " + VITAMIN_E,
        EffectKey.MEMORY,
    ),
    (
        "EPA 및 DHA 함유 유지 : 혈중 중성지질 개선" + ONE_DOT + "혈행 개선에 도움을 줄 수 있음\n비타민E : " + VITAMIN_E,
        EffectKey.BLOOD_CIRCULATION,
    ),
    (
        MEM_BLOCK + "\n건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음. 혈중 중성지질 개선" + ONE_DOT
        + "혈행 개선에 도움을 줄 수 있음.\n[비타민E] " + VITAMIN_E,
        EffectKey.BLOOD_CIRCULATION,
    ),
    (MEM_BLOCK + " 기억력 개선" + ONE_DOT + "혈행 개선에 도움을 줄 수 있음", EffectKey.MEMORY),
    (MEM_BLOCK + " 기억력 개선" + ONE_DOT + " 혈행 개선에 도움을 줄 수 있음", EffectKey.MEMORY),
])
def test_one_dot_leader_reads_as_a_middle_dot(official: str, effect: EffectKey) -> None:
    assert _attributed(official, OMEGA3, effect)


def test_one_dot_leader_confirms_like_a_middle_dot() -> None:
    official = MEM_BLOCK + " 기억력 개선" + ONE_DOT + "혈행 개선에 도움을 줄 수 있음"
    assert _decide(MEM_AD, official).verdict is Verdict.CONFIRMED


@pytest.mark.parametrize("official", [
    MEM_BLOCK + " 기억력 개선" + ONE_DOT + " 검토 중" + ONE_DOT + " 혈행 개선에 도움을 줄 수 있음",
    MEM_BLOCK + " 기억력 개선" + ONE_DOT + "\n혈행 개선에 도움을 줄 수 있음",
    MEM_BLOCK + " 기억력 개선 검토 중" + ONE_DOT + "혈행 개선에 도움을 줄 수 있음",
    MEM_BLOCK + " 기억력 개선．혈행 개선에 도움을 줄 수 있음",
])
def test_one_dot_leader_does_not_join_annotations_or_lines(official: str) -> None:
    assert not _attributed(official, OMEGA3, EffectKey.MEMORY)


@pytest.mark.parametrize("official", [
    MEM_BLOCK + "\n혈중 중성지질 개선. 혈행 개선에 도움을 줄 수 있음.\n[비타민E] " + VITAMIN_E,
    MEM_BLOCK + "\n혈중 중성지질 개선.혈행 개선에 도움을 줄 수 있음\n[비타민E] " + VITAMIN_E,
    MEM_BLOCK + "\n혈중 중성지질 개선" + ONE_DOT + " 혈행 개선 검토 중" + ONE_DOT + "\n[비타민E] " + VITAMIN_E,
])
def test_ascii_period_or_unknown_text_still_holds(official: str) -> None:
    assert not _attributed(official, OMEGA3, EffectKey.BLOOD_CIRCULATION)


# Dot variants ("ㆍ", "･", "•") may mark or separate complete statements on one line, as "·" does.
def test_dot_variants_separate_complete_statements() -> None:
    official = (
        MEM_BLOCK + " ㆍ혈중 중성지질 개선ㆍ혈행 개선에 도움을 줄 수 있음ㆍ건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음\n"
        "[비타민E] " + VITAMIN_E
    )
    assert _attributed(official, OMEGA3, EffectKey.BLOOD_CIRCULATION)
    assert _attributed(official, OMEGA3, EffectKey.DRY_EYE_EYE_HEALTH)


def test_bullets_without_a_predicate_on_their_own_line_still_hold() -> None:
    official = (
        MEM_BLOCK + "\nㆍ혈중 중성지질 개선\nㆍ혈행 개선에 도움을 줄 수 있음\n"
        "ㆍ건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음\n[비타민E] " + VITAMIN_E
    )
    assert not _attributed(official, OMEGA3, EffectKey.BLOOD_CIRCULATION)


# "노화로 인하여" is the same wording as the notified "노화로 인해".
def test_inhayeo_wording_of_the_lutein_statement_is_accepted() -> None:
    official = (
        "[마리골드꽃추출물] (1) 노화로 인하여 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음\n"
        "[비타민E] " + VITAMIN_E
    )
    assert _attributed(official, LUTEIN, EffectKey.MACULAR_PIGMENT_EYE_HEALTH)


# A content percentage at the end of a header name names the same ingredient.
@pytest.mark.parametrize("header", [
    "1)\t루테인지아잔틴복합추출물20%: ",
    "[루테인지아잔틴복합추출물20%(기능성원료인정제2013-23호)] ",
])
def test_trailing_content_percentage_in_a_header_is_a_decoration(header: str) -> None:
    official = header + EYE + "\n[비타민E] " + VITAMIN_E
    assert _attributed(official, LUTEIN, EffectKey.MACULAR_PIGMENT_EYE_HEALTH)


@pytest.mark.parametrize("header", [
    "[루테인20%추출물] ",
    "[루테인(재평가)20%] ",
    "[루테인 20% 미만] ",
])
def test_percentage_inside_or_with_other_text_still_holds(header: str) -> None:
    official = header + EYE + "\n[비타민E] " + VITAMIN_E
    assert not _attributed(official, LUTEIN, EffectKey.MACULAR_PIGMENT_EYE_HEALTH)


# "정제1", "<캡슐2>" lines without a body separate the units of a product; they are not ingredients.
@pytest.mark.parametrize("divider", ["정제1", "﻿정제1", "<정제1>", "캡슐4", "연질캡슐2", "액상3"])
def test_dosage_unit_divider_without_a_body_does_not_hold(divider: str) -> None:
    official = divider + "\n" + MEM_BLOCK + " " + MEM_LINE + "\n정제2\n[비타민E] " + VITAMIN_E
    assert _attributed(official, OMEGA3, EffectKey.MEMORY)
    assert _decide(MEM_AD, official).verdict is Verdict.CONFIRMED


@pytest.mark.parametrize("official", [
    "정제1 검토 중\n" + MEM_BLOCK + " " + MEM_LINE + "\n[비타민E] " + VITAMIN_E,
    "정제1(재평가)\n" + MEM_BLOCK + " " + MEM_LINE + "\n[비타민E] " + VITAMIN_E,
    MEM_BLOCK + " " + MEM_LINE + "\n정제2\n기억력 개선 재검토 중\n[비타민E] " + VITAMIN_E,
    MEM_BLOCK + " " + MEM_LINE + "\n정제2 : 기억력 개선에 도움을 줄 수 있음\n[비타민E] " + VITAMIN_E,
])
def test_dosage_unit_variants_or_dividers_with_a_body_still_hold(official: str) -> None:
    assert not _attributed(official, OMEGA3, EffectKey.MEMORY)
