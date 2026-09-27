"""Evaluate the core MVP pipeline on a development case set.

Each case is one advertisement sentence and, optionally, a user-confirmed report number. The
script extracts claims, confirms them, decides verdicts and compares them with the expected
verdicts. Expected labels in the development set are developer labels, not human ground truth.

Exit codes: 0 evaluated, 1 false clearance found with --require-zero-false-clearance,
3 input error.
"""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ValidationError

from claimledger.claims_v1 import confirm_claims, extract_claims
from claimledger.domain import ConfirmedProduct, ProductCandidate, Verdict
from claimledger.evaluation import confirmed_recall, false_clearance_rate
from claimledger.snapshot import SnapshotError, load_c003_snapshot, parse_aware_datetime
from claimledger.verdict_v1 import decide_claim


class DevCase(BaseModel):
    model_config = {"frozen": True}

    case_id: str
    report_no: str | None
    ad_text: str
    expected_verdict: Verdict | None
    note: str = ""


class DevCaseError(ValueError):
    pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate development cases for the core MVP slice")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--source-export", type=Path, required=True)
    parser.add_argument("--source-retrieved-at", required=True)
    parser.add_argument("--output", type=Path, help="write the summary JSON here as well")
    parser.add_argument("--require-zero-false-clearance", action="store_true")
    return parser.parse_args(argv)


def load_cases(path: Path) -> list[DevCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        cases = [DevCase.model_validate(item) for item in payload["cases"]]
    except (KeyError, TypeError, ValidationError) as exc:
        raise DevCaseError(f"invalid case file: {exc}") from exc
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise DevCaseError("case ids must be unique")
    return cases


def _evaluate_case(case: DevCase, products: dict[str, ProductCandidate]) -> dict:
    product = None
    if case.report_no is not None:
        if case.report_no not in products:
            raise DevCaseError(f"{case.case_id}: report number {case.report_no} is not in the snapshot")
        product = ConfirmedProduct(product=products[case.report_no], confirmed_by_user=True)
    claims = confirm_claims(extract_claims(case.ad_text), "all")
    decisions = [decide_claim(claim, product) for claim in claims]

    if case.expected_verdict is None:
        outcome = "agree" if not decisions else "unexpected_claim"
        actual = decisions[0].verdict if decisions else None
        reason = decisions[0].reason.value if decisions else None
    elif len(decisions) != 1:
        # A missing claim means no judgment was made. Several claims count as confirmed if any is.
        actual = (
            Verdict.CONFIRMED
            if any(item.verdict is Verdict.CONFIRMED for item in decisions)
            else Verdict.UNVERIFIABLE
        )
        reason = "CLAIM_NOT_EXTRACTED" if not decisions else "MULTIPLE_CLAIMS"
        outcome = "claim_count_error"
    else:
        actual = decisions[0].verdict
        reason = decisions[0].reason.value
        outcome = "agree" if actual is case.expected_verdict else "disagree"
    return {
        "case_id": case.case_id,
        "report_no": case.report_no,
        "expected_verdict": case.expected_verdict.value if case.expected_verdict else None,
        "actual_verdict": actual.value if actual else None,
        "reason_code": reason,
        "claim_count": len(decisions),
        "outcome": outcome,
    }


def evaluate(cases: Sequence[DevCase], products: Sequence[ProductCandidate]) -> dict:
    by_report = {product.report_no: product for product in products}
    results = [_evaluate_case(case, by_report) for case in cases]
    judged = [row for row in results if row["expected_verdict"] is not None]
    expected = [row["expected_verdict"] for row in judged]
    actual = [row["actual_verdict"] for row in judged]
    false_clearances = sum(
        1 for exp, act in zip(expected, actual, strict=True) if exp != "confirmed" and act == "confirmed"
    )
    unexpected = [row for row in results if row["outcome"] == "unexpected_claim"]
    return {
        "case_count": len(results),
        "judged_case_count": len(judged),
        "exact_agreement_count": sum(1 for row in judged if row["outcome"] == "agree"),
        "false_clearance_count": false_clearances
        + sum(1 for row in unexpected if row["actual_verdict"] == "confirmed"),
        "false_clearance_rate": false_clearance_rate(expected, actual) if judged else 0.0,
        "confirmed_recall": confirmed_recall(expected, actual) if judged else 0.0,
        "coverage": (
            sum(1 for value in actual if value != "unverifiable") / len(judged) if judged else 0.0
        ),
        "claim_extraction_error_count": sum(
            1 for row in results if row["outcome"] in {"claim_count_error", "unexpected_claim"}
        ),
        "results": results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        retrieved_at = parse_aware_datetime(args.source_retrieved_at, "--source-retrieved-at")
        cases = load_cases(args.cases)
        summary = evaluate(cases, load_c003_snapshot(args.source_export, retrieved_at))
    except (DevCaseError, SnapshotError, OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 3
    text = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    print(text, end="")
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8", newline="\n")
    if args.require_zero_false_clearance and summary["false_clearance_count"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
