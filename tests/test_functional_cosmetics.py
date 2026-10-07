"""Functional cosmetics sources on data.go.kr (synthetic payloads, no network)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from claimledger.errors import DataSourceError
from claimledger.sources.functional_cosmetics import (
    REPORTED,
    REVIEWED,
    FunctionalCosmeticsClient,
    parse_cosmetics_payload,
)
from scripts import audit_cosmetics

NOW = datetime(2026, 10, 7, tzinfo=UTC)
SECRET = "synthetic-service-key-000"


def _reported(seq: str, name: str, effect: str = "피부의 미백에 도움을 준다", **extra: str) -> dict:
    return {
        "COSMETIC_REPORT_SEQ": f"R{seq}", "ITEM_SEQ": seq, "ITEM_NAME": name, "ENTP_NAME": "테스트 화장품",
        "MANUF_NAME": "테스트 제조", "REPORT_DATE": "20250102", "CANCEL_APPROVAL_YN": "N",
        "EE_CODE": "1", "EE_NAME": "미백", "EE_DOC_DATA": effect, "EFFECT_YN1": "Y", "EFFECT_YN2": "N",
        "EFFECT_YN3": "N", "SPF": "", "PA": "", "BIZRNO": "0000000000", "MANUF_PLACE": "테스트 주소", **extra,
    }


def _reviewed(seq: str, name: str, effect: str = "피부의 주름개선에 도움을 준다") -> dict:
    return {
        "ITEM_SEQ": seq, "ITEM_NAME": name, "ENTP_NAME": "테스트 화장품", "ITEM_NO": f"제{seq}호",
        "ITEM_PERMIT_DATE": "20240305", "COSMETIC_NOTICE_NAME": "고시품목", "EE_DOC_DATA": effect,
        "BIZRNO": "0000000000",
    }


def _payload(items: object, total: int | None = None, code: str = "00") -> dict:
    count = len(items) if isinstance(items, list) else 1
    return {
        "header": {"resultCode": code, "resultMsg": "NORMAL SERVICE."},
        "body": {"pageNo": 1, "numOfRows": 100, "totalCount": count if total is None else total, "items": items},
    }


def test_reported_rows_keep_identity_and_official_effect_only() -> None:
    page = parse_cosmetics_payload(_payload([_reported("101", "미백 크림")]), REPORTED, NOW)

    assert page.total_count == 1
    item = page.items[0]
    assert (item.item_seq, item.item_name, item.company) == ("101", "미백 크림", "테스트 화장품")
    assert item.effect_text == "피부의 미백에 도움을 준다"
    assert (item.effect_name, item.whitening, item.wrinkle, item.sunscreen) == ("미백", True, False, False)
    assert item.registered_on == "20250102" and item.withdrawn is False
    assert item.source_id == "data.go.kr:15095680" and item.retrieved_at == NOW
    dumped = item.model_dump(mode="json")
    assert "BIZRNO" not in dumped and "테스트 주소" not in json.dumps(dumped, ensure_ascii=False)


def test_reviewed_rows_use_the_permit_fields() -> None:
    item = parse_cosmetics_payload(_payload([_reviewed("201", "주름 세럼")]), REVIEWED, NOW).items[0]

    assert (item.item_seq, item.effect_text) == ("201", "피부의 주름개선에 도움을 준다")
    assert item.registered_on == "20240305" and item.notice_class == "고시품목"
    assert item.whitening is None and item.withdrawn is None
    assert item.source_id == "data.go.kr:15056939"


@pytest.mark.parametrize("items", [
    [{"item": _reported("1", "가")}, {"item": _reported("2", "나")}],
    {"item": [_reported("1", "가"), _reported("2", "나")]},
])
def test_documented_item_wrappers_are_accepted(items: object) -> None:
    page = parse_cosmetics_payload(_payload(items, total=2), REPORTED, NOW)
    assert [item.item_seq for item in page.items] == ["1", "2"]


def test_single_wrapped_item_and_the_response_envelope() -> None:
    wrapped = {"response": _payload({"item": _reported("7", "하나")}, total=1)}
    assert parse_cosmetics_payload(wrapped, REPORTED, NOW).items[0].item_seq == "7"
    assert parse_cosmetics_payload(_payload("", total=0), REPORTED, NOW).items == ()


@pytest.mark.parametrize("payload", [
    _payload([_reported("1", "가")], code="30"),
    {"header": {"resultCode": "00"}},
    _payload([_reported("", "이름만")]),
    _payload([_reported("1", "")]),
    _payload([_reported("1", "가")], total=-1),
    _payload("unexpected text", total=1),
    _payload([["not", "an", "object"]]),
])
def test_errors_and_unknown_shapes_fail_closed(payload: dict) -> None:
    with pytest.raises(DataSourceError):
        parse_cosmetics_payload(payload, REPORTED, NOW)


def _client(handler) -> FunctionalCosmeticsClient:
    return FunctionalCosmeticsClient(REPORTED, SECRET, httpx.Client(transport=httpx.MockTransport(handler)))


def test_client_sends_the_documented_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_payload([_reported("1", "가")]))

    page = _client(handler).fetch_page(3, 50)

    assert page.items[0].item_seq == "1"
    url = seen[0].url
    assert url.host == "apis.data.go.kr"
    assert url.path == "/1471000/FtnltCosmRptPrdlstInfoService01/getRptPrdlstInq01"
    assert dict(url.params) == {"serviceKey": SECRET, "pageNo": "3", "numOfRows": "50", "type": "json"}


@pytest.mark.parametrize("response", [
    httpx.Response(500, text="boom"),
    httpx.Response(200, text=(
        "<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
        "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>"
        "<returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"
    )),
    httpx.Response(200, json=["not", "an", "object"]),
])
def test_client_errors_never_contain_the_key(response: httpx.Response) -> None:
    with pytest.raises(DataSourceError) as error:
        _client(lambda request: response).fetch_page(1, 10)
    assert SECRET not in str(error.value) and error.value.__cause__ is None


def test_gateway_error_text_names_the_reason() -> None:
    xml = "<OpenAPI_ServiceResponse><cmmMsgHeader><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg></cmmMsgHeader></OpenAPI_ServiceResponse>"
    with pytest.raises(DataSourceError, match="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"):
        _client(lambda request: httpx.Response(200, text=xml)).fetch_page(1, 10)
    with pytest.raises(DataSourceError):
        FunctionalCosmeticsClient(REPORTED, "  ")


def test_an_encoded_key_is_not_encoded_twice() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_payload([_reported("1", "가")]))

    FunctionalCosmeticsClient(
        REPORTED, "ab%2Bcd%3D%3D", httpx.Client(transport=httpx.MockTransport(handler))
    ).fetch_page(1, 1)
    assert dict(seen[0].url.params)["serviceKey"] == "ab+cd=="


class _FakeClient:
    def __init__(self, rows: list[dict], total: int | None = None) -> None:
        self.rows, self.total, self.calls = rows, len(rows) if total is None else total, []

    def fetch_page(self, page_no: int, num_of_rows: int):
        self.calls.append((page_no, num_of_rows))
        chunk = self.rows[(page_no - 1) * num_of_rows : page_no * num_of_rows]
        return parse_cosmetics_payload(_payload(chunk, total=self.total), REPORTED, NOW)


def _audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, client: _FakeClient, *extra: str) -> int:
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", SECRET)
    monkeypatch.setattr(audit_cosmetics, "_client", lambda source, key: client)
    return audit_cosmetics.main(["--service", "reported", "--output-dir", str(tmp_path), "--page-size", "2", *extra])


def test_audit_writes_the_export_and_measures_the_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        _reported("1", "미백 크림"),
        _reported("2", "미백 크림", effect=""),
        _reported("3", "선크림", EE_NAME="자외선차단", EFFECT_YN1="N", EFFECT_YN3="Y", SPF="50", PA="PA+++"),
        _reported("4", "철회 제품", CANCEL_APPROVAL_YN="Y"),
        _reported("4", "철회 제품", CANCEL_APPROVAL_YN="Y"),
    ]
    client = _FakeClient(rows)

    assert _audit(tmp_path, monkeypatch, client) == 0

    assert client.calls == [(1, 2), (2, 2), (3, 2)]
    export = (tmp_path / "functional-cosmetics-reported.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(export) == 5 and SECRET not in "".join(export)
    report = json.loads((tmp_path / "functional-cosmetics-reported.audit.json").read_text(encoding="utf-8"))
    assert report["total_count"] == 5 and report["row_count"] == 5 and len(report["sha256"]) == 64
    assert report["duplicate_item_seq_rows"] == 1 and report["withdrawn_rows"] == 2
    assert report["missing"]["effect_text"] == 1 and report["missing"]["item_name"] == 0
    assert report["effect_names"] == {"미백": 4, "자외선차단": 1}
    assert report["flags"] == {"whitening": 4, "wrinkle": 0, "sunscreen": 1}
    # Product names shared by several item numbers cannot identify a product on their own.
    assert report["names_shared_by_several_items"] == 1
    assert SECRET not in json.dumps(report)


def test_audit_fails_closed_on_a_short_download_or_missing_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _audit(tmp_path, monkeypatch, _FakeClient([_reported("1", "가")], total=3)) == 3
    assert not (tmp_path / "functional-cosmetics-reported.jsonl").exists()
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY")
    assert audit_cosmetics.main(["--service", "reported", "--output-dir", str(tmp_path)]) == 3


def test_a_probe_reads_only_the_requested_pages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeClient([_reported(str(n), f"제품 {n}") for n in range(1, 8)])

    assert _audit(tmp_path, monkeypatch, client, "--max-pages", "1") == 0

    report = json.loads((tmp_path / "functional-cosmetics-reported.audit.json").read_text(encoding="utf-8"))
    assert client.calls == [(1, 2)]
    assert report["total_count"] == 7 and report["row_count"] == 2 and report["complete"] is False
