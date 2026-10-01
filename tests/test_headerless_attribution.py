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


def test_owner_keys_group_target_families_and_keep_other_names() -> None:
    assert owner_key("프로바이오틱스") == "group:probiotics"
    assert owner_key("Lactiplantibacillus plantarum HAC01 프로바이오틱스") == "group:probiotics"
    assert owner_key("Bifidobacterium breve B-3") == "group:probiotics"
    assert owner_key("EPA 및 DHA의 함유유지") == "group:omega3"
    assert owner_key("루테인지아잔틴복합추출물20%") == "group:lutein_zeaxanthin"
    assert owner_key("은행잎 추출물") == "은행잎추출물"
    assert owner_key("유산균발효홍삼") == "유산균발효홍삼"


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
    assert "원료명" in REASON_MESSAGES[VerdictReason.MATCHES_UNLABELED_OFFICIAL_FUNCTION]
    strong = _decide("배변활동을 확실히 개선합니다.", PROBIOTIC_STATEMENT, "프로바이오틱스(고시형)")
    assert strong.verdict is Verdict.MISMATCH
    held = _decide("배변활동 원활에 도움을 줄 수 있어요.", PROBIOTIC_STATEMENT, "결정셀룰로스")
    assert held.verdict is Verdict.UNVERIFIABLE


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
