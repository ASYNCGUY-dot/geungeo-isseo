from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from claimledger.domain import IngredientGroup
from claimledger.product_review import ProductReviewLabel

NOW = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)


def valid_label_values() -> dict[str, object]:
    return {
        "group": IngredientGroup.MILK_THISTLE,
        "report_no": "TEST-001",
        "mapping_verdict": "correct",
        "mapping_reason_code": "none",
        "function_text_status": "usable",
        "function_reason_code": "none",
        "review_note": "",
        "reviewer": "reviewer-01",
        "reviewed_at_iso8601": NOW,
    }


def test_product_review_label_accepts_a_consistent_decision() -> None:
    label = ProductReviewLabel.model_validate(valid_label_values())

    assert label.mapping_verdict.value == "correct"
    assert label.function_text_status.value == "usable"
    assert label.reviewed_at_iso8601 == NOW


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"mapping_verdict": "correct", "mapping_reason_code": "wrong_group"},
            "correct mapping requires reason none",
        ),
        (
            {"mapping_verdict": "incorrect", "mapping_reason_code": "none"},
            "non-correct mapping requires a reason",
        ),
        (
            {"function_text_status": "usable", "function_reason_code": "missing_text"},
            "usable function text requires reason none",
        ),
        (
            {"function_text_status": "uncertain", "function_reason_code": "none"},
            "non-usable function text requires a reason",
        ),
        (
            {
                "mapping_verdict": "uncertain",
                "mapping_reason_code": "needs_expert",
                "review_note": "",
            },
            "needs_expert and other reasons require a review note",
        ),
        ({"reviewer": '=HYPERLINK("bad")'}, "spreadsheet formula prefix"),
        ({"review_note": "+SUM(1,1)"}, "spreadsheet formula prefix"),
        (
            {"reviewed_at_iso8601": datetime(2026, 8, 28, 9, 0)},  # noqa: DTZ001
            "timezone",
        ),
    ],
)
def test_product_review_label_rejects_inconsistent_or_unsafe_values(
    changes: dict[str, object], message: str
) -> None:
    values = valid_label_values()
    values.update(changes)

    with pytest.raises(ValidationError, match=message):
        ProductReviewLabel.model_validate(values)


def test_product_review_label_rejects_a_core_ingredient_group() -> None:
    values = valid_label_values()
    values["group"] = IngredientGroup.OMEGA3

    with pytest.raises(ValidationError, match="comparison ingredient group"):
        ProductReviewLabel.model_validate(values)
