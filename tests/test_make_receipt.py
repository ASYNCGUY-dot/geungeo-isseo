import json
from pathlib import Path

import pytest

from scripts import make_receipt

RETRIEVED_AT = "2026-08-27T12:42:29.050550+00:00"
GENERATED_AT = "2026-09-27T03:00:00+00:00"


def _write_export(path: Path) -> Path:
    rows = [
        {
            "report_no": "200400000000010",
            "name": "눈건강 루테인",
            "company": "가나 업체",
            "primary_function": "[루테인] 노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음",
            "raw_materials": "마리골드꽃추출물(고시형)",
            "intake_method": "1일 1회",
        },
        {
            "report_no": "200400000000011",
            "name": "장건강 유산균",
            "company": "다라 업체",
            "primary_function": "① 유산균 증식 및 유해균 억제･배변활동 원활･장 건강에 도움을 줄 수 있음",
            "raw_materials": "프로바이오틱스(고시형)",
            "intake_method": "1일 1회",
        },
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    return path


def _base_args(tmp_path: Path) -> list[str]:
    ad = tmp_path / "ad.txt"
    ad.write_text("눈 건강에 도움을 줄 수 있어요.\n시력이 확실하게 좋아집니다!", encoding="utf-8")
    return [
        "--source-export",
        str(_write_export(tmp_path / "export.jsonl")),
        "--source-retrieved-at",
        RETRIEVED_AT,
        "--ad-text-file",
        str(ad),
        "--generated-at",
        GENERATED_AT,
    ]


def test_confirmed_report_no_writes_json_and_markdown(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "receipt"
    code = make_receipt.main(
        _base_args(tmp_path)
        + ["--report-no", "200400000000010", "--confirm-claims", "all", "--output-dir", str(out)]
    )

    assert code == 0
    payload = json.loads((out / "receipt.json").read_text(encoding="utf-8"))
    assert payload["product"]["report_no"] == "200400000000010"
    assert [claim["verdict"] for claim in payload["claims"]] == ["confirmed", "unverifiable"]
    assert payload["claims"][1]["reason_code"] == "CLAIM_OUTSIDE_RULE_SCOPE"
    assert "# 근거영수증" in (out / "receipt.md").read_text(encoding="utf-8")
    assert "확인됨 1" in capsys.readouterr().out


def test_query_only_lists_candidates_and_does_not_decide(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "receipt"
    code = make_receipt.main(_base_args(tmp_path) + ["--query", "루테인", "--output-dir", str(out)])

    assert code == 2
    assert "200400000000010" in capsys.readouterr().out
    assert not out.exists()


def test_unconfirmed_claims_stay_unverifiable(tmp_path: Path) -> None:
    out = tmp_path / "receipt"
    code = make_receipt.main(
        _base_args(tmp_path) + ["--report-no", "200400000000010", "--output-dir", str(out)]
    )

    assert code == 0
    payload = json.loads((out / "receipt.json").read_text(encoding="utf-8"))
    assert {claim["reason_code"] for claim in payload["claims"]} == {"CLAIM_UNCONFIRMED"}


def test_unknown_report_no_and_existing_output_are_errors(tmp_path: Path) -> None:
    out = tmp_path / "receipt"
    assert make_receipt.main(
        _base_args(tmp_path) + ["--report-no", "999", "--output-dir", str(out)]
    ) == 3
    out.mkdir()
    (out / "receipt.json").write_text("{}", encoding="utf-8")
    assert make_receipt.main(
        _base_args(tmp_path) + ["--report-no", "200400000000010", "--output-dir", str(out)]
    ) == 3
    assert (out / "receipt.json").read_text(encoding="utf-8") == "{}"


def test_naive_source_time_is_rejected(tmp_path: Path) -> None:
    args = _base_args(tmp_path)
    args[args.index(RETRIEVED_AT)] = "2026-08-27T12:42:29"
    assert make_receipt.main(args + ["--report-no", "200400000000010", "--output-dir", str(tmp_path / "o")]) == 3
