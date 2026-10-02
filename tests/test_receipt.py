import json
from datetime import UTC, datetime

import pytest

from claimledger.claims_v1 import confirm_claims, extract_claims
from claimledger.domain import ConfirmedProduct, ProductCandidate, Verdict
from claimledger.headerless import headerless_references
from claimledger.receipt import (
    PUBLIC_VERDICT_LABELS,
    RECEIPT_VERSION,
    build_receipt,
    receipt_to_json,
    render_markdown,
)
from claimledger.verdict_v1 import decide_claim

GENERATED_AT = datetime(2026, 9, 27, 3, 0, tzinfo=UTC)
AD_TEXT = (
    "혈중 중성지질 개선에 도움을 줄 수 있어요.\n"
    "혈액순환이 확실히 좋아집니다!\n"
    "고지혈증 예방 효과"
)
FUNCTION_TEXT = "[EPA 및 DHA 함유 유지] 혈중 중성지질 개선·혈행 개선에 도움을 줄 수 있음"


def _product() -> ConfirmedProduct:
    return ConfirmedProduct(
        product=ProductCandidate(
            report_no="200400000000002",
            name="오메가 테스트",
            company="테스트 업체",
            primary_function=FUNCTION_TEXT,
            raw_materials="EPA 및 DHA 함유 유지(고시형)",
            intake_method="1일 1회",
            source_id="C003",
            retrieved_at=datetime(2026, 8, 27, 12, 42, tzinfo=UTC),
        ),
        confirmed_by_user=True,
    )


def _decisions(product: ConfirmedProduct | None):
    claims = confirm_claims(extract_claims(AD_TEXT), "all")
    return [decide_claim(claim, product) for claim in claims]


def test_receipt_records_each_claim_with_public_label_and_quote() -> None:
    receipt = build_receipt(AD_TEXT, _product(), _decisions(_product()), GENERATED_AT)

    assert receipt.receipt_version == RECEIPT_VERSION
    assert [claim.verdict for claim in receipt.claims] == [
        Verdict.CONFIRMED,
        Verdict.MISMATCH,
        Verdict.MISMATCH,
    ]
    assert [claim.verdict_label for claim in receipt.claims] == ["확인됨", "근거 불일치", "근거 불일치"]
    first = receipt.claims[0]
    assert first.official_quote is not None
    assert first.official_quote.statement_text in FUNCTION_TEXT
    assert first.official_quote.header == "EPA 및 DHA 함유 유지"
    assert receipt.claims[2].official_quote is None
    assert receipt.verdict_counts == {"confirmed": 1, "mismatch": 2}
    assert receipt.product is not None and receipt.product.report_no == "200400000000002"
    assert receipt.rule_versions == (
        "claim-extract-v1.2", "official-function-v2.11", "headerless-attribution-v3",
        *headerless_references(), "claim-verdict-v1.3",
    )
    assert headerless_references()[0].startswith("official-statement-owners-v1@")
    assert receipt.limitations


def test_receipt_json_is_deterministic_and_excludes_nothing_needed() -> None:
    first = receipt_to_json(build_receipt(AD_TEXT, _product(), _decisions(_product()), GENERATED_AT))
    second = receipt_to_json(build_receipt(AD_TEXT, _product(), _decisions(_product()), GENERATED_AT))

    assert first == second
    payload = json.loads(first)
    assert payload["ad_text"] == AD_TEXT
    assert len(payload["ad_text_sha256"]) == 64
    assert payload["claims"][0]["reason_code"] == "MATCHES_OFFICIAL_FUNCTION"


def test_markdown_shows_labels_quotes_and_limitations_without_scores() -> None:
    markdown = render_markdown(build_receipt(AD_TEXT, _product(), _decisions(_product()), GENERATED_AT))

    assert "# 근거영수증" in markdown
    assert "확인됨" in markdown and "근거 불일치" in markdown
    assert "혈중 중성지질 개선·혈행 개선에 도움을 줄 수 있음" in markdown
    assert "이 영수증의 한계" in markdown
    assert "점수" not in markdown


def test_unconfirmed_product_receipt_has_no_product_and_all_unverifiable() -> None:
    receipt = build_receipt(AD_TEXT, None, _decisions(None), GENERATED_AT)

    assert receipt.product is None
    assert {claim.verdict for claim in receipt.claims} == {Verdict.UNVERIFIABLE}
    assert "제품이 확정되지 않았습니다" in render_markdown(receipt)


def test_receipt_rejects_claims_that_do_not_quote_the_given_ad_text() -> None:
    with pytest.raises(ValueError, match="claim text does not match"):
        build_receipt("다른 광고 문구입니다", _product(), _decisions(_product()), GENERATED_AT)


def test_receipt_rejects_naive_generation_time() -> None:
    with pytest.raises(ValueError, match="timezone"):
        build_receipt(AD_TEXT, _product(), _decisions(_product()), datetime(2026, 9, 27))  # noqa: DTZ001


def test_every_public_verdict_has_a_label() -> None:
    assert set(PUBLIC_VERDICT_LABELS) == set(Verdict)
