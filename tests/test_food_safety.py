import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from claimledger.errors import DataSourceError
from claimledger.sources.food_safety import parse_c003_payload

FIXTURE = Path(__file__).parent / "fixtures" / "c003_success.json"
NOW = datetime(2026, 8, 22, tzinfo=UTC)


def success_payload_with_first_row(**updates: str) -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    copied = deepcopy(payload)
    copied["C003"]["row"][0].update(updates)
    return copied


def test_parse_c003_success_fixture() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    page = parse_c003_payload(payload, retrieved_at=NOW)
    assert page.total_count == 2
    assert [product.report_no for product in page.products] == ["TEST-0001", "TEST-0002"]


def test_parse_c003_rejects_unapproved_service() -> None:
    payload = {"C003": {"RESULT": {"CODE": "INFO-110", "MSG": "활용신청 내역이 없습니다."}}}
    with pytest.raises(DataSourceError, match="INFO-110"):
        parse_c003_payload(payload, retrieved_at=NOW)


def test_parse_c003_rejects_missing_report_number() -> None:
    payload = success_payload_with_first_row(PRDLST_REPORT_NO="")
    with pytest.raises(DataSourceError, match="PRDLST_REPORT_NO"):
        parse_c003_payload(payload, retrieved_at=NOW)
