from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from claimledger.domain import EvaluationCase, Verdict
from claimledger.evaluation import evaluate_verdicts

NOW = datetime(2026, 8, 24, tzinfo=UTC)


def _case(case_id: str, *, frozen: bool = True) -> EvaluationCase:
    return EvaluationCase(
        case_id=case_id,
        ingredient_group="lutein_zeaxanthin",
        expected_verdict=Verdict.MISMATCH,
        frozen=frozen,
        report_no=f"C003-{case_id}",
        source_id="C003",
        retrieved_at=NOW,
        rule_version="evaluation-label-v1",
        matched_source_text="루테인 지아잔틴 복합 추출물",
        source_url=f"https://example.test/c003/{case_id}",
    )


def test_evaluation_case_requires_frozen_identity_and_expected_verdict() -> None:
    case = EvaluationCase(
        case_id="core-lutein-001",
        ingredient_group="lutein_zeaxanthin",
        expected_verdict=Verdict.MISMATCH,
        frozen=True,
        report_no="C003-CORE-LUTEIN-001",
        source_id="C003",
        retrieved_at=NOW,
        rule_version="evaluation-label-v1",
        matched_source_text="루테인 지아잔틴 복합 추출물",
        source_url="https://example.test/c003/CORE-LUTEIN-001",
    )

    assert case.frozen is True
    assert case.report_no == "C003-CORE-LUTEIN-001"
    assert case.source_id == "C003"
    assert case.source_url.endswith("CORE-LUTEIN-001")


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
        report_no="C003-UNSAFE-CASE",
        source_id="C003",
        retrieved_at=NOW,
        rule_version="evaluation-label-v1",
        matched_source_text="루테인 지아잔틴 복합 추출물",
        source_url="https://example.test/c003/UNSAFE-CASE",
    )

    with pytest.raises(ValueError, match="frozen"):
        evaluate_verdicts([unfrozen_case], [Verdict.MISMATCH])


@pytest.mark.parametrize(
    "field, value",
    [
        ("case_id", " "),
        ("ingredient_group", " "),
        ("report_no", " "),
        ("source_id", " "),
        ("rule_version", " "),
        ("matched_source_text", " "),
        ("source_url", " "),
    ],
)
def test_evaluation_case_rejects_blank_identity_or_provenance(field: str, value: str) -> None:
    payload = _case("traceable").model_dump()
    payload[field] = value

    with pytest.raises(ValidationError):
        EvaluationCase.model_validate(payload)


def test_evaluation_case_rejects_missing_retrieval_provenance() -> None:
    payload = _case("traceable").model_dump()
    payload.pop("retrieved_at")

    with pytest.raises(ValidationError, match="retrieved_at"):
        EvaluationCase.model_validate(payload)


def test_evaluation_case_preserves_literal_matched_source_text() -> None:
    literal_source_text = "  루테인 지아잔틴 복합 추출물\n"
    payload = _case("literal-source").model_dump()
    payload["matched_source_text"] = literal_source_text

    case = EvaluationCase.model_validate(payload)

    assert case.matched_source_text == literal_source_text


def test_evaluation_revalidates_frozen_case_constructed_with_blank_provenance() -> None:
    invalid_case = EvaluationCase.model_construct(
        case_id="constructed-invalid",
        ingredient_group="lutein_zeaxanthin",
        expected_verdict=Verdict.MISMATCH,
        frozen=True,
        report_no=" ",
        source_id="C003",
        retrieved_at=NOW,
        rule_version="evaluation-label-v1",
        matched_source_text="루테인 지아잔틴 복합 추출물",
        source_url="https://example.test/c003/CONSTRUCTED-INVALID",
    )

    with pytest.raises(ValidationError, match="report_no"):
        evaluate_verdicts([invalid_case], [Verdict.MISMATCH])
