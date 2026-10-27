"""Score the health-food engine on the multi-sentence advertisement evaluation (claim-eval-v3).

Each case is one advertisement whose sentences carry expected labels (`none` for a sentence that
claims no function, null where the labelers disagreed). The whole advertisement goes through
`decide_ad`; a sentence takes the verdict of the claims whose spans overlap it, `confirmed` if any of
them is confirmed, so a confirmation that reaches a sentence labeled otherwise is a false clearance.
A sentence no claim overlaps gets `none`. Expected labels are blind AI labels, not human ground truth.

Exit codes: 0 scored, 1 false clearance found with --require-zero-false-clearance, 3 input error.
"""

import argparse
import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from claimledger.claims_v1 import CLAIM_EXTRACTION_VERSION, confirm_claims, extract_claims
from claimledger.domain import ConfirmedProduct, Verdict
from claimledger.snapshot import SnapshotError, load_c003_snapshot, parse_aware_datetime
from claimledger.verdict_v1 import CLAIM_VERDICT_VERSION, decide_ad

LABELS = ("confirmed", "mismatch", "unverifiable", "none")
_RANK = (Verdict.CONFIRMED, Verdict.MISMATCH, Verdict.UNVERIFIABLE)


class AdScoreError(ValueError):
    pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score the multi-sentence advertisement evaluation")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--source-export", type=Path, required=True)
    parser.add_argument("--source-retrieved-at", required=True)
    parser.add_argument("--output", type=Path, help="write the summary JSON here as well")
    parser.add_argument("--require-zero-false-clearance", action="store_true")
    return parser.parse_args(argv)


def _validate(case: dict) -> None:
    text = case["ad_text"]
    for segment in case["segments"]:
        start, end = segment["span"]
        if text[start:end] != segment["text"]:
            raise AdScoreError(f"{case['case_id']}/{segment['seg_no']}: the span does not hold the sentence")
        if segment["expected"] not in (*LABELS, None):
            raise AdScoreError(f"{case['case_id']}/{segment['seg_no']}: invalid label {segment['expected']!r}")


def _score_case(case: dict, product: ConfirmedProduct) -> dict:
    claims = confirm_claims(extract_claims(case["ad_text"]), "all")
    decisions = list(decide_ad(case["ad_text"], claims, product))
    segments = []
    for segment in case["segments"]:
        start, end = segment["span"]
        overlapping = [item for item in decisions if item.claim.span[0] < end and item.claim.span[1] > start]
        verdicts = {item.verdict for item in overlapping}
        actual = next((verdict.value for verdict in _RANK if verdict in verdicts), "none")
        segments.append({
            "seg_no": segment["seg_no"],
            "expected": segment["expected"],
            "actual": actual,
            "reasons": sorted({item.reason.value for item in overlapping}),
        })
    return {"case_id": case["case_id"], "scenario": case.get("scenario"), "layout": case.get("layout"), "segments": segments}


def _ratio(count: int, of: int) -> dict:
    return {"count": count, "of": of}


def _metrics(rows: list[tuple[str, str]]) -> dict:
    """False clearance and confirmed recall over (expected, actual) pairs of labeled sentences."""
    claims = [actual for expected, actual in rows if expected in {"mismatch", "unverifiable"}]
    nones = [actual for expected, actual in rows if expected == "none"]
    confirmed = [actual for expected, actual in rows if expected == "confirmed"]
    return {
        "false_clearance_count": claims.count("confirmed") + nones.count("confirmed"),
        "false_clearance_claims": _ratio(claims.count("confirmed"), len(claims)),
        "false_clearance_none": _ratio(nones.count("confirmed"), len(nones)),
        "confirmed_recall": _ratio(confirmed.count("confirmed"), len(confirmed)),
    }


def score(cases: Sequence[dict], products: dict[str, ConfirmedProduct]) -> dict:
    results = []
    for case in cases:
        _validate(case)
        if case["report_no"] not in products:
            raise AdScoreError(f"{case['case_id']}: report number {case['report_no']} is not in the snapshot")
        results.append(_score_case(case, products[case["report_no"]]))
    labeled = [
        (row, segment) for row in results for segment in row["segments"] if segment["expected"] is not None
    ]
    pairs = [(segment["expected"], segment["actual"]) for _, segment in labeled]
    expected_counts = {label: sum(1 for expected, _ in pairs if expected == label) for label in LABELS}
    complete = [row for row in results if all(segment["expected"] is not None for segment in row["segments"])]
    honest = [
        row for row in complete
        if all(segment["expected"] in {"confirmed", "none"} for segment in row["segments"])
        and any(segment["expected"] == "confirmed" for segment in row["segments"])
    ]
    by: dict[str, dict[str, list]] = {"scenario": defaultdict(list), "layout": defaultdict(list)}
    for row, segment in labeled:
        for key in by:
            by[key][row[key] or ""].append((segment["expected"], segment["actual"]))
    return {
        "engine": {"extraction": CLAIM_EXTRACTION_VERSION, "verdict": CLAIM_VERDICT_VERSION},
        "case_count": len(results),
        "segment_count": sum(len(row["segments"]) for row in results),
        "labeled_segment_count": len(pairs),
        "expected_counts": expected_counts,
        **_metrics(pairs),
        "segment_agreement": _ratio(sum(1 for expected, actual in pairs if expected == actual), len(pairs)),
        "ads": {
            "false_cleared": sum(
                1 for row in results
                if any(s["actual"] == "confirmed" and s["expected"] not in {"confirmed", None} for s in row["segments"])
            ),
            "fully_labeled": len(complete),
            "expected_all_confirmed": len(honest),
            "engine_all_confirmed": sum(
                1 for row in honest
                if all(s["actual"] == ("confirmed" if s["expected"] == "confirmed" else "none") for s in row["segments"])
            ),
        },
        "by_scenario": {key: _metrics(value) for key, value in sorted(by["scenario"].items())},
        "by_layout": {key: _metrics(value) for key, value in sorted(by["layout"].items())},
        "results": results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        retrieved_at = parse_aware_datetime(args.source_retrieved_at, "--source-retrieved-at")
        cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]
        products = {
            product.report_no: ConfirmedProduct(product=product, confirmed_by_user=True)
            for product in load_c003_snapshot(args.source_export, retrieved_at)
        }
        summary = score(cases, products)
    except (AdScoreError, SnapshotError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: {exc}")
        return 3
    text = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    print(json.dumps({key: value for key, value in summary.items() if key != "results"}, ensure_ascii=False, indent=2))
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8", newline="\n")
    if args.require_zero_false_clearance and summary["false_clearance_count"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
