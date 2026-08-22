from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from claimledger.domain import Claim, ProductCandidate, Verdict


def test_public_verdict_values_are_stable() -> None:
    assert [item.value for item in Verdict] == [
        "confirmed",
        "mismatch",
        "insufficient",
        "unverifiable",
        "contradicted",
    ]


def test_product_candidate_rejects_blank_identity_fields() -> None:
    with pytest.raises(ValidationError):
        ProductCandidate(
            report_no="",
            name="루테인 테스트 제품",
            company="테스트 제조사",
            primary_function="눈 건강에 도움을 줄 수 있음",
            raw_materials="루테인지아잔틴복합추출물",
            intake_method="1일 1회",
            source_id="C003",
            retrieved_at=datetime.now(UTC),
        )


def test_claim_preserves_original_text() -> None:
    claim = Claim(original_text="눈 피로를 완전히 없앱니다", normalized_subject="눈 피로")
    assert claim.original_text == "눈 피로를 완전히 없앱니다"
