"""Check a cosmetics advertisement against a functional cosmetic's official efficacy.

Works on the local export written by scripts/audit_cosmetics.py, without the network. The product
is never chosen automatically: --query only lists candidate records with their official efficacy.
--ad-text alone lists the claims the rules would judge and the sentences they would not, with no
verdict. A verdict needs the record number the user picked (--record-id) and an explicit
confirmation of which extracted claims to judge (--confirm-claims all, or claim ids such as C1 C2).

Exit codes: 0 done, 3 input error.
"""

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from claimledger.cosmetics_claims import (
    confirm_cosmetic_claims,
    extract_cosmetic_claims,
    normalize_ad_text,
    unread_sentences,
)
from claimledger.cosmetics_receipt import build_cosmetic_receipt
from claimledger.cosmetics_verdict import ConfirmedCosmetic, decide_cosmetic_ad
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
    return normalize_ad_text(text)


def _candidates(args: argparse.Namespace) -> dict:
    _, items = load_cosmetics_export(args.export_dir, SOURCES[args.source])
    return {"candidates": [
        {
            "record_id": item.record_id, "item_name": item.item_name, "company": item.company,
            "registered_on": item.registered_on, "official_statement": item.statement,
        }
        for item in search(items, args.query, args.limit)
    ]}


def _extraction(args: argparse.Namespace) -> dict:
    """What the rules would judge and what they would not, for the user to confirm."""
    text = _ad_text(args)
    return {
        "extracted_claims": [
            {"claim_id": claim.claim_id, "text": claim.text} for claim in extract_cosmetic_claims(text)
        ],
        "unread_text": [sentence.text for sentence in unread_sentences(text)],
    }


def _receipt(args: argparse.Namespace) -> dict:
    _, items = load_cosmetics_export(args.export_dir, SOURCES[args.source])
    product = next((item for item in items if item.record_id == args.record_id), None)
    if product is None:
        raise InputError(f"record {args.record_id} is not in the {args.source} export")
    text = _ad_text(args)
    selected = "all" if args.confirm_claims == ["all"] else args.confirm_claims
    claims = confirm_cosmetic_claims(extract_cosmetic_claims(text), selected)
    confirmed = ConfirmedCosmetic(product=product, confirmed_by_user=True)
    decisions = decide_cosmetic_ad(text, claims, confirmed)
    return build_cosmetic_receipt(text, confirmed, decisions, datetime.now(UTC)).model_dump(mode="json")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    has_text = args.ad_text is not None or args.ad_text_file is not None
    try:
        if args.confirm_claims is not None and args.record_id is None:
            raise InputError("--confirm-claims needs the --record-id of the product the user confirmed")
        if args.confirm_claims is not None:
            body = _receipt(args)
        elif has_text:
            body = _extraction(args)
        elif args.record_id is None and args.query is not None:
            body = _candidates(args)
        else:
            raise InputError(
                "give --query to list candidates, --ad-text to list the claims to confirm, "
                "or --record-id with --confirm-claims to judge"
            )
    except (InputError, DataSourceError, OSError, ValueError) as error:
        print(f"error: {error}")
        return 3
    print(json.dumps(body, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
