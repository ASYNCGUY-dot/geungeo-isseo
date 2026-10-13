"""Frozen evaluation set for cosmetics claims: sampling, blind sheets, label merge and scoring (synthetic export)."""

import csv
import json
from pathlib import Path

import pytest

from claimledger.sources.functional_cosmetics import EXPORT_FIELDS
from scripts import build_cosmetic_eval

WHITENING = "피부의 미백에 도움을 준다."
WRINKLE = "피부의 주름개선에 도움을 준다."
SUN = "자외선으로부터 피부를 보호한다.(SPF50+, PA++++)"
TEMPLATE = "※ 해당하는 효능효과 이외에는 모두 삭제하시기 바랍니다."
# Stratum -> (efficacy sentence, efficacy document) for the synthetic rows.
KINDS = {
    "both": (f"{WHITENING} {WRINKLE}", ""),
    "whitening_only": (WHITENING, ""),
    "wrinkle_only": ("", WRINKLE),
    "with_sunscreen": ("", f"{WHITENING}\n{SUN}"),
    "other_function": ("", SUN),
    "held_missing": ("", ""),
    "held_template": ("", f"{WHITENING}\n{TEMPLATE}"),
    "held_unrecognized": ("", "피부의 미백에 도움은 준다."),
    "held_conflicting": (WHITENING, SUN),
}


def _export(tmp_path: Path) -> Path:
    directory = tmp_path / "export"
    directory.mkdir(exist_ok=True)
    for source in ("reported", "reviewed"):
        rows = []
        for kind_index, (sentence, document) in enumerate(KINDS.values()):
            for index in range(40):
                row = dict.fromkeys(EXPORT_FIELDS, "")
                row.update({
                    # Record numbers must not reveal the stratum: the labeling sheet shows them.
                    "record_id": f"{source[:3]}{kind_index}{index:03d}", "item_name": f"합성 제품 {kind_index}-{index}",
                    "company": "합성 화장품", "registered_on": "20250102",
                    "effect_name": sentence if source == "reported" else "",
                    "effect_text": document if source == "reported" else "\n".join(filter(None, [sentence, document])),
                    "effect_doc_unreadable": False, "whitening": None, "wrinkle": None, "sunscreen": None,
                    "withdrawn": False,
                })
                # The loader re-reads the raw document, so the synthetic text is stored there as well.
                row["effect_doc"] = "".join(
                    f'<PARAGRAPH tagName="p"><![CDATA[{line}]]></PARAGRAPH>' for line in row["effect_text"].split("\n") if line
                )
                rows.append(row)
        stem = directory / f"functional-cosmetics-{source}"
        stem.with_suffix(".jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
        )
        stem.with_suffix(".audit.json").write_text(
            json.dumps({"retrieved_at": "2026-10-11T05:18:59+00:00", "total_count": len(rows), "sha256": "A" * 64}),
            encoding="utf-8",
        )
    return directory


def _sample(tmp_path: Path, *extra: str) -> dict:
    code = build_cosmetic_eval.main([
        "sample", "--export-dir", str(_export(tmp_path)), "--seed", "11",
        "--manifest", str(tmp_path / "manifest.json"), "--generation-sheet", str(tmp_path / "generation.md"),
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
    assert len(items) == 100 and [item["case_id"] for item in items] == [f"CC-{n:03d}" for n in range(1, 101)]
    assert len({(item["source"], item["record_id"]) for item in items}) == 100
    counts: dict[tuple[str, str], int] = {}
    for item in items:
        counts[(item["stratum"], item["claim_type"])] = counts.get((item["stratum"], item["claim_type"]), 0) + 1
    assert counts == {
        (stratum, claim_type): count
        for stratum, allocation in build_cosmetic_eval.ALLOCATION.items()
        for claim_type, count in allocation.items()
    }
    assert {item["source"] for item in items} == {"reported", "reviewed"}
    assert manifest["sources"]["reported"]["sha256"] == "A" * 64 and manifest["seed"] == 11
    assert manifest["allocation_id"] == "claims-v1" and manifest["allocation"] == build_cosmetic_eval.ALLOCATION


def test_the_second_allocation_probes_wrong_mismatches(tmp_path: Path) -> None:
    manifest = _sample(tmp_path, "--allocation", "claims-v2")
    allocation = build_cosmetic_eval.ALLOCATIONS["claims-v2"]
    items = manifest["items"]

    assert manifest["allocation_id"] == "claims-v2" and manifest["allocation"] == allocation
    assert len(items) == 100 == sum(sum(counts.values()) for counts in allocation.values())
    counts: dict[tuple[str, str], int] = {}
    for item in items:
        counts[(item["stratum"], item["claim_type"])] = counts.get((item["stratum"], item["claim_type"]), 0) + 1
    assert counts == {(stratum, kind): count for stratum, kinds in allocation.items() for kind, count in kinds.items()}

    asides = [item for item in items if item["claim_type"] == "bystander"]
    assert asides and all(item["stratum"] in {"whitening_only", "wrinkle_only"} for item in asides)
    for item in asides:
        # The product's own function is the topic; the other one is only named beside it.
        own = {"whitening_only": "whitening", "wrinkle_only": "wrinkle"}[item["stratum"]]
        assert item["topic"] == [own] and item["style"] == "support"
        assert item["aside"] == {"whitening": "주름개선", "wrinkle": "미백"}[own]
    makeup = [item for item in items if item["claim_type"] == "makeup"]
    assert makeup and all(item["topic"] == [] and item["style"] == "makeup" for item in makeup)
    assert all(item["aside"] is None for item in items if item["claim_type"] != "bystander")

    sheet = (tmp_path / "generation.md").read_text(encoding="utf-8")
    assert "함께 쓰는 다른 제품" in sheet and "메이크업 효과" in sheet
    for hidden in ("bystander", "makeup", "held", "stratum", "absent", WHITENING):
        assert hidden not in sheet


def test_topics_follow_the_claim_type(tmp_path: Path) -> None:
    for item in _sample(tmp_path)["items"]:
        topic, stratum, kind = set(item["topic"]), item["stratum"], item["claim_type"]
        if kind == "out_of_scope":
            assert not topic and item["topic_text"] in build_cosmetic_eval.OUT_OF_SCOPE_TOPICS
            assert item["aside"] is None
            continue
        assert topic and topic <= {"whitening", "wrinkle"}
        if kind == "absent":
            assert stratum in {"whitening_only", "wrinkle_only", "other_function"}
            assert {"whitening_only": "wrinkle" in topic, "wrinkle_only": "whitening" in topic}.get(stratum, True)
        if kind == "official" and stratum == "whitening_only":
            assert topic == {"whitening"}
        if kind == "ingredient":
            assert item["subject"] in build_cosmetic_eval.INGREDIENTS.values()
        if kind == "medical":
            assert item["hint"]


def test_the_generation_sheet_hides_strata_and_official_text(tmp_path: Path) -> None:
    _sample(tmp_path)
    sheet = (tmp_path / "generation.md").read_text(encoding="utf-8")
    assert "CC-001" in sheet
    for hidden in ("held", "stratum", "absent", "out_of_scope", "both", WHITENING, TEMPLATE):
        assert hidden not in sheet
    with (tmp_path / "ads.csv").open(encoding="utf-8", newline="") as handle:
        assert [row["case_id"] for row in csv.DictReader(handle)][:2] == ["CC-001", "CC-002"]


def _ads(tmp_path: Path, manifest: dict, text: str = "미백에 도움을 줍니다.") -> Path:
    path = tmp_path / "ads-filled.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "ad_text"])
        writer.writeheader()
        for item in manifest["items"]:
            writer.writerow({"case_id": item["case_id"], "ad_text": text})
    return path


def test_the_labeling_sheet_shows_official_fields_but_not_strata(tmp_path: Path) -> None:
    manifest = _sample(tmp_path)
    code = build_cosmetic_eval.main([
        "sheet", "--manifest", str(tmp_path / "manifest.json"), "--ads", str(_ads(tmp_path, manifest)),
        "--export-dir", str(tmp_path / "export"), "--labeling-sheet", str(tmp_path / "labeling.md"),
        "--labels-template", str(tmp_path / "labels.csv"),
    ])
    sheet = (tmp_path / "labeling.md").read_text(encoding="utf-8")
    assert code == 0 and "미백에 도움을 줍니다." in sheet and WHITENING in sheet and TEMPLATE in sheet
    assert "(없음)" in sheet
    for hidden in ("held", "stratum", "absent", "out_of_scope", "claim_type", "whitening_only"):
        assert hidden not in sheet


def _labels(tmp_path: Path, manifest: dict, labeler: str, flips: dict[str, str]) -> Path:
    path = tmp_path / f"labels-{labeler}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "label", "labeler", "note"])
        writer.writeheader()
        for item in manifest["items"]:
            label = flips.get(item["case_id"], "unverifiable")
            writer.writerow({"case_id": item["case_id"], "label": label, "labeler": labeler, "note": ""})
    return path


def test_cases_keep_agreed_labels_and_the_strict_file_keeps_all(tmp_path: Path) -> None:
    manifest = _sample(tmp_path)
    ads = _ads(tmp_path, manifest)
    first = _labels(tmp_path, manifest, "a", {"CC-002": "confirmed"})
    second = _labels(tmp_path, manifest, "b", {"CC-002": "mismatch"})
    code = build_cosmetic_eval.main([
        "cases", "--manifest", str(tmp_path / "manifest.json"), "--ads", str(ads),
        "--labels", str(first), "--labels", str(second), "--output", str(tmp_path / "cases.json"),
        "--strict-output", str(tmp_path / "strict.json"), "--disagreements", str(tmp_path / "d.json"),
    ])
    cases = json.loads((tmp_path / "cases.json").read_text(encoding="utf-8"))["cases"]
    strict = {case["case_id"]: case for case in json.loads((tmp_path / "strict.json").read_text(encoding="utf-8"))["cases"]}
    assert code == 0 and len(cases) == 99 and len(strict) == 100
    assert cases[0] == {
        "case_id": "CC-001", "source": manifest["items"][0]["source"], "record_id": manifest["items"][0]["record_id"],
        "ad_text": "미백에 도움을 줍니다.", "expected_verdict": "unverifiable", "note": "",
    }
    assert strict["CC-002"]["expected_verdict"] == "mismatch"
    assert json.loads((tmp_path / "d.json").read_text(encoding="utf-8")) == [
        {"case_id": "CC-002", "labels": {"a": "confirmed", "b": "mismatch"}}
    ]
    bad = tmp_path / "bad.csv"
    bad.write_text("case_id,label,labeler,note\nCC-001,maybe,a,\n", encoding="utf-8")
    assert build_cosmetic_eval.main([
        "cases", "--manifest", str(tmp_path / "manifest.json"), "--ads", str(ads), "--labels", str(bad),
        "--labels", str(second), "--output", str(tmp_path / "x.json"), "--disagreements", str(tmp_path / "y.json"),
    ]) == 3


def _score(tmp_path: Path, cases: list[dict], *extra: str) -> tuple[int, dict]:
    path = tmp_path / "score-cases.json"
    path.write_text(json.dumps({"dataset_id": "t", "cases": cases}, ensure_ascii=False), encoding="utf-8")
    code = build_cosmetic_eval.main([
        "score", "--cases", str(path), "--export-dir", str(_export(tmp_path)),
        "--output", str(tmp_path / "score.json"), *extra,
    ])
    output = tmp_path / "score.json"
    return code, json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}


def _case(case_id: str, record_id: str, ad: str, expected: str, source: str = "reported") -> dict:
    return {"case_id": case_id, "source": source, "record_id": record_id, "ad_text": ad, "expected_verdict": expected, "note": ""}


def test_score_reports_agreement_recall_and_false_clearance(tmp_path: Path) -> None:
    cases = [
        _case("A", "rep0000", "미백과 주름개선에 도움을 줍니다.", "confirmed"),
        _case("B", "rep1000", "주름개선에 도움을 줍니다.", "mismatch"),
        _case("C", "rep5000", "미백에 도움을 줍니다.", "unverifiable"),
        _case("D", "rev0000", "나이아신아마이드가 미백에 도움을 줍니다.", "confirmed", source="reviewed"),
        _case("E", "rep0001", "촉촉한 사용감입니다.", "unverifiable"),
        # Unjudged text beside a recognized sentence withholds the confirmation.
        _case("F", "rep0002", "단 2주. 미백에 도움을 줍니다.", "mismatch"),
    ]
    code, summary = _score(tmp_path, cases, "--require-zero-false-clearance")
    assert code == 0
    assert summary["judged_case_count"] == 6 and summary["exact_agreement_count"] == 3
    assert summary["false_clearance_count"] == 0 and summary["confirmed_recall"] == 0.5
    assert summary["claim_extraction_error_count"] == 1
    by_id = {row["case_id"]: row for row in summary["results"]}
    assert by_id["D"]["actual_verdict"] == "unverifiable" and by_id["D"]["reason_code"] == "CLAIM_SCOPE_UNRESOLVED"
    assert by_id["E"]["outcome"] == "claim_count_error" and by_id["E"]["actual_verdict"] == "unverifiable"
    assert by_id["F"]["actual_verdict"] == "unverifiable" and by_id["F"]["reason_code"] == "AD_TEXT_NOT_FULLY_READ"
    assert summary["rule_versions"] == ["cosmetic-claim-v1.8", "cosmetic-efficacy-v1.1", "cosmetic-verdict-v1.4"]


def test_a_false_clearance_fails_the_gate(tmp_path: Path) -> None:
    cases = [_case("A", "rep0000", "미백에 도움을 줍니다.", "unverifiable")]
    code, summary = _score(tmp_path, cases, "--require-zero-false-clearance")
    assert code == 1 and summary["false_clearance_count"] == 1
    assert _score(tmp_path, cases)[0] == 0


@pytest.mark.parametrize("case", [
    _case("A", "nope", "미백에 도움을 줍니다.", "confirmed"),
    {**_case("A", "rep0000", "미백에 도움을 줍니다.", "confirmed"), "source": "unknown"},
])
def test_unknown_records_are_input_errors(tmp_path: Path, case: dict) -> None:
    assert _score(tmp_path, [case])[0] == 3


def test_a_later_sample_can_leave_out_the_records_of_an_earlier_one(tmp_path: Path) -> None:
    first = _sample(tmp_path)
    used = {(item["source"], item["record_id"]) for item in first["items"]}
    arguments = [
        "sample", "--export-dir", str(tmp_path / "export"), "--seed", "11", "--eval-id", "cosmetic-eval-v2",
        "--case-prefix", "CD", "--manifest", str(tmp_path / "second.json"),
        "--generation-sheet", str(tmp_path / "generation-2.md"), "--ads-template", str(tmp_path / "ads-2.csv"),
    ]
    # The same seed would pick the same records again.
    assert build_cosmetic_eval.main(arguments) == 0
    again = json.loads((tmp_path / "second.json").read_text(encoding="utf-8"))
    assert {(item["source"], item["record_id"]) for item in again["items"]} == used

    assert build_cosmetic_eval.main([*arguments, "--exclude-manifest", str(tmp_path / "manifest.json")]) == 0
    second = json.loads((tmp_path / "second.json").read_text(encoding="utf-8"))
    assert not used & {(item["source"], item["record_id"]) for item in second["items"]}
    assert second["excluded_evals"] == ["cosmetic-eval-v1"] and second["items"][0]["case_id"] == "CD-001"
    assert "excluded_evals" not in first


def test_the_labeling_sheet_says_how_to_read_a_condition_on_the_effect(tmp_path: Path) -> None:
    manifest = _sample(tmp_path)
    assert build_cosmetic_eval.main([
        "sheet", "--manifest", str(tmp_path / "manifest.json"), "--ads", str(_ads(tmp_path, manifest)),
        "--export-dir", str(tmp_path / "export"), "--labeling-sheet", str(tmp_path / "labeling.md"),
        "--labels-template", str(tmp_path / "labels.csv"),
    ]) == 0
    sheet = (tmp_path / "labeling.md").read_text(encoding="utf-8")
    # The two labelers of v1 split on exactly this.
    assert "꾸준히 바르면" in sheet and "조건이 붙은 것" in sheet
