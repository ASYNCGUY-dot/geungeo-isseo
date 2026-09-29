import hashlib
import json
from pathlib import Path

from scripts import build_header_vocabulary

RETRIEVED_AT = "2026-08-27T12:42:29.050550+00:00"


def _export(path: Path) -> Path:
    rows = [
        ("가", "[비타민E] 항산화 작용을 하여 유해산소로부터 세포를 보호하는데 필요\n[검토 중] 기억력 개선"),
        ("나", "- 비타민 E: 항산화 작용을 하여 유해산소로부터 세포를 보호하는데 필요"),
        ("다", "[아연] 정상적인 면역기능에 필요"),
        ("가", "[아연(제2020-1호)] 정상적인 면역기능에 필요"),
        ("라", ""),
    ]
    path.write_text(
        "\n".join(
            json.dumps({"report_no": str(i), "company": company, "primary_function": text}, ensure_ascii=False)
            for i, (company, text) in enumerate(rows)
        ) + "\n",
        encoding="utf-8",
    )
    return path


def _exclusions(path: Path, names: dict[str, str]) -> Path:
    payload = {"reviewer": "test", "reviewed_at": "2026-09-29T00:00:00+09:00", "exclusions": names}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _run(tmp_path: Path, exclusions: dict[str, str], *extra: str) -> tuple[int, dict]:
    output = tmp_path / "vocabulary.json"
    code = build_header_vocabulary.main([
        "--source-export", str(_export(tmp_path / "export.jsonl")),
        "--source-retrieved-at", RETRIEVED_AT,
        "--exclusions", str(_exclusions(tmp_path / "exclusions.json", exclusions)),
        "--output", str(output),
        *extra,
    ])
    return code, json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}


def test_names_need_two_companies_and_reviewed_exclusions_are_removed(tmp_path: Path) -> None:
    code, payload = _run(tmp_path, {"아연": "test exclusion"})

    assert code == 0
    assert payload["names"] == ["비타민e"]
    assert payload["excluded"] == {"아연": "test exclusion"}
    assert payload["candidate_count"] == 2
    assert payload["min_companies"] == 2
    assert payload["review"]["reviewer"] == "test"
    source = payload["source"]
    assert source["source_id"] == "C003"
    assert source["retrieved_at"] == RETRIEVED_AT
    expected = hashlib.sha256((tmp_path / "export.jsonl").read_bytes()).hexdigest().upper()
    assert source["sha256"] == expected


def test_output_is_deterministic(tmp_path: Path) -> None:
    _run(tmp_path, {})
    first = (tmp_path / "vocabulary.json").read_bytes()
    _run(tmp_path, {})
    assert (tmp_path / "vocabulary.json").read_bytes() == first


def test_stale_exclusion_or_naive_time_is_an_input_error(tmp_path: Path) -> None:
    code, payload = _run(tmp_path, {"검토중": "only one company uses it"})
    assert code == 3
    assert payload == {}

    output = tmp_path / "other.json"
    code = build_header_vocabulary.main([
        "--source-export", str(_export(tmp_path / "export.jsonl")),
        "--source-retrieved-at", "2026-08-27T12:42:29",
        "--exclusions", str(_exclusions(tmp_path / "exclusions.json", {})),
        "--output", str(output),
    ])
    assert code == 3
    assert not output.exists()
