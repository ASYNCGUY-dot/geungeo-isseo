"""Tests for the frozen claim-level evaluation builder (synthetic C003 rows, no network)."""

import csv
import json
from pathlib import Path

from claimledger.official_v2 import EffectKey, effect_mentioned
from scripts import build_claim_eval

EYE = "노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음"
OMEGA = "혈중 중성지질 개선･혈행 개선에 도움을 줄 수 있음"
PROBIOTIC = "유산균 증식 및 유해균 억제･배변활동 원활･장 건강에 도움을 줄 수 있음"
VITAMIN_E = "항산화 작용을 하여 유해산소로부터 세포를 보호하는데 필요"
TARGETS = {
    "lutein": ("마리골드꽃추출물", EYE),
    "omega": ("EPA 및 DHA 함유 유지", OMEGA),
    "probiotic": ("프로바이오틱스", PROBIOTIC),
}


def _rows() -> list[dict]:
    rows = []
    for key, (name, statement) in TARGETS.items():
        for index in range(16):
            company = f"{key}-업체{index % 5}"
            variants = {
                "header": (f"[{name}] {statement}\n[비타민E] {VITAMIN_E}", f"{name}(고시형), 비타민E"),
                "headerless": (statement, f"{name}(고시형), 젤라틴"),
                "held": (f"[{name}] {statement}\n[검토 중] 확인 필요", f"{name}(고시형)"),
                "no_effect": (f"[비타민E] {VITAMIN_E}", f"{name}(고시형), 비타민E"),
            }
            # Report numbers must not reveal the stratum: the labeling sheet shows them.
            for number, (text, raw) in enumerate(variants.values()):
                rows.append({
                    "report_no": f"{key}-v{number}-{index:02d}", "name": f"{key} 제품 {index}",
                    "company": company, "primary_function": text, "raw_materials": raw,
                    "intake_method": "1일 1회",
                })
    return rows


def _export(tmp_path: Path) -> Path:
    path = tmp_path / "c003.jsonl"
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in _rows()) + "\n", encoding="utf-8")
    return path


def _sample(tmp_path: Path, *extra: str) -> dict:
    code = build_claim_eval.main([
        "sample", "--source-export", str(_export(tmp_path)),
        "--source-retrieved-at", "2026-08-27T12:42:29+00:00", "--seed", "7",
        "--manifest", str(tmp_path / "manifest.json"),
        "--generation-sheet", str(tmp_path / "generation.md"),
        "--ads-template", str(tmp_path / "ads.csv"), *extra,
    ])
    assert code == 0
    return json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))


def test_sample_allocates_strata_and_claim_types_deterministically(tmp_path: Path) -> None:
    manifest = _sample(tmp_path)
    first = (tmp_path / "manifest.json").read_bytes()
    _sample(tmp_path)
    assert (tmp_path / "manifest.json").read_bytes() == first

    items = manifest["items"]
    assert len(items) == 100
    assert [item["case_id"] for item in items] == [f"CE-{i:03d}" for i in range(1, 101)]
    assert len({item["report_no"] for item in items}) == 100
    counts: dict[tuple[str, str], int] = {}
    for item in items:
        counts[(item["stratum"], item["claim_type"])] = counts.get((item["stratum"], item["claim_type"]), 0) + 1
    expected = {
        (stratum, claim_type): count
        for stratum, allocation in build_claim_eval.ALLOCATION.items()
        for claim_type, count in allocation.items()
    }
    assert counts == expected


def test_sampled_effects_match_the_official_text(tmp_path: Path) -> None:
    rows = {row["report_no"]: row for row in _rows()}
    for item in _sample(tmp_path)["items"]:
        text = rows[item["report_no"]]["primary_function"]
        if item["claim_type"] == "out_of_scope":
            assert item["effect"] is None and item["topic"] in build_claim_eval.OUT_OF_SCOPE_TOPICS
            continue
        effect = EffectKey(item["effect"])
        if item["claim_type"] == "other_effect" or item["stratum"] == "no_effect":
            assert not effect_mentioned(text, effect)
        else:
            assert effect_mentioned(text, effect)
        if item["claim_type"] == "disease":
            assert item["disease_hint"]


def test_excluded_products_are_not_sampled(tmp_path: Path) -> None:
    earlier = tmp_path / "earlier.json"
    earlier.write_text(json.dumps({"eval_id": "x", "items": [{"report_no": "lutein-v0-00"}]}), encoding="utf-8")
    dev = tmp_path / "dev.json"
    dev.write_text(json.dumps({"cases": [{"report_no": "omega-v0-00"}, {"report_no": None}]}), encoding="utf-8")
    manifest = _sample(tmp_path, "--exclude-manifest", str(earlier), "--exclude-cases", str(dev))
    used = {item["report_no"] for item in manifest["items"]}
    assert "lutein-v0-00" not in used and "omega-v0-00" not in used
    assert manifest["excluded_products"] == 2


def test_generation_sheet_names_topics_but_not_strata_or_official_text(tmp_path: Path) -> None:
    _sample(tmp_path)
    sheet = (tmp_path / "generation.md").read_text(encoding="utf-8")
    assert "CE-001" in sheet and "headerless" not in sheet and "no_effect" not in sheet
    assert EYE not in sheet and OMEGA not in sheet
    with (tmp_path / "ads.csv").open(encoding="utf-8", newline="") as handle:
        assert [row["case_id"] for row in csv.DictReader(handle)][:2] == ["CE-001", "CE-002"]


def _ads(tmp_path: Path, manifest: dict) -> Path:
    path = tmp_path / "ads-filled.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "ad_text"])
        writer.writeheader()
        for item in manifest["items"]:
            writer.writerow({"case_id": item["case_id"], "ad_text": f"{item['case_id']} 광고 문장입니다."})
    return path


def test_labeling_sheet_hides_claim_types_and_strata(tmp_path: Path) -> None:
    manifest = _sample(tmp_path)
    code = build_claim_eval.main([
        "sheet", "--manifest", str(tmp_path / "manifest.json"), "--ads", str(_ads(tmp_path, manifest)),
        "--source-export", str(tmp_path / "c003.jsonl"),
        "--labeling-sheet", str(tmp_path / "labeling.md"), "--labels-template", str(tmp_path / "labels.csv"),
    ])
    sheet = (tmp_path / "labeling.md").read_text(encoding="utf-8")
    assert code == 0
    assert "CE-001 광고 문장입니다." in sheet and EYE in sheet
    for hidden in ("exaggerated", "out_of_scope", "other_effect", "headerless", "held", "stratum"):
        assert hidden not in sheet
    # The rule scope is one list of functions, not functions paired with ingredients (claim-eval-v1 flaw).
    assert "어느 원료가 주어인지와 관계없이" in sheet and "루테인의 황반색소밀도" not in sheet


def test_cases_keep_agreed_labels_and_list_disagreements(tmp_path: Path) -> None:
    manifest = _sample(tmp_path)
    ads = _ads(tmp_path, manifest)
    labels = []
    for labeler, flipped in (("a", "confirmed"), ("b", "unverifiable")):
        path = tmp_path / f"labels-{labeler}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["case_id", "label", "labeler", "note"])
            writer.writeheader()
            for item in manifest["items"]:
                label = flipped if item["case_id"] == "CE-002" else "mismatch"
                writer.writerow({"case_id": item["case_id"], "label": label, "labeler": labeler, "note": ""})
        labels.append(path)
    output, strict = tmp_path / "cases.json", tmp_path / "cases-strict.json"
    code = build_claim_eval.main([
        "cases", "--manifest", str(tmp_path / "manifest.json"), "--ads", str(ads),
        "--labels", str(labels[0]), "--labels", str(labels[1]),
        "--output", str(output), "--strict-output", str(strict),
        "--disagreements", str(tmp_path / "disagreements.json"),
    ])
    payload = json.loads(output.read_text(encoding="utf-8"))
    disagreements = json.loads((tmp_path / "disagreements.json").read_text(encoding="utf-8"))
    assert code == 0
    assert len(payload["cases"]) == 99 and payload["dataset_id"] == manifest["eval_id"]
    assert payload["cases"][0] == {
        "case_id": "CE-001", "report_no": manifest["items"][0]["report_no"],
        "ad_text": "CE-001 광고 문장입니다.", "expected_verdict": "mismatch", "note": "",
    }
    assert disagreements == [{"case_id": "CE-002", "labels": {"a": "confirmed", "b": "unverifiable"}}]
    # The strict file keeps every case; a disagreement takes a non-confirmed label.
    strict_cases = {case["case_id"]: case for case in json.loads(strict.read_text(encoding="utf-8"))["cases"]}
    assert len(strict_cases) == 100 and strict_cases["CE-002"]["expected_verdict"] == "unverifiable"
    bad = tmp_path / "bad.csv"
    bad.write_text("case_id,label,labeler,note\nCE-001,maybe,a,\n", encoding="utf-8")
    assert build_claim_eval.main([
        "cases", "--manifest", str(tmp_path / "manifest.json"), "--ads", str(ads),
        "--labels", str(bad), "--labels", str(labels[1]),
        "--output", str(output), "--disagreements", str(tmp_path / "d.json"),
    ]) == 3
