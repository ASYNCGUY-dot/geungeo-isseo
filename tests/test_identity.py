from datetime import UTC, datetime

import pytest

from claimledger.domain import ProductCandidate
from claimledger.errors import IdentityRequiredError
from claimledger.identity import confirm_candidate, require_confirmed_product

NOW = datetime(2026, 8, 22, tzinfo=UTC)
PRODUCT_A = ProductCandidate(
    report_no="TEST-0001",
    name="테스트 제품 A",
    company="테스트 제조사 A",
    source_id="C003",
    retrieved_at=NOW,
)
PRODUCT_B = ProductCandidate(
    report_no="TEST-0002",
    name="테스트 제품 B",
    company="테스트 제조사 B",
    source_id="C003",
    retrieved_at=NOW,
)


def test_exact_report_number_can_be_user_confirmed() -> None:
    confirmed = confirm_candidate([PRODUCT_A, PRODUCT_B], "TEST-0002")
    assert confirmed.confirmed_by_user is True
    assert confirmed.product.report_no == "TEST-0002"


def test_unknown_report_number_is_not_guessed() -> None:
    with pytest.raises(IdentityRequiredError, match="not present"):
        confirm_candidate([PRODUCT_A, PRODUCT_B], "TEST-9999")


def test_blank_selection_is_rejected() -> None:
    with pytest.raises(IdentityRequiredError, match="selection"):
        confirm_candidate([PRODUCT_A], "")


def test_duplicate_report_numbers_are_rejected() -> None:
    with pytest.raises(IdentityRequiredError, match="duplicate"):
        confirm_candidate([PRODUCT_A, PRODUCT_A], "TEST-0001")


def test_missing_confirmed_product_is_rejected() -> None:
    with pytest.raises(IdentityRequiredError, match="required"):
        require_confirmed_product(None)
