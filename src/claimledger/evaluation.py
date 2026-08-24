from collections.abc import Sequence

from claimledger.domain import EvaluationCase, EvaluationSummary, Verdict


def _validate_verdict_sequences(expected: Sequence[Verdict], actual: Sequence[Verdict]) -> None:
    if not expected:
        raise ValueError("evaluation set is empty")
    if len(expected) != len(actual):
        raise ValueError("expected and actual lengths differ")


def false_clearance_rate(expected: Sequence[Verdict], actual: Sequence[Verdict]) -> float:
    _validate_verdict_sequences(expected, actual)

    non_confirmed_indices = [
        index for index, verdict in enumerate(expected) if verdict is not Verdict.CONFIRMED
    ]
    if not non_confirmed_indices:
        return 0.0

    false_clearances = sum(
        actual[index] is Verdict.CONFIRMED for index in non_confirmed_indices
    )
    return false_clearances / len(non_confirmed_indices)


def confirmed_recall(expected: Sequence[Verdict], actual: Sequence[Verdict]) -> float:
    _validate_verdict_sequences(expected, actual)

    confirmed_indices = [
        index for index, verdict in enumerate(expected) if verdict is Verdict.CONFIRMED
    ]
    if not confirmed_indices:
        return 0.0

    confirmed_predictions = sum(
        actual[index] is Verdict.CONFIRMED for index in confirmed_indices
    )
    return confirmed_predictions / len(confirmed_indices)


def evaluate_verdicts(
    cases: Sequence[EvaluationCase], actual: Sequence[Verdict]
) -> EvaluationSummary:
    if not cases:
        raise ValueError("evaluation set is empty")
    if len(cases) != len(actual):
        raise ValueError("case and actual lengths differ")

    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("evaluation case IDs must be unique; duplicate ID found")
    if any(case.frozen is not True for case in cases):
        raise ValueError("evaluation cases must be frozen")

    expected = [case.expected_verdict for case in cases]
    unverifiable_count = sum(verdict is Verdict.UNVERIFIABLE for verdict in actual)
    sample_size = len(cases)

    return EvaluationSummary(
        sample_size=sample_size,
        false_clearance_rate=false_clearance_rate(expected, actual),
        confirmed_recall=confirmed_recall(expected, actual),
        coverage=(sample_size - unverifiable_count) / sample_size,
        unverifiable_count=unverifiable_count,
    )


def zero_error_upper_bound(sample_size: int) -> float:
    if sample_size < 1:
        raise ValueError("sample_size must be at least 1")
    return 3 / sample_size
