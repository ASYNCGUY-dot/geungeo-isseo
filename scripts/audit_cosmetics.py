"""Phase 0 data gate for cosmetics: download and measure the MFDS functional cosmetics sources.

No cosmetics verdict is designed before this audit shows what the official data holds. For the
reported (보고) and reviewed (심사) product lists it writes a JSONL export and an audit report with
the total count, missing fields, duplicate item numbers, product names shared by several items,
withdrawn reports and the distribution of official functions.

The service key comes from DATA_GO_KR_SERVICE_KEY in the environment or, if absent, from that
single variable in --env-file. The key is never printed or written. Exports must stay in an
ignored path (the default is build/cosmetics/).

Exit codes: 0 measured, 3 source or input error.
"""

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

from claimledger.errors import DataSourceError
from claimledger.sources.functional_cosmetics import (
    REPORTED,
    SOURCES,
    CosmeticsSource,
    FunctionalCosmetic,
    FunctionalCosmeticsClient,
)

_KEY_NAME = "DATA_GO_KR_SERVICE_KEY"
_EXPORT_FIELDS = (
    "item_seq", "item_name", "company", "registered_on", "effect_text", "effect_code", "effect_name",
    "whitening", "wrinkle", "sunscreen", "spf", "pa", "withdrawn", "notice_class",
)
_REQUIRED_FIELDS = ("item_name", "company", "registered_on", "effect_text")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit the MFDS functional cosmetics sources")
    parser.add_argument("--service", choices=[*SOURCES, "both"], default="both")
    parser.add_argument("--output-dir", type=Path, default=Path("build/cosmetics"))
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, help="probe only: stop after this many pages")
    return parser.parse_args(argv)


def _api_key(env_file: Path | None) -> str:
    if key := os.environ.get(_KEY_NAME, "").strip():
        return key
    if env_file is None:
        return ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == _KEY_NAME and value.strip():
            return value.strip().strip("\"'")
    return ""


def _client(source: CosmeticsSource, key: str) -> FunctionalCosmeticsClient:
    return FunctionalCosmeticsClient(source, key, httpx.Client(timeout=30.0))


def fetch(client, page_size: int, max_pages: int | None) -> tuple[int, list[FunctionalCosmetic]]:
    items: list[FunctionalCosmetic] = []
    total, page_no = None, 1
    while total is None or len(items) < total:
        if max_pages is not None and page_no > max_pages:
            break
        page = client.fetch_page(page_no, page_size)
        total = page.total_count if total is None else total
        if not page.items:
            break
        items.extend(page.items)
        page_no += 1
    if max_pages is None and len(items) != total:
        raise DataSourceError(f"returned {len(items)} rows, expected {total}")
    return total or 0, items


def measure(source: CosmeticsSource, total: int, items: list[FunctionalCosmetic], text: str) -> dict:
    by_name: dict[str, set[str]] = defaultdict(set)
    for item in items:
        by_name[item.item_name].add(item.item_seq)
    fields = (*_REQUIRED_FIELDS, "effect_name") if source is REPORTED else _REQUIRED_FIELDS
    report = {
        "source_id": source.source_id,
        "endpoint": source.url,
        "retrieved_at": (items[0].retrieved_at if items else datetime.now(UTC)).isoformat(),
        "total_count": total,
        "row_count": len(items),
        "complete": len(items) == total,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest().upper(),
        "missing": {field: sum(1 for item in items if not getattr(item, field)) for field in fields},
        "duplicate_item_seq_rows": len(items) - len({item.item_seq for item in items}),
        "names_shared_by_several_items": sum(1 for seqs in by_name.values() if len(seqs) > 1),
        "distinct_effect_texts": len({item.effect_text for item in items if item.effect_text}),
    }
    if source is REPORTED:
        report["withdrawn_rows"] = sum(1 for item in items if item.withdrawn)
        report["effect_names"] = dict(Counter(item.effect_name for item in items if item.effect_name).most_common(40))
        report["flags"] = {
            flag: sum(1 for item in items if getattr(item, flag)) for flag in ("whitening", "wrinkle", "sunscreen")
        }
    else:
        report["notice_classes"] = dict(Counter(item.notice_class for item in items if item.notice_class))
    return report


def audit(source: CosmeticsSource, key: str, args: argparse.Namespace) -> dict:
    total, items = fetch(_client(source, key), args.page_size, args.max_pages)
    text = "".join(
        json.dumps({field: getattr(item, field) for field in _EXPORT_FIELDS}, ensure_ascii=False) + "\n"
        for item in items
    )
    report = measure(source, total, items, text)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.output_dir / f"functional-cosmetics-{source.key}"
    stem.with_suffix(".jsonl").write_text(text, encoding="utf-8", newline="\n")
    stem.with_suffix(".audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    sources = list(SOURCES.values()) if args.service == "both" else [SOURCES[args.service]]
    try:
        key = _api_key(args.env_file)
        if not key:
            raise DataSourceError(f"{_KEY_NAME} is not set")
        for source in sources:
            report = audit(source, key, args)
            missing = ", ".join(f"{field} {count}" for field, count in report["missing"].items())
            print(
                f"{source.key}: {report['row_count']} of {report['total_count']} rows"
                f"{'' if report['complete'] else ' (probe)'}; missing: {missing}; "
                f"shared names {report['names_shared_by_several_items']}"
            )
    except (DataSourceError, OSError) as exc:
        print(f"error: {exc}")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
