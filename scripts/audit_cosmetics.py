"""Phase 0 data gate for cosmetics: download and measure the MFDS functional cosmetics sources.

No cosmetics verdict is designed before this audit shows what the official data holds. For the
reported (보고) and reviewed (심사) product lists it writes a JSONL export and an audit report with
the total count, missing fields, duplicate record numbers, product names shared by several
records, withdrawn reports, unreadable efficacy documents and the distribution of official efficacy
statements. A row's statement is its efficacy document if readable, otherwise its efficacy sentence.
It also measures what decides whether rules can read the data: missing statements by registration
year, how few sentence forms cover the rows, rows whose document and sentence disagree, rows that
still carry the form's instruction text, and the overlap of the two lists.

--from-export measures an earlier export again without the network (the raw document is kept in
the export, so a changed document reader is applied to the same download).

The service key comes from the environment or, if absent, from --env-file. Each list may have its
own key (DATA_GO_KR_SERVICE_KEY_REPORTED, DATA_GO_KR_SERVICE_KEY_REVIEWED); otherwise the shared
DATA_GO_KR_SERVICE_KEY is used for both. Keys are never printed or written. Exports must stay in
an ignored path (the default is build/cosmetics/).

Exit codes: 0 measured, 3 source or input error.
"""

import argparse
import hashlib
import json
import os
import re
import time
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
    doc_paragraphs,
)

_KEY_NAME = "DATA_GO_KR_SERVICE_KEY"
_EXPORT_FIELDS = (
    "record_id", "item_name", "company", "registered_on", "effect_text", "effect_code", "effect_name",
    "effect_doc_unreadable", "whitening", "wrinkle", "sunscreen", "spf", "pa", "withdrawn", "notice_class",
    "effect_doc",
)
_REQUIRED_FIELDS = ("item_name", "company", "registered_on", "statement")
# Analysis only: list markers and parenthesised details (SPF, colour) are removed to count forms.
_MARKER = re.compile(r"^\s*(?:[-–·•*○▶]\s*\.?|\(?\d{1,2}\s*[.)。]|[①-⑳])\s*")
_PARENTHESISED = re.compile(r"\([^()]*\)")
# "※ 해당하는 효능효과 이외에는 모두 삭제하시기 바랍니다": the reporting form's own instruction.
_TEMPLATE_NOTE = "삭제하시기바랍니다"
_TOP_CORES = (1, 5, 10, 20, 40)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit the MFDS functional cosmetics sources")
    parser.add_argument("--service", choices=[*SOURCES, "both"], default="both")
    parser.add_argument("--output-dir", type=Path, default=Path("build/cosmetics"))
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--max-pages", type=int, help="probe only: stop after this many pages")
    parser.add_argument(
        "--from-export", type=Path,
        help="measure the export in this directory again instead of downloading",
    )
    return parser.parse_args(argv)


def _key_names(source: CosmeticsSource) -> tuple[str, str]:
    return f"{_KEY_NAME}_{source.key.upper()}", _KEY_NAME


def _api_key(env_file: Path | None, source: CosmeticsSource) -> str:
    """The source's own key if set, otherwise the shared one; the environment wins over the file."""
    from_file: dict[str, str] = {}
    if env_file is not None:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            from_file[name.strip()] = value.strip().strip("\"'")
    for name in _key_names(source):
        if key := os.environ.get(name, "").strip() or from_file.get(name, ""):
            return key
    return ""


def _client(source: CosmeticsSource, key: str) -> FunctionalCosmeticsClient:
    return FunctionalCosmeticsClient(source, key, httpx.Client(timeout=30.0))


# Timeouts, connection failures and 5xx answers are retried; key, quota and shape errors are not.
_TRANSIENT = re.compile(r"request timeout|request failed|returned HTTP 5\d\d")
_ATTEMPTS = 3


def _fetch_page(client, page_no: int, page_size: int):
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            return client.fetch_page(page_no, page_size)
        except DataSourceError as error:
            if attempt == _ATTEMPTS or not _TRANSIENT.search(str(error)):
                raise
            time.sleep(2.0 * attempt)
    raise AssertionError("unreachable")


def fetch(client, page_size: int, max_pages: int | None) -> tuple[int, list[FunctionalCosmetic]]:
    items: list[FunctionalCosmetic] = []
    total, page_no = None, 1
    while total is None or len(items) < total:
        if max_pages is not None and page_no > max_pages:
            break
        page = _fetch_page(client, page_no, page_size)
        total = page.total_count if total is None else total
        if not page.items:
            break
        items.extend(page.items)
        page_no += 1
    if max_pages is None and len(items) != total:
        raise DataSourceError(f"returned {len(items)} rows, expected {total}")
    return total or 0, items


def sentence_cores(statement: str) -> tuple[str, ...]:
    """Sentences of a statement without list markers, parenthesised details, spaces and periods."""
    cores: list[str] = []
    for line in statement.split("\n"):
        line = _PARENTHESISED.sub("", _MARKER.sub("", line))
        for part in re.split(r"[.。]", line):
            if core := re.sub(r"\s+", "", _MARKER.sub("", part)):
                cores.append(core)
    return tuple(cores)


def _statement_source(item: FunctionalCosmetic) -> str:
    if item.effect_text:
        return "document"
    return "effect_name" if item.effect_name else "none"


def _year(item: FunctionalCosmetic) -> str:
    return item.registered_on[:4] if re.fullmatch(r"\d{8}", item.registered_on) else "unknown"


def measure(source: CosmeticsSource, total: int, items: list[FunctionalCosmetic], text: str) -> dict:
    ids_by_name: dict[str, set[str]] = defaultdict(set)
    companies_by_name: dict[str, set[str]] = defaultdict(set)
    by_year: dict[str, dict[str, int]] = defaultdict(lambda: {"rows": 0, "missing": 0})
    for item in items:
        ids_by_name[item.item_name].add(item.record_id)
        companies_by_name[item.item_name].add(item.company)
        by_year[_year(item)]["rows"] += 1
        by_year[_year(item)]["missing"] += 0 if item.statement else 1
    shared = [name for name, ids in ids_by_name.items() if len(ids) > 1]
    statements = Counter(item.statement for item in items if item.statement)
    cores_by_row = [sentence_cores(item.statement) for item in items if item.statement]
    core_counts = Counter(core for cores in cores_by_row for core in cores)
    ranked = [core for core, _ in core_counts.most_common()]
    report = {
        "source_id": source.source_id,
        "endpoint": source.url,
        "retrieved_at": (items[0].retrieved_at if items else datetime.now(UTC)).isoformat(),
        "total_count": total,
        "row_count": len(items),
        "complete": len(items) == total,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest().upper(),
        "missing": {field: sum(1 for item in items if not getattr(item, field)) for field in _REQUIRED_FIELDS},
        "statement_missing_by_year": dict(sorted(by_year.items())),
        "statement_source": dict(sorted(Counter(_statement_source(item) for item in items).items())),
        "unreadable_documents": sum(1 for item in items if item.effect_doc_unreadable),
        # Both an efficacy sentence and a document exist and they do not say the same thing.
        "conflicting_sources": sum(
            1 for item in items
            if item.effect_text and item.effect_name
            and sorted(sentence_cores(item.effect_text)) != sorted(sentence_cores(item.effect_name))
        ),
        "template_instruction_rows": sum(
            1 for cores in cores_by_row if any(_TEMPLATE_NOTE in core for core in cores)
        ),
        "duplicate_id_rows": len(items) - len({item.record_id for item in items}),
        "names_shared_by_several_records": len(shared),
        "records_under_shared_names": sum(len(ids_by_name[name]) for name in shared),
        "shared_names_with_one_company": sum(1 for name in shared if len(companies_by_name[name]) == 1),
        "distinct_statements": len(statements),
        "statements": dict(statements.most_common(60)),
        "distinct_sentence_cores": len(core_counts),
        "sentence_cores": dict(core_counts.most_common(40)),
        "rows_fully_covered_by_top_cores": {
            str(top): sum(1 for cores in cores_by_row if set(cores) <= set(ranked[:top])) for top in _TOP_CORES
        },
    }
    if source is REPORTED:
        report["withdrawn_rows"] = sum(1 for item in items if item.withdrawn)
        report["effect_codes"] = dict(sorted(Counter(item.effect_code for item in items if item.effect_code).items()))
        report["flags"] = {
            flag: sum(1 for item in items if getattr(item, flag)) for flag in ("whitening", "wrinkle", "sunscreen")
        }
    else:
        report["notice_classes"] = dict(Counter(item.notice_class for item in items if item.notice_class))
    return report


def _stem(directory: Path, source: CosmeticsSource) -> Path:
    return directory / f"functional-cosmetics-{source.key}"


def load_export(source: CosmeticsSource, directory: Path) -> tuple[int, list[FunctionalCosmetic]]:
    """Rows of an earlier export, with the efficacy document read again by the current reader."""
    stem = _stem(directory, source)
    try:
        previous = json.loads(stem.with_suffix(".audit.json").read_text(encoding="utf-8"))
        rows = [
            json.loads(line)
            for line in stem.with_suffix(".jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        retrieved_at = datetime.fromisoformat(previous["retrieved_at"])
        total = int(previous["total_count"])
    except (OSError, ValueError, KeyError) as error:
        raise DataSourceError(f"{source.key} export in {directory} cannot be read: {type(error).__name__}") from None
    items = []
    for row in rows:
        lines = doc_paragraphs(row["effect_doc"])
        items.append(FunctionalCosmetic(
            **{field: row[field] for field in _EXPORT_FIELDS if field not in {"effect_text", "effect_doc_unreadable"}},
            effect_text="\n".join(lines),
            effect_doc_unreadable=bool(row["effect_doc"].strip()) and not lines,
            source_id=source.source_id,
            retrieved_at=retrieved_at,
        ))
    return total, items


def write_outputs(
    source: CosmeticsSource, total: int, items: list[FunctionalCosmetic], directory: Path,
) -> dict:
    text = "".join(
        json.dumps({field: getattr(item, field) for field in _EXPORT_FIELDS}, ensure_ascii=False) + "\n"
        for item in items
    )
    report = measure(source, total, items, text)
    directory.mkdir(parents=True, exist_ok=True)
    stem = _stem(directory, source)
    stem.with_suffix(".jsonl").write_text(text, encoding="utf-8", newline="\n")
    stem.with_suffix(".audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return report


def overlap(reported: list[FunctionalCosmetic], reviewed: list[FunctionalCosmetic]) -> dict:
    """How many product names, and names with the same company, appear in both lists."""
    return {
        "names_in_both_lists": len({item.item_name for item in reported} & {item.item_name for item in reviewed}),
        "name_and_company_in_both_lists": len(
            {(item.item_name, item.company) for item in reported}
            & {(item.item_name, item.company) for item in reviewed}
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    sources = list(SOURCES.values()) if args.service == "both" else [SOURCES[args.service]]
    directory = args.from_export or args.output_dir
    loaded: dict[str, list[FunctionalCosmetic]] = {}
    try:
        keys: dict[str, str] = {}
        if args.from_export is None:
            # Resolve every key first so that nothing is downloaded when one is missing.
            keys = {source.key: _api_key(args.env_file, source) for source in sources}
            for source in sources:
                if not keys[source.key]:
                    raise DataSourceError(f"{' or '.join(_key_names(source))} is not set")
        for source in sources:
            if args.from_export is None:
                total, items = fetch(_client(source, keys[source.key]), args.page_size, args.max_pages)
            else:
                total, items = load_export(source, directory)
            report = write_outputs(source, total, items, directory)
            loaded[source.key] = items
            missing = ", ".join(f"{field} {count}" for field, count in report["missing"].items())
            print(
                f"{source.key}: {report['row_count']} of {report['total_count']} rows"
                f"{'' if report['complete'] else ' (probe)'}; missing: {missing}; "
                f"unreadable documents {report['unreadable_documents']}; "
                f"shared names {report['names_shared_by_several_records']}; "
                f"distinct statements {report['distinct_statements']}"
            )
        if len(loaded) == len(SOURCES):
            (directory / "functional-cosmetics-overlap.json").write_text(
                json.dumps(overlap(loaded["reported"], loaded["reviewed"]), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8", newline="\n",
            )
    except (DataSourceError, OSError) as exc:
        print(f"error: {exc}")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
