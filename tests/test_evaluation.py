from datetime import UTC, datetime

import pytest

from claimledger.domain import EvaluationCase, Verdict
from claimledger.evaluation import (
    confirmed_recall,
    evaluate_verdicts,
    false_clearance_rate,
    zero_error_upper_bound,
)

NOW = datetime(2026, 8, 24, tzinfo=UTC)


def _case(case_id: str, expected_verdict: Verdict) -> EvaluationCase:
    return EvaluationCase(
        case_id=case_id,
        ingredient_group="omega3",
        expected_verdict=expected_verdict,
        frozen=True,
        report_no=f"C003-{case_id}",
        source_id="C003",
        retrieved_at=NOW,
        rule_version="evaluation-label-v1",
        matched_source_text="EPA 및 DHA 함유 유지",
        source_url=f"https://example.test/c003/{case_id}",
    )


def test_false_clearance_rate_counts_only_harmful_direction() -> None:
    expected = [Verdict.MISMATCH, Verdict.UNVERIFIABLE, Verdict.CONFIRMED]
    actual = [Verdict.CONFIRMED, Verdict.UNVERIFIABLE, Verdict.MISMATCH]
    assert false_clearance_rate(expected, actual) == 0.5


def test_zero_error_bound_for_one_hundred_examples() -> None:
    assert zero_error_upper_bound(100) == pytest.approx(0.03)


def test_empty_evaluation_set_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        false_clearance_rate([], [])


def test_mismatched_evaluation_lengths_are_rejected() -> None:
    with pytest.raises(ValueError, match="length"):
        false_clearance_rate([Verdict.MISMATCH], [])


def test_evaluation_reports_false_clearance_recall_and_coverage_separately() -> None:
    cases = [
        _case("a", Verdict.CONFIRMED),
        _case("b", Verdict.MISMATCH),
        _case("c", Verdict.UNVERIFIABLE),
    ]

    summary = evaluate_verdicts(
        cases,
        [Verdict.CONFIRMED, Verdict.UNVERIFIABLE, Verdict.UNVERIFIABLE],
    )

    assert summary.false_clearance_rate == 0.0
    assert summary.confirmed_recall == 1.0
    assert summary.coverage == 1 / 3
    assert summary.unverifiable_count == 2


def test_confirmed_recall_is_zero_without_expected_confirmed_cases() -> None:
    assert confirmed_recall(
        [Verdict.MISMATCH, Verdict.UNVERIFIABLE],
        [Verdict.CONFIRMED, Verdict.MISMATCH],
    ) == 0.0


def test_public_metrics_normalize_serialized_verdicts() -> None:
    expected = ["confirmed", "mismatch"]
    actual = ["confirmed", "confirmed"]

    assert false_clearance_rate(expected, actual) == 1.0
    assert confirmed_recall(expected, actual) == 1.0


def test_evaluation_normalizes_serialized_actual_verdicts() -> None:
    summary = evaluate_verdicts(
        [_case("serialized", Verdict.MISMATCH)],
        ["unverifiable"],
    )

    assert summary.coverage == 0.0
    assert summary.unverifiable_count == 1


@pytest.mark.parametrize("metric", [false_clearance_rate, confirmed_recall])
@pytest.mark.parametrize(
    ("expected", "actual"),
    [(["not-a-verdict"], ["confirmed"]), (["confirmed"], ["not-a-verdict"]), (["confirmed"], [None])],
)
def test_public_metrics_reject_unknown_or_malformed_verdicts(
    metric: object, expected: list[object], actual: list[object]
) -> None:
    with pytest.raises(ValueError, match="verdict"):
        metric(expected, actual)  # type: ignore[operator]


def test_evaluation_rejects_unknown_serialized_actual_verdict() -> None:
    with pytest.raises(ValueError, match="verdict"):
        evaluate_verdicts([_case("invalid-actual", Verdict.MISMATCH)], ["not-a-verdict"])
