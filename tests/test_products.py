import json
from pathlib import Path

import pytest

from claimledger.domain import ProductCandidate
from claimledger.products import (
    ProductSearchDocument,
    ProductSearchResult,
    build_search_document,
    normalize_search_text,
    search_products,
)

FIXTURE = Path(__file__).parent / "fixtures" / "product_records.json"
PRODUCTS = tuple(ProductCandidate.model_validate(item) for item in json.loads(FIXTURE.read_text()))
PRODUCT_A = ProductCandidate.model_copy(
    PRODUCTS[0], update={"report_no": "A", "name": "오메가3", "company": "테스트 제조사"}
)
PRODUCT_B = ProductCandidate.model_copy(
    PRODUCTS[1], update={"report_no": "B", "name": "다른 제품", "company": "다른 제조사"}
)


def test_normalization_preserves_digits_but_unifies_spacing_and_width() -> None:
    assert normalize_search_text(" 오메가－3  1000 mg ") == "오메가-3 1000 mg"


def test_search_document_normalizes_only_search_fields() -> None:
    product = PRODUCTS[0].model_copy(update={"name": " Ｏmega－3  1000 mg "})

    document = build_search_document(product)

    assert isinstance(document, ProductSearchDocument)
    assert document.normalized_name == "omega-3 1000 mg"
    assert document.normalized_company == "테스트 제조사"
    assert document.normalization_version == "product-search-v1"
    assert product.name == " Ｏmega－3  1000 mg "


def test_search_returns_candidates_without_confirming_identity() -> None:
    results = search_products([PRODUCT_A, PRODUCT_B], "테스트 제조사 오메가3")

    assert isinstance(results[0], ProductSearchResult)
    assert results[0].candidate.report_no == PRODUCT_A.report_no
    assert results[0].matched_fields == ("name", "company")
    assert results[0].normalization_version == "product-search-v1"
    assert not hasattr(results[0], "confirmed_by_user")


def test_search_ranks_exact_report_number_before_text_matches() -> None:
    results = search_products(PRODUCTS, "TEST-OMEGA-002")

    assert [item.candidate.report_no for item in results] == ["TEST-OMEGA-002"]
    assert results[0].matched_fields == ("report_no",)


def test_partial_report_number_tokens_are_not_report_number_evidence() -> None:
    product = PRODUCT_A.model_copy(
        update={"report_no": "ALPHA-123", "name": "Omega Prime", "company": "Acme"}
    )

    result = search_products([product], "ALPHA omega")[0]

    assert result.matched_fields == ("name",)


@pytest.mark.parametrize(
    ("query", "near_match", "exact_match"),
    [
        (
            "acme labs omega pro",
            {"report_no": "A", "name": "omega pro", "company": "acme labs"},
            {"report_no": "B", "name": "acme labs", "company": "omega pro"},
        ),
        (
            "a b co",
            {"report_no": "A", "name": "A-B", "company": "co"},
            {"report_no": "B", "name": "A B", "company": "co"},
        ),
        (
            "omega co",
            {"report_no": "A", "name": "omega omega", "company": "co"},
            {"report_no": "B", "name": "omega", "company": "co"},
        ),
    ],
    ids=("reordered", "punctuation", "repeated-token"),
)
def test_exact_name_company_tier_preserves_normalized_text_identity(
    query: str, near_match: dict[str, str], exact_match: dict[str, str]
) -> None:
    results = search_products(
        [PRODUCT_A.model_copy(update=near_match), PRODUCT_A.model_copy(update=exact_match)], query
    )

    assert [result.candidate.report_no for result in results] == ["B", "A"]


def test_search_uses_report_number_to_break_equal_token_overlap() -> None:
    tied = search_products(
        [
            PRODUCT_A.model_copy(update={"report_no": "B"}),
            PRODUCT_A.model_copy(update={"report_no": "A"}),
        ],
        "오메가3",
    )

    assert [item.candidate.report_no for item in tied] == ["A", "B"]


def test_blank_query_is_rejected() -> None:
    with pytest.raises(ValueError, match="query"):
        search_products([PRODUCT_A], " ")


def test_search_ranking_is_stable_across_repeated_runs() -> None:
    expected = ["TEST-OMEGA-001", "TEST-OMEGA-002"]

    assert [item.candidate.report_no for item in search_products(PRODUCTS, "오메가3 1000mg")] == expected
    assert [item.candidate.report_no for item in search_products(PRODUCTS, "오메가3 1000mg")] == expected
