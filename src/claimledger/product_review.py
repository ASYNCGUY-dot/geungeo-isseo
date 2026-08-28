import hashlib
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from claimledger.domain import IngredientGroup, NonBlankText
from claimledger.extension_selection import COMPARISON_GROUPS, ReviewSample

_SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


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
