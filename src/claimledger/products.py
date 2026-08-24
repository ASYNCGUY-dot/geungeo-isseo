import re
import unicodedata
from collections.abc import Sequence

from claimledger.domain import (
    ProductCandidate,
    ProductSearchDocument,
    ProductSearchResult,
    SearchMatchedField,
)

NORMALIZATION_VERSION = "product-search-v1"
_MATCH_FIELD_ORDER: tuple[SearchMatchedField, ...] = ("report_no", "name", "company")


def normalize_search_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(normalized.split())


def build_search_document(product: ProductCandidate) -> ProductSearchDocument:
    return ProductSearchDocument(
        product=product,
        normalized_report_no=normalize_search_text(product.report_no),
        normalized_name=normalize_search_text(product.name),
        normalized_company=normalize_search_text(product.company),
        normalization_version=NORMALIZATION_VERSION,
    )


def _search_tokens(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"\w+", text))


def _matched_fields(
    document: ProductSearchDocument, query_tokens: frozenset[str]
) -> tuple[SearchMatchedField, ...]:
    field_tokens = {
        "report_no": _search_tokens(document.normalized_report_no),
        "name": _search_tokens(document.normalized_name),
        "company": _search_tokens(document.normalized_company),
    }
    return tuple(
        field for field in _MATCH_FIELD_ORDER if field_tokens[field].intersection(query_tokens)
    )


def _rank_document(
    document: ProductSearchDocument, query: str, query_tokens: frozenset[str]
) -> tuple[int, int, tuple[SearchMatchedField, ...]] | None:
    matched_fields = _matched_fields(document, query_tokens)
    document_tokens = _search_tokens(
        f"{document.normalized_name} {document.normalized_company}"
    )
    token_overlap = len(query_tokens.intersection(document_tokens))

    if query == document.normalized_report_no:
        return 3, token_overlap, ("report_no",)
    if query_tokens == document_tokens:
        return 2, token_overlap, ("name", "company")
    if token_overlap > 0:
        return 1, token_overlap, matched_fields
    return None


def search_products(
    products: Sequence[ProductCandidate], query: str, limit: int = 10
) -> tuple[ProductSearchResult, ...]:
    normalized_query = normalize_search_text(query)
    if not normalized_query:
        raise ValueError("query must not be blank")

    query_tokens = _search_tokens(normalized_query)
    ranked: list[tuple[int, int, str, ProductSearchResult]] = []
    for product in products:
        document = build_search_document(product)
        ranked_document = _rank_document(document, normalized_query, query_tokens)
        if ranked_document is None:
            continue
        rank, overlap, matched_fields = ranked_document
        ranked.append(
            (
                rank,
                overlap,
                product.report_no,
                ProductSearchResult(
                    candidate=product,
                    matched_fields=matched_fields,
                    normalization_version=NORMALIZATION_VERSION,
                ),
            )
        )

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return tuple(item[3] for item in ranked[:limit])
