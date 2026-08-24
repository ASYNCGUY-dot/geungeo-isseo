from collections.abc import Sequence

from claimledger.domain import EvaluationCase, EvaluationSummary, Verdict


def _normalize_verdicts(
    values: Sequence[Verdict | str], *, label: str
) -> list[Verdict]:
    normalized: list[Verdict] = []
    for value in values:
        try:
            normalized.append(Verdict(value))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} contains an invalid verdict: {value!r}") from exc
    return normalized


def _validate_verdict_sequences(
    expected: Sequence[Verdict | str], actual: Sequence[Verdict | str]
) -> tuple[list[Verdict], list[Verdict]]:
    if not expected:
        raise ValueError("evaluation set is empty")
    if len(expected) != len(actual):
        raise ValueError("expected and actual lengths differ")
    return (
        _normalize_verdicts(expected, label="expected verdicts"),
        _normalize_verdicts(actual, label="actual verdicts"),
    )


def false_clearance_rate(
    expected: Sequence[Verdict | str], actual: Sequence[Verdict | str]
) -> float:
    expected_verdicts, actual_verdicts = _validate_verdict_sequences(expected, actual)

    non_confirmed_indices = [
        index
        for index, verdict in enumerate(expected_verdicts)
        if verdict is not Verdict.CONFIRMED
    ]
    if not non_confirmed_indices:
        return 0.0

    false_clearances = sum(
        actual_verdicts[index] is Verdict.CONFIRMED for index in non_confirmed_indices
    )
    return false_clearances / len(non_confirmed_indices)


def confirmed_recall(
    expected: Sequence[Verdict | str], actual: Sequence[Verdict | str]
) -> float:
    expected_verdicts, actual_verdicts = _validate_verdict_sequences(expected, actual)

    confirmed_indices = [
        index for index, verdict in enumerate(expected_verdicts) if verdict is Verdict.CONFIRMED
    ]
    if not confirmed_indices:
        return 0.0

    confirmed_predictions = sum(
        actual_verdicts[index] is Verdict.CONFIRMED for index in confirmed_indices
    )
    return confirmed_predictions / len(confirmed_indices)


def evaluate_verdicts(
    cases: Sequence[EvaluationCase], actual: Sequence[Verdict | str]
) -> EvaluationSummary:
    if not cases:
        raise ValueError("evaluation set is empty")
    if len(cases) != len(actual):
        raise ValueError("case and actual lengths differ")

    if any(case.frozen is not True for case in cases):
        raise ValueError("evaluation cases must be frozen")

    validated_cases = [EvaluationCase.model_validate(case.model_dump()) for case in cases]
    case_ids = [case.case_id for case in validated_cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("evaluation case IDs must be unique; duplicate ID found")

    expected = [case.expected_verdict for case in validated_cases]
    actual_verdicts = _normalize_verdicts(actual, label="actual verdicts")
    unverifiable_count = sum(verdict is Verdict.UNVERIFIABLE for verdict in actual_verdicts)
    sample_size = len(validated_cases)

    return EvaluationSummary(
        sample_size=sample_size,
        false_clearance_rate=false_clearance_rate(expected, actual_verdicts),
        confirmed_recall=confirmed_recall(expected, actual_verdicts),
        coverage=(sample_size - unverifiable_count) / sample_size,
        unverifiable_count=unverifiable_count,
    )


def zero_error_upper_bound(sample_size: int) -> float:
    if sample_size < 1:
        raise ValueError("sample_size must be at least 1")
    return 3 / sample_size
