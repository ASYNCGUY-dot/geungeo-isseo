from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from claimledger.domain import ProductCandidate
from claimledger.errors import DataSourceError

_MODEL_TO_SOURCE_FIELD = {
    "report_no": "PRDLST_REPORT_NO",
    "name": "PRDLST_NM",
    "company": "BSSH_NM",
    "primary_function": "PRIMARY_FNCLTY",
    "raw_materials": "RAWMTRL_NM",
    "intake_method": "NTK_MTHD",
}


@dataclass(frozen=True)
class C003Page:
    total_count: int
    products: tuple[ProductCandidate, ...]


def parse_c003_payload(payload: dict[str, Any], retrieved_at: datetime) -> C003Page:
    envelope = payload.get("C003")
    if not isinstance(envelope, dict):
        raise DataSourceError("C003 response object is missing")

    result = envelope.get("RESULT")
    if not isinstance(result, dict):
        raise DataSourceError("C003 RESULT object is missing")

    code = str(result.get("CODE", "UNKNOWN"))
    message = str(result.get("MSG", ""))
    if code != "INFO-000":
        raise DataSourceError(f"C003 returned {code}: {message}")

    try:
        total_count = int(envelope["total_count"])
    except (KeyError, TypeError, ValueError) as error:
        raise DataSourceError("C003 total_count must be a non-negative integer") from error
    if total_count < 0:
        raise DataSourceError("C003 total_count must be a non-negative integer")

    rows = envelope.get("row")
    if not isinstance(rows, list):
        raise DataSourceError("C003 row must be a list")

    products = tuple(_parse_product(row, index, retrieved_at) for index, row in enumerate(rows))
    return C003Page(total_count=total_count, products=products)


def _parse_product(row: object, index: int, retrieved_at: datetime) -> ProductCandidate:
    if not isinstance(row, dict):
        raise DataSourceError(f"C003 row {index} must be an object")

    values = {
        "report_no": row.get("PRDLST_REPORT_NO"),
        "name": row.get("PRDLST_NM"),
        "company": row.get("BSSH_NM"),
        "primary_function": row.get("PRIMARY_FNCLTY", ""),
        "raw_materials": row.get("RAWMTRL_NM", ""),
        "intake_method": row.get("NTK_MTHD", ""),
        "source_id": "C003",
        "retrieved_at": retrieved_at,
    }
    try:
        return ProductCandidate.model_validate(values)
    except ValidationError as error:
        field = str(error.errors()[0]["loc"][0])
        source_field = _MODEL_TO_SOURCE_FIELD.get(field, field)
        raise DataSourceError(f"C003 row {index} has invalid {source_field}") from error
