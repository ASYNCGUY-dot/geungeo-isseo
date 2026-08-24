import random
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from claimledger.domain import (
    ExtensionReviewProduct,
    IngredientGroup,
    MappingStatus,
    NonBlankText,
    ProductCandidate,
)
from claimledger.ingredients import map_ingredients

COMPARISON_GROUPS: tuple[IngredientGroup, ...] = (
    IngredientGroup.MILK_THISTLE,
    IngredientGroup.VITAMIN_D,
    IngredientGroup.RED_GINSENG,
    IngredientGroup.COENZYME_Q10,
    IngredientGroup.MAGNESIUM,
)
DEFAULT_REVIEW_SIZE = 20
DEFAULT_REVIEW_SEED = 20260823

Rate = Annotated[float, Field(ge=0.0, le=1.0)]
HumanScore = Annotated[int, Field(strict=True, ge=1, le=5)]


class ReviewSample(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_no: NonBlankText
    group: IngredientGroup
    name: NonBlankText
    company: NonBlankText
    primary_function: str
    raw_materials: str
    intake_method: str
    mapping_status: MappingStatus
    mapping_rule_version: NonBlankText


class ExtensionCandidateStats(BaseModel):
    model_config = ConfigDict(frozen=True)

    group: IngredientGroup
    product_count: Annotated[int, Field(ge=1)]
    complete_record_rate: Rate
    verified_mapping_rate: Rate
    advertising_risk_score: HumanScore
    functional_diversity_score: HumanScore
    implementation_feasibility_score: HumanScore
    reviewer: NonBlankText
    reviewed_at: datetime

    @model_validator(mode="after")
    def _require_comparison_group(self) -> "ExtensionCandidateStats":
        if self.group not in COMPARISON_GROUPS:
            raise ValueError("extension statistics require a comparison ingredient group")
        return self


class _FourComponentMapping(BaseModel, Mapping[str, float]):
    model_config = ConfigDict(frozen=True)

    component_names: ClassVar[tuple[str, ...]] = (
        "data_quality",
        "advertising_risk",
        "functional_diversity",
        "implementation_feasibility",
    )

    def __getitem__(self, key: str) -> float:
        if key not in self.component_names:
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.component_names)

    def __len__(self) -> int:
        return len(self.component_names)


class ExtensionScoreComponents(_FourComponentMapping):
    data_quality: Rate
    advertising_risk: Rate
    functional_diversity: Rate
    implementation_feasibility: Rate


class ExtensionScoreWeights(_FourComponentMapping):
    data_quality: Literal[0.25] = 0.25
    advertising_risk: Literal[0.25] = 0.25
    functional_diversity: Literal[0.25] = 0.25
    implementation_feasibility: Literal[0.25] = 0.25


class ScoredExtensionCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    stats: ExtensionCandidateStats
    components: ExtensionScoreComponents
    weights: ExtensionScoreWeights
    balanced_score: Rate


class ExtensionRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: Literal["clarity", "high_risk_high_value"]
    group: IngredientGroup
    balanced_score: Rate
    components: ExtensionScoreComponents
    reviewer: NonBlankText
    reviewed_at: datetime
    rationale: NonBlankText
    finalized: Literal[False] = False


class ExtensionRecommendations(BaseModel):
    model_config = ConfigDict(frozen=True)

    clarity: ExtensionRecommendation
    high_risk_high_value: ExtensionRecommendation
    status: Literal["recommendation_only"] = "recommendation_only"
    finalized: Literal[False] = False


def _canonical_products(
    products: Sequence[ProductCandidate | ExtensionReviewProduct],
) -> tuple[ProductCandidate | ExtensionReviewProduct, ...]:
    ordered = sorted(
        products,
        key=lambda product: (product.report_no, product.model_dump_json()),
    )
    unique_by_report_no: dict[str, ProductCandidate | ExtensionReviewProduct] = {}
    for product in ordered:
        unique_by_report_no.setdefault(product.report_no, product)
    return tuple(unique_by_report_no.values())


def select_review_sample(
    products: Sequence[ProductCandidate | ExtensionReviewProduct],
    group: IngredientGroup,
    size: int = DEFAULT_REVIEW_SIZE,
    seed: int = DEFAULT_REVIEW_SEED,
) -> tuple[ReviewSample, ...]:
    if group not in COMPARISON_GROUPS:
        raise ValueError("review samples are limited to comparison ingredient groups")
    if size < 1:
        raise ValueError("sample size must be at least 1")

    pool: list[ReviewSample] = []
    for product in _canonical_products(products):
        mapping = map_ingredients(product)
        if group not in mapping.groups:
            continue
        pool.append(
            ReviewSample(
                report_no=product.report_no,
                group=group,
                name=product.name,
                company=product.company,
                primary_function=product.primary_function,
                raw_materials=product.raw_materials,
                intake_method=product.intake_method,
                mapping_status=mapping.status,
                mapping_rule_version=mapping.rule_version,
            )
        )

    if len(pool) < size:
        raise ValueError(
            f"{group.value} has {len(pool)} unique candidates; {size} are required"
        )

    selected = random.Random(seed).sample(pool, size)
    return tuple(sorted(selected, key=lambda sample: sample.report_no))


def score_extension_candidate(stats: ExtensionCandidateStats) -> ScoredExtensionCandidate:
    components = ExtensionScoreComponents(
        data_quality=(stats.complete_record_rate + stats.verified_mapping_rate) / 2,
        advertising_risk=stats.advertising_risk_score / 5,
        functional_diversity=stats.functional_diversity_score / 5,
        implementation_feasibility=stats.implementation_feasibility_score / 5,
    )
    weights = ExtensionScoreWeights()
    balanced_score = sum(components[name] * weights[name] for name in components)
    return ScoredExtensionCandidate(
        stats=stats,
        components=components,
        weights=weights,
        balanced_score=balanced_score,
    )


def _recommendation(
    candidate: ScoredExtensionCandidate,
    *,
    category: Literal["clarity", "high_risk_high_value"],
    rationale: str,
) -> ExtensionRecommendation:
    return ExtensionRecommendation(
        category=category,
        group=candidate.stats.group,
        balanced_score=candidate.balanced_score,
        components=candidate.components,
        reviewer=candidate.stats.reviewer,
        reviewed_at=candidate.stats.reviewed_at,
        rationale=rationale,
    )


def recommend_extension_candidates(
    reviewed_stats: Sequence[ExtensionCandidateStats],
) -> ExtensionRecommendations:
    if any(not isinstance(stats, ExtensionCandidateStats) for stats in reviewed_stats):
        raise TypeError("recommendations require ExtensionCandidateStats inputs")

    group_counts = Counter(stats.group for stats in reviewed_stats)
    duplicates = tuple(group for group in COMPARISON_GROUPS if group_counts[group] > 1)
    if duplicates:
        values = ", ".join(group.value for group in duplicates)
        raise ValueError(f"reviewed candidate groups must be unique; duplicates: {values}")

    unexpected = tuple(
        sorted(set(group_counts).difference(COMPARISON_GROUPS), key=lambda group: group.value)
    )
    if unexpected:
        values = ", ".join(group.value for group in unexpected)
        raise ValueError(f"reviewed candidate groups contain unexpected groups: {values}")

    missing = tuple(group for group in COMPARISON_GROUPS if group_counts[group] == 0)
    if missing:
        values = ", ".join(group.value for group in missing)
        raise ValueError(f"reviewed candidate groups incomplete; missing: {values}")

    candidates = tuple(score_extension_candidate(stats) for stats in reviewed_stats)

    clarity = max(
        candidates,
        key=lambda candidate: (
            candidate.components["data_quality"]
            + candidate.components["implementation_feasibility"],
            candidate.balanced_score,
            candidate.stats.group.value,
        ),
    )
    remaining = tuple(candidate for candidate in candidates if candidate is not clarity)
    high_risk_high_value = max(
        remaining,
        key=lambda candidate: (
            candidate.components["advertising_risk"]
            + candidate.components["functional_diversity"],
            candidate.balanced_score,
            candidate.stats.group.value,
        ),
    )

    return ExtensionRecommendations(
        clarity=_recommendation(
            clarity,
            category="clarity",
            rationale=(
                "Highest combined data_quality and implementation_feasibility among "
                "reviewed comparison candidates."
            ),
        ),
        high_risk_high_value=_recommendation(
            high_risk_high_value,
            category="high_risk_high_value",
            rationale=(
                "Highest combined advertising_risk and functional_diversity among "
                "the remaining reviewed comparison candidates."
            ),
        ),
    )
