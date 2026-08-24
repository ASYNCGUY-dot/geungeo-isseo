import pytest

from claimledger.domain import EvaluationCase, Verdict
from claimledger.evaluation import (
    confirmed_recall,
    evaluate_verdicts,
    false_clearance_rate,
    zero_error_upper_bound,
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
        EvaluationCase(
            case_id="a",
            ingredient_group="omega3",
            expected_verdict=Verdict.CONFIRMED,
            frozen=True,
        ),
        EvaluationCase(
            case_id="b",
            ingredient_group="omega3",
            expected_verdict=Verdict.MISMATCH,
            frozen=True,
        ),
        EvaluationCase(
            case_id="c",
            ingredient_group="omega3",
            expected_verdict=Verdict.UNVERIFIABLE,
            frozen=True,
        ),
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
