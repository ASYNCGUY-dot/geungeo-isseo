import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import AwareDatetime

from claimledger.functional_role_review import validate_functional_role_review_pack
from claimledger.product_review import ReviewGateStatus

EXIT_CODES = {
    ReviewGateStatus.COMPLETE: 0,
    ReviewGateStatus.PENDING: 2,
    ReviewGateStatus.INVALID: 3,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a functional-role review pack")
    parser.add_argument("--pack-dir", type=Path, required=True)
    parser.add_argument("--source-export", type=Path, required=True)
    parser.add_argument("--product-review-pack", type=Path, required=True)
    parser.add_argument("--rules", type=Path, required=True)
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


def _reject_overlapping_summary_output(
    summary_output: Path,
    *,
    pack_dir: Path,
    source_export: Path,
    product_review_pack: Path,
    rules: Path,
) -> None:
    resolved_output = summary_output.resolve(strict=False)
    protected_directories = (
        pack_dir.resolve(strict=False),
        product_review_pack.resolve(strict=False),
    )
    protected_files = {
        source_export.resolve(strict=False),
        rules.resolve(strict=False),
    }
    if resolved_output in protected_files or any(
        resolved_output == directory or directory in resolved_output.parents
        for directory in protected_directories
    ):
        raise ValueError("summary output must not overwrite validation inputs")


def main(
    argv: list[str] | None = None,
    *,
    validated_at: AwareDatetime | None = None,
) -> int:
    args = parse_args(argv)
    result = validate_functional_role_review_pack(
        args.pack_dir,
        args.source_export,
        args.product_review_pack,
        args.rules,
        validated_at=validated_at or datetime.now(UTC),
    )
    if result.status is ReviewGateStatus.COMPLETE and args.summary_output is not None:
        _reject_overlapping_summary_output(
            args.summary_output,
            pack_dir=args.pack_dir,
            source_export=args.source_export,
            product_review_pack=args.product_review_pack,
            rules=args.rules,
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
