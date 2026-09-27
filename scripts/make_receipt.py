"""Build a claim-by-claim evidence receipt for a text advertisement and a user-confirmed product.

Exit codes: 0 receipt written, 2 product confirmation still required (candidates printed),
3 input or output error. Product identity is never auto-confirmed from a search.
"""

import argparse
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from claimledger.claims_v1 import confirm_claims, extract_claims
from claimledger.domain import ConfirmedProduct, ProductCandidate
from claimledger.errors import IdentityRequiredError
from claimledger.identity import confirm_candidate
from claimledger.products import search_products
from claimledger.receipt import (
    PUBLIC_VERDICT_LABELS,
    build_receipt,
    receipt_to_json,
    render_markdown,
)
from claimledger.snapshot import load_c003_snapshot, parse_aware_datetime
from claimledger.verdict_v1 import decide_claim


class ReceiptCliError(ValueError):
    pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a claim evidence receipt (근거영수증)")
    parser.add_argument("--source-export", type=Path, required=True, help="C003 6-field JSONL snapshot")
    parser.add_argument(
        "--source-retrieved-at",
        required=True,
        help="timezone-aware ISO time when the C003 snapshot was retrieved",
    )
    parser.add_argument("--ad-text-file", type=Path, required=True, help="UTF-8 advertisement text")
    parser.add_argument("--report-no", help="user-confirmed C003 report number")
    parser.add_argument("--query", help="search candidates only; prints them and exits with code 2")
    parser.add_argument("--confirm-claims", help="'all' or comma-separated claim ids such as C1,C3")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--generated-at", help="timezone-aware ISO time for reproducible output")
    return parser.parse_args(argv)


def _confirm(products: list[ProductCandidate], report_no: str) -> ConfirmedProduct:
    candidates = [product for product in products if product.report_no == report_no]
    try:
        return confirm_candidate(candidates, report_no)
    except IdentityRequiredError as exc:
        raise ReceiptCliError(f"report number {report_no} cannot be confirmed: {exc}") from exc


def _claim_selection(value: str | None) -> list[str] | str:
    if value is None:
        return []
    if value.strip() == "all":
        return "all"
    return [item.strip() for item in value.split(",") if item.strip()]


def _write_outputs(output_dir: Path, json_text: str, markdown: str) -> None:
    targets = (output_dir / "receipt.json", output_dir / "receipt.md")
    if any(path.exists() for path in targets):
        raise ReceiptCliError("receipt files already exist; choose a new output directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    targets[0].write_text(json_text, encoding="utf-8", newline="\n")
    targets[1].write_text(markdown, encoding="utf-8", newline="\n")


def run(args: argparse.Namespace) -> int:
    retrieved_at = parse_aware_datetime(args.source_retrieved_at, "--source-retrieved-at")
    generated_at = (
        parse_aware_datetime(args.generated_at, "--generated-at") if args.generated_at else datetime.now(UTC)
    )
    products = load_c003_snapshot(args.source_export, retrieved_at)

    if args.report_no is None and args.query:
        results = search_products(products, args.query)
        print("제품을 확정해야 판정할 수 있습니다. 아래 후보 중 --report-no로 선택하세요.")
        for result in results:
            candidate = result.candidate
            print(f"  {candidate.report_no}\t{candidate.name}\t{candidate.company}")
        return 2

    product = _confirm(products, args.report_no) if args.report_no else None
    ad_text = args.ad_text_file.read_text(encoding="utf-8")
    claims = extract_claims(ad_text)
    try:
        claims = confirm_claims(claims, _claim_selection(args.confirm_claims))
    except ValueError as exc:
        raise ReceiptCliError(str(exc)) from exc
    decisions = [decide_claim(claim, product) for claim in claims]
    receipt = build_receipt(ad_text, product, decisions, generated_at)
    _write_outputs(args.output_dir, receipt_to_json(receipt), render_markdown(receipt))

    counts = Counter(decision.verdict for decision in decisions)
    summary = ", ".join(f"{PUBLIC_VERDICT_LABELS[verdict]} {count}" for verdict, count in counts.items())
    print(f"근거영수증을 만들었습니다: {args.output_dir}")
    print(f"주장 {len(decisions)}개 — {summary or '판정할 주장 없음'}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(args)
    except (ReceiptCliError, OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
