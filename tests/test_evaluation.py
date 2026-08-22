import pytest

from claimledger.domain import Verdict
from claimledger.evaluation import false_clearance_rate, zero_error_upper_bound


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
