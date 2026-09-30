import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from claimledger.errors import DataSourceError
from claimledger.sources.ingredient_approvals import I0040Client, parse_i0040_payload
from scripts import fetch_i0040

NOW = datetime(2026, 9, 30, tzinfo=UTC)


def _row(number: str, name: str, function: str) -> dict:
    return {
        "HF_FNCLTY_MTRAL_RCOGN_NO": number,
        "PRMS_DT": "20060817",
        "BSSH_NM": "테스트 업체",
        "INDUTY_NM": "건강기능식품수입업",
        "ADDR": "테스트 주소",
        "APLC_RAWMTRL_NM": name,
        "FNCLTY_CN": function,
        "DAY_INTK_CN": ".",
        "IFTKN_ATNT_MATR_CN": ".",
    }


def _payload(rows: list[dict], total: int | None = None) -> dict:
    return {
        "I-0040": {
            "total_count": str(len(rows) if total is None else total),
            "row": rows,
            "RESULT": {"CODE": "INFO-000", "MSG": "정상처리되었습니다."},
        }
    }


def test_parse_keeps_only_identity_and_function_fields() -> None:
    page = parse_i0040_payload(_payload([_row("2006-15", "라피노스", "배변활동을 원활히 하는데 도움")]), NOW)

    assert page.total_count == 1
    approval = page.approvals[0]
    assert (approval.approval_no, approval.ingredient_name) == ("2006-15", "라피노스")
    assert approval.function_text == "배변활동을 원활히 하는데 도움"
    assert approval.source_id == "I-0040"
    assert approval.retrieved_at == NOW
    assert "address" not in approval.model_dump()


@pytest.mark.parametrize("payload", [
    {"I-0040": {"RESULT": {"CODE": "INFO-300", "MSG": "유효 호출건수를 이미 초과하셨습니다."}}},
    {"C003": {}},
    _payload([_row("", "라피노스", "도움")]),
    _payload([], total=-1),
])
def test_parse_rejects_errors_and_invalid_rows(payload: dict) -> None:
    with pytest.raises(DataSourceError):
        parse_i0040_payload(payload, NOW)


def test_client_path_and_sanitized_errors() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json=_payload([_row("2006-15", "라피노스", "도움")]))

    client = I0040Client("secret-key", httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.fetch_page(1, 1000).total_count == 1
    assert paths == ["/api/secret-key/I-0040/json/1/1000"]

    failing = I0040Client(
        "secret-key",
        httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503, request=request))),
    )
    with pytest.raises(DataSourceError) as error:
        failing.fetch_page(1, 1000)
    assert "secret-key" not in str(error.value)

    with pytest.raises(DataSourceError, match="API key"):
        I0040Client(" ")


@pytest.mark.parametrize("handler", [
    lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=request)),
    lambda request: httpx.Response(200, content=b"not json"),
    lambda request: httpx.Response(200, json=[1, 2]),
    lambda request: httpx.Response(200, json={"I-0040": {"RESULT": {"CODE": "INFO-000"}}}),
    lambda request: httpx.Response(200, json={"I-0040": {"RESULT": {"CODE": "INFO-000"}, "total_count": "1", "row": {}}}),
    lambda request: httpx.Response(200, json={"I-0040": {"RESULT": {"CODE": "INFO-000"}, "total_count": "1", "row": [1]}}),
])
def test_client_turns_transport_and_shape_failures_into_errors(handler) -> None:
    client = I0040Client("secret-key", httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(DataSourceError) as error:
        client.fetch_page(1, 10)
    assert "secret-key" not in str(error.value)


def test_client_rejects_invalid_page_range() -> None:
    with pytest.raises(DataSourceError, match="page range"):
        I0040Client("secret-key").fetch_page(5, 1)


def test_env_file_without_the_key_yields_no_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FOOD_SAFETY_API_KEY", raising=False)
    monkeypatch.delenv("FOODSAFETY_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=1\nFOODSAFETY_API_KEY=\n", encoding="utf-8")

    assert fetch_i0040._api_key(env_file) == ""


def test_fetch_script_pages_writes_minimal_rows_and_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    rows = [_row(f"2006-{i}", f"원료{i}", "도움") for i in range(3)]

    def handler(request: httpx.Request) -> httpx.Response:
        start, end = (int(part) for part in request.url.path.rsplit("/", 2)[-2:])
        return httpx.Response(200, json=_payload(rows[start - 1:end], total=len(rows)))

    monkeypatch.setattr(fetch_i0040, "_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=1\nFOOD_SAFETY_API_KEY=secret-key\n", encoding="utf-8")
    monkeypatch.delenv("FOOD_SAFETY_API_KEY", raising=False)
    output = tmp_path / "i0040.jsonl"

    code = fetch_i0040.main(["--env-file", str(env_file), "--output", str(output), "--page-size", "2"])

    assert code == 0
    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [line["approval_no"] for line in lines] == ["2006-0", "2006-1", "2006-2"]
    assert set(lines[0]) == {"approval_no", "approved_on", "company", "ingredient_name", "function_text"}
    manifest = json.loads(output.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_id"] == "I-0040"
    assert manifest["row_count"] == manifest["total_count"] == 3
    assert len(manifest["sha256"]) == 64
    assert "secret-key" not in capsys.readouterr().out


def test_env_file_accepts_the_project_variable_spelling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FOOD_SAFETY_API_KEY", raising=False)
    monkeypatch.delenv("FOODSAFETY_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nFOODSAFETY_API_KEY=secret-key\n", encoding="utf-8")

    assert fetch_i0040._api_key(env_file) == "secret-key"


def test_fetch_script_without_key_or_with_short_result_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FOOD_SAFETY_API_KEY", raising=False)
    assert fetch_i0040.main(["--output", str(tmp_path / "a.jsonl")]) == 3

    monkeypatch.setenv("FOOD_SAFETY_API_KEY", "secret-key")
    short = httpx.MockTransport(lambda request: httpx.Response(200, json=_payload([], total=5)))
    monkeypatch.setattr(fetch_i0040, "_http_client", lambda: httpx.Client(transport=short))
    assert fetch_i0040.main(["--output", str(tmp_path / "b.jsonl")]) == 3
    assert not (tmp_path / "b.jsonl").exists()
