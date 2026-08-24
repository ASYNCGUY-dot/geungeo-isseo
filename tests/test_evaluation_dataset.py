import pytest
from pydantic import ValidationError

from claimledger.domain import EvaluationCase, Verdict
from claimledger.evaluation import evaluate_verdicts


def _case(case_id: str, *, frozen: bool = True) -> EvaluationCase:
    return EvaluationCase(
        case_id=case_id,
        ingredient_group="lutein_zeaxanthin",
        expected_verdict=Verdict.MISMATCH,
        frozen=frozen,
    )


def test_evaluation_case_requires_frozen_identity_and_expected_verdict() -> None:
    case = EvaluationCase(
        case_id="core-lutein-001",
        ingredient_group="lutein_zeaxanthin",
        expected_verdict=Verdict.MISMATCH,
        frozen=True,
    )

    assert case.frozen is True


def test_evaluation_case_is_immutable() -> None:
    case = _case("core-lutein-001")

    with pytest.raises(ValidationError, match="frozen"):
        case.case_id = "core-lutein-002"


def test_evaluation_rejects_an_empty_dataset() -> None:
    with pytest.raises(ValueError, match="empty"):
        evaluate_verdicts([], [])


def test_evaluation_rejects_duplicate_case_ids() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        evaluate_verdicts([_case("duplicate"), _case("duplicate")], [Verdict.MISMATCH] * 2)


def test_evaluation_rejects_mismatched_case_and_actual_lengths() -> None:
    with pytest.raises(ValueError, match="length"):
        evaluate_verdicts([_case("a")], [])


def test_evaluation_rejects_case_that_bypasses_frozen_validation() -> None:
    unfrozen_case = EvaluationCase.model_construct(
        case_id="unsafe-case",
        ingredient_group="lutein_zeaxanthin",
        expected_verdict=Verdict.MISMATCH,
        frozen=False,
    )

    with pytest.raises(ValueError, match="frozen"):
        evaluate_verdicts([unfrozen_case], [Verdict.MISMATCH])
