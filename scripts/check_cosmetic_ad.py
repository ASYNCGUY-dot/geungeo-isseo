"""Check a cosmetics advertisement against a functional cosmetic's official efficacy.

Works on the local export written by scripts/audit_cosmetics.py, without the network. The product
is never chosen automatically: --query only lists candidate records with their official efficacy,
and a verdict needs the record number the user picked (--record-id) and an explicit confirmation
of which extracted claims to judge (--confirm-claims all, or claim ids such as C1 C2).

Exit codes: 0 done, 3 input error.
"""

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from claimledger.cosmetics_claims import confirm_cosmetic_claims, extract_cosmetic_claims
from claimledger.cosmetics_receipt import build_cosmetic_receipt
from claimledger.cosmetics_verdict import ConfirmedCosmetic, decide_cosmetic_claim
from claimledger.errors import DataSourceError
from claimledger.official_v2 import _compact
from claimledger.sources.functional_cosmetics import (
    SOURCES,
    FunctionalCosmetic,
    load_cosmetics_export,
)

MAX_AD_TEXT_LENGTH = 5000


class InputError(ValueError):
    pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check a cosmetics advertisement")
    parser.add_argument("--export-dir", type=Path, default=Path("build/cosmetics"))
    parser.add_argument("--source", choices=list(SOURCES), default="reported")
    parser.add_argument("--query", help="list candidate records by product or company name")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--record-id", help="record number of the product the user confirmed")
    parser.add_argument("--ad-text")
    parser.add_argument("--ad-text-file", type=Path)
    parser.add_argument("--confirm-claims", nargs="+", help="'all' or the claim ids to judge")
    return parser.parse_args(argv)


def search(items: Sequence[FunctionalCosmetic], query: str, limit: int) -> list[FunctionalCosmetic]:
    """Records whose product or company name contains every word of the query, newest first."""
    words = [_compact(word)[0] for word in query.split()]
    if not words:
        raise InputError("the query is empty")
    hits = [
        item for item in items
        if all(word in _compact(f"{item.item_name} {item.company}")[0] for word in words)
    ]
    hits.sort(key=lambda item: (item.registered_on, item.record_id), reverse=True)
    return hits[: max(1, limit)]


def _ad_text(args: argparse.Namespace) -> str:
    text = args.ad_text_file.read_text(encoding="utf-8") if args.ad_text_file else (args.ad_text or "")
    if not text.strip():
        raise InputError("the advertisement text is empty")
    if len(text) > MAX_AD_TEXT_LENGTH:
        raise InputError(f"the advertisement text is longer than {MAX_AD_TEXT_LENGTH} characters")
    return text


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        _, items = load_cosmetics_export(args.export_dir, SOURCES[args.source])
        if args.record_id is None:
            if args.query is None:
                raise InputError("give --query to list candidates or --record-id to judge")
            body = {"candidates": [
                {
                    "record_id": item.record_id, "item_name": item.item_name, "company": item.company,
                    "registered_on": item.registered_on, "official_statement": item.statement,
                }
                for item in search(items, args.query, args.limit)
            ]}
        else:
            if args.confirm_claims is None:
                raise InputError("--confirm-claims is required: 'all' or the claim ids to judge")
            product = next((item for item in items if item.record_id == args.record_id), None)
            if product is None:
                raise InputError(f"record {args.record_id} is not in the {args.source} export")
            text = _ad_text(args)
            selected = "all" if args.confirm_claims == ["all"] else args.confirm_claims
            claims = confirm_cosmetic_claims(extract_cosmetic_claims(text), selected)
            confirmed = ConfirmedCosmetic(product=product, confirmed_by_user=True)
            decisions = [decide_cosmetic_claim(claim, confirmed) for claim in claims]
            body = build_cosmetic_receipt(text, confirmed, decisions, datetime.now(UTC)).model_dump(mode="json")
    except (InputError, DataSourceError, OSError, ValueError) as error:
        print(f"error: {error}")
        return 3
    print(json.dumps(body, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
