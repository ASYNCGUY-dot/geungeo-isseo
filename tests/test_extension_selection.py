import csv
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from claimledger.domain import IngredientGroup, ProductCandidate
from claimledger.extension_selection import (
    COMPARISON_GROUPS,
    ExtensionCandidateStats,
    recommend_extension_candidates,
    score_extension_candidate,
    select_review_sample,
)

NOW = datetime(2026, 8, 24, tzinfo=UTC)


def product(report_no: str, raw_materials: str = "홍삼 농축액") -> ProductCandidate:
    return ProductCandidate(
        report_no=report_no,
        name=f"검토 제품 {report_no}",
        company="검토 제조사",
        primary_function="건강에 도움을 줄 수 있음",
        raw_materials=raw_materials,
        intake_method="1일 1회",
        source_id="C003",
        retrieved_at=NOW,
    )


PRODUCTS = tuple(product(f"REVIEW-{index:03d}") for index in range(25))


def test_review_sample_is_reproducible_and_has_unique_report_numbers() -> None:
    first = select_review_sample(
        PRODUCTS,
        IngredientGroup.RED_GINSENG,
        size=20,
        seed=20260823,
    )
    second = select_review_sample(
        tuple(reversed(PRODUCTS)),
        IngredientGroup.RED_GINSENG,
        size=20,
        seed=20260823,
    )

    assert first == second
    assert len({item.report_no for item in first}) == 20


def test_extension_score_keeps_data_risk_diversity_and_feasibility_separate() -> None:
    stats = ExtensionCandidateStats(
        group=IngredientGroup.MILK_THISTLE,
        product_count=100,
        complete_record_rate=0.95,
        verified_mapping_rate=0.90,
        advertising_risk_score=3,
        functional_diversity_score=4,
        implementation_feasibility_score=5,
        reviewer="reviewer-01",
        reviewed_at=NOW,
    )

    scored = score_extension_candidate(stats)

    assert scored.components["data_quality"] == pytest.approx(0.925)
    assert scored.components == pytest.approx(
        {
            "data_quality": 0.925,
            "advertising_risk": 0.6,
            "functional_diversity": 0.8,
            "implementation_feasibility": 1.0,
        }
    )
    assert scored.weights == {
        "data_quality": 0.25,
        "advertising_risk": 0.25,
        "functional_diversity": 0.25,
        "implementation_feasibility": 0.25,
    }
    assert scored.balanced_score == pytest.approx(0.83125)


def test_review_sample_deduplicates_before_rejecting_an_undersized_pool() -> None:
    duplicated_products = PRODUCTS[:19] + (PRODUCTS[0],)

    with pytest.raises(ValueError, match="19 unique candidates; 20 are required"):
        select_review_sample(duplicated_products, IngredientGroup.RED_GINSENG)


def test_review_sample_rejects_core_ingredient_groups() -> None:
    with pytest.raises(ValueError, match="comparison ingredient groups"):
        select_review_sample(PRODUCTS, IngredientGroup.OMEGA3)


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"advertising_risk_score": 0}, "greater than or equal to 1"),
        ({"advertising_risk_score": "3"}, "valid integer"),
        ({"functional_diversity_score": 6}, "less than or equal to 5"),
        ({"implementation_feasibility_score": 3.5}, "valid integer"),
        ({"reviewer": "   "}, "at least 1 character"),
        ({"reviewed_at": None}, "valid datetime"),
    ],
)
def test_human_review_fields_are_strictly_validated(
    update: dict[str, object], message: str
) -> None:
    values = {
        "group": IngredientGroup.MILK_THISTLE,
        "product_count": 100,
        "complete_record_rate": 0.95,
        "verified_mapping_rate": 0.90,
        "advertising_risk_score": 3,
        "functional_diversity_score": 4,
        "implementation_feasibility_score": 5,
        "reviewer": "reviewer-01",
        "reviewed_at": NOW,
    }
    values.update(update)

    with pytest.raises(ValidationError, match=message):
        ExtensionCandidateStats(**values)


def candidate_stats(
    group: IngredientGroup,
    *,
    complete_record_rate: float,
    verified_mapping_rate: float,
    advertising_risk_score: int,
    functional_diversity_score: int,
    implementation_feasibility_score: int,
) -> ExtensionCandidateStats:
    return ExtensionCandidateStats(
        group=group,
        product_count=20,
        complete_record_rate=complete_record_rate,
        verified_mapping_rate=verified_mapping_rate,
        advertising_risk_score=advertising_risk_score,
        functional_diversity_score=functional_diversity_score,
        implementation_feasibility_score=implementation_feasibility_score,
        reviewer="reviewer-01",
        reviewed_at=NOW,
    )


def test_recommendations_are_transparent_distinct_and_never_finalized() -> None:
    scored = tuple(
        score_extension_candidate(stats)
        for stats in (
            candidate_stats(
                IngredientGroup.MILK_THISTLE,
                complete_record_rate=1.0,
                verified_mapping_rate=1.0,
                advertising_risk_score=1,
                functional_diversity_score=2,
                implementation_feasibility_score=5,
            ),
            candidate_stats(
                IngredientGroup.VITAMIN_D,
                complete_record_rate=0.8,
                verified_mapping_rate=0.8,
                advertising_risk_score=5,
                functional_diversity_score=5,
                implementation_feasibility_score=3,
            ),
            candidate_stats(
                IngredientGroup.MAGNESIUM,
                complete_record_rate=0.9,
                verified_mapping_rate=0.9,
                advertising_risk_score=3,
                functional_diversity_score=3,
                implementation_feasibility_score=4,
            ),
        )
    )

    recommendations = recommend_extension_candidates(scored)

    assert recommendations.clarity.group is IngredientGroup.MILK_THISTLE
    assert recommendations.high_risk_high_value.group is IngredientGroup.VITAMIN_D
    assert recommendations.clarity.components == scored[0].components
    assert "data_quality" in recommendations.clarity.rationale
    assert "advertising_risk" in recommendations.high_risk_high_value.rationale
    assert recommendations.status == "recommendation_only"
    assert recommendations.finalized is False


RAW_MATERIALS = {
    IngredientGroup.MILK_THISTLE: "밀크씨슬",
    IngredientGroup.VITAMIN_D: "비타민 D",
    IngredientGroup.RED_GINSENG: "홍삼 농축액",
    IngredientGroup.COENZYME_Q10: "코엔자임 Q10",
    IngredientGroup.MAGNESIUM: "마그네슘",
}


def jsonl_records(per_group: int = 20) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for group in COMPARISON_GROUPS:
        for index in range(per_group):
            records.append(
                {
                    "report_no": f"{group.value.upper()}-{index:03d}",
                    "name": f"{group.value} 검토 제품 {index}",
                    "company": "검토 제조사",
                    "primary_function": "건강에 도움을 줄 수 있음",
                    "raw_materials": RAW_MATERIALS[group],
                    "intake_method": "1일 1회",
                    "source_id": "C003",
                    "retrieved_at": "2026-08-24T00:00:00Z",
                }
            )
    return records


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def run_cli(input_path: Path, output_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/build_extension_review.py",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--seed",
            "20260823",
        ],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_builds_reproducible_20_per_group_review_files(tmp_path: Path) -> None:
    input_path = tmp_path / "products.jsonl"
    first_output = tmp_path / "first"
    second_output = tmp_path / "second"
    write_jsonl(input_path, list(reversed(jsonl_records())))

    first = run_cli(input_path, first_output)
    second = run_cli(input_path, second_output)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert {path.name for path in first_output.iterdir()} == {
        "README.md",
        "review_labels.csv",
        "samples.csv",
    }
    assert all(
        (first_output / name).read_bytes() == (second_output / name).read_bytes()
        for name in ("README.md", "review_labels.csv", "samples.csv")
    )
    with (first_output / "samples.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 100
    assert {
        group.value: len({row["report_no"] for row in rows if row["group"] == group.value})
        for group in COMPARISON_GROUPS
    } == {group.value: 20 for group in COMPARISON_GROUPS}
    summary = (first_output / "README.md").read_text(encoding="utf-8")
    assert "recommendation only" in summary.lower()
    assert "finalized extension ingredients: none" in summary.lower()


@pytest.mark.parametrize("failure", ["duplicate", "secret", "malformed", "undersized"])
def test_cli_refuses_invalid_or_unsafe_input(tmp_path: Path, failure: str) -> None:
    input_path = tmp_path / "products.jsonl"
    records = jsonl_records()
    if failure == "duplicate":
        records.append(records[0].copy())
        write_jsonl(input_path, records)
        expected = "duplicate report_no"
    elif failure == "secret":
        records[0]["api" + "_key"] = "live" + "-secret-value-123456"
        write_jsonl(input_path, records)
        expected = "possible live secret"
    elif failure == "malformed":
        input_path.write_text('{"report_no": \n', encoding="utf-8")
        expected = "malformed JSON"
    else:
        write_jsonl(input_path, jsonl_records(per_group=19))
        expected = "19 unique candidates; 20 are required"

    result = run_cli(input_path, tmp_path / "output")

    assert result.returncode != 0
    assert expected in result.stderr
    assert not (tmp_path / "output").exists()


def test_cli_refuses_an_absent_input_file(tmp_path: Path) -> None:
    result = run_cli(tmp_path / "missing.jsonl", tmp_path / "output")

    assert result.returncode != 0
    assert "input file does not exist" in result.stderr
    assert not (tmp_path / "output").exists()


def test_review_label_fixture_declares_all_required_human_fields() -> None:
    fixture = Path(__file__).parent / "fixtures" / "extension_review_labels.csv"

    with fixture.open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))

    assert header == [
        "group",
        "report_no",
        "advertising_risk_score_1_to_5",
        "functional_diversity_score_1_to_5",
        "implementation_feasibility_score_1_to_5",
        "reviewer",
        "reviewed_at_iso8601",
    ]
