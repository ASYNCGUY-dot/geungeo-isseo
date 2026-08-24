import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from claimledger.domain import ProductCandidate
from claimledger.extension_selection import (
    COMPARISON_GROUPS,
    DEFAULT_REVIEW_SEED,
    DEFAULT_REVIEW_SIZE,
    ReviewSample,
    select_review_sample,
)

SAMPLE_FIELDS = (
    "seed",
    "group",
    "report_no",
    "name",
    "company",
    "primary_function",
    "raw_materials",
    "intake_method",
    "mapping_status",
    "mapping_rule_version",
)
REVIEW_LABEL_FIELDS = (
    "group",
    "report_no",
    "advertising_risk_score_1_to_5",
    "functional_diversity_score_1_to_5",
    "implementation_feasibility_score_1_to_5",
    "reviewer",
    "reviewed_at_iso8601",
)
_SECRET_PATTERNS = (
    re.compile(r"\b(?:OPENAI|FOODSAFETY|TAVILY|ANTHROPIC)_API_KEY\b", re.IGNORECASE),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(
        r'''["']?(?:api[_-]?key|access[_-]?token|client[_-]?secret)["']?'''
        r'''\s*[:=]\s*["']?(?!redacted\b|placeholder\b|dummy\b|test\b)'''
        r"[A-Za-z0-9_./+=-]{8,}",
        re.IGNORECASE,
    ),
)
_SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class ReviewBuildError(ValueError):
    pass


def _reject_possible_secrets(raw_input: str) -> None:
    if any(pattern.search(raw_input) for pattern in _SECRET_PATTERNS):
        raise ReviewBuildError("input contains a possible live secret")


def _parse_record(value: Any, line_number: int) -> ProductCandidate:
    if not isinstance(value, dict):
        raise ReviewBuildError(f"line {line_number} must contain one JSON object")
    unknown_fields = set(value).difference(ProductCandidate.model_fields)
    if unknown_fields:
        fields = ", ".join(sorted(unknown_fields))
        raise ReviewBuildError(f"line {line_number} contains unexpected fields: {fields}")
    try:
        return ProductCandidate.model_validate(value)
    except ValidationError as exc:
        raise ReviewBuildError(f"line {line_number} is not a valid product record: {exc}") from exc


def load_products(input_path: Path) -> tuple[ProductCandidate, ...]:
    if not input_path.is_file():
        raise ReviewBuildError(f"input file does not exist: {input_path}")
    try:
        raw_input = input_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ReviewBuildError("input must be UTF-8 JSONL") from exc
    _reject_possible_secrets(raw_input)

    products: list[ProductCandidate] = []
    for line_number, line in enumerate(raw_input.splitlines(), start=1):
        if not line.strip():
            raise ReviewBuildError(f"line {line_number} is blank")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReviewBuildError(f"line {line_number} contains malformed JSON") from exc
        products.append(_parse_record(value, line_number))

    report_numbers: set[str] = set()
    duplicates: set[str] = set()
    for product in products:
        if product.report_no in report_numbers:
            duplicates.add(product.report_no)
        report_numbers.add(product.report_no)
    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        raise ReviewBuildError(f"input contains duplicate report_no values: {duplicate_list}")
    return tuple(products)


def build_samples(
    products: tuple[ProductCandidate, ...], seed: int
) -> tuple[ReviewSample, ...]:
    samples: list[ReviewSample] = []
    for group in COMPARISON_GROUPS:
        try:
            group_samples = select_review_sample(
                products,
                group,
                size=DEFAULT_REVIEW_SIZE,
                seed=seed,
            )
        except ValueError as exc:
            raise ReviewBuildError(str(exc)) from exc
        if len(group_samples) != DEFAULT_REVIEW_SIZE:
            raise ReviewBuildError(
                f"{group.value} did not produce exactly {DEFAULT_REVIEW_SIZE} samples"
            )
        samples.extend(group_samples)
    return tuple(samples)


def _sample_row(sample: ReviewSample, seed: int) -> dict[str, object]:
    return {
        "seed": seed,
        "group": sample.group.value,
        "report_no": _spreadsheet_safe(sample.report_no),
        "name": _spreadsheet_safe(sample.name),
        "company": _spreadsheet_safe(sample.company),
        "primary_function": _spreadsheet_safe(sample.primary_function),
        "raw_materials": _spreadsheet_safe(sample.raw_materials),
        "intake_method": _spreadsheet_safe(sample.intake_method),
        "mapping_status": sample.mapping_status.value,
        "mapping_rule_version": sample.mapping_rule_version,
    }


def _spreadsheet_safe(value: str) -> str:
    if value.startswith(_SPREADSHEET_FORMULA_PREFIXES):
        return f"'{value}"
    return value


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_review_pack(output_dir: Path, samples: tuple[ReviewSample, ...], seed: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        output_dir / "samples.csv",
        SAMPLE_FIELDS,
        [_sample_row(sample, seed) for sample in samples],
    )
    _write_csv(
        output_dir / "review_labels.csv",
        REVIEW_LABEL_FIELDS,
        [
            {
                "group": sample.group.value,
                "report_no": _spreadsheet_safe(sample.report_no),
                "advertising_risk_score_1_to_5": "",
                "functional_diversity_score_1_to_5": "",
                "implementation_feasibility_score_1_to_5": "",
                "reviewer": "",
                "reviewed_at_iso8601": "",
            }
            for sample in samples
        ],
    )

    group_lines = "\n".join(
        f"- `{group.value}`: {sum(sample.group is group for sample in samples)} unique samples"
        for group in COMPARISON_GROUPS
    )
    readme = f"""# Extension Ingredient Review Pack

- Seed: `{seed}`
- Sample size: `{DEFAULT_REVIEW_SIZE}` per comparison group
- Total samples: `{len(samples)}`
- Review status: pending human labels
- Recommendation status: recommendation only
- Finalized extension ingredients: none

## Sample counts

{group_lines}

## Review contract

Enter integer scores from 1 through 5 for advertising risk, functional diversity,
and implementation feasibility. Every scored row also requires a reviewer and an
ISO 8601 reviewed-at timestamp. Recommendations may be produced only from reviewed
scores; they never finalize either extension ingredient.
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8", newline="\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an offline extension review pack")
    parser.add_argument("--input", type=Path, required=True, help="UTF-8 C003 JSONL input")
    parser.add_argument("--output-dir", type=Path, required=True, help="generated artifact directory")
    parser.add_argument("--seed", type=int, default=DEFAULT_REVIEW_SEED)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        products = load_products(args.input)
        samples = build_samples(products, args.seed)
        write_review_pack(args.output_dir, samples, args.seed)
    except ReviewBuildError as exc:
        raise SystemExit(f"error: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
