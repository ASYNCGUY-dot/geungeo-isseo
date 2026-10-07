"""Resource and browser hardening of the local API (2026-10-07 security check)."""

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from claimledger.api import MAX_BODY_BYTES, create_app
from claimledger.domain import ProductCandidate
from scripts import serve_api

AT = datetime(2026, 10, 7, tzinfo=UTC)


def _products() -> list[ProductCandidate]:
    return [ProductCandidate(
        report_no="R1", name="루테인 테스트", company="가나 업체",
        primary_function="[루테인] 노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음",
        raw_materials="마리골드꽃추출물", intake_method="1일 1회", source_id="C003", retrieved_at=AT,
    )]


def test_the_analysis_store_drops_the_oldest_analysis() -> None:
    client = TestClient(create_app(_products(), source_retrieved_at=AT, max_analyses=3))
    ids = [
        client.post("/api/v1/analyses", json={"ad_text": f"눈 건강에 도움을 줄 수 있어요 {n}."}).json()["analysis_id"]
        for n in range(4)
    ]
    assert client.get(f"/api/v1/analyses/{ids[0]}").status_code == 404
    assert [client.get(f"/api/v1/analyses/{item}").status_code for item in ids[1:]] == [200, 200, 200]


def test_oversized_and_unsized_bodies_are_rejected_before_parsing() -> None:
    client = TestClient(create_app(_products(), source_retrieved_at=AT))
    big = client.post(
        "/api/v1/analyses", content=b'{"ad_text": "' + b"a" * MAX_BODY_BYTES + b'"}',
        headers={"content-type": "application/json"},
    )
    assert big.status_code == 413 and big.json()["error"]["code"] == "REQUEST_TOO_LARGE"

    def chunks():
        yield b'{"ad_text": "'
        yield b'x"}'

    unsized = client.post("/api/v1/analyses", content=chunks(), headers={"content-type": "application/json"})
    assert unsized.status_code == 411 and unsized.json()["error"]["code"] == "LENGTH_REQUIRED"
    assert client.post("/api/v1/analyses", json={"ad_text": "눈 건강에 도움을 줄 수 있어요."}).status_code == 201


def test_confirmation_fields_are_bounded() -> None:
    client = TestClient(create_app(_products(), source_retrieved_at=AT))
    path = "/api/v1/analyses/" + client.post(
        "/api/v1/analyses", json={"ad_text": "눈 건강에 도움을 줄 수 있어요."}
    ).json()["analysis_id"]
    assert client.put(path + "/claims/confirmation", json={"claim_ids": ["C1"] * 2001}).status_code == 422
    assert client.put(path + "/claims/confirmation", json={"claim_ids": ["C" * 33]}).status_code == 422
    assert client.put(path + "/product-confirmation", json={"report_no": "9" * 65}).status_code == 422
    assert client.put(path + "/product-confirmation", json={"report_no": "R1"}).status_code == 200


def test_only_allowed_hosts_are_served_when_configured() -> None:
    app = create_app(_products(), source_retrieved_at=AT, allowed_hosts=("127.0.0.1", "localhost"))
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/health", headers={"host": "localhost:8000"}).status_code == 200
    assert client.get("/api/v1/health", headers={"host": "rebind.example"}).status_code == 400
    # Without the option (tests, embedding) no host is rejected.
    assert TestClient(create_app(_products(), source_retrieved_at=AT)).get("/api/v1/health").status_code == 200


def test_browser_hardening_headers() -> None:
    client = TestClient(create_app(_products(), source_retrieved_at=AT))
    page = client.get("/")
    policy = page.headers["content-security-policy"]
    assert "default-src 'none'" in policy and "frame-ancestors 'none'" in policy and "connect-src 'self'" in policy
    for response in (page, client.get("/api/v1/health"), client.get("/api/v1/analyses/none")):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
    # The interactive API docs load scripts from a CDN, so the page policy is not applied there.
    assert "content-security-policy" not in client.get("/api/v1/health").headers


def _export(path: Path) -> Path:
    row = {
        "report_no": "R1", "name": "루테인", "company": "가",
        "primary_function": "[루테인] 노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음",
        "raw_materials": "마리골드꽃추출물", "intake_method": "1일 1회",
    }
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def test_the_server_script_serves_local_hosts_only_by_default(tmp_path: Path) -> None:
    base = ["--source-export", str(_export(tmp_path / "e.jsonl")), "--source-retrieved-at", "2026-08-27T12:42:29+00:00"]
    client = TestClient(serve_api.build_app(serve_api.parse_args(base)), base_url="http://127.0.0.1:8000")
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/health", headers={"host": "rebind.example"}).status_code == 400
    extra = serve_api.build_app(serve_api.parse_args([*base, "--allowed-host", "review.internal"]))
    assert TestClient(extra, base_url="http://review.internal").get("/api/v1/health").status_code == 200
