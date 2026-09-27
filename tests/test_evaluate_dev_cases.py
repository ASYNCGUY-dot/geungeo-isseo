import json
from pathlib import Path

import pytest

from scripts import evaluate_dev_cases

RETRIEVED_AT = "2026-08-27T12:42:29.050550+00:00"
OMEGA = "[EPA 및 DHA 함유 유지] 혈중 중성지질 개선·혈행 개선에 도움을 줄 수 있음"


def _export(path: Path) -> Path:
    rows = [
        {"report_no": "R1", "name": "오메가", "company": "가", "primary_function": OMEGA,
         "raw_materials": "EPA 및 DHA 함유 유지", "intake_method": "1일 1회"},
        {"report_no": "R2", "name": "무표시", "company": "나", "primary_function": "혈행 개선에 도움을 줄 수 있음",
         "raw_materials": "원재료", "intake_method": "1일 1회"},
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    return path


def _cases(path: Path, cases: list[dict]) -> Path:
    path.write_text(json.dumps({"dataset_id": "t", "cases": cases}, ensure_ascii=False), encoding="utf-8")
    return path


def _run(tmp_path: Path, cases: list[dict], *extra: str) -> tuple[int, dict]:
    output = tmp_path / "summary.json"
    code = evaluate_dev_cases.main(
        [
            "--cases", str(_cases(tmp_path / "cases.json", cases)),
            "--source-export", str(_export(tmp_path / "export.jsonl")),
            "--source-retrieved-at", RETRIEVED_AT,
            "--output", str(output),
            *extra,
        ]
    )
    return code, json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}


def test_metrics_for_correct_predictions(tmp_path: Path) -> None:
    code, summary = _run(
        tmp_path,
        [
            {"case_id": "A", "report_no": "R1", "ad_text": "혈행 개선에 도움을 줄 수 있어요.", "expected_verdict": "confirmed"},
            {"case_id": "B", "report_no": "R1", "ad_text": "혈행이 확실히 좋아집니다.", "expected_verdict": "mismatch"},
            {"case_id": "C", "report_no": "R2", "ad_text": "혈행 개선에 도움을 줄 수 있어요.", "expected_verdict": "unverifiable"},
            {"case_id": "D", "report_no": None, "ad_text": "혈행 개선에 도움을 줄 수 있어요.", "expected_verdict": "unverifiable"},
            {"case_id": "E", "report_no": "R1", "ad_text": "의약품이 아닙니다.", "expected_verdict": None},
        ],
    )

    assert code == 0
    assert summary["judged_case_count"] == 4
    assert summary["exact_agreement_count"] == 4
    assert summary["false_clearance_count"] == 0
    assert summary["false_clearance_rate"] == 0.0
    assert summary["confirmed_recall"] == 1.0
    assert summary["coverage"] == 0.5
    assert summary["claim_extraction_error_count"] == 0
    assert [row["outcome"] for row in summary["results"]] == ["agree"] * 5


def test_false_clearance_is_counted_and_can_fail_the_run(tmp_path: Path) -> None:
    cases = [{"case_id": "A", "report_no": "R1", "ad_text": "혈행 개선에 도움을 줄 수 있어요.", "expected_verdict": "mismatch"}]

    code, summary = _run(tmp_path, cases)
    assert code == 0
    assert summary["false_clearance_count"] == 1
    assert summary["results"][0]["outcome"] == "disagree"

    code, _ = _run(tmp_path, cases, "--require-zero-false-clearance")
    assert code == 1


def test_missing_or_extra_claims_are_extraction_errors(tmp_path: Path) -> None:
    code, summary = _run(
        tmp_path,
        [
            {"case_id": "A", "report_no": "R1", "ad_text": "하루 한 알", "expected_verdict": "confirmed"},
            {"case_id": "B", "report_no": "R1", "ad_text": "혈행 개선에 도움.", "expected_verdict": None},
        ],
    )

    assert code == 0
    assert summary["claim_extraction_error_count"] == 2
    assert summary["results"][0]["actual_verdict"] == "unverifiable"
    assert summary["results"][1]["outcome"] == "unexpected_claim"


def test_unknown_report_number_is_an_input_error(tmp_path: Path) -> None:
    code, _ = _run(tmp_path, [{"case_id": "A", "report_no": "NOPE", "ad_text": "혈행 개선에 도움", "expected_verdict": "confirmed"}])

    assert code == 3


def test_duplicate_case_ids_are_rejected(tmp_path: Path) -> None:
    case = {"case_id": "A", "report_no": "R1", "ad_text": "혈행 개선에 도움", "expected_verdict": "confirmed"}

    code, _ = _run(tmp_path, [case, case])

    assert code == 3


@pytest.mark.parametrize("payload", [{"dataset_id": "t"}, {"cases": [{"case_id": "A"}]}])
def test_malformed_case_file_is_an_input_error(tmp_path: Path, payload: dict) -> None:
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps(payload), encoding="utf-8")

    code = evaluate_dev_cases.main(
        [
            "--cases", str(cases),
            "--source-export", str(_export(tmp_path / "export.jsonl")),
            "--source-retrieved-at", RETRIEVED_AT,
        ]
    )

    assert code == 3


@pytest.mark.parametrize("bad", ["2026-08-27T12:42:29", "not-a-date"])
def test_source_time_must_be_aware(tmp_path: Path, bad: str) -> None:
    code = evaluate_dev_cases.main(
        [
            "--cases", str(_cases(tmp_path / "cases.json", [])),
            "--source-export", str(_export(tmp_path / "export.jsonl")),
            "--source-retrieved-at", bad,
        ]
    )

    assert code == 3
