from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from claimledger.domain import ProductCandidate
from claimledger.errors import DataSourceError
from claimledger.sources.food_safety import C003Client, CoverageAudit, audit_products

REPORT_PATH = Path(__file__).parents[1] / "docs" / "evidence" / "C003_COVERAGE_REPORT.md"


def fetch_all_products(client: C003Client) -> tuple[int, list[ProductCandidate]]:
    first_page = client.fetch_page(1, 100)
    total_count = first_page.total_count
    products = list(first_page.products)

    start = 101
    while start <= total_count:
        end = min(start + 999, total_count)
        page = client.fetch_page(start, end)
        if page.total_count != total_count:
            raise DataSourceError("C003 total_count changed during pagination")
        products.extend(page.products)
        start = end + 1

    if len(products) != total_count:
        raise DataSourceError(
            f"C003 fetched count mismatch: expected {total_count}, received {len(products)}"
        )
    return total_count, products


def _rate(complete_count: int, total_count: int) -> str:
    if total_count == 0:
        return "0.00%"
    return f"{complete_count / total_count:.2%}"


def render_report(
    *,
    retrieved_at: datetime,
    status: str,
    total_count: int | None = None,
    audit: CoverageAudit | None = None,
    blocked_reason: str | None = None,
) -> str:
    lines = [
        "# C003 Coverage Report",
        "",
        f"- Audit timestamp: `{retrieved_at.isoformat()}`",
        "- Source: `Food Safety Korea C003`",
        f"- Status: `{status}`",
    ]
    if blocked_reason is not None:
        lines.extend((f"- Blocked reason: `{blocked_reason}`", ""))
        return "\n".join(lines)

    if total_count is None or audit is None:
        raise ValueError("successful report requires total_count and audit")

    fields = (
        ("Product name", audit.missing_name_count),
        ("Company", audit.missing_company_count),
        ("Primary function", audit.missing_primary_function_count),
        ("Raw materials", audit.missing_raw_materials_count),
        ("Intake method", audit.missing_intake_method_count),
    )
    lines.extend(
        (
            f"- API total count: `{total_count}`",
            f"- Fetched count: `{audit.record_count}`",
            f"- Unique official report numbers: `{audit.unique_report_count}`",
            f"- Duplicate official report numbers: `{audit.duplicate_report_count}`",
            "",
            "## Field completeness",
            "",
            "| Field | Missing | Complete | Completeness rate |",
            "|---|---:|---:|---:|",
        )
    )
    for label, missing_count in fields:
        complete_count = audit.record_count - missing_count
        lines.append(
            f"| {label} | {missing_count} | {complete_count} | "
            f"{_rate(complete_count, audit.record_count)} |"
        )

    lines.extend(("", "## Candidate coverage", ""))
    for candidate, count in audit.candidate_counts.items():
        lines.append(f"- `{candidate}`: `{count}` records")
    candidate_note = "> Candidate counts use disclosed case-insensitive substring matching over product name, primary function, and raw materials. They measure candidate coverage, not clinical equivalence."
    lines.extend(("", candidate_note, ""))
    return "\n".join(lines)


def write_report(content: str) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(content, encoding="utf-8")


def main() -> int:
    retrieved_at = datetime.now(UTC)
    api_key = os.environ.get("FOODSAFETY_API_KEY", "")
    try:
        client = C003Client(api_key=api_key)
        total_count, products = fetch_all_products(client)
        audit = audit_products(products)
        identity_missing = (
            audit.missing_name_count + audit.missing_company_count > 0
        )
        status = "PASS" if not identity_missing and audit.duplicate_report_count == 0 else "LIMITED"
        write_report(
            render_report(
                retrieved_at=retrieved_at,
                status=status,
                total_count=total_count,
                audit=audit,
            )
        )
        return 0
    except DataSourceError as error:
        write_report(
            render_report(
                retrieved_at=retrieved_at,
                status="BLOCKED",
                blocked_reason=str(error),
            )
        )
        print(f"C003 audit blocked: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
