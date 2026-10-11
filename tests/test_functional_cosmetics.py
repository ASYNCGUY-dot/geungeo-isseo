"""Functional cosmetics sources on data.go.kr (synthetic payloads shaped like the live ones, no network)."""

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
    doc_paragraphs,
    parse_cosmetics_payload,
)
from scripts import audit_cosmetics

NOW = datetime(2026, 10, 7, tzinfo=UTC)
SECRET = "synthetic-service-key-000"
KEY_NAMES = ("DATA_GO_KR_SERVICE_KEY", "DATA_GO_KR_SERVICE_KEY_REPORTED", "DATA_GO_KR_SERVICE_KEY_REVIEWED")


def _doc(*paragraphs: str) -> str:
    body = "".join(
        f'      <PARAGRAPH tagName="p" textIndent="" marginLeft=""><![CDATA[{text}]]></PARAGRAPH>\r\n'
        for text in paragraphs
    )
    return f'<DOC title="효능효과" type="EE">\r\n  <SECTION title="">\r\n    <ARTICLE title="">\r\n{body}    </ARTICLE>\r\n  </SECTION>\r\n</DOC>'


def _reported(seq: str, name: str, effect: str | None = "피부의 미백에 도움을 준다.", **extra: str | None) -> dict:
    # Live rows (2026-10-11): ITEM_SEQ is null, the report number is the identity, the efficacy
    # sentence is EE_NAME, EE_DOC_DATA is usually null and the EFFECT_YN flags do not follow it.
    return {
        "COSMETIC_REPORT_SEQ": seq, "ITEM_SEQ": None, "ITEM_NAME": name, "ENTP_NAME": "테스트 화장품",
        "MANUF_NAME": None, "REPORT_DATE": "20250102", "CANCEL_APPROVAL_YN": "N",
        "EE_CODE": "1" if effect else None, "EE_NAME": effect, "EE_DOC_DATA": None, "EFFECT_YN1": None,
        "EFFECT_YN2": "N", "EFFECT_YN3": "N", "SPF": None, "PA": None, "BIZRNO": "0000000000",
        "MANUF_PLACE": "테스트 주소", **extra,
    }


def _reviewed(seq: str, name: str, doc: str | None = None) -> dict:
    return {
        "ITEM_SEQ": seq, "ITEM_NAME": name, "ENTP_NAME": "테스트 화장품", "ITEM_NO": "5",
        "ITEM_PERMIT_DATE": "20240305", "COSMETIC_NOTICE_NAME": None,
        "EE_DOC_DATA": _doc("피부의 주름개선에 도움을 준다.") if doc is None else doc, "BIZRNO": "0000000000",
    }


def _payload(items: object, total: int | None = None, code: str = "00") -> dict:
    count = len(items) if isinstance(items, list) else 1
    return {
        "header": {"resultCode": code, "resultMsg": "NORMAL SERVICE."},
        "body": {"pageNo": 1, "numOfRows": 100, "totalCount": count if total is None else total, "items": items},
    }


def test_reported_rows_use_the_report_number_and_the_efficacy_sentence() -> None:
    page = parse_cosmetics_payload(_payload([_reported("2026030396", "미백 토너패드")]), REPORTED, NOW)

    assert page.total_count == 1
    item = page.items[0]
    assert (item.record_id, item.item_name, item.company) == ("2026030396", "미백 토너패드", "테스트 화장품")
    assert (item.effect_code, item.effect_name, item.effect_text) == ("1", "피부의 미백에 도움을 준다.", "")
    assert item.statement == "피부의 미백에 도움을 준다."
    assert (item.whitening, item.wrinkle, item.sunscreen) == (None, False, False)
    assert item.registered_on == "20250102" and item.withdrawn is False
    assert item.source_id == "data.go.kr:15095680" and item.retrieved_at == NOW
    dumped = item.model_dump(mode="json")
    assert "BIZRNO" not in dumped and "테스트 주소" not in json.dumps(dumped, ensure_ascii=False)


def test_reviewed_rows_read_the_efficacy_document() -> None:
    doc = _doc("<!--StartFragment -->자외선으로부터 피부를 보호한다.(SPF50+, PA++++) \n<!--EndFragment -->", "피부의 미백에 도움을 준다.")
    item = parse_cosmetics_payload(_payload([_reviewed("202603070", "선로션", doc)]), REVIEWED, NOW).items[0]

    assert item.record_id == "202603070" and item.registered_on == "20240305"
    assert item.effect_text == "자외선으로부터 피부를 보호한다.(SPF50+, PA++++)\n피부의 미백에 도움을 준다."
    assert item.statement == item.effect_text and item.effect_doc == doc and not item.effect_doc_unreadable
    assert item.whitening is None and item.withdrawn is None
    assert item.source_id == "data.go.kr:15056939"


def test_document_paragraphs_are_plain_lines() -> None:
    assert doc_paragraphs(_doc("피부의 미백에&nbsp;도움을 준다.<br/>피부의 주름개선에 도움을 준다.", "  ")) == (
        "피부의 미백에 도움을 준다.", "피부의 주름개선에 도움을 준다.",
    )
    plain = '<DOC><SECTION><ARTICLE><PARAGRAPH tagName="p">모발의 염모(흑색)</PARAGRAPH></ARTICLE></SECTION></DOC>'
    assert doc_paragraphs(plain) == ("모발의 염모(흑색)",)
    assert doc_paragraphs("") == ()


def test_a_title_only_document_is_read_from_its_article_titles() -> None:
    # 393 live documents (2026-10-11) hold the efficacy only in ARTICLE titles, with no paragraph.
    doc = (
        '<DOC title="효능효과" type="EE"><SECTION title="">'
        '<ARTICLE title="1. 피부의 미백에 도움을 준다."></ARTICLE>'
        '<ARTICLE title="2. 자외선으로부터 피부를 보호한다.(SPF 45, PA+++)" />'
        '<ARTICLE title=""></ARTICLE></SECTION></DOC>'
    )
    assert doc_paragraphs(doc) == ("1. 피부의 미백에 도움을 준다.", "2. 자외선으로부터 피부를 보호한다.(SPF 45, PA+++)")
    item = parse_cosmetics_payload(_payload([_reviewed("1", "제목 문서", doc)]), REVIEWED, NOW).items[0]
    assert item.effect_doc_unreadable is False and item.statement.startswith("1. 피부의 미백")
    # A title above paragraphs is a heading, not a statement (one live document: "기준 및 시험방법").
    mixed = '<DOC><SECTION><ARTICLE title="기준 및 시험방법"><PARAGRAPH tagName="p"><![CDATA[피부의 미백에 도움을 준다.]]></PARAGRAPH></ARTICLE></SECTION></DOC>'
    assert doc_paragraphs(mixed) == ("피부의 미백에 도움을 준다.",)


def test_a_document_without_readable_paragraphs_is_flagged_not_guessed() -> None:
    odd = '<DOC title="효능효과" type="EE"><SECTION><TABLE><TR><TD>표로 적은 효능</TD></TR></TABLE></SECTION></DOC>'
    item = parse_cosmetics_payload(_payload([_reviewed("1", "표 문서", odd)]), REVIEWED, NOW).items[0]
    assert item.effect_text == "" and item.effect_doc_unreadable is True and item.statement == ""
    empty = parse_cosmetics_payload(_payload([_reviewed("2", "빈 문서", "")]), REVIEWED, NOW).items[0]
    assert empty.effect_text == "" and empty.effect_doc_unreadable is False


@pytest.mark.parametrize("items", [
    [{"item": _reported("1", "가")}, {"item": _reported("2", "나")}],
    {"item": [_reported("1", "가"), _reported("2", "나")]},
])
def test_documented_item_wrappers_are_accepted(items: object) -> None:
    page = parse_cosmetics_payload(_payload(items, total=2), REPORTED, NOW)
    assert [item.record_id for item in page.items] == ["1", "2"]


def test_single_wrapped_item_and_the_response_envelope() -> None:
    wrapped = {"response": _payload({"item": _reported("7", "하나")}, total=1)}
    assert parse_cosmetics_payload(wrapped, REPORTED, NOW).items[0].record_id == "7"
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


def test_the_identity_field_is_not_borrowed_from_the_other_list() -> None:
    # A reviewed row without ITEM_SEQ is rejected even if it carried a report number.
    row = {**_reviewed("", "번호 없음"), "COSMETIC_REPORT_SEQ": "2026000001"}
    with pytest.raises(DataSourceError):
        parse_cosmetics_payload(_payload([row]), REVIEWED, NOW)


def _client(handler) -> FunctionalCosmeticsClient:
    return FunctionalCosmeticsClient(REPORTED, SECRET, httpx.Client(transport=httpx.MockTransport(handler)))


def test_client_sends_the_documented_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_payload([_reported("1", "가")]))

    page = _client(handler).fetch_page(3, 50)

    assert page.items[0].record_id == "1"
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


def test_the_live_gateway_error_format_names_the_reason() -> None:
    # Observed on 2026-10-09 with a dummy key: HTTP 403 and a JSON body, not XML.
    body = {"OpenAPI_ServiceResponse": {"cmmMsgHeader": {
        "errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR", "returnAuthMsg": "등록되지 않은 서비스키",
        "returnReasonCode": "30",
    }}}
    for status in (403, 200):
        with pytest.raises(DataSourceError) as error:
            _client(lambda request, status=status: httpx.Response(status, json=body)).fetch_page(1, 1)
        assert "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in str(error.value) and SECRET not in str(error.value)
    with pytest.raises(DataSourceError, match="HTTP 403"):
        _client(lambda request: httpx.Response(403, json=body)).fetch_page(1, 1)
    # Free text from the gateway is not echoed: only an upper-case reason code is.
    odd = {"OpenAPI_ServiceResponse": {"cmmMsgHeader": {"errMsg": f"key {SECRET} rejected"}}}
    with pytest.raises(DataSourceError) as error:
        _client(lambda request: httpx.Response(403, json=odd)).fetch_page(1, 1)
    assert SECRET not in str(error.value)


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
    def __init__(self, rows: list[dict], total: int | None = None, source=REPORTED) -> None:
        self.rows, self.total, self.source, self.calls = rows, len(rows) if total is None else total, source, []

    def fetch_page(self, page_no: int, num_of_rows: int):
        self.calls.append((page_no, num_of_rows))
        chunk = self.rows[(page_no - 1) * num_of_rows : page_no * num_of_rows]
        return parse_cosmetics_payload(_payload(chunk, total=self.total), self.source, NOW)


def _audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, client: _FakeClient, *extra: str) -> int:
    for name in KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", SECRET)
    monkeypatch.setattr(audit_cosmetics, "_client", lambda source, key: client)
    service = client.source.key
    return audit_cosmetics.main(["--service", service, "--output-dir", str(tmp_path), "--page-size", "2", *extra])


def test_audit_writes_the_export_and_measures_the_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    both = "피부의 미백에 도움을 준다. 피부의 주름개선에 도움을 준다."
    rows = [
        _reported("1", "미백 크림"),
        _reported("2", "미백 크림", effect=None),
        _reported("3", "선크림", effect="자외선으로부터 피부를 보호한다.", EE_CODE="5", SPF="50+", PA="++++"),
        _reported("4", "철회 제품", effect=both, EE_CODE="3", CANCEL_APPROVAL_YN="Y"),
        _reported("4", "철회 제품", effect=both, EE_CODE="3", CANCEL_APPROVAL_YN="Y"),
        _reported("5", "문서 제품", effect=None, EE_DOC_DATA=_doc("여드름성 피부를 완화하는 데 도움을 준다.")),
    ]
    client = _FakeClient(rows)

    assert _audit(tmp_path, monkeypatch, client) == 0

    assert client.calls == [(1, 2), (2, 2), (3, 2)]
    export = (tmp_path / "functional-cosmetics-reported.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(export) == 6 and SECRET not in "".join(export)
    assert json.loads(export[0])["record_id"] == "1"
    report = json.loads((tmp_path / "functional-cosmetics-reported.audit.json").read_text(encoding="utf-8"))
    assert report["total_count"] == 6 and report["row_count"] == 6 and len(report["sha256"]) == 64
    assert report["duplicate_id_rows"] == 1 and report["withdrawn_rows"] == 2
    # A row has an official statement if either the document or the efficacy sentence is present.
    assert report["missing"] == {"item_name": 0, "company": 0, "registered_on": 0, "statement": 1}
    assert report["statement_source"] == {"document": 1, "effect_name": 4, "none": 1}
    assert report["effect_codes"] == {"1": 1, "3": 2, "5": 1}
    assert report["statements"][both] == 2 and report["distinct_statements"] == 4
    assert report["unreadable_documents"] == 0
    # Product names shared by several records cannot identify a product on their own.
    assert report["names_shared_by_several_records"] == 1
    assert SECRET not in json.dumps(report)


def test_audit_of_the_reviewed_list_counts_unreadable_documents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        _reviewed("1", "주름 세럼"),
        _reviewed("2", "오래된 제품", ""),
        _reviewed("3", "표 문서", "<DOC><SECTION><TABLE><TR><TD>표</TD></TR></TABLE></SECTION></DOC>"),
    ]
    assert _audit(tmp_path, monkeypatch, _FakeClient(rows, source=REVIEWED)) == 0
    report = json.loads((tmp_path / "functional-cosmetics-reviewed.audit.json").read_text(encoding="utf-8"))
    assert report["missing"]["statement"] == 2 and report["unreadable_documents"] == 1
    assert report["statement_source"] == {"document": 1, "none": 2}
    assert "withdrawn_rows" not in report


def test_sentence_cores_drop_markers_details_and_punctuation() -> None:
    cores = audit_cosmetics.sentence_cores
    assert cores("1. 피부의 미백에 도움을 준다.\n-. 자외선으로부터 피부를 보호한다. (SPF50+, PA+++)") == (
        "피부의미백에도움을준다", "자외선으로부터피부를보호한다",
    )
    assert cores("피부의 미백에 도움을 준다. 피부의 주름개선에 도움을 준다.") == (
        "피부의미백에도움을준다", "피부의주름개선에도움을준다",
    )
    assert cores("모발(백모)의 염모(흑색)") == ("모발의염모",) and cores("") == ()


def test_audit_measures_regularity_conflicts_and_template_remnants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    whitening = "피부의 미백에 도움을 준다."
    rows = [
        _reported("1", "가", effect=whitening),
        _reported("2", "나", effect=None, REPORT_DATE="20130102"),
        # The efficacy sentence and the document disagree: conflicting official data.
        _reported("3", "다", effect=whitening, EE_DOC_DATA=_doc("자외선으로부터 피부를 보호한다.(SPF50+, PA+++)")),
        # The form's instruction was left in: the list of functions may be the unedited template.
        _reported("4", "라", effect=None, EE_DOC_DATA=_doc(
            "- 피부의 미백에 도움을 준다.", "※ 해당하는 효능효과 이외에는 모두 삭제하시기 바랍니다.",
        )),
        _reported("5", "가", effect=whitening, ENTP_NAME="다른 업체"),
    ]

    assert _audit(tmp_path, monkeypatch, _FakeClient(rows)) == 0

    report = json.loads((tmp_path / "functional-cosmetics-reported.audit.json").read_text(encoding="utf-8"))
    assert report["statement_missing_by_year"] == {
        "2013": {"rows": 1, "missing": 1}, "2025": {"rows": 4, "missing": 0},
    }
    assert report["conflicting_sources"] == 1 and report["template_instruction_rows"] == 1
    assert report["sentence_cores"]["피부의미백에도움을준다"] == 3 and report["distinct_sentence_cores"] == 3
    assert report["rows_fully_covered_by_top_cores"]["1"] == 2
    assert report["names_shared_by_several_records"] == 1 and report["records_under_shared_names"] == 2
    assert report["shared_names_with_one_company"] == 0


def test_an_export_is_measured_again_without_the_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        _reported("1", "가"),
        _reported("2", "나", effect=None, EE_DOC_DATA=_doc("여드름성 피부를 완화하는 데 도움을 준다.")),
    ]
    assert _audit(tmp_path, monkeypatch, _FakeClient(rows)) == 0
    first = json.loads((tmp_path / "functional-cosmetics-reported.audit.json").read_text(encoding="utf-8"))
    # A stale parsed text in the export is replaced by a fresh reading of the raw document.
    export = tmp_path / "functional-cosmetics-reported.jsonl"
    lines = [json.loads(line) for line in export.read_text(encoding="utf-8").splitlines()]
    lines[1]["effect_text"], lines[1]["effect_doc_unreadable"] = "", True
    export.write_text("".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines), encoding="utf-8")

    def no_network(source, key):
        raise AssertionError("the network must not be used")

    monkeypatch.setattr(audit_cosmetics, "_client", no_network)
    for name in KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    assert audit_cosmetics.main(["--service", "reported", "--from-export", str(tmp_path)]) == 0

    again = json.loads((tmp_path / "functional-cosmetics-reported.audit.json").read_text(encoding="utf-8"))
    assert again["retrieved_at"] == first["retrieved_at"] and again["total_count"] == 2
    assert again["statement_source"] == {"document": 1, "effect_name": 1} and again["unreadable_documents"] == 0
    assert json.loads(export.read_text(encoding="utf-8").splitlines()[1])["effect_text"].startswith("여드름성")
    assert audit_cosmetics.main(["--service", "reviewed", "--from-export", str(tmp_path)]) == 3


def test_both_lists_report_their_overlap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(source, key):
        rows = (
            [_reported("1", "같은 이름"), _reported("2", "보고만")]
            if source is REPORTED
            else [_reviewed("9", "같은 이름"), {**_reviewed("8", "보고만"), "ENTP_NAME": "다른 업체"}]
        )
        return _FakeClient(rows, source=source)

    for name in KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", SECRET)
    monkeypatch.setattr(audit_cosmetics, "_client", fake)

    assert audit_cosmetics.main(["--output-dir", str(tmp_path)]) == 0

    overlap = json.loads((tmp_path / "functional-cosmetics-overlap.json").read_text(encoding="utf-8"))
    assert overlap == {"names_in_both_lists": 2, "name_and_company_in_both_lists": 1}


def test_audit_fails_closed_on_a_short_download_or_missing_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _audit(tmp_path, monkeypatch, _FakeClient([_reported("1", "가")], total=3)) == 3
    assert not (tmp_path / "functional-cosmetics-reported.jsonl").exists()
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY")
    assert audit_cosmetics.main(["--service", "reported", "--output-dir", str(tmp_path)]) == 3


class _FlakyClient(_FakeClient):
    def __init__(self, rows: list[dict], failures: list[str]) -> None:
        super().__init__(rows)
        self.failures = failures

    def fetch_page(self, page_no: int, num_of_rows: int):
        if self.failures:
            self.calls.append((page_no, num_of_rows))
            raise DataSourceError(self.failures.pop(0))
        return super().fetch_page(page_no, num_of_rows)


def test_transient_failures_are_retried_but_key_errors_are_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[float] = []
    monkeypatch.setattr(audit_cosmetics.time, "sleep", waits.append)
    rows = [_reported(str(n), f"제품 {n}") for n in range(1, 4)]

    flaky = _FlakyClient(rows, ["data.go.kr:15095680 request timeout", "data.go.kr:15095680 returned HTTP 502"])
    assert _audit(tmp_path, monkeypatch, flaky) == 0
    assert len(waits) == 2 and flaky.calls[:3] == [(1, 2), (1, 2), (1, 2)]

    waits.clear()
    dead = _FlakyClient(rows, ["data.go.kr:15095680 request failed"] * 5)
    assert _audit(tmp_path / "dead", monkeypatch, dead) == 3
    assert len(dead.calls) == 3 and not (tmp_path / "dead").exists()

    waits.clear()
    denied = _FlakyClient(rows, ["data.go.kr:15095680 returned HTTP 403: SERVICE_KEY_IS_NOT_REGISTERED_ERROR"])
    assert _audit(tmp_path / "denied", monkeypatch, denied) == 3
    assert waits == [] and len(denied.calls) == 1


def test_each_source_may_have_its_own_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # It is not confirmed whether data.go.kr issues one key per account or one per API.
    seen: dict[str, str] = {}

    def fake(source, key):
        seen[source.key] = key
        rows = [_reported("1", "가")] if source is REPORTED else [_reviewed("1", "가")]
        return _FakeClient(rows, source=source)

    for name in KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(audit_cosmetics, "_client", fake)
    env = tmp_path / ".env"
    env.write_text(
        "FOODSAFETY_API_KEY=unrelated\nDATA_GO_KR_SERVICE_KEY=shared-key\n"
        "DATA_GO_KR_SERVICE_KEY_REVIEWED='reviewed-key'\nDATA_GO_KR_SERVICE_KEY_REPORTED=\n",
        encoding="utf-8",
    )

    assert audit_cosmetics.main(["--env-file", str(env), "--output-dir", str(tmp_path / "out")]) == 0
    # The reported slot is empty, so the shared key is used there; the reviewed slot wins for its API.
    assert seen == {"reported": "shared-key", "reviewed": "reviewed-key"}

    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY_REPORTED", "from-environment")
    assert audit_cosmetics.main(["--service", "reported", "--env-file", str(env), "--output-dir", str(tmp_path / "out")]) == 0
    assert seen["reported"] == "from-environment"


def test_a_missing_key_names_both_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    for name in KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text("DATA_GO_KR_SERVICE_KEY_REPORTED=only-reported\n", encoding="utf-8")
    monkeypatch.setattr(audit_cosmetics, "_client", lambda source, key: _FakeClient([_reported("1", "가")]))

    assert audit_cosmetics.main(["--env-file", str(env), "--output-dir", str(tmp_path / "out")]) == 3

    message = capsys.readouterr().out
    assert "DATA_GO_KR_SERVICE_KEY_REVIEWED" in message and "DATA_GO_KR_SERVICE_KEY" in message
    assert "only-reported" not in message
    # Nothing is downloaded when a requested source has no key.
    assert not (tmp_path / "out").exists()


def test_a_probe_reads_only_the_requested_pages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeClient([_reported(str(n), f"제품 {n}") for n in range(1, 8)])

    assert _audit(tmp_path, monkeypatch, client, "--max-pages", "1") == 0

    report = json.loads((tmp_path / "functional-cosmetics-reported.audit.json").read_text(encoding="utf-8"))
    assert client.calls == [(1, 2)]
    assert report["total_count"] == 7 and report["row_count"] == 2 and report["complete"] is False
