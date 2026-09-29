"""Build a reviewed official header or clause vocabulary from a C003 snapshot.

A normalized header name (--kind header) or body clause (--kind clause) enters the vocabulary when
at least --min-companies distinct companies use it in their official function text and the
reviewed exclusions file does not remove it. The parser holds the whole field when any other
header or body clause sits next to evidence.
"""

import argparse
import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from claimledger.official_v2 import (
    normalize_header_name,
    segment_body_clauses,
    segment_header_names,
)
from claimledger.snapshot import parse_aware_datetime

VOCABULARY_VERSIONS = {
    "header": "official-header-vocabulary-v1",
    "clause": "official-clause-vocabulary-v1",
}


class VocabularyError(ValueError):
    pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an official header or clause vocabulary")
    parser.add_argument("--kind", choices=sorted(VOCABULARY_VERSIONS), default="header")
    parser.add_argument("--source-export", type=Path, required=True)
    parser.add_argument("--source-retrieved-at", required=True)
    parser.add_argument("--exclusions", type=Path, required=True)
    parser.add_argument("--min-companies", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def _names(kind: str, text: str) -> list[str]:
    if kind == "clause":
        return list(segment_body_clauses(text))
    return [normalize_header_name(header) for header in segment_header_names(text)]


def build_vocabulary(
    source: Path, retrieved_at: str, review: dict, min_companies: int, kind: str = "header",
) -> dict:
    companies: dict[str, set[str]] = defaultdict(set)
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        for name in _names(kind, row.get("primary_function") or ""):
            if name:
                companies[name].add(row.get("company") or "")
    candidates = {name for name, owners in companies.items() if len(owners) >= min_companies}
    exclusions: dict[str, str] = review["exclusions"]
    stale = sorted(set(exclusions) - candidates)
    if stale:
        raise VocabularyError(f"exclusions are not vocabulary candidates: {stale}")
    return {
        "vocabulary_version": VOCABULARY_VERSIONS[kind],
        "source": {
            "source_id": "C003",
            "file_name": source.name,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest().upper(),
            "retrieved_at": retrieved_at,
        },
        "rule": (
            f"normalized {kind} names used by >= {min_companies} distinct companies, "
            "minus reviewed exclusions"
        ),
        "min_companies": min_companies,
        "candidate_count": len(candidates),
        "review": {key: value for key, value in review.items() if key != "exclusions"},
        "excluded": dict(sorted(exclusions.items())),
        "names": sorted(candidates - set(exclusions)),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        retrieved_at = parse_aware_datetime(args.source_retrieved_at, "--source-retrieved-at")
        review = json.loads(args.exclusions.read_text(encoding="utf-8"))
        payload = build_vocabulary(
            args.source_export, retrieved_at.isoformat(), review, args.min_companies, args.kind
        )
    except (VocabularyError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}")
        return 3
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    args.output.write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(payload['names'])} names ({payload['candidate_count']} candidates) -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
