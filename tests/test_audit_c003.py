from datetime import UTC, datetime

from claimledger.sources.food_safety import CoverageAudit
from scripts.audit_c003 import render_report


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
