from collections.abc import Sequence

from claimledger.domain import Verdict


def false_clearance_rate(expected: Sequence[Verdict], actual: Sequence[Verdict]) -> float:
    if not expected:
        raise ValueError("evaluation set is empty")
    if len(expected) != len(actual):
        raise ValueError("expected and actual lengths differ")

    non_confirmed_indices = [
        index for index, verdict in enumerate(expected) if verdict is not Verdict.CONFIRMED
    ]
    if not non_confirmed_indices:
        return 0.0

    false_clearances = sum(
        actual[index] is Verdict.CONFIRMED for index in non_confirmed_indices
    )
    return false_clearances / len(non_confirmed_indices)


def zero_error_upper_bound(sample_size: int) -> float:
    if sample_size < 1:
        raise ValueError("sample_size must be at least 1")
    return 3 / sample_size
