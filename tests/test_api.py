from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from claimledger.api import create_app
from claimledger.domain import ProductCandidate

RETRIEVED_AT = datetime(2026, 8, 27, 12, 42, 29, tzinfo=UTC)
AD_TEXT = "혈중 중성지질 개선에 도움을 줄 수 있어요.\n혈액순환이 좋아집니다!\n본 제품은 의약품이 아닙니다."


def _products() -> list[ProductCandidate]:
    return [
        ProductCandidate(
            report_no="R100",
            name="오메가 테스트",
            company="가나 업체",
            primary_function="[EPA 및 DHA 함유 유지] 혈중 중성지질 개선·혈행 개선에 도움을 줄 수 있음",
            raw_materials="EPA 및 DHA 함유 유지(고시형)",
            intake_method="1일 1회",
            source_id="C003",
            retrieved_at=RETRIEVED_AT,
        ),
        ProductCandidate(
            report_no="R200",
            name="오메가 무표시",
            company="다라 업체",
            primary_function="혈중 중성지질 개선에 도움을 줄 수 있음",
            raw_materials="정제어유",
            intake_method="1일 1회",
            source_id="C003",
            retrieved_at=RETRIEVED_AT,
        ),
    ]


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(_products(), source_retrieved_at=RETRIEVED_AT))


def _create(client: TestClient) -> dict:
    response = client.post("/api/v1/analyses", json={"ad_text": AD_TEXT})
    assert response.status_code == 201
    return response.json()


def test_duplicate_report_numbers_are_rejected_at_startup() -> None:
    products = _products()

    with pytest.raises(ValueError, match="duplicate report number"):
        create_app([products[0], products[0]], source_retrieved_at=RETRIEVED_AT)


def test_health_reports_snapshot_size(client: TestClient) -> None:
    body = client.get("/api/v1/health").json()

    assert body["status"] == "ok"
    assert body["product_count"] == 2
    assert body["source_retrieved_at"].startswith("2026-08-27T12:42:29")


def test_product_search_returns_candidates_without_confirming(client: TestClient) -> None:
    response = client.get("/api/v1/products/search", params={"q": "오메가"})

    assert response.status_code == 200
    assert [item["report_no"] for item in response.json()["candidates"]] == ["R100", "R200"]


def test_blank_search_uses_error_contract(client: TestClient) -> None:
    response = client.get("/api/v1/products/search", params={"q": "  "})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "INPUT_INVALID"
    assert error["retryable"] is False
    assert error["trace_id"]


def test_create_analysis_extracts_unconfirmed_claims(client: TestClient) -> None:
    body = _create(client)

    assert body["analysis_id"]
    assert [claim["claim_id"] for claim in body["claims"]] == ["C1", "C2"]
    assert all(claim["confirmed_by_user"] is False for claim in body["claims"])
    assert body["product"] is None
    assert body["receipt_available"] is False


@pytest.mark.parametrize("text", ["", "   ", "가" * 5001])
def test_ad_text_must_be_nonblank_and_bounded(client: TestClient, text: str) -> None:
    response = client.post("/api/v1/analyses", json={"ad_text": text})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INPUT_INVALID"


def test_evaluate_requires_confirmed_product(client: TestClient) -> None:
    analysis_id = _create(client)["analysis_id"]

    response = client.post(f"/api/v1/analyses/{analysis_id}/evaluate")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "PRODUCT_IDENTITY_UNCONFIRMED"
    assert error["user_action"] == "select_product"
    assert error["analysis_id"] == analysis_id


def test_full_flow_produces_receipt(client: TestClient) -> None:
    analysis_id = _create(client)["analysis_id"]

    product = client.put(f"/api/v1/analyses/{analysis_id}/product-confirmation", json={"report_no": "R100"})
    assert product.status_code == 200
    assert product.json()["product"]["report_no"] == "R100"
    claims = client.put(f"/api/v1/analyses/{analysis_id}/claims/confirmation", json={"claim_ids": ["C1", "C2"]})
    assert claims.status_code == 200
    evaluated = client.post(f"/api/v1/analyses/{analysis_id}/evaluate")

    assert evaluated.status_code == 200
    receipt = evaluated.json()
    assert [claim["verdict"] for claim in receipt["claims"]] == ["confirmed", "mismatch"]
    assert [claim["verdict_label"] for claim in receipt["claims"]] == ["확인됨", "근거 불일치"]
    assert client.get(f"/api/v1/analyses/{analysis_id}/receipt").json() == receipt
    markdown = client.get(f"/api/v1/analyses/{analysis_id}/receipt", params={"format": "markdown"})
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "# 근거영수증" in markdown.text


def test_unconfirmed_claims_are_reported_as_unverifiable(client: TestClient) -> None:
    analysis_id = _create(client)["analysis_id"]
    client.put(f"/api/v1/analyses/{analysis_id}/product-confirmation", json={"report_no": "R100"})
    client.put(f"/api/v1/analyses/{analysis_id}/claims/confirmation", json={"claim_ids": ["C2"]})

    receipt = client.post(f"/api/v1/analyses/{analysis_id}/evaluate").json()

    assert [claim["reason_code"] for claim in receipt["claims"]] == [
        "CLAIM_UNCONFIRMED",
        "EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL",
    ]


def test_changing_product_invalidates_previous_receipt(client: TestClient) -> None:
    analysis_id = _create(client)["analysis_id"]
    client.put(f"/api/v1/analyses/{analysis_id}/product-confirmation", json={"report_no": "R100"})
    client.post(f"/api/v1/analyses/{analysis_id}/evaluate")

    client.put(f"/api/v1/analyses/{analysis_id}/product-confirmation", json={"report_no": "R200"})
    response = client.get(f"/api/v1/analyses/{analysis_id}/receipt")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RECEIPT_NOT_READY"
    assert client.get(f"/api/v1/analyses/{analysis_id}").json()["receipt_available"] is False


def test_unknown_ids_and_report_numbers_are_errors(client: TestClient) -> None:
    assert client.get("/api/v1/analyses/nope").json()["error"]["code"] == "ANALYSIS_NOT_FOUND"
    analysis_id = _create(client)["analysis_id"]

    product = client.put(f"/api/v1/analyses/{analysis_id}/product-confirmation", json={"report_no": "R999"})
    assert product.status_code == 404
    assert product.json()["error"]["code"] == "PRODUCT_NOT_FOUND"

    claims = client.put(f"/api/v1/analyses/{analysis_id}/claims/confirmation", json={"claim_ids": ["C9"]})
    assert claims.status_code == 422
    assert claims.json()["error"]["code"] == "CLAIM_NOT_FOUND"


def test_evaluate_ignores_client_supplied_verdicts(client: TestClient) -> None:
    analysis_id = _create(client)["analysis_id"]
    client.put(f"/api/v1/analyses/{analysis_id}/product-confirmation", json={"report_no": "R200"})
    client.put(f"/api/v1/analyses/{analysis_id}/claims/confirmation", json={"claim_ids": ["C1"]})

    receipt = client.post(
        f"/api/v1/analyses/{analysis_id}/evaluate", json={"verdict": "confirmed"}
    ).json()

    assert receipt["claims"][0]["verdict"] == "unverifiable"
    assert receipt["claims"][0]["reason_code"] == "OFFICIAL_ATTRIBUTION_AMBIGUOUS"


def test_index_page_is_served(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "근거있어" in response.text
