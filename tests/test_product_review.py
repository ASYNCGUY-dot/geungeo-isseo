import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from claimledger import product_review as product_review_module
from claimledger.domain import IngredientGroup
from claimledger.product_review import (
    ProductReviewLabel,
    ProductReviewManifest,
    ReviewGateStatus,
    ReviewGroupCounts,
    ReviewIssue,
    ReviewValidationResult,
    sha256_file,
    validate_product_review_pack,
    wilson_interval,
)

NOW = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)


def valid_label_values() -> dict[str, object]:
    return {
        "group": IngredientGroup.MILK_THISTLE,
        "report_no": "TEST-001",
        "mapping_verdict": "correct",
        "mapping_reason_code": "none",
        "function_text_status": "usable",
        "function_reason_code": "none",
        "review_note": "",
        "reviewer": "reviewer-01",
        "reviewed_at_iso8601": NOW,
    }


def test_product_review_label_accepts_a_consistent_decision() -> None:
    label = ProductReviewLabel.model_validate(valid_label_values())

    assert label.mapping_verdict.value == "correct"
    assert label.function_text_status.value == "usable"
    assert label.reviewed_at_iso8601 == NOW


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"mapping_verdict": "correct", "mapping_reason_code": "wrong_group"},
            "correct mapping requires reason none",
        ),
        (
            {"mapping_verdict": "incorrect", "mapping_reason_code": "none"},
            "non-correct mapping requires a reason",
        ),
        (
            {"function_text_status": "usable", "function_reason_code": "missing_text"},
            "usable function text requires reason none",
        ),
        (
            {"function_text_status": "uncertain", "function_reason_code": "none"},
            "non-usable function text requires a reason",
        ),
        (
            {
                "mapping_verdict": "uncertain",
                "mapping_reason_code": "needs_expert",
                "review_note": "",
            },
            "needs_expert and other reasons require a review note",
        ),
        ({"reviewer": '=HYPERLINK("bad")'}, "spreadsheet formula prefix"),
        ({"review_note": "+SUM(1,1)"}, "spreadsheet formula prefix"),
        (
            {"reviewed_at_iso8601": datetime(2026, 8, 28, 9, 0)},  # noqa: DTZ001
            "timezone",
        ),
    ],
)
def test_product_review_label_rejects_inconsistent_or_unsafe_values(
    changes: dict[str, object], message: str
) -> None:
    values = valid_label_values()
    values.update(changes)

    with pytest.raises(ValidationError, match=message):
        ProductReviewLabel.model_validate(values)


def test_product_review_label_rejects_a_core_ingredient_group() -> None:
    values = valid_label_values()
    values["group"] = IngredientGroup.OMEGA3

    with pytest.raises(ValidationError, match="comparison ingredient group"):
        ProductReviewLabel.model_validate(values)


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
LABEL_FIELDS = (
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
RAW_MATERIALS = {
    IngredientGroup.MILK_THISTLE: "밀크씨슬 추출물",
    IngredientGroup.VITAMIN_D: "비타민 D",
    IngredientGroup.RED_GINSENG: "홍삼 농축액",
    IngredientGroup.COENZYME_Q10: "코엔자임 Q10",
    IngredientGroup.MAGNESIUM: "마그네슘",
}
REVIEW_GROUPS = tuple(RAW_MATERIALS)


def _write_csv(
    path: Path,
    fields: tuple[str, ...],
    rows: list[dict[str, object]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _synthetic_rows() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    samples: list[dict[str, object]] = []
    exports: list[dict[str, object]] = []
    for group in REVIEW_GROUPS:
        for index in range(20):
            report_no = f"{group.value.upper()}-{index:03d}"
            export = {
                "report_no": report_no,
                "name": f"{group.value} synthetic product {index}",
                "company": "synthetic manufacturer",
                "primary_function": "synthetic official function text",
                "raw_materials": RAW_MATERIALS[group],
                "intake_method": "once daily",
            }
            exports.append(export)
            samples.append(
                {
                    "seed": 20260823,
                    "group": group.value,
                    **export,
                    "mapping_status": "verified_mapping",
                    "mapping_rule_version": "ingredient-map-v1",
                }
            )
    return samples, exports


def _blank_label_rows(
    samples: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        {
            "group": sample["group"],
            "report_no": sample["report_no"],
            "mapping_verdict": "",
            "mapping_reason_code": "",
            "function_text_status": "",
            "function_reason_code": "",
            "review_note": "",
            "reviewer": "",
            "reviewed_at_iso8601": "",
        }
        for sample in samples
    ]


def _write_manifest(pack_dir: Path, source_export: Path) -> None:
    manifest = ProductReviewManifest(
        group_counts=ReviewGroupCounts(),
        samples_sha256=sha256_file(pack_dir / "samples.csv"),
        source_export_sha256=sha256_file(source_export),
        mapping_rule_versions=("ingredient-map-v1",),
    )
    (pack_dir / "manifest.json").write_text(
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_valid_blank_pack(tmp_path: Path) -> tuple[Path, Path]:
    samples, exports = _synthetic_rows()
    source_export = tmp_path / "source-products.jsonl"
    source_export.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in exports),
        encoding="utf-8",
    )
    pack_dir = tmp_path / "review-pack"
    pack_dir.mkdir()
    (pack_dir / "README.md").write_text(
        "# Synthetic C003 Product Review Pack v2\n",
        encoding="utf-8",
    )
    _write_csv(pack_dir / "samples.csv", SAMPLE_FIELDS, samples)
    _write_csv(
        pack_dir / "product_review_labels.csv",
        LABEL_FIELDS,
        _blank_label_rows(samples),
    )
    _write_manifest(pack_dir, source_export)
    return pack_dir, source_export


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_completed_pack(
    tmp_path: Path,
    *,
    mapping_verdict: str = "correct",
    mapping_reason_code: str = "none",
    function_text_status: str = "usable",
    function_reason_code: str = "none",
    review_note: str = "",
    reviewer: str = "reviewer-01",
    reviewed_at: datetime = NOW,
) -> tuple[Path, Path]:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)
    labels_path = pack_dir / "product_review_labels.csv"
    rows = _read_csv(labels_path)
    for row in rows:
        row.update(
            {
                "mapping_verdict": mapping_verdict,
                "mapping_reason_code": mapping_reason_code,
                "function_text_status": function_text_status,
                "function_reason_code": function_reason_code,
                "review_note": review_note,
                "reviewer": reviewer,
                "reviewed_at_iso8601": reviewed_at.isoformat(),
            }
        )
    _write_csv(labels_path, LABEL_FIELDS, rows)
    return pack_dir, source_export


def _replace_manifest_hash(pack_dir: Path, field: str, value: str) -> None:
    manifest_path = pack_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = value
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def mutate_pack(pack_dir: Path, source_export: Path, mutation: str) -> None:
    labels_path = pack_dir / "product_review_labels.csv"
    samples_path = pack_dir / "samples.csv"
    if mutation == "extra_file":
        (pack_dir / "unexpected.txt").write_text("unexpected", encoding="utf-8")
    elif mutation == "sample_hash":
        samples_path.write_bytes(samples_path.read_bytes() + b"\n")
    elif mutation == "source_hash":
        extra = {
            "report_no": "EXTRA-000",
            "name": "extra synthetic product",
            "company": "synthetic manufacturer",
            "primary_function": "synthetic official function text",
            "raw_materials": "synthetic material",
            "intake_method": "once daily",
        }
        source_export.write_text(
            source_export.read_text(encoding="utf-8")
            + json.dumps(extra, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
    elif mutation == "duplicate_label_key":
        rows = _read_csv(labels_path)
        rows[1]["group"] = rows[0]["group"]
        rows[1]["report_no"] = rows[0]["report_no"]
        _write_csv(labels_path, LABEL_FIELDS, rows)
    elif mutation == "missing_label_key":
        rows = _read_csv(labels_path)
        _write_csv(labels_path, LABEL_FIELDS, rows[:-1])
    elif mutation == "unexpected_label_key":
        rows = _read_csv(labels_path)
        rows[-1]["report_no"] = "UNEXPECTED-999"
        _write_csv(labels_path, LABEL_FIELDS, rows)
    elif mutation == "wrong_header":
        rows = _read_csv(labels_path)
        fields = ("report_no", "group", *LABEL_FIELDS[2:])
        _write_csv(labels_path, fields, rows)
    elif mutation == "wrong_group_count":
        samples = _read_csv(samples_path)
        labels = _read_csv(labels_path)
        samples[0]["group"] = IngredientGroup.VITAMIN_D.value
        labels[0]["group"] = IngredientGroup.VITAMIN_D.value
        _write_csv(samples_path, SAMPLE_FIELDS, samples)
        _write_csv(labels_path, LABEL_FIELDS, labels)
        _replace_manifest_hash(
            pack_dir,
            "samples_sha256",
            sha256_file(samples_path),
        )
    elif mutation == "sample_source":
        samples = _read_csv(samples_path)
        samples[0]["name"] = "tampered synthetic product"
        _write_csv(samples_path, SAMPLE_FIELDS, samples)
        _replace_manifest_hash(
            pack_dir,
            "samples_sha256",
            sha256_file(samples_path),
        )
    elif mutation == "sample_mapping":
        samples = _read_csv(samples_path)
        samples[0]["mapping_status"] = "ambiguous"
        _write_csv(samples_path, SAMPLE_FIELDS, samples)
        _replace_manifest_hash(
            pack_dir,
            "samples_sha256",
            sha256_file(samples_path),
        )
    else:
        raise AssertionError(f"unknown mutation: {mutation}")


def test_blank_exact_v2_template_is_pending_zero_of_one_hundred(tmp_path: Path) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)

    result = validate_product_review_pack(
        pack_dir,
        source_export,
        validated_at=NOW,
    )

    assert result.status is ReviewGateStatus.PENDING
    assert result.expected_label_count == 100
    assert result.valid_label_count == 0
    assert result.pending_label_count == 100
    assert result.issues == ()
    assert result.summary is None
    assert result.advertising_evidence_status == "NOT_MEASURED"
    assert result.extension_recommendation_status == "BLOCKED"
    assert result.finalized is False


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("extra_file", "PACK_FILE_SET"),
        ("sample_hash", "SAMPLES_HASH_MISMATCH"),
        ("source_hash", "SOURCE_EXPORT_HASH_MISMATCH"),
        ("duplicate_label_key", "DUPLICATE_LABEL_KEY"),
        ("missing_label_key", "LABEL_KEY_SET_MISMATCH"),
        ("unexpected_label_key", "LABEL_KEY_SET_MISMATCH"),
        ("wrong_header", "LABEL_HEADER_MISMATCH"),
        ("wrong_group_count", "GROUP_COUNT_MISMATCH"),
        ("sample_source", "SAMPLE_SOURCE_MISMATCH"),
        ("sample_mapping", "SAMPLE_MAPPING_MISMATCH"),
    ],
)
def test_pack_identity_mutations_are_invalid(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)
    mutate_pack(pack_dir, source_export, mutation)

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.INVALID
    assert result.valid_label_count is None
    assert result.pending_label_count is None
    assert result.summary is None
    assert expected_code in {issue.code for issue in result.issues}
    assert result.extension_recommendation_status == "BLOCKED"
    assert result.finalized is False


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing_pack", "PACK_DIRECTORY_MISSING"),
        ("missing_export", "SOURCE_EXPORT_MISSING"),
        ("malformed_manifest", "MANIFEST_INVALID"),
        ("malformed_samples", "SAMPLES_NOT_UTF8"),
        ("malformed_export", "SOURCE_EXPORT_NOT_UTF8"),
    ],
)
def test_missing_or_malformed_pack_inputs_return_invalid(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)
    if mutation == "missing_pack":
        pack_dir = tmp_path / "missing-pack"
    elif mutation == "missing_export":
        source_export.unlink()
    elif mutation == "malformed_manifest":
        (pack_dir / "manifest.json").write_text("{", encoding="utf-8")
    elif mutation == "malformed_samples":
        samples_path = pack_dir / "samples.csv"
        samples_path.write_bytes(b"\xff")
        _replace_manifest_hash(pack_dir, "samples_sha256", sha256_file(samples_path))
    elif mutation == "malformed_export":
        source_export.write_bytes(b"\xff")
        _replace_manifest_hash(
            pack_dir,
            "source_export_sha256",
            sha256_file(source_export),
        )

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.INVALID
    assert expected_code in {issue.code for issue in result.issues}
    assert result.valid_label_count is None
    assert result.pending_label_count is None


@pytest.mark.parametrize(
    ("mutation", "expected_code", "expected_message"),
    [
        ("empty", "SOURCE_EXPORT_INVALID", "has no records"),
        ("blank_record", "SOURCE_EXPORT_INVALID", "contains a blank record"),
        ("malformed_json", "SOURCE_EXPORT_INVALID", "contains malformed JSON"),
        (
            "wrong_contract",
            "SOURCE_EXPORT_INVALID",
            "does not match the six-field contract",
        ),
        ("invalid_record", "SOURCE_EXPORT_INVALID", "record is invalid"),
        (
            "duplicate_report",
            "SOURCE_EXPORT_DUPLICATE",
            "contains a duplicate report number",
        ),
    ],
)
def test_source_export_record_failures_are_invalid(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
    expected_message: str,
) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)
    source_lines = source_export.read_text(encoding="utf-8").splitlines()

    if mutation == "empty":
        source_lines = []
    elif mutation == "blank_record":
        source_lines.insert(0, "")
    elif mutation == "malformed_json":
        source_lines[0] = "{"
    elif mutation == "wrong_contract":
        row = json.loads(source_lines[0])
        row["unexpected"] = "field"
        source_lines[0] = json.dumps(row, ensure_ascii=False)
    elif mutation == "invalid_record":
        row = json.loads(source_lines[0])
        row["report_no"] = ""
        source_lines[0] = json.dumps(row, ensure_ascii=False)
    elif mutation == "duplicate_report":
        source_lines.insert(1, source_lines[0])
    else:
        raise AssertionError(f"unknown source mutation: {mutation}")

    source_export.write_text(
        "\n".join(source_lines) + ("\n" if source_lines else ""),
        encoding="utf-8",
        newline="\n",
    )
    _replace_manifest_hash(
        pack_dir,
        "source_export_sha256",
        sha256_file(source_export),
    )

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.INVALID
    assert any(
        issue.code == expected_code and expected_message in issue.message
        for issue in result.issues
    )
    assert result.valid_label_count is None
    assert result.pending_label_count is None


def test_naive_validation_time_is_invalid(tmp_path: Path) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)

    result = validate_product_review_pack(
        pack_dir,
        source_export,
        validated_at=datetime(2026, 8, 28, 9, 0),  # noqa: DTZ001
    )

    assert result.status is ReviewGateStatus.INVALID
    assert {issue.code for issue in result.issues} == {"VALIDATED_AT_INVALID"}
    assert result.valid_label_count is None
    assert result.pending_label_count is None


def test_pack_directory_read_failure_returns_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)
    original_iterdir = Path.iterdir

    def fail_pack_iterdir(path: Path):  # type: ignore[no-untyped-def]
        if path == pack_dir:
            raise OSError("simulated directory read failure")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", fail_pack_iterdir)

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.INVALID
    assert {issue.code for issue in result.issues} == {"PACK_DIRECTORY_INVALID"}


def test_document_read_failure_returns_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)
    readme_path = pack_dir / "README.md"
    original_open = Path.open

    def fail_readme_open(path: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if path == readme_path:
            raise OSError("simulated document read failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_readme_open)

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.INVALID
    assert {issue.code for issue in result.issues} == {"README_NOT_UTF8"}


def test_csv_parser_failure_returns_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)

    def fail_csv_reader(*args: object, **kwargs: object) -> None:
        raise csv.Error("simulated CSV parser failure")

    monkeypatch.setattr(product_review_module.csv, "DictReader", fail_csv_reader)

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.INVALID
    assert {
        "LABEL_ROW_INVALID",
        "SAMPLE_ROW_INVALID",
    } <= {issue.code for issue in result.issues}


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("invalid_seed", "SAMPLE_ROW_INVALID"),
        ("unexpected_group", "UNEXPECTED_SAMPLE_GROUP"),
        ("duplicate_key", "DUPLICATE_SAMPLE_KEY"),
        ("manifest_rule_version", "MAPPING_RULE_VERSION_MISMATCH"),
    ],
)
def test_sample_contract_mutations_are_invalid(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)
    samples_path = pack_dir / "samples.csv"
    samples = _read_csv(samples_path)

    if mutation == "invalid_seed":
        samples[0]["seed"] = "1"
    elif mutation == "unexpected_group":
        samples[0]["group"] = IngredientGroup.OMEGA3.value
    elif mutation == "duplicate_key":
        samples[1]["group"] = samples[0]["group"]
        samples[1]["report_no"] = samples[0]["report_no"]
    elif mutation == "manifest_rule_version":
        manifest_path = pack_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["mapping_rule_versions"] = ["ingredient-map-v2"]
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    else:
        raise AssertionError(f"unknown sample mutation: {mutation}")

    if mutation != "manifest_rule_version":
        _write_csv(samples_path, SAMPLE_FIELDS, samples)
        _replace_manifest_hash(pack_dir, "samples_sha256", sha256_file(samples_path))

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.INVALID
    assert expected_code in {issue.code for issue in result.issues}
    assert result.valid_label_count is None
    assert result.pending_label_count is None


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("malformed_row", "LABEL_ROW_INVALID"),
        ("invalid_group", "INVALID_LABEL_KEY"),
        ("noncomparison_group", "INVALID_LABEL_KEY"),
        ("invalid_value", "LABEL_VALUE_INVALID"),
    ],
)
def test_label_contract_mutations_are_invalid(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)
    labels_path = pack_dir / "product_review_labels.csv"

    if mutation == "malformed_row":
        lines = labels_path.read_text(encoding="utf-8").splitlines()
        lines[1] += ",unexpected"
        labels_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    else:
        rows = _read_csv(labels_path)
        if mutation == "invalid_group":
            rows[0]["group"] = "not-an-ingredient-group"
        elif mutation == "noncomparison_group":
            rows[0]["group"] = IngredientGroup.OMEGA3.value
        elif mutation == "invalid_value":
            rows[0].update(
                {
                    "mapping_verdict": "correct",
                    "mapping_reason_code": "wrong_group",
                    "function_text_status": "usable",
                    "function_reason_code": "none",
                    "reviewer": "reviewer-01",
                    "reviewed_at_iso8601": NOW.isoformat(),
                }
            )
        else:
            raise AssertionError(f"unknown label mutation: {mutation}")
        _write_csv(labels_path, LABEL_FIELDS, rows)

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.INVALID
    assert expected_code in {issue.code for issue in result.issues}
    assert result.valid_label_count is None
    assert result.pending_label_count is None


def test_complete_labels_produce_metrics_but_no_recommendation(tmp_path: Path) -> None:
    pack_dir, source_export = write_completed_pack(tmp_path)

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.COMPLETE
    assert result.valid_label_count == 100
    assert result.pending_label_count == 0
    assert result.summary is not None
    assert result.summary.overall.sample_count == 100
    assert result.summary.overall.mapping_correct_count == 100
    assert result.summary.overall.mapping_precision_decidable == 1.0
    assert len(result.summary.groups) == 5
    assert tuple(group.group for group in result.summary.groups) == REVIEW_GROUPS
    assert {group.sample_count for group in result.summary.groups} == {20}
    assert result.advertising_evidence_status == "NOT_MEASURED"
    assert result.extension_recommendation_status == "BLOCKED"
    assert result.finalized is False


def test_wilson_interval_and_not_measured_denominator_are_explicit() -> None:
    assert wilson_interval(0, 0) is None

    perfect = wilson_interval(20, 20)
    assert perfect is not None
    assert perfect.lower == pytest.approx(0.838874841947, abs=1e-12)
    assert perfect.upper == pytest.approx(1.0, abs=1e-12)

    half = wilson_interval(10, 20)
    assert half is not None
    assert half.lower == pytest.approx(0.299298008198, abs=1e-12)
    assert half.upper == pytest.approx(0.700701991802, abs=1e-12)


@pytest.mark.parametrize(("successes", "total"), [(-1, 20), (21, 20), (1, -1)])
def test_wilson_interval_rejects_impossible_counts(successes: int, total: int) -> None:
    with pytest.raises(ValueError, match="0 <= successes <= total"):
        wilson_interval(successes, total)


def test_all_uncertain_mappings_do_not_become_zero_precision(tmp_path: Path) -> None:
    pack_dir, source_export = write_completed_pack(
        tmp_path,
        mapping_verdict="uncertain",
        mapping_reason_code="needs_expert",
        review_note="expert review required",
    )

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.COMPLETE
    assert result.summary is not None
    assert result.summary.overall.mapping_precision_decidable is None
    assert result.summary.overall.mapping_precision_wilson_95 is None
    assert result.summary.overall.mapping_uncertainty_rate == 1.0


def test_complete_summary_counts_mixed_labels_and_review_window(tmp_path: Path) -> None:
    pack_dir, source_export = write_completed_pack(tmp_path)
    labels_path = pack_dir / "product_review_labels.csv"
    rows = _read_csv(labels_path)
    for index, row in enumerate(rows):
        if 70 <= index < 80:
            row["mapping_verdict"] = "incorrect"
            row["mapping_reason_code"] = "wrong_group"
        elif index >= 80:
            row["mapping_verdict"] = "uncertain"
            row["mapping_reason_code"] = "needs_expert"

        if 60 <= index < 85:
            row["function_text_status"] = "incomplete"
            row["function_reason_code"] = "missing_text"
        elif index >= 85:
            row["function_text_status"] = "uncertain"
            row["function_reason_code"] = "needs_expert"

        if index >= 80:
            row["review_note"] = "expert review required"
        row["reviewer"] = "reviewer-a" if index < 25 else "reviewer-b"
        row["reviewed_at_iso8601"] = (
            NOW - timedelta(days=2) if index < 50 else NOW - timedelta(hours=1)
        ).isoformat()
    _write_csv(labels_path, LABEL_FIELDS, rows)

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.COMPLETE
    assert result.summary is not None
    metrics = result.summary.overall
    assert metrics.mapping_correct_count == 70
    assert metrics.mapping_incorrect_count == 10
    assert metrics.mapping_uncertain_count == 20
    assert metrics.mapping_precision_decidable == pytest.approx(0.875)
    assert metrics.mapping_precision_wilson_95 is not None
    assert metrics.mapping_uncertainty_rate == pytest.approx(0.2)
    assert metrics.function_usable_rate == pytest.approx(0.6)
    assert metrics.function_incomplete_rate == pytest.approx(0.25)
    assert metrics.function_uncertainty_rate == pytest.approx(0.15)
    assert [count.model_dump() for count in result.summary.reviewer_counts] == [
        {"reviewer": "reviewer-a", "row_count": 25},
        {"reviewer": "reviewer-b", "row_count": 75},
    ]
    assert result.summary.review_started_at == NOW - timedelta(days=2)
    assert result.summary.review_completed_at == NOW - timedelta(hours=1)


@pytest.mark.parametrize(
    ("changes", "expected_code"),
    [
        ({"mapping_verdict": "not-a-verdict"}, "LABEL_VALUE_INVALID"),
        (
            {"mapping_verdict": "correct", "mapping_reason_code": "wrong_group"},
            "LABEL_VALUE_INVALID",
        ),
        (
            {
                "mapping_verdict": "uncertain",
                "mapping_reason_code": "needs_expert",
                "review_note": "",
            },
            "LABEL_VALUE_INVALID",
        ),
        ({"reviewer": '=HYPERLINK("bad")'}, "LABEL_VALUE_INVALID"),
        (
            {
                "mapping_verdict": "uncertain",
                "mapping_reason_code": "other",
                "review_note": "+SUM(1,1)",
            },
            "LABEL_VALUE_INVALID",
        ),
        ({"reviewer": ""}, "PARTIAL_LABEL"),
        ({"reviewed_at_iso8601": "2026-08-28T09:00:00"}, "LABEL_VALUE_INVALID"),
        (
            {"reviewed_at_iso8601": (NOW + timedelta(hours=24, seconds=1)).isoformat()},
            "LABEL_REVIEWED_AT_FUTURE",
        ),
    ],
)
def test_invalid_completed_label_returns_invalid_without_summary(
    tmp_path: Path,
    changes: dict[str, str],
    expected_code: str,
) -> None:
    pack_dir, source_export = write_completed_pack(tmp_path)
    labels_path = pack_dir / "product_review_labels.csv"
    rows = _read_csv(labels_path)
    rows[0].update(changes)
    _write_csv(labels_path, LABEL_FIELDS, rows)

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.INVALID
    assert expected_code in {issue.code for issue in result.issues}
    assert result.valid_label_count is None
    assert result.pending_label_count is None
    assert result.summary is None


def test_hash_read_failure_returns_invalid_instead_of_raising(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)

    def fail_hash_read(path: Path) -> str:
        raise OSError(f"simulated unreadable file: {path.name}")

    monkeypatch.setattr(product_review_module, "sha256_file", fail_hash_read)

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.INVALID
    assert {issue.code for issue in result.issues} == {"HASH_READ_FAILED"}
    assert result.valid_label_count is None
    assert result.pending_label_count is None


def test_partial_human_row_is_invalid_instead_of_speculative_progress(
    tmp_path: Path,
) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)
    labels_path = pack_dir / "product_review_labels.csv"
    rows = _read_csv(labels_path)
    rows[0]["mapping_verdict"] = "correct"
    _write_csv(labels_path, LABEL_FIELDS, rows)

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.INVALID
    assert {issue.code for issue in result.issues} == {"PARTIAL_LABEL"}
    assert result.issues[0].line_number == 2


def test_possible_secret_is_rejected_without_echoing_its_value(tmp_path: Path) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)
    rows = [json.loads(line) for line in source_export.read_text(encoding="utf-8").splitlines()]
    secret_value = "live" + "-secret-value-123456"
    rows[0]["api" + "_key"] = secret_value
    source_export.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    _replace_manifest_hash(
        pack_dir,
        "source_export_sha256",
        sha256_file(source_export),
    )

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.INVALID
    assert "POSSIBLE_SECRET" in {issue.code for issue in result.issues}
    assert secret_value not in result.model_dump_json()


def test_source_json_field_order_does_not_change_pack_identity(tmp_path: Path) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)
    rows = [json.loads(line) for line in source_export.read_text(encoding="utf-8").splitlines()]
    reordered = [{key: row[key] for key in reversed(row)} for row in rows]
    source_export.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in reordered),
        encoding="utf-8",
    )
    _replace_manifest_hash(
        pack_dir,
        "source_export_sha256",
        sha256_file(source_export),
    )

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.PENDING, result.issues
    assert result.valid_label_count == 0
    assert result.pending_label_count == 100


def test_spreadsheet_neutralization_preserves_source_identity(tmp_path: Path) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)
    source_rows = [
        json.loads(line) for line in source_export.read_text(encoding="utf-8").splitlines()
    ]
    source_rows[0].update(
        {
            "report_no": "=FORMULA-000",
            "name": "+SUM(1,1)",
            "company": "-1+1",
            "primary_function": "@formula",
            "raw_materials": "\t=CMD 밀크씨슬",
            "intake_method": "\r=CMD",
        }
    )
    source_export.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in source_rows),
        encoding="utf-8",
    )

    samples_path = pack_dir / "samples.csv"
    labels_path = pack_dir / "product_review_labels.csv"
    samples = _read_csv(samples_path)
    labels = _read_csv(labels_path)
    for field in (
        "report_no",
        "name",
        "company",
        "primary_function",
        "raw_materials",
        "intake_method",
    ):
        samples[0][field] = "'" + str(source_rows[0][field])
    labels[0]["report_no"] = samples[0]["report_no"]
    _write_csv(samples_path, SAMPLE_FIELDS, samples)
    _write_csv(labels_path, LABEL_FIELDS, labels)
    _replace_manifest_hash(pack_dir, "samples_sha256", sha256_file(samples_path))
    _replace_manifest_hash(
        pack_dir,
        "source_export_sha256",
        sha256_file(source_export),
    )

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.PENDING, result.issues
    assert result.valid_label_count == 0
    assert result.pending_label_count == 100


def test_invalid_status_cannot_claim_zero_review_progress() -> None:
    with pytest.raises(ValidationError, match="INVALID requires"):
        ReviewValidationResult(
            status=ReviewGateStatus.INVALID,
            valid_label_count=0,
            pending_label_count=0,
            issues=(ReviewIssue(code="bad_pack", message="pack is invalid"),),
        )
