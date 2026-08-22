import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from claimledger.domain import ProductCandidate
from claimledger.errors import DataSourceError
from claimledger.sources.food_safety import C003Client, audit_products, parse_c003_payload

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


def test_client_builds_expected_c003_path() -> None:
    requested_paths: list[str] = []
    success_payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(200, json=success_payload)

    client = C003Client(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    page = client.fetch_page(1, 100)
    assert requested_paths == ["/api/test-key/C003/json/1/100"]
    assert page.total_count == 2


def test_client_converts_timeout_to_data_source_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = C003Client(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(DataSourceError, match="timeout"):
        client.fetch_page(1, 100)


def test_client_rejects_blank_key_before_request() -> None:
    with pytest.raises(DataSourceError, match="API key"):
        C003Client(api_key=" ")


def test_client_rejects_non_success_http_status() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503, request=request))
    client = C003Client(api_key="test-key", http_client=httpx.Client(transport=transport))
    with pytest.raises(DataSourceError, match="HTTP 503"):
        client.fetch_page(1, 100)


def test_audit_products_reports_missing_fields_duplicates_and_candidates() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    products = list(parse_c003_payload(payload, retrieved_at=NOW).products)
    products.append(products[0].model_copy(update={"primary_function": ""}))
    products.append(
        ProductCandidate(
            report_no="TEST-0003",
            name="프로바이오틱스 테스트 제품",
            company="테스트 제조사 C",
            primary_function="",
            raw_materials="유산균 probiotics",
            intake_method="",
            source_id="C003",
            retrieved_at=NOW,
        )
    )

    audit = audit_products(products)

    assert audit.record_count == 4
    assert audit.unique_report_count == 3
    assert audit.duplicate_report_count == 1
    assert audit.missing_primary_function_count == 2
    assert audit.missing_intake_method_count == 1
    assert audit.candidate_counts == {
        "lutein_zeaxanthin": 2,
        "omega3": 1,
        "probiotics": 1,
    }
