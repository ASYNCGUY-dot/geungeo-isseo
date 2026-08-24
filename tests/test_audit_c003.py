import json
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from claimledger.domain import ProductCandidate
from claimledger.sources.food_safety import CoverageAudit
from scripts import audit_c003
from scripts.audit_c003 import parse_args, render_report, write_products_jsonl


def test_success_report_preserves_api_code_and_phase_decision() -> None:
    audit = CoverageAudit(
        record_count=3,
        unique_report_count=3,
        duplicate_report_count=0,
        missing_name_count=0,
        missing_company_count=0,
        missing_primary_function_count=0,
        missing_raw_materials_count=0,
        missing_intake_method_count=0,
        candidate_counts={
            "lutein_zeaxanthin": 1,
            "omega3": 1,
            "probiotics": 1,
        },
    )

    report = render_report(
        retrieved_at=datetime(2026, 8, 23, tzinfo=UTC),
        status="PASS",
        total_count=3,
        audit=audit,
    )

    assert "API result code: `INFO-000`" in report
    assert "Phase 0 decision: `CONTINUE_PRODUCT_MVP`" in report


def test_export_products_jsonl_contains_only_approved_review_fields(tmp_path: Path) -> None:
    output_path = tmp_path / "c003-products.jsonl"
    product = ProductCandidate(
        report_no="TEST-0001",
        name="테스트 제품",
        company="테스트 회사",
        primary_function="눈 건강에 도움을 줄 수 있음",
        raw_materials="루테인",
        intake_method="하루 1회",
        source_id="C003",
        retrieved_at=datetime(2026, 8, 24, tzinfo=UTC),
    )

    write_products_jsonl((product,), output_path)

    raw_export = output_path.read_text(encoding="utf-8")
    exported = json.loads(raw_export)
    assert exported == {
        "report_no": "TEST-0001",
        "name": "테스트 제품",
        "company": "테스트 회사",
        "primary_function": "눈 건강에 도움을 줄 수 있음",
        "raw_materials": "루테인",
        "intake_method": "하루 1회",
    }
    assert "local-c003-api-key-must-not-leak" not in raw_export
    assert "C003" not in raw_export
    assert "RESULT" not in raw_export
    assert "total_count" not in raw_export
    assert "source_id" not in raw_export
    assert "retrieved_at" not in raw_export


def test_interrupted_export_preserves_destination_and_cleans_ignored_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "data" / "c003-products.jsonl"
    staging_dir = tmp_path / "build" / "c003-export"
    output_path.parent.mkdir(parents=True)
    output_path.write_text("previous-export\n", encoding="utf-8")
    product = ProductCandidate(
        report_no="TEST-0001",
        name="테스트 제품",
        company="테스트 회사",
        primary_function="눈 건강에 도움을 줄 수 있음",
        raw_materials="루테인",
        intake_method="하루 1회",
        source_id="C003",
        retrieved_at=datetime(2026, 8, 24, tzinfo=UTC),
    )

    def interrupted_products() -> Iterator[ProductCandidate]:
        yield product
        assert len(tuple(staging_dir.glob("*.tmp"))) == 1
        raise RuntimeError("interrupted export")

    monkeypatch.setattr(audit_c003, "EXPORT_STAGING_DIR", staging_dir)

    with pytest.raises(RuntimeError, match="interrupted export"):
        write_products_jsonl(interrupted_products(), output_path)

    assert output_path.read_text(encoding="utf-8") == "previous-export\n"
    assert not staging_dir.exists()


def test_cli_accepts_the_documented_export_products_path() -> None:
    args = parse_args(["--export-products", r"data\c003-products.jsonl"])

    assert args.export_products == Path(r"data\c003-products.jsonl")


def test_cli_export_products_writes_the_redacted_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "data" / "c003-products.jsonl"
    product = ProductCandidate(
        report_no="TEST-0001",
        name="테스트 제품",
        company="테스트 회사",
        primary_function="눈 건강에 도움을 줄 수 있음",
        raw_materials="루테인",
        intake_method="하루 1회",
        source_id="C003",
        retrieved_at=datetime(2026, 8, 24, tzinfo=UTC),
    )

    def fetch_one_product(client: object) -> tuple[int, list[ProductCandidate]]:
        del client
        return 1, [product]

    monkeypatch.setattr(audit_c003, "REPORT_PATH", tmp_path / "coverage-report.md")
    monkeypatch.setattr(audit_c003, "fetch_all_products", fetch_one_product)
    monkeypatch.setenv("FOOD_SAFETY_API_KEY", "test-only-placeholder")
    monkeypatch.setattr(
        sys,
        "argv",
        ["audit_c003.py", "--export-products", str(output_path)],
    )

    assert audit_c003.main() == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))[
        "report_no"
    ] == "TEST-0001"
