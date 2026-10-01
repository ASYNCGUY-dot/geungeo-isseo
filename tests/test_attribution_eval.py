import csv
import json
from pathlib import Path

import pytest

from claimledger.attribution_eval import Stratum, candidate_pairs, classify_pair
from claimledger.domain import IngredientGroup
from claimledger.official_v2 import EffectKey
from scripts import build_attribution_eval, score_attribution_eval

OMEGA = IngredientGroup.OMEGA3
PROBIOTICS = IngredientGroup.PROBIOTICS
EYE = "노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음"


@pytest.mark.parametrize(("text", "group", "effect", "stratum"), [
    ("[EPA 및 DHA 함유 유지] 혈행 개선에 도움을 줄 수 있음", OMEGA, EffectKey.BLOOD_CIRCULATION,
     Stratum.ATTRIBUTED_CANONICAL),
    ("[비타민E] 항산화 작용을 하여 유해산소로부터 세포를 보호하는데 필요\n- EPA와 DHA 함유 유지 : 혈행 개선에 도움을 줄 수 있음",
     OMEGA, EffectKey.BLOOD_CIRCULATION, Stratum.ATTRIBUTED_VARIANT_HEADER),
    ("[EPA 및 DHA 함유 유지] (가) 혈행 개선에 도움을 줄 수 있음 (나) 기억력 개선에 도움을 줄 수 있음",
     OMEGA, EffectKey.MEMORY, Stratum.ATTRIBUTED_EXTENDED_FORMAT),
    ("[EPA 및 DHA 함유 유지] 혈행 개선에 도움을 줄 수 있음 [검토 중] 기억력 개선",
     OMEGA, EffectKey.BLOOD_CIRCULATION, Stratum.HELD_UNDER_TARGET_HEADER),
    ("① 유산균 증식 및 유해균 억제에 도움을 줄 수 있음", PROBIOTICS,
     EffectKey.PROBIOTIC_GROWTH_HARMFUL_INHIBITION, Stratum.HELD_HEADERLESS),
    ("[프락토올리고당] 배변활동 원활에 도움을 줄 수 있음", PROBIOTICS, EffectKey.BOWEL_MOVEMENT,
     Stratum.HELD_OTHER),
])
def test_pairs_are_classified_by_parser_path(text, group, effect, stratum) -> None:
    assert classify_pair(text, group, effect) is stratum


VITAMIN_E = "[비타민E] 항산화 작용을 하여 유해산소로부터 세포를 보호하는데 필요"
OMEGA_STATEMENT = "혈중 중성지질 개선･혈행 개선･기억력 개선･건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음"


# Formats first accepted in official-function-v2.7/v2.8 get their own attributed stratum.
@pytest.mark.parametrize(("text", "group", "effect"), [
    ("[EPA 및 DHA 함유 유지] : " + OMEGA_STATEMENT + "\n" + VITAMIN_E, OMEGA, EffectKey.MEMORY),
    ("[EPA 및 DHA 함유 유지]\n(1) 기능성 내용 : " + OMEGA_STATEMENT + "\n" + VITAMIN_E, OMEGA, EffectKey.MEMORY),
    (
        "[루테인지아잔틴복합추출물]\n(국문) " + EYE + "\n(영문) May help the eye health by maintaining the density "
        "of macular pigments which can be decreased by aging\n" + VITAMIN_E,
        IngredientGroup.LUTEIN_ZEAXANTHIN, EffectKey.MACULAR_PIGMENT_EYE_HEALTH,
    ),
    (
        "[EPA 및 DHA 함유유지]①기억력 개선에 도움을 줄 수 있음(생리활성기능 2등급)\n" + VITAMIN_E,
        OMEGA, EffectKey.MEMORY,
    ),
    (
        "* 셀레늄(or 셀렌)\n① 유해산소로부터 세포를 보호하는데 필요\n* 프로바이오틱스\n① 배변활동 원활에 도움을 줄 수 있음",
        PROBIOTICS, EffectKey.BOWEL_MOVEMENT,
    ),
    (
        "마리골드꽃주정추출물(지아잔틴함유)(제2025-70호)\n" + EYE + "\n비타민E\n항산화 작용을 하여 유해산소로부터 세포를 보호하는데 필요",
        IngredientGroup.LUTEIN_ZEAXANTHIN, EffectKey.MACULAR_PIGMENT_EYE_HEALTH,
    ),
])
def test_pairs_attributed_through_new_formats_get_their_own_stratum(text, group, effect) -> None:
    assert classify_pair(text, group, effect) is Stratum.ATTRIBUTED_NEW_FORMAT


PROBIOTIC_STATEMENT = "유산균 증식 및 유해균 억제･배변활동 원활･장 건강에 도움을 줄 수 있음"


def test_headerless_attribution_gets_its_own_stratum_when_raw_materials_are_given() -> None:
    effect = EffectKey.BOWEL_MOVEMENT
    assert classify_pair(PROBIOTIC_STATEMENT, PROBIOTICS, effect, "프로바이오틱스(고시형), 덱스트린") is (
        Stratum.ATTRIBUTED_HEADERLESS
    )
    assert classify_pair(PROBIOTIC_STATEMENT, PROBIOTICS, effect) is Stratum.HELD_HEADERLESS
    assert classify_pair(PROBIOTIC_STATEMENT, PROBIOTICS, effect, "덱스트린") is Stratum.HELD_HEADERLESS


def test_candidate_pairs_pass_raw_materials_to_the_classifier() -> None:
    rows = [{"report_no": "H", "primary_function": PROBIOTIC_STATEMENT, "raw_materials": "프로바이오틱스(고시형)"}]
    strata = {p.effect: p.stratum for p in candidate_pairs(rows)}
    assert strata[EffectKey.GUT_HEALTH] is Stratum.ATTRIBUTED_HEADERLESS


@pytest.mark.parametrize("text", [
    "[EPA 및 DHA 함유 유지] 기억력 개선에 도움을 줄 수 있음\n" + VITAMIN_E,
    "EPA 및 DHA 함유 유지(제2004-1호) : 기억력 개선에 도움을 줄 수 있음\n" + VITAMIN_E,
    "[EPA 및 DHA 함유 유지] 기억력 개선에 도움을 줄 수 있음\n[아연] 정상적인 면역기능에 필요\n" + VITAMIN_E,
])
def test_formats_read_before_v27_are_not_counted_as_new(text) -> None:
    assert classify_pair(text, OMEGA, EffectKey.MEMORY) in (
        Stratum.ATTRIBUTED_CANONICAL, Stratum.ATTRIBUTED_VARIANT_HEADER, Stratum.ATTRIBUTED_EXTENDED_FORMAT,
    )


def test_candidate_pairs_need_the_target_in_raw_materials_or_an_attribution() -> None:
    rows = [
        {"report_no": "A", "primary_function": "배변활동 원활에 도움을 줄 수 있음", "raw_materials": "프로바이오틱스"},
        {"report_no": "B", "primary_function": "배변활동 원활에 도움을 줄 수 있음", "raw_materials": "차전자피"},
        {"report_no": "C", "primary_function": f"[루테인] {EYE}", "raw_materials": "정제"},
    ]
    pairs = {(p.report_no, p.group, p.effect) for p in candidate_pairs(rows)}

    assert ("A", PROBIOTICS, EffectKey.BOWEL_MOVEMENT) in pairs
    assert not any(report_no == "B" for report_no, _, _ in pairs)
    assert ("C", IngredientGroup.LUTEIN_ZEAXANTHIN, EffectKey.MACULAR_PIGMENT_EYE_HEALTH) in pairs


def _export(path: Path) -> Path:
    rows = []
    for i in range(12):
        rows.append({"report_no": f"C{i}", "name": f"오메가{i}", "company": f"업체{i % 3}",
                     "primary_function": "[EPA 및 DHA 함유 유지] 혈행 개선에 도움을 줄 수 있음",
                     "raw_materials": "EPA 및 DHA 함유 유지", "intake_method": "1일 1회"})
        rows.append({"report_no": f"H{i}", "name": f"유산균{i}", "company": f"업체{i % 3}",
                     "primary_function": "유산균 증식 및 유해균 억제에 도움을 줄 수 있음",
                     # 프락토올리고당 could own this single-effect statement, so it stays held.
                     "raw_materials": "프로바이오틱스, 프락토올리고당", "intake_method": "1일 1회"})
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return path


def _build(tmp_path: Path, *extra: str) -> tuple[int, dict]:
    out = tmp_path / "manifest.json"
    code = build_attribution_eval.main([
        "--source-export", str(_export(tmp_path / "c003.jsonl")),
        "--source-retrieved-at", "2026-08-27T12:42:29+00:00",
        "--seed", "20261001",
        "--quota", "attributed_canonical=3", "--quota", "held_headerless=2",
        "--manifest", str(out),
        "--review-sheet", str(tmp_path / "review.md"),
        "--labels-template", str(tmp_path / "labels.csv"),
        *extra,
    ])
    return code, json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}


def test_build_samples_quotas_deterministically_and_hides_the_stratum(tmp_path: Path) -> None:
    code, manifest = _build(tmp_path)
    first = (tmp_path / "manifest.json").read_bytes()
    _build(tmp_path)

    assert code == 0
    assert (tmp_path / "manifest.json").read_bytes() == first
    strata = [item["stratum"] for item in manifest["items"]]
    assert strata.count("attributed_canonical") == 3 and strata.count("held_headerless") == 2
    assert [item["item_id"] for item in manifest["items"]] == [f"AE-{i:03d}" for i in range(1, 6)]
    assert len({item["report_no"] for item in manifest["items"]}) == 5
    assert manifest["frame_counts"]["attributed_canonical"] == 12
    sheet = (tmp_path / "review.md").read_text(encoding="utf-8")
    assert "AE-001" in sheet and "attributed" not in sheet and "held" not in sheet
    with (tmp_path / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["item_id"] for row in rows] == [f"AE-{i:03d}" for i in range(1, 6)]
    assert all(row["label"] == "" for row in rows)


def test_build_excludes_products_of_an_earlier_manifest_and_uses_the_item_prefix(tmp_path: Path) -> None:
    _, first = _build(tmp_path)
    earlier = tmp_path / "earlier.json"
    earlier.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
    used = {item["report_no"] for item in first["items"]}

    code, second = _build(
        tmp_path, "--exclude-manifest", str(earlier), "--item-prefix", "AE2", "--eval-id", "attribution-eval-v2",
    )

    assert code == 0
    assert not used & {item["report_no"] for item in second["items"]}
    assert [item["item_id"] for item in second["items"]] == [f"AE2-{i:03d}" for i in range(1, 6)]
    assert second["eval_id"] == "attribution-eval-v2"
    excluded = second["excluded_manifests"]
    assert excluded[0]["eval_id"] == first["eval_id"] and excluded[0]["products"] == 5
    assert len(excluded[0]["sha256"]) == 64
    assert "AE2-001" in (tmp_path / "review.md").read_text(encoding="utf-8")


def test_score_reports_false_attribution_and_missed_attribution(tmp_path: Path) -> None:
    _, manifest = _build(tmp_path)
    labels = tmp_path / "labels.csv"
    with labels.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["item_id", "label", "labeler", "note"])
        writer.writeheader()
        for item in manifest["items"]:
            label = "no" if item["stratum"] == "attributed_canonical" and item["item_id"] == next(
                i["item_id"] for i in manifest["items"] if i["stratum"] == "attributed_canonical"
            ) else "yes"
            writer.writerow({"item_id": item["item_id"], "label": label, "labeler": "test", "note": ""})
    output = tmp_path / "score.json"

    code = score_attribution_eval.main([
        "--manifest", str(tmp_path / "manifest.json"), "--labels", str(labels),
        "--source-export", str(tmp_path / "c003.jsonl"),
        "--source-retrieved-at", "2026-08-27T12:42:29+00:00", "--output", str(output),
    ])

    summary = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    canonical = summary["strata"]["attributed_canonical"]
    assert (canonical["n"], canonical["false_attribution"], canonical["correct"]) == (3, 1, 2)
    assert canonical["false_attribution_wilson"][0] > 0
    held = summary["strata"]["held_headerless"]
    assert (held["n"], held["missed_attribution"]) == (2, 2)
    assert summary["stratum_drift"] == []
    assert summary["unlabeled"] == 0


def test_score_counts_a_held_item_that_is_now_attributed_with_a_no_label(tmp_path: Path) -> None:
    # Review P2-1: an item frozen as held, now attributed by a newer rule and labelled "no", is a
    # false attribution of the current parser even though its frozen stratum is a held one.
    _, manifest = _build(tmp_path)
    moved = next(item for item in manifest["items"] if item["stratum"] == "attributed_canonical")
    moved["stratum"] = "held_headerless"
    (tmp_path / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    labels = tmp_path / "labels.csv"
    with labels.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["item_id", "label", "labeler", "note"])
        writer.writeheader()
        for item in manifest["items"]:
            label = "no" if item["item_id"] == moved["item_id"] else "yes"
            writer.writerow({"item_id": item["item_id"], "label": label, "labeler": "test", "note": ""})
    output = tmp_path / "score.json"
    args = [
        "--manifest", str(tmp_path / "manifest.json"), "--labels", str(labels),
        "--source-export", str(tmp_path / "c003.jsonl"),
        "--source-retrieved-at", "2026-08-27T12:42:29+00:00", "--output", str(output),
    ]

    assert score_attribution_eval.main([*args, "--require-zero-false-attribution"]) == 1
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["drift_false_attribution"] == [moved["item_id"]]


def test_score_rejects_unknown_labels_and_counts_unlabeled(tmp_path: Path) -> None:
    _build(tmp_path)
    labels = tmp_path / "labels.csv"
    labels.write_text("item_id,label,labeler,note\nAE-001,maybe,test,\n", encoding="utf-8")
    args = [
        "--manifest", str(tmp_path / "manifest.json"), "--labels", str(labels),
        "--source-export", str(tmp_path / "c003.jsonl"),
        "--source-retrieved-at", "2026-08-27T12:42:29+00:00", "--output", str(tmp_path / "s.json"),
    ]
    assert score_attribution_eval.main(args) == 3

    labels.write_text("item_id,label,labeler,note\nAE-001,yes,test,\n", encoding="utf-8")
    assert score_attribution_eval.main(args) == 0
    assert json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))["unlabeled"] == 4
