import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from enum import StrEnum
from io import StringIO
from pathlib import Path
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from claimledger.domain import (
    ExtensionReviewProduct,
    IngredientGroup,
    MappingStatus,
    NonBlankText,
)
from claimledger.extension_selection import COMPARISON_GROUPS, ReviewSample
from claimledger.ingredients import map_ingredients

_SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_PACK_FILES = {
    "README.md",
    "manifest.json",
    "product_review_labels.csv",
    "samples.csv",
}
_SAMPLE_FIELDS = (
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
_LABEL_FIELDS = (
    "group",
    "report_no",
    "mapping_verdict",
    "mapping_reason_code",
    "function_text_status",
    "function_reason_code",
    "review_note",
    "reviewer",
    "reviewed_at_iso8601",
)
_REQUIRED_HUMAN_FIELDS = (
    "mapping_verdict",
    "mapping_reason_code",
    "function_text_status",
    "function_reason_code",
    "reviewer",
    "reviewed_at_iso8601",
)
_SOURCE_FIELDS = tuple(ExtensionReviewProduct.model_fields)
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


class MappingVerdict(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    UNCERTAIN = "uncertain"


class MappingReasonCode(StrEnum):
    NONE = "none"
    WRONG_GROUP = "wrong_group"
    ALIAS_COLLISION = "alias_collision"
    COMBINATION_PRODUCT = "combination_product"
    NEGATIVE_OR_EXCLUSION_CONTEXT = "negative_or_exclusion_context"
    NEEDS_EXPERT = "needs_expert"
    OTHER = "other"


class FunctionTextStatus(StrEnum):
    USABLE = "usable"
    INCOMPLETE = "incomplete"
    UNCERTAIN = "uncertain"


class FunctionReasonCode(StrEnum):
    NONE = "none"
    MISSING_TEXT = "missing_text"
    TRUNCATED_OR_MALFORMED = "truncated_or_malformed"
    TOO_VAGUE_FOR_RULE = "too_vague_for_rule"
    NEEDS_EXPERT = "needs_expert"
    OTHER = "other"


def _reject_formula_prefix(value: str, field_name: str) -> None:
    if value.startswith(_SPREADSHEET_FORMULA_PREFIXES):
        raise ValueError(f"{field_name} starts with a spreadsheet formula prefix")


class ProductReviewLabel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    group: IngredientGroup
    report_no: NonBlankText
    mapping_verdict: MappingVerdict
    mapping_reason_code: MappingReasonCode
    function_text_status: FunctionTextStatus
    function_reason_code: FunctionReasonCode
    review_note: str = ""
    reviewer: NonBlankText
    reviewed_at_iso8601: AwareDatetime

    @model_validator(mode="after")
    def _validate_human_contract(self) -> "ProductReviewLabel":
        if self.group not in COMPARISON_GROUPS:
            raise ValueError("product review requires a comparison ingredient group")
        if self.mapping_verdict is MappingVerdict.CORRECT:
            if self.mapping_reason_code is not MappingReasonCode.NONE:
                raise ValueError("correct mapping requires reason none")
        elif self.mapping_reason_code is MappingReasonCode.NONE:
            raise ValueError("non-correct mapping requires a reason")
        if self.function_text_status is FunctionTextStatus.USABLE:
            if self.function_reason_code is not FunctionReasonCode.NONE:
                raise ValueError("usable function text requires reason none")
        elif self.function_reason_code is FunctionReasonCode.NONE:
            raise ValueError("non-usable function text requires a reason")
        note_required = self.mapping_reason_code in {
            MappingReasonCode.NEEDS_EXPERT,
            MappingReasonCode.OTHER,
        } or self.function_reason_code in {
            FunctionReasonCode.NEEDS_EXPERT,
            FunctionReasonCode.OTHER,
        }
        if note_required and not self.review_note.strip():
            raise ValueError("needs_expert and other reasons require a review note")
        _reject_formula_prefix(self.reviewer, "reviewer")
        _reject_formula_prefix(self.review_note, "review_note")
        return self


class ReviewGroupCounts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    milk_thistle: Literal[20] = 20
    vitamin_d: Literal[20] = 20
    red_ginseng: Literal[20] = 20
    coenzyme_q10: Literal[20] = 20
    magnesium: Literal[20] = 20


class ProductReviewManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_version: Literal["c003-product-review-v2"] = "c003-product-review-v2"
    seed: Literal[20260823] = 20260823
    sample_count: Literal[100] = 100
    group_counts: ReviewGroupCounts
    samples_sha256: str = Field(pattern=r"^[0-9A-F]{64}$")
    source_export_sha256: str = Field(pattern=r"^[0-9A-F]{64}$")
    mapping_rule_versions: tuple[NonBlankText, ...]

    @model_validator(mode="after")
    def _require_sorted_unique_rule_versions(self) -> "ProductReviewManifest":
        if not self.mapping_rule_versions:
            raise ValueError("mapping rule versions must not be empty")
        if self.mapping_rule_versions != tuple(sorted(set(self.mapping_rule_versions))):
            raise ValueError("mapping rule versions must be sorted and unique")
        return self


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def build_product_review_manifest(
    samples_path: Path,
    source_export_path: Path,
    samples: tuple[ReviewSample, ...],
    seed: int,
) -> ProductReviewManifest:
    if seed != 20260823:
        raise ValueError("v2 seed must be 20260823")
    if len(samples) != 100:
        raise ValueError("v2 review pack requires exactly 100 samples")

    counts = Counter(sample.group for sample in samples)
    expected_counts = Counter({group: 20 for group in COMPARISON_GROUPS})
    if counts != expected_counts:
        raise ValueError("v2 review pack requires exactly 20 samples per comparison group")

    rule_versions = tuple(sorted({sample.mapping_rule_version for sample in samples}))
    return ProductReviewManifest(
        group_counts=ReviewGroupCounts(
            **{group.value: counts[group] for group in COMPARISON_GROUPS}
        ),
        samples_sha256=sha256_file(samples_path),
        source_export_sha256=sha256_file(source_export_path),
        mapping_rule_versions=rule_versions,
    )


class ReviewGateStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PENDING = "PENDING"
    INVALID = "INVALID"


class ProductReviewSample(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: Literal[20260823]
    group: IngredientGroup
    report_no: NonBlankText
    name: NonBlankText
    company: NonBlankText
    primary_function: str
    raw_materials: str
    intake_method: str
    mapping_status: MappingStatus
    mapping_rule_version: NonBlankText

    @field_validator("seed", mode="before")
    @classmethod
    def _parse_csv_seed(cls, value: object) -> object:
        if value == "20260823":
            return 20260823
        return value


class ReviewIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: NonBlankText
    message: NonBlankText
    line_number: int | None = None
    group: str | None = None
    report_no: str | None = None


class WilsonInterval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lower: float = Field(ge=0.0, le=1.0)
    upper: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _require_ordered_bounds(self) -> "WilsonInterval":
        if self.lower > self.upper:
            raise ValueError("Wilson lower bound must not exceed upper bound")
        return self


class ReviewMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sample_count: int = Field(ge=1)
    mapping_correct_count: int = Field(ge=0)
    mapping_incorrect_count: int = Field(ge=0)
    mapping_uncertain_count: int = Field(ge=0)
    mapping_precision_decidable: float | None = Field(ge=0.0, le=1.0)
    mapping_precision_wilson_95: WilsonInterval | None
    mapping_uncertainty_rate: float = Field(ge=0.0, le=1.0)
    function_usable_rate: float = Field(ge=0.0, le=1.0)
    function_incomplete_rate: float = Field(ge=0.0, le=1.0)
    function_uncertainty_rate: float = Field(ge=0.0, le=1.0)


class GroupReviewMetrics(ReviewMetrics):
    group: IngredientGroup


class ReviewerCount(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reviewer: NonBlankText
    row_count: int = Field(ge=1)


class ProductReviewSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    overall: ReviewMetrics
    groups: tuple[GroupReviewMetrics, ...]
    reviewer_counts: tuple[ReviewerCount, ...]
    review_started_at: AwareDatetime
    review_completed_at: AwareDatetime


class ReviewValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ReviewGateStatus
    expected_label_count: Literal[100] = 100
    valid_label_count: int | None = Field(ge=0, le=100)
    pending_label_count: int | None = Field(ge=0, le=100)
    issues: tuple[ReviewIssue, ...]
    summary: ProductReviewSummary | None = None
    advertising_evidence_status: Literal["NOT_MEASURED"] = "NOT_MEASURED"
    extension_recommendation_status: Literal["BLOCKED"] = "BLOCKED"
    finalized: Literal[False] = False

    @model_validator(mode="after")
    def _require_status_consistency(self) -> "ReviewValidationResult":
        if self.status is ReviewGateStatus.COMPLETE:
            if (
                self.valid_label_count != 100
                or self.pending_label_count != 0
                or self.summary is None
                or self.issues
            ):
                raise ValueError("COMPLETE requires 100 valid labels and a clean summary")
        elif self.status is ReviewGateStatus.PENDING:
            if (
                self.valid_label_count is None
                or self.pending_label_count is None
                or self.valid_label_count + self.pending_label_count != 100
                or self.pending_label_count == 0
                or self.summary is not None
                or self.issues
            ):
                raise ValueError("PENDING requires a clean incomplete 100-row pack")
        elif (
            self.valid_label_count is not None
            or self.pending_label_count is not None
            or self.summary is not None
            or not self.issues
        ):
            raise ValueError("INVALID requires issues and unreported progress counts")
        return self


def _issue_sort_key(issue: ReviewIssue) -> tuple[int, str, str, str]:
    return (
        issue.line_number if issue.line_number is not None else -1,
        issue.code,
        issue.group or "",
        issue.report_no or "",
    )


def _invalid_result(issues: list[ReviewIssue]) -> ReviewValidationResult:
    return ReviewValidationResult(
        status=ReviewGateStatus.INVALID,
        valid_label_count=None,
        pending_label_count=None,
        issues=tuple(sorted(issues, key=_issue_sort_key)),
    )


def _issue(
    code: str,
    message: str,
    *,
    line_number: int | None = None,
    group: str | None = None,
    report_no: str | None = None,
) -> ReviewIssue:
    return ReviewIssue(
        code=code,
        message=message,
        line_number=line_number,
        group=group,
        report_no=report_no,
    )


def _contains_possible_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def _read_utf8(
    path: Path,
    code: str,
    message: str,
    issues: list[ReviewIssue],
    *,
    preserve_newlines: bool = False,
) -> str | None:
    try:
        with path.open(
            encoding="utf-8",
            newline="" if preserve_newlines else None,
        ) as handle:
            return handle.read()
    except UnicodeDecodeError:
        issues.append(_issue(code, message))
    except OSError:
        issues.append(_issue(code, message))
    return None


def _parse_source_export(
    text: str,
    issues: list[ReviewIssue],
) -> dict[str, ExtensionReviewProduct]:
    products: dict[str, ExtensionReviewProduct] = {}
    lines = text.splitlines()
    if not lines:
        issues.append(_issue("SOURCE_EXPORT_INVALID", "source export has no records"))
        return products
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            issues.append(
                _issue(
                    "SOURCE_EXPORT_INVALID",
                    "source export contains a blank record",
                    line_number=line_number,
                )
            )
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            issues.append(
                _issue(
                    "SOURCE_EXPORT_INVALID",
                    "source export contains malformed JSON",
                    line_number=line_number,
                )
            )
            continue
        if not isinstance(value, dict) or set(value) != set(_SOURCE_FIELDS):
            issues.append(
                _issue(
                    "SOURCE_EXPORT_INVALID",
                    "source export record does not match the six-field contract",
                    line_number=line_number,
                )
            )
            continue
        try:
            product = ExtensionReviewProduct.model_validate(value)
        except ValidationError:
            issues.append(
                _issue(
                    "SOURCE_EXPORT_INVALID",
                    "source export record is invalid",
                    line_number=line_number,
                )
            )
            continue
        if product.report_no in products:
            issues.append(
                _issue(
                    "SOURCE_EXPORT_DUPLICATE",
                    "source export contains a duplicate report number",
                    line_number=line_number,
                    report_no=product.report_no,
                )
            )
            continue
        products[product.report_no] = product
    return products


def _parse_csv_rows(
    text: str,
    expected_fields: tuple[str, ...],
    *,
    header_code: str,
    row_code: str,
    document_name: str,
    issues: list[ReviewIssue],
) -> list[tuple[int, dict[str, str]]]:
    try:
        reader = csv.DictReader(StringIO(text, newline=""))
        if tuple(reader.fieldnames or ()) != expected_fields:
            issues.append(
                _issue(header_code, f"{document_name} header does not match the v2 contract")
            )
            return []
        rows: list[tuple[int, dict[str, str]]] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                issues.append(
                    _issue(
                        row_code,
                        f"{document_name} row is malformed",
                        line_number=line_number,
                    )
                )
                continue
            rows.append((line_number, {key: value for key, value in row.items() if key}))
        return rows
    except csv.Error:
        issues.append(_issue(row_code, f"{document_name} is malformed"))
        return []


def _spreadsheet_literal(value: str) -> str:
    if len(value) >= 2 and value[0] == "'" and value[1] in _SPREADSHEET_FORMULA_PREFIXES:
        return value[1:]
    return value


def _sample_matches_source(
    sample: ProductReviewSample,
    source: ExtensionReviewProduct,
) -> bool:
    return all(
        _spreadsheet_literal(getattr(sample, field)) == getattr(source, field)
        for field in _SOURCE_FIELDS
    )


def _sample_matches_mapping(
    sample: ProductReviewSample,
    source: ExtensionReviewProduct,
) -> bool:
    mapping = map_ingredients(source)
    return (
        sample.group in mapping.groups
        and sample.mapping_status is mapping.status
        and sample.mapping_rule_version == mapping.rule_version
    )


def validate_product_review_pack(
    pack_dir: Path,
    source_export_path: Path,
    *,
    validated_at: AwareDatetime,
) -> ReviewValidationResult:
    issues: list[ReviewIssue] = []
    if not isinstance(validated_at, datetime) or validated_at.utcoffset() is None:
        return _invalid_result(
            [_issue("VALIDATED_AT_INVALID", "validated_at must be timezone-aware")]
        )
    if not pack_dir.is_dir():
        return _invalid_result(
            [_issue("PACK_DIRECTORY_MISSING", "review pack directory does not exist")]
        )
    if not source_export_path.is_file():
        return _invalid_result(
            [_issue("SOURCE_EXPORT_MISSING", "source export file does not exist")]
        )
    try:
        actual_files = {path.name for path in pack_dir.iterdir()}
    except OSError:
        return _invalid_result([_issue("PACK_DIRECTORY_INVALID", "review pack is unreadable")])
    if actual_files != _PACK_FILES:
        return _invalid_result(
            [_issue("PACK_FILE_SET", "review pack file set does not match the v2 contract")]
        )

    documents = {
        "README.md": _read_utf8(
            pack_dir / "README.md",
            "README_NOT_UTF8",
            "README is not readable UTF-8",
            issues,
        ),
        "manifest.json": _read_utf8(
            pack_dir / "manifest.json",
            "MANIFEST_NOT_UTF8",
            "manifest is not readable UTF-8",
            issues,
        ),
        "samples.csv": _read_utf8(
            pack_dir / "samples.csv",
            "SAMPLES_NOT_UTF8",
            "samples CSV is not readable UTF-8",
            issues,
            preserve_newlines=True,
        ),
        "product_review_labels.csv": _read_utf8(
            pack_dir / "product_review_labels.csv",
            "LABELS_NOT_UTF8",
            "labels CSV is not readable UTF-8",
            issues,
            preserve_newlines=True,
        ),
        "source export": _read_utf8(
            source_export_path,
            "SOURCE_EXPORT_NOT_UTF8",
            "source export is not readable UTF-8",
            issues,
        ),
    }
    if issues:
        return _invalid_result(issues)
    for name, text in documents.items():
        if text is not None and _contains_possible_secret(text):
            issues.append(_issue("POSSIBLE_SECRET", f"{name} contains a possible secret"))
    if issues:
        return _invalid_result(issues)

    manifest: ProductReviewManifest | None = None
    manifest_text = documents["manifest.json"]
    if manifest_text is not None:
        try:
            manifest = ProductReviewManifest.model_validate_json(manifest_text)
        except (ValidationError, ValueError):
            issues.append(_issue("MANIFEST_INVALID", "manifest does not match the v2 contract"))

    source_text = documents["source export"]
    source_products = (
        _parse_source_export(source_text, issues) if source_text is not None else {}
    )
    samples_text = documents["samples.csv"]
    sample_rows = (
        _parse_csv_rows(
            samples_text,
            _SAMPLE_FIELDS,
            header_code="SAMPLE_HEADER_MISMATCH",
            row_code="SAMPLE_ROW_INVALID",
            document_name="samples CSV",
            issues=issues,
        )
        if samples_text is not None
        else []
    )
    labels_text = documents["product_review_labels.csv"]
    label_rows = (
        _parse_csv_rows(
            labels_text,
            _LABEL_FIELDS,
            header_code="LABEL_HEADER_MISMATCH",
            row_code="LABEL_ROW_INVALID",
            document_name="labels CSV",
            issues=issues,
        )
        if labels_text is not None
        else []
    )

    if manifest is not None:
        try:
            samples_sha256 = sha256_file(pack_dir / "samples.csv")
            source_export_sha256 = sha256_file(source_export_path)
        except OSError:
            issues.append(
                _issue(
                    "HASH_READ_FAILED",
                    "review pack hash input became unreadable",
                )
            )
        else:
            if samples_sha256 != manifest.samples_sha256:
                issues.append(
                    _issue(
                        "SAMPLES_HASH_MISMATCH",
                        "samples CSV hash does not match manifest",
                    )
                )
            if source_export_sha256 != manifest.source_export_sha256:
                issues.append(
                    _issue(
                        "SOURCE_EXPORT_HASH_MISMATCH",
                        "source export hash does not match manifest",
                    )
                )

    samples: list[tuple[int, ProductReviewSample]] = []
    sample_keys: set[tuple[str, str]] = set()
    group_counts: Counter[IngredientGroup] = Counter()
    for line_number, row in sample_rows:
        try:
            sample = ProductReviewSample.model_validate(row)
        except ValidationError:
            issues.append(
                _issue(
                    "SAMPLE_ROW_INVALID",
                    "sample row does not match the v2 contract",
                    line_number=line_number,
                )
            )
            continue
        group = sample.group.value
        key = (group, sample.report_no)
        if sample.group not in COMPARISON_GROUPS:
            issues.append(
                _issue(
                    "UNEXPECTED_SAMPLE_GROUP",
                    "sample row uses a non-comparison group",
                    line_number=line_number,
                    group=group,
                    report_no=sample.report_no,
                )
            )
        if key in sample_keys:
            issues.append(
                _issue(
                    "DUPLICATE_SAMPLE_KEY",
                    "samples CSV contains a duplicate composite key",
                    line_number=line_number,
                    group=group,
                    report_no=sample.report_no,
                )
            )
        sample_keys.add(key)
        group_counts[sample.group] += 1
        source_report_no = _spreadsheet_literal(sample.report_no)
        source = source_products.get(source_report_no)
        if source is None or not _sample_matches_source(sample, source):
            issues.append(
                _issue(
                    "SAMPLE_SOURCE_MISMATCH",
                    "sample row does not match its source export record",
                    line_number=line_number,
                    group=group,
                    report_no=sample.report_no,
                )
            )
        elif not _sample_matches_mapping(sample, source):
            issues.append(
                _issue(
                    "SAMPLE_MAPPING_MISMATCH",
                    "sample mapping does not match the deterministic rule",
                    line_number=line_number,
                    group=group,
                    report_no=sample.report_no,
                )
            )
        samples.append((line_number, sample))

    expected_group_counts = Counter({group: 20 for group in COMPARISON_GROUPS})
    if len(samples) != 100 or group_counts != expected_group_counts:
        issues.append(
            _issue(
                "GROUP_COUNT_MISMATCH",
                "samples CSV must contain five comparison groups with 20 rows each",
            )
        )
    if manifest is not None:
        manifest_counts = {
            IngredientGroup(group): count
            for group, count in manifest.group_counts.model_dump().items()
        }
        if group_counts != Counter(manifest_counts):
            issues.append(
                _issue(
                    "GROUP_COUNT_MISMATCH",
                    "sample group counts do not match manifest",
                )
            )
        sample_rule_versions = tuple(
            sorted({sample.mapping_rule_version for _, sample in samples})
        )
        if sample_rule_versions != manifest.mapping_rule_versions:
            issues.append(
                _issue(
                    "MAPPING_RULE_VERSION_MISMATCH",
                    "sample rule versions do not match manifest",
                )
            )

    label_keys: set[tuple[str, str]] = set()
    valid_label_count = 0
    pending_label_count = 0
    for line_number, row in label_rows:
        group_value = row["group"]
        report_no = row["report_no"].strip()
        try:
            group = IngredientGroup(group_value)
        except ValueError:
            issues.append(
                _issue(
                    "INVALID_LABEL_KEY",
                    "label row uses an invalid group",
                    line_number=line_number,
                )
            )
            continue
        if group not in COMPARISON_GROUPS or not report_no:
            issues.append(
                _issue(
                    "INVALID_LABEL_KEY",
                    "label row uses an invalid composite key",
                    line_number=line_number,
                )
            )
            continue
        key = (group.value, report_no)
        if key in label_keys:
            issues.append(
                _issue(
                    "DUPLICATE_LABEL_KEY",
                    "labels CSV contains a duplicate composite key",
                    line_number=line_number,
                    group=group.value,
                    report_no=report_no,
                )
            )
        label_keys.add(key)

        human_values = [row[field] for field in _LABEL_FIELDS[2:]]
        if all(value == "" for value in human_values):
            pending_label_count += 1
            continue
        if any(not row[field].strip() for field in _REQUIRED_HUMAN_FIELDS):
            issues.append(
                _issue(
                    "PARTIAL_LABEL",
                    "label row has only part of the required human review",
                    line_number=line_number,
                    group=group.value,
                    report_no=report_no,
                )
            )
            continue
        try:
            ProductReviewLabel.model_validate(row)
        except ValidationError:
            issues.append(
                _issue(
                    "LABEL_VALUE_INVALID",
                    "label row violates the human review contract",
                    line_number=line_number,
                    group=group.value,
                    report_no=report_no,
                )
            )
            continue
        valid_label_count += 1

    if label_keys != sample_keys:
        issues.append(
            _issue(
                "LABEL_KEY_SET_MISMATCH",
                "label and sample composite key sets do not match",
            )
        )
    if issues:
        return _invalid_result(issues)
    if pending_label_count:
        return ReviewValidationResult(
            status=ReviewGateStatus.PENDING,
            valid_label_count=valid_label_count,
            pending_label_count=pending_label_count,
            issues=(),
        )
    return _invalid_result(
        [
            _issue(
                "COMPLETE_SUMMARY_UNAVAILABLE",
                "complete review summary calculation is not available",
            )
        ]
    )
