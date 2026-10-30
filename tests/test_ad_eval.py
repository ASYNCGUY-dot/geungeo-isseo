"""Tests for the multi-sentence advertisement evaluation (synthetic C003 rows, no network)."""

import csv
import json
from collections import Counter
from pathlib import Path

from claimledger.claims_v1 import CLAIM_EXTRACTION_VERSION
from claimledger.official_v2 import EFFECT_GROUP, EffectKey, effect_mentioned
from claimledger.verdict_v1 import CLAIM_VERDICT_VERSION
from scripts import build_ad_eval, score_ad_eval

RETRIEVED_AT = "2026-08-27T12:42:29+00:00"
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
        for index in range(20):
            variants = {
                "header": (f"[{name}] {statement}\n[비타민E] {VITAMIN_E}", f"{name}(고시형), 비타민E"),
                "headerless": (statement, f"{name}(고시형), 젤라틴"),
                "held": (f"[{name}] {statement}\n[검토 중] 확인 필요", f"{name}(고시형)"),
                "no_effect": (f"[비타민E] {VITAMIN_E}", f"{name}(고시형), 비타민E"),
            }
            for number, (text, raw) in enumerate(variants.values()):
                rows.append({
                    "report_no": f"{key}-v{number}-{index:02d}", "name": f"{key} 제품 {index}",
                    "company": f"{key}-업체{index % 5}", "primary_function": text, "raw_materials": raw,
                    "intake_method": "1일 1회",
                })
    for index in range(60):
        rows.append({
            "report_no": f"combo-{index:02d}", "name": f"복합 제품 {index}", "company": "복합업체",
            "primary_function": f"[마리골드꽃추출물] {EYE}\n[EPA 및 DHA 함유 유지] {OMEGA}",
            "raw_materials": "마리골드꽃추출물(고시형), EPA 및 DHA 함유 유지(고시형)", "intake_method": "1일 1회",
        })
    return rows


def _export(tmp_path: Path) -> Path:
    path = tmp_path / "c003.jsonl"
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in _rows()) + "\n", encoding="utf-8")
    return path


def _sample(tmp_path: Path, *extra: str) -> dict:
    code = build_ad_eval.main([
        "sample", "--source-export", str(_export(tmp_path)),
        "--source-retrieved-at", RETRIEVED_AT, "--seed", "7",
        "--manifest", str(tmp_path / "manifest.json"),
        "--generation-sheet", str(tmp_path / "generation.md"),
        "--segments-template", str(tmp_path / "segments.csv"), *extra,
    ])
    assert code == 0
    return json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))


def _claims(item: dict) -> list[dict]:
    return [segment for segment in item["segments"] if segment["role"] == "claim"]


def _contexts(item: dict) -> list[str]:
    return [segment["kind"] for segment in item["segments"] if segment["role"] == "context"]


def test_sample_is_deterministic_and_fills_every_cell(tmp_path: Path) -> None:
    manifest = _sample(tmp_path)
    first = (tmp_path / "manifest.json").read_bytes()
    _sample(tmp_path)
    assert (tmp_path / "manifest.json").read_bytes() == first

    items = manifest["items"]
    assert [item["case_id"] for item in items] == [f"C3-{i:03d}" for i in range(1, 101)]
    assert len({item["report_no"] for item in items}) == 100
    counts = Counter((item["scenario"], item["stratum"], item["claim_type"]) for item in items)
    assert counts == {(scenario, stratum, claim_type): count for scenario, stratum, claim_type, count in build_ad_eval.CELLS}
    for scenario in {item["scenario"] for item in items}:
        layouts = Counter(item["layout"] for item in items if item["scenario"] == scenario)
        assert set(layouts) == set(build_ad_eval.LAYOUTS) and max(layouts.values()) - min(layouts.values()) <= 1
    modifiers = Counter(kind for item in items for kind in _contexts(item) if kind in build_ad_eval.MODIFIERS)
    assert modifiers == {kind: 4 for kind in build_ad_eval.MODIFIERS}
    for item in items:
        assert [segment["seg_no"] for segment in item["segments"]] == list(range(1, len(item["segments"]) + 1))
        assert 2 <= len(item["segments"]) <= 4


def test_scenarios_set_the_sentence_roles(tmp_path: Path) -> None:
    rows = {row["report_no"]: row for row in _rows()}
    for item in _sample(tmp_path)["items"]:
        text = rows[item["report_no"]]["primary_function"]
        claims, contexts = _claims(item), _contexts(item)
        if "notice" in contexts:
            assert item["segments"][-1]["kind"] == "notice"
        if item["scenario"] in {"honest", "unsupported"}:
            assert len(claims) == 1 and set(contexts) <= {"intro", "usage", "notice"} and contexts
        if item["scenario"] in {"honest", "modifier", "two_claims", "carryover"}:
            assert all(claim["style"] == "support" for claim in claims)
            assert all(effect_mentioned(text, EffectKey(claim["effect"])) for claim in claims)
        if item["scenario"] == "two_claims":
            assert len(claims) == 2 and claims[0]["effect"] != claims[1]["effect"]
        if item["scenario"] == "carryover":
            first, second = claims
            assert (first["subject_mode"], second["subject_mode"]) == ("ingredient", "omitted")
            assert EFFECT_GROUP[EffectKey(second["effect"])].value != first["group"]
        if item["scenario"] == "modifier":
            assert len(claims) == 1
            assert len([kind for kind in contexts if kind in build_ad_eval.MODIFIERS]) == 1
        if item["claim_type"] in {"other_effect"} or item["stratum"] == "no_effect":
            assert not effect_mentioned(text, EffectKey(claims[0]["effect"]))
        if item["claim_type"] == "disease":
            assert claims[0]["disease_hint"]


def test_generation_sheet_names_roles_but_not_scenarios_or_official_text(tmp_path: Path) -> None:
    _sample(tmp_path)
    sheet = (tmp_path / "generation.md").read_text(encoding="utf-8")
    assert "C3-001" in sheet and "의약품" in sheet
    for hidden in ("carryover", "unsupported", "honest", "headerless", "no_effect", "lines_no_period", EYE, OMEGA):
        assert hidden not in sheet
    with (tmp_path / "segments.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0] == {"case_id": "C3-001", "seg_no": "1", "text": ""}


def test_layouts_keep_each_sentence_span() -> None:
    texts = ["루테인은 눈 건강에 도움을 줄 수 있습니다.", "하루 한 번 드세요!", "의약품이 아닙니다."]
    expected = {
        "inline": "루테인은 눈 건강에 도움을 줄 수 있습니다. 하루 한 번 드세요! 의약품이 아닙니다.",
        "lines": "루테인은 눈 건강에 도움을 줄 수 있습니다.\n하루 한 번 드세요!\n의약품이 아닙니다.",
        "lines_no_period": "루테인은 눈 건강에 도움을 줄 수 있습니다\n하루 한 번 드세요!\n의약품이 아닙니다",
        "wrapped": "루테인은 눈 건강에\n도움을 줄 수 있습니다.\n하루 한 번 드세요!\n의약품이 아닙니다.",
    }
    for layout, text in expected.items():
        ad_text, spans = build_ad_eval.compose(layout, texts, wrap=0)
        assert ad_text == text
        assert [ad_text[start:end].replace("\n", " ") for start, end in spans][1:] == [
            texts[1], texts[2] if layout != "lines_no_period" else "의약품이 아닙니다",
        ]
    ad_text, spans = build_ad_eval.compose("lines_no_period", ["좋아요...", "끝."], wrap=None)
    assert ad_text == "좋아요...\n끝" and spans == [(0, 6), (7, 8)]


def _segments(tmp_path: Path, manifest: dict, *, broken: str | None = None) -> Path:
    path = tmp_path / "segments-filled.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "seg_no", "text"])
        writer.writeheader()
        for item in manifest["items"]:
            for segment in item["segments"]:
                text = f"{item['case_id']}의 {segment['seg_no']}번 문장입니다."
                if broken == "newline" and item["case_id"] == "C3-003":
                    text = "두 줄\n문장."
                if broken == "missing" and item["case_id"] == "C3-003":
                    continue
                writer.writerow({"case_id": item["case_id"], "seg_no": segment["seg_no"], "text": text})
    return path


def _sheet(tmp_path: Path, segments: Path) -> int:
    return build_ad_eval.main([
        "sheet", "--manifest", str(tmp_path / "manifest.json"), "--segments", str(segments),
        "--source-export", str(tmp_path / "c003.jsonl"), "--ads-output", str(tmp_path / "ads.json"),
        "--labeling-sheet", str(tmp_path / "labeling.md"), "--labels-template", str(tmp_path / "labels.csv"),
    ])


def test_sheet_composes_ads_and_hides_scenarios(tmp_path: Path) -> None:
    manifest = _sample(tmp_path)
    assert _sheet(tmp_path, _segments(tmp_path, manifest)) == 0
    ads = {case["case_id"]: case for case in json.loads((tmp_path / "ads.json").read_text(encoding="utf-8"))["cases"]}
    for item in manifest["items"]:
        case = ads[item["case_id"]]
        assert case["report_no"] == item["report_no"] and case["layout"] == item["layout"]
        for segment in case["segments"]:
            start, end = segment["span"]
            assert case["ad_text"][start:end] == segment["text"]
    sheet = (tmp_path / "labeling.md").read_text(encoding="utf-8")
    assert "`none`" in sheet and "어느 원료가 주어인지와 관계없이" in sheet and EYE in sheet
    for hidden in ("carryover", "unsupported", "honest", "modifier", "exaggerated", "headerless", "stratum"):
        assert hidden not in sheet
    with (tmp_path / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == sum(len(item["segments"]) for item in manifest["items"])
    assert rows[0] == {"case_id": "C3-001", "seg_no": "1", "label": "", "labeler": "", "note": ""}


def test_sheet_rejects_missing_or_multiline_sentences(tmp_path: Path) -> None:
    manifest = _sample(tmp_path)
    assert _sheet(tmp_path, _segments(tmp_path, manifest, broken="newline")) == 3
    assert _sheet(tmp_path, _segments(tmp_path, manifest, broken="missing")) == 3


def _labels(tmp_path: Path, manifest: dict, labeler: str, flipped: str) -> Path:
    path = tmp_path / f"labels-{labeler}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "seg_no", "label", "labeler", "note"])
        writer.writeheader()
        for item in manifest["items"]:
            for segment in item["segments"]:
                label = "none" if segment["role"] == "context" else "mismatch"
                if (item["case_id"], segment["seg_no"]) == ("C3-002", 1):
                    label = flipped
                writer.writerow({
                    "case_id": item["case_id"], "seg_no": segment["seg_no"], "label": label,
                    "labeler": labeler, "note": "",
                })
    return path


def test_cases_merge_labels_per_sentence(tmp_path: Path) -> None:
    manifest = _sample(tmp_path)
    assert _sheet(tmp_path, _segments(tmp_path, manifest)) == 0
    labels = [_labels(tmp_path, manifest, "a", "confirmed"), _labels(tmp_path, manifest, "b", "unverifiable")]
    output, strict = tmp_path / "cases.json", tmp_path / "cases-strict.json"
    arguments = [
        "cases", "--manifest", str(tmp_path / "manifest.json"), "--ads", str(tmp_path / "ads.json"),
        "--output", str(output), "--strict-output", str(strict),
        "--disagreements", str(tmp_path / "disagreements.json"),
    ]
    assert build_ad_eval.main([*arguments, "--labels", str(labels[0]), "--labels", str(labels[1])]) == 0

    cases = {case["case_id"]: case for case in json.loads(output.read_text(encoding="utf-8"))["cases"]}
    first = manifest["items"][0]
    assert cases["C3-001"]["scenario"] == first["scenario"]
    assert [segment["expected"] for segment in cases["C3-001"]["segments"]] == [
        "none" if segment["role"] == "context" else "mismatch" for segment in first["segments"]
    ]
    assert cases["C3-002"]["segments"][0]["expected"] is None
    disagreements = json.loads((tmp_path / "disagreements.json").read_text(encoding="utf-8"))
    assert disagreements == [{"case_id": "C3-002", "seg_no": 1, "labels": {"a": "confirmed", "b": "unverifiable"}}]
    strict_cases = {case["case_id"]: case for case in json.loads(strict.read_text(encoding="utf-8"))["cases"]}
    assert strict_cases["C3-002"]["segments"][0]["expected"] == "unverifiable"

    bad = tmp_path / "bad.csv"
    bad.write_text("case_id,seg_no,label,labeler,note\nC3-001,1,maybe,a,\n", encoding="utf-8")
    assert build_ad_eval.main([*arguments, "--labels", str(bad), "--labels", str(labels[1])]) == 3


OMEGA_HEADER = "[EPA 및 DHA 함유 유지] 혈중 중성지질 개선·혈행 개선에 도움을 줄 수 있음"
NOTICE = "본 제품은 질병의 예방 및 치료를 위한 의약품이 아닙니다"


def _score(tmp_path: Path, cases: list[dict], *extra: str) -> tuple[int, dict]:
    export = tmp_path / "export.jsonl"
    export.write_text(json.dumps({
        "report_no": "R1", "name": "오메가", "company": "가", "primary_function": OMEGA_HEADER,
        "raw_materials": "EPA 및 DHA 함유 유지", "intake_method": "1일 1회",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"dataset_id": "t", "cases": cases}, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "score.json"
    code = score_ad_eval.main([
        "--cases", str(path), "--source-export", str(export), "--source-retrieved-at", RETRIEVED_AT,
        "--output", str(output), *extra,
    ])
    return code, json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}


def _case(case_id: str, layout: str, texts: list[str], expected: list[str | None]) -> dict:
    ad_text, spans = build_ad_eval.compose(layout, texts, wrap=None)
    return {
        "case_id": case_id, "report_no": "R1", "scenario": "s", "layout": layout, "ad_text": ad_text,
        "segments": [
            {"seg_no": number, "span": list(span), "text": ad_text[span[0]:span[1]], "expected": label}
            for number, (span, label) in enumerate(zip(spans, expected, strict=True), start=1)
        ],
    }


def test_score_matches_claims_to_sentences(tmp_path: Path) -> None:
    claim = "오메가3는 혈행 개선에 도움을 줄 수 있습니다."
    code, summary = _score(tmp_path, [
        _case("A", "inline", [claim, NOTICE + "."], ["confirmed", "none"]),
        _case("B", "lines_no_period", [claim, NOTICE + "."], ["confirmed", "none"]),
        _case("C", "lines_no_period", [claim, "하루 한 번 드세요."], ["confirmed", "none"]),
        _case("D", "inline", [claim, "혈행이 확실히 좋아집니다."], ["confirmed", None]),
    ])
    assert code == 0
    assert summary["engine"] == {"extraction": CLAIM_EXTRACTION_VERSION, "verdict": CLAIM_VERDICT_VERSION}
    actual = {row["case_id"]: [segment["actual"] for segment in row["segments"]] for row in summary["results"]}
    # Lines without periods join the claim and the usage line into one sentence the rules do not read;
    # a neighbour the rules do not fully read withholds the confirmation even without a label.
    assert actual == {
        "A": ["confirmed", "none"], "B": ["confirmed", "none"],
        "C": ["unverifiable", "unverifiable"], "D": ["unverifiable", "mismatch"],
    }
    assert summary["confirmed_recall"] == {"count": 2, "of": 4}
    assert summary["false_clearance_count"] == 0
    assert summary["labeled_segment_count"] == 7
    assert summary["ads"]["expected_all_confirmed"] == 3 and summary["ads"]["engine_all_confirmed"] == 2


def test_false_clearance_counts_sentences_labeled_as_no_claim(tmp_path: Path) -> None:
    claim = "혈행 개선에 도움을 줄 수 있어요."
    cases = [_case("A", "inline", [claim, NOTICE + "."], ["mismatch", "none"]),
             _case("B", "inline", [NOTICE + ".", claim], ["none", "none"])]
    code, summary = _score(tmp_path, cases)
    assert code == 0
    assert summary["false_clearance_count"] == 2
    assert summary["false_clearance_claims"] == {"count": 1, "of": 1}
    assert summary["false_clearance_none"] == {"count": 1, "of": 3}
    assert summary["ads"]["false_cleared"] == 2
    code, _ = _score(tmp_path, cases, "--require-zero-false-clearance")
    assert code == 1

    broken = _case("X", "inline", [claim], ["confirmed"])
    broken["segments"][0]["span"] = [0, 3]
    code, _ = _score(tmp_path, [broken])
    assert code == 3


def test_score_reports_how_each_context_sentence_was_read(tmp_path: Path) -> None:
    claim = "오메가3는 혈행 개선에 도움을 줄 수 있습니다."
    cases = [
        _case("A", "inline", [claim, NOTICE + "."], ["confirmed", "none"]),
        _case("B", "inline", [claim, "하루 한 번 드세요.", "본 제품은 의약품이 아닙니다 ※."], ["confirmed", "none", "none"]),
        _case("C", "lines_no_period", [claim, "질병의 예방 및 치료에 쓰는 의약품이 아닙니다."], ["confirmed", "none"]),
    ]
    roles = {"A": ["claim", "notice"], "B": ["claim", "usage", "notice"], "C": ["claim", "notice"]}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"items": [
        {"case_id": case_id, "segments": [
            {"seg_no": number, "role": "claim"} if kind == "claim" else {"seg_no": number, "role": "context", "kind": kind}
            for number, kind in enumerate(kinds, start=1)
        ]}
        for case_id, kinds in roles.items()
    ]}, ensure_ascii=False), encoding="utf-8")

    code, summary = _score(tmp_path, cases, "--manifest", str(manifest))

    assert code == 0
    readings = {row["case_id"]: [segment["reading"] for segment in row["segments"]] for row in summary["results"]}
    # A sentence is read as a claim, left unread (it withholds its neighbours' confirmation) or set aside as
    # the notice; the notice joined to a claim by lines without periods is read as part of that claim.
    assert readings == {"A": ["claim", "notice"], "B": ["claim", "unread", "unread"], "C": ["claim", "claim"]}
    assert summary["by_context_kind"]["notice"] == {
        "count": 3, "reading": {"claim": 1, "notice": 1, "unread": 1}, "actual": {"mismatch": 1, "none": 2},
    }
    assert summary["by_context_kind"]["usage"]["reading"] == {"unread": 1}
    # 근거 불일치 on sentences labeled confirmed or none: the joined claim and notice of C.
    assert summary["wrong_mismatch"] == {"count": 2, "of": 7}

    _, without = _score(tmp_path, cases)
    assert "by_context_kind" not in without
