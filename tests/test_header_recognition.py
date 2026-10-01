"""Synthetic developer regressions for official header recognition, not an accuracy benchmark."""

from datetime import UTC, datetime

import pytest

from claimledger.claims_v1 import confirm_claims, extract_claims
from claimledger.domain import ConfirmedProduct, IngredientGroup, ProductCandidate, Verdict
from claimledger.official_v2 import (
    OFFICIAL_FUNCTION_V2_VERSION,
    known_header_vocabulary,
    normalize_header_name,
    parse_official_function_v2,
)
from claimledger.verdict_v1 import decide_claim

AT = datetime(2026, 9, 29, tzinfo=UTC)
MEMORY = "[EPA 및 DHA 함유 유지] 기억력 개선에 도움을 줄 수 있음"
CIRCULATION = "혈행 개선에 도움을 줄 수 있음"
EYE = "노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음"
VITAMIN_E = "항산화 작용을 하여 유해산소로부터 세포를 보호하는데 필요"


def _decide(ad: str, official: str):
    claims = confirm_claims(extract_claims(ad), "all")
    assert len(claims) == 1
    product = ProductCandidate(
        report_no="SYNTHETIC-H", name="합성 테스트 제품", company="합성 테스트 업체",
        primary_function=official, raw_materials="합성 fixture", intake_method="합성 fixture",
        source_id="C003", retrieved_at=AT,
    )
    return decide_claim(claims[0], ConfirmedProduct(product=product, confirmed_by_user=True))


@pytest.mark.parametrize("official", [
    MEMORY + " [검토 중] 기억력 개선",
    MEMORY + "\n[검토 중] 기억력 개선",
    MEMORY + "\n검토 중: 기억력 개선",
    MEMORY + "\n검토 중\n기억력 개선",
    MEMORY + "\n[참고] 기억력 개선 문구 재확인",
    "[검토 중] 기억력 개선\n" + MEMORY,
    "[EPA 및 DHA 함유 유지(검토중)] 기억력 개선에 도움을 줄 수 있음",
])
def test_unknown_annotation_header_with_body_holds_the_field(official: str) -> None:
    decision = _decide("기억력 개선에 도움을 줄 수 있어요.", official)
    assert decision.verdict is Verdict.UNVERIFIABLE
    assert decision.official_effect is None


@pytest.mark.parametrize("official", [
    f"[비타민E] {VITAMIN_E}\n[EPA 및 DHA 함유 유지] {CIRCULATION}",
    f"[EPA 및 DHA 함유 유지] {CIRCULATION}\n[은행잎추출물] 기억력 개선에 도움을 줄 수 있음",
    f"[아연] 정상적인 면역기능에 필요\n[EPA 및 DHA 함유 유지] {CIRCULATION}",
])
def test_known_other_ingredient_headers_do_not_block_target_evidence(official: str) -> None:
    decision = _decide("혈행 개선에 도움을 줄 수 있어요.", official)
    assert decision.verdict is Verdict.CONFIRMED
    assert decision.official_effect is not None
    assert official[slice(*decision.official_effect.statement_span)] == (
        decision.official_effect.statement_text
    )


@pytest.mark.parametrize(("official", "ad"), [
    (f"[루테인지아잔틴복합추출물(제2018-4호)] {EYE}", "눈 건강에 도움을 줄 수 있어요."),
    (f"[마리골드꽃추출물(지아잔틴함유)(제2025-7호)] {EYE}", "눈 건강에 도움을 줄 수 있어요."),
    (f"[마리골드꽃주정추출물(지아잔틴함유)(제2025-70호)] {EYE}", "눈 건강에 도움을 줄 수 있어요."),
    (f"[루테인지아잔틴추출복합물(제2025-35호)] {EYE}", "눈 건강에 도움을 줄 수 있어요."),
    (f"EPA와 DHA 함유 유지 : {CIRCULATION}", "혈행 개선에 도움을 줄 수 있어요."),
    (f"[오메가-3 지방산 함유 유지 제품] {CIRCULATION}", "혈행 개선에 도움을 줄 수 있어요."),
    ("[프로바이오틱스(고시형)] 배변활동 원활에 도움을 줄 수 있음", "배변활동 원활에 도움을 줄 수 있어요."),
])
def test_official_name_variants_are_recognized(official: str, ad: str) -> None:
    assert _decide(ad, official).verdict is Verdict.CONFIRMED


@pytest.mark.parametrize(("official", "ad"), [
    (f"[비타민E] {VITAMIN_E}\n- EPA 및 DHA 함유 유지 : {CIRCULATION}", "혈행 개선에 도움을 줄 수 있어요."),
    (f"[비타민E] {VITAMIN_E}\n2) EPA 및 DHA 함유 유지: {CIRCULATION}", "혈행 개선에 도움을 줄 수 있어요."),
    (
        f"① 비타민 E: {VITAMIN_E}\n* 프로바이오틱스\n배변활동 원활에 도움을 줄 수 있음",
        "배변활동 원활에 도움을 줄 수 있어요.",
    ),
])
def test_list_marker_is_removed_from_headers_after_the_first_line(official: str, ad: str) -> None:
    assert _decide(ad, official).verdict is Verdict.CONFIRMED


@pytest.mark.parametrize("official", [
    "[프로바이오틱스 HY7714] 배변활동 원활에 도움을 줄 수 있음",
    "[프로바이오틱스(미확인)] 배변활동 원활에 도움을 줄 수 있음",
    "[프로바이오틱스 등 복합물] 배변활동 원활에 도움을 줄 수 있음",
    "[프락토올리고당] 배변활동 원활에 도움을 줄 수 있음",
])
def test_strain_composite_or_unexplained_names_are_not_the_generic_target(official: str) -> None:
    decision = _decide("배변활동 원활에 도움을 줄 수 있어요.", official)
    assert decision.verdict is not Verdict.CONFIRMED


@pytest.mark.parametrize(("official", "ad"), [
    ("[(안) EPA 및 DHA 함유 유지] 기억력 개선에 도움을 줄 수 있음", "기억력 개선에 도움을 줄 수 있어요."),
    ("[(미)프로바이오틱스] 배변활동 원활에 도움을 줄 수 있음", "배변활동 원활에 도움을 줄 수 있어요."),
    ("[(폐)프로바이오틱스] 배변활동 원활에 도움을 줄 수 있음", "배변활동 원활에 도움을 줄 수 있어요."),
    ("[(삭)프로바이오틱스] 배변활동 원활에 도움을 줄 수 있음", "배변활동 원활에 도움을 줄 수 있어요."),
    ("[(안)프로바이오틱스(고시형)] 배변활동 원활에 도움을 줄 수 있음", "배변활동 원활에 도움을 줄 수 있어요."),
    (
        "[아연] 정상적인 면역기능에 필요\n(미) 프로바이오틱스: 배변활동 원활에 도움을 줄 수 있음",
        "배변활동 원활에 도움을 줄 수 있어요.",
    ),
    (
        "[아연] 정상적인 면역기능에 필요\n(구) 프로바이오틱스 : 배변활동 원활에 도움을 줄 수 있음",
        "배변활동 원활에 도움을 줄 수 있어요.",
    ),
    (
        "[아연] 정상적인 면역기능에 필요\n(안) EPA 및 DHA 함유 유지: 기억력 개선에 도움을 줄 수 있음",
        "기억력 개선에 도움을 줄 수 있어요.",
    ),
    ("(안) EPA 및 DHA 함유 유지: 기억력 개선에 도움을 줄 수 있음", "기억력 개선에 도움을 줄 수 있어요."),
])
def test_single_syllable_qualifier_is_not_a_list_marker(official: str, ad: str) -> None:
    decision = _decide(ad, official)
    assert decision.verdict is not Verdict.CONFIRMED
    assert decision.official_effect is None


@pytest.mark.parametrize(("official", "ad"), [
    (
        "[아연] 정상적인 면역기능에 필요\n(가) 프로바이오틱스: 배변활동 원활에 도움을 줄 수 있음",
        "배변활동 원활에 도움을 줄 수 있어요.",
    ),
    ("[③프로바이오틱스] 배변활동 원활에 도움을 줄 수 있음", "배변활동 원활에 도움을 줄 수 있어요."),
    (
        f"[비타민E] {VITAMIN_E}\n② EPA 및 DHA 함유 유지: {CIRCULATION}",
        "혈행 개선에 도움을 줄 수 있어요.",
    ),
])
def test_real_list_markers_are_still_removed(official: str, ad: str) -> None:
    assert _decide(ad, official).verdict is Verdict.CONFIRMED


def test_variant_header_does_not_lend_its_group_to_another_groups_effect() -> None:
    official = "[루테인지아잔틴복합추출물(제2018-4호)] 건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음"
    decision = _decide("건조한 눈 개선에 도움을 줄 수 있어요.", official)
    assert decision.verdict is not Verdict.CONFIRMED
    assert decision.official_effect is None


@pytest.mark.parametrize(("header", "normalized"), [
    ("- EPA 및 DHA 함유 유지", "epa및dha함유유지"),
    ("2) 비타민 E", "비타민e"),
    ("마리골드꽃추출물(지아잔틴함유)(제2025-7호)", "마리골드꽃추출물"),
    ("프로바이오틱스 제품(고시형)", "프로바이오틱스"),
    ("EPA 및 DHA 함유 유지(검토중)", "epa및dha함유유지(검토중)"),
    ("③프로바이오틱스", "프로바이오틱스"),
    ("(나) 프로바이오틱스", "프로바이오틱스"),
    ("(안) 프로바이오틱스", "(안)프로바이오틱스"),
    ("(철)", "(철)"),
])
def test_header_normalization_strips_only_allowlisted_decorations(
    header: str, normalized: str,
) -> None:
    assert normalize_header_name(header) == normalized


def test_parse_reports_target_groups_for_variant_headers() -> None:
    parsed = parse_official_function_v2(f"[비타민E] {VITAMIN_E}\n- EPA와 DHA 함유 유지 : {CIRCULATION}")
    assert parsed.parser_version == OFFICIAL_FUNCTION_V2_VERSION == "official-function-v2.7"
    assert [effect.attributed_groups for effect in parsed.effects] == [(IngredientGroup.OMEGA3,)]


def test_vocabulary_is_bound_to_its_source_and_review() -> None:
    vocabulary = known_header_vocabulary()
    assert vocabulary.source_id == "C003"
    assert len(vocabulary.source_sha256) == 64
    assert vocabulary.min_companies >= 2
    assert {"비타민e", "은행잎추출물", "아연"} <= vocabulary.names
    assert not vocabulary.names & set(vocabulary.excluded)
    assert "검토중" not in vocabulary.names
    assert all(name == normalize_header_name(name) for name in vocabulary.names)
