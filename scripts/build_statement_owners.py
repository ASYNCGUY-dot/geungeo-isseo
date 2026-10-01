"""Build the statement owner table for headerless attribution from a C003 snapshot.

For every header block in every product, each target support statement on its lines is counted
for the block's owner: the target family ("group:<target>") or the normalized header name. The
value is the number of distinct companies. Headerless fields are not counted, so the table only
reflects wording that companies wrote under an explicit ingredient name.
"""

import argparse
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from claimledger.headerless import (
    HEADERLESS_ATTRIBUTION_VERSION,
    MIN_COMPANIES,
    STATEMENT_OWNERS_VERSION,
    owner_key,
)
from claimledger.official_v2 import (
    OFFICIAL_FUNCTION_V2_VERSION,
    parse_official_function_v2,
    support_statements,
)
from claimledger.snapshot import parse_aware_datetime


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the statement owner table")
    parser.add_argument("--source-export", type=Path, required=True)
    parser.add_argument("--source-retrieved-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def build_owners(rows: Iterable[Mapping[str, str]]) -> dict[str, dict[str, int]]:
    companies: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in rows:
        text = row.get("primary_function") or ""
        if not text.strip():
            continue
        company = row.get("company") or row["report_no"]
        for block in parse_official_function_v2(text).blocks:
            if block.header is None:
                continue
            owner = owner_key(block.header)
            for start, end in block.body_spans:
                for statement in support_statements(text[start:end]):
                    companies[statement][owner].add(company)
    return {
        statement: {owner: len(names) for owner, names in sorted(by_owner.items())}
        for statement, by_owner in sorted(companies.items())
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        retrieved_at = parse_aware_datetime(args.source_retrieved_at, "--source-retrieved-at")
        data = args.source_export.read_bytes()
        rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    except (ValueError, OSError) as exc:
        print(f"error: {exc}")
        return 3
    statements = build_owners(rows)
    payload = {
        "table_version": STATEMENT_OWNERS_VERSION,
        "attribution_version": HEADERLESS_ATTRIBUTION_VERSION,
        "source": {
            "source_id": "C003",
            "file_name": args.source_export.name,
            "sha256": hashlib.sha256(data).hexdigest().upper(),
            "retrieved_at": retrieved_at.isoformat(),
        },
        "parser_version": OFFICIAL_FUNCTION_V2_VERSION,
        "rule": (
            "target support statements on header-block lines; value = distinct companies per owner "
            "(target family 'group:<target>' or normalized header name); headerless fields not counted"
        ),
        "min_companies": MIN_COMPANIES,
        "statements": statements,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"{len(statements)} statements -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
