import json
from datetime import datetime
from pathlib import Path

import pytest

from claimledger.snapshot import SnapshotError, load_c003_snapshot, parse_aware_datetime


def _export(path: Path) -> Path:
    row = {
        "report_no": "R1",
        "name": "루테인",
        "company": "가",
        "primary_function": "[루테인] 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음",
        "raw_materials": "마리골드꽃추출물",
        "intake_method": "1일 1회",
    }
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n\n", encoding="utf-8")
    return path


def test_snapshot_rows_carry_source_and_given_time(tmp_path: Path) -> None:
    retrieved_at = parse_aware_datetime("2026-08-27T12:42:29+00:00", "t")

    products = load_c003_snapshot(_export(tmp_path / "e.jsonl"), retrieved_at)

    assert [(p.report_no, p.source_id, p.retrieved_at) for p in products] == [("R1", "C003", retrieved_at)]


def test_snapshot_refuses_naive_retrieval_time(tmp_path: Path) -> None:
    with pytest.raises(SnapshotError, match="timezone"):
        load_c003_snapshot(_export(tmp_path / "e.jsonl"), datetime(2026, 8, 27, 12, 42, 29))  # noqa: DTZ001


@pytest.mark.parametrize(("value", "message"), [("2026-08-27T12:42:29", "timezone"), ("어제", "ISO")])
def test_parse_aware_datetime_rejects_naive_or_invalid(value: str, message: str) -> None:
    with pytest.raises(SnapshotError, match=message):
        parse_aware_datetime(value, "--source-retrieved-at")
