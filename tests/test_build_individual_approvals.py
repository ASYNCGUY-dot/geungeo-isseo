import hashlib
import json
from pathlib import Path

from scripts import build_individual_approvals

ROWS = [
    {"approval_no": "2022-34", "approved_on": "20221101", "company": "가", "ingredient_name": "열처리녹차추출물",
     "function_text": "기억력 개선에 도움을 줄 수 있음"},
    {"approval_no": "2021-24", "approved_on": "20210601", "company": "나", "ingredient_name": "병풀추출분말",
     "function_text": "노화로 인해 감소될 수 있는 황반색소 밀도를 유지하여 눈 건강에 도움을 줄 수 있음 , 간 건강에 도움을 줄 수 있음"},
    {"approval_no": "2010-1", "approved_on": "20100101", "company": "다", "ingredient_name": "체지방원료",
     "function_text": "체지방 감소에 도움을 줄 수 있음"},
    {"approval_no": "", "approved_on": "20240311", "company": "라", "ingredient_name": "번호없는원료",
     "function_text": "혈행 개선에 도움을 줄 수 있음"},
]


def _source(tmp_path: Path, rows=ROWS, sha: str | None = None) -> tuple[Path, Path]:
    source = tmp_path / "i0040.jsonl"
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    source.write_text(text, encoding="utf-8", newline="\n")
    manifest = tmp_path / "i0040.manifest.json"
    manifest.write_text(json.dumps({
        "source_id": "I-0040", "retrieved_at": "2026-11-21T08:27:03+00:00", "total_count": len(rows) + 2,
        "row_count": len(rows), "incomplete_count": 2,
        "sha256": sha or hashlib.sha256(text.encode("utf-8")).hexdigest().upper(),
    }), encoding="utf-8")
    return source, manifest


def test_table_keeps_the_carriers_of_target_functions_with_the_source(tmp_path: Path) -> None:
    source, manifest = _source(tmp_path)
    output = tmp_path / "table.json"

    assert build_individual_approvals.main(["--source", str(source), "--manifest", str(manifest), "--output", str(output)]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["table_version"] == "individual-approvals-v1"
    assert payload["source"]["source_id"] == "I-0040" and payload["source"]["incomplete_count"] == 2
    assert payload["source"]["sha256"] == json.loads(manifest.read_text(encoding="utf-8"))["sha256"]
    items = {item["ingredient_name"]: item for item in payload["items"]}
    assert set(items) == {"열처리녹차추출물", "병풀추출분말", "번호없는원료"}
    assert items["열처리녹차추출물"]["effects"] == ["memory"]
    assert "macular_pigment_eye_health" in items["병풀추출분말"]["effects"]
    assert set(items["열처리녹차추출물"]) == {"approval_no", "ingredient_name", "function_text", "effects"}
    assert payload["carrier_count"] == 3 and payload["row_count"] == 4


def test_table_refuses_a_source_that_does_not_match_its_manifest(tmp_path: Path) -> None:
    source, manifest = _source(tmp_path, sha="0" * 64)
    assert build_individual_approvals.main([
        "--source", str(source), "--manifest", str(manifest), "--output", str(tmp_path / "t.json"),
    ]) == 3
    assert not (tmp_path / "t.json").exists()
