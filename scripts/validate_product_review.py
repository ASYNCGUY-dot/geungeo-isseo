import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import AwareDatetime

from claimledger.product_review import ReviewGateStatus, validate_product_review_pack

EXIT_CODES = {
    ReviewGateStatus.COMPLETE: 0,
    ReviewGateStatus.PENDING: 2,
    ReviewGateStatus.INVALID: 3,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a C003 product review pack v2")
    parser.add_argument("--pack-dir", type=Path, required=True)
    parser.add_argument("--source-export", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path)
    return parser.parse_args(argv)


def _write_complete_summary(path: Path, serialized: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(serialized, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(
    argv: list[str] | None = None,
    *,
    validated_at: AwareDatetime | None = None,
) -> int:
    args = parse_args(argv)
    result = validate_product_review_pack(
        args.pack_dir,
        args.source_export,
        validated_at=validated_at or datetime.now(UTC),
    )
    serialized = (
        json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(serialized, end="")
    if result.status is ReviewGateStatus.COMPLETE and args.summary_output is not None:
        _write_complete_summary(args.summary_output, serialized)
    return EXIT_CODES[result.status]


if __name__ == "__main__":
    raise SystemExit(main())
