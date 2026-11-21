"""Food Safety Korea I-0040: individually approved functional ingredients and their functions.

Only the approval identity and the official function text are kept; addresses, intake amounts and
cautions are not needed for attribution and are dropped at parse time. A row without an ingredient
name identifies nothing and is counted, not kept; a named row without an approval number is kept
(the live list of 2026-11-21 has two of the first and one of the second).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import AwareDatetime, BaseModel, Field, ValidationError

from claimledger.errors import DataSourceError

SERVICE_ID = "I-0040"


class IngredientApproval(BaseModel):
    model_config = {"frozen": True}

    approval_no: str
    approved_on: str
    company: str
    ingredient_name: str = Field(min_length=1)
    function_text: str
    source_id: str = SERVICE_ID
    retrieved_at: AwareDatetime


@dataclass(frozen=True)
class I0040Page:
    total_count: int
    approvals: tuple[IngredientApproval, ...]
    # Rows without an ingredient name on this page.
    incomplete_count: int = 0


class I0040Client:
    base_url = "https://openapi.foodsafetykorea.go.kr"

    def __init__(
        self, api_key: str, http_client: httpx.Client | None = None, timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key.strip()
        if not self.api_key:
            raise DataSourceError("I-0040 API key is required")
        self.http_client = http_client or httpx.Client(timeout=timeout)
        self.timeout = timeout

    def fetch_page(self, start: int, end: int) -> I0040Page:
        if start < 1 or end < start:
            raise DataSourceError("I-0040 page range must satisfy 1 <= start <= end")
        # The key is part of the path. httpx errors quote the URL, so they are not chained.
        request_url = f"{self.base_url}/api/{self.api_key}/{SERVICE_ID}/json/{start}/{end}"
        try:
            response = self.http_client.get(request_url, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException:
            raise DataSourceError("I-0040 request timeout") from None
        except httpx.HTTPStatusError as error:
            raise DataSourceError(f"I-0040 returned HTTP {error.response.status_code}") from None
        except (httpx.HTTPError, ValueError):
            raise DataSourceError("I-0040 request or JSON parsing failed") from None
        if not isinstance(payload, dict):
            raise DataSourceError("I-0040 response must be a JSON object")
        return parse_i0040_payload(payload, retrieved_at=datetime.now(UTC))


def parse_i0040_payload(payload: dict[str, Any], retrieved_at: datetime) -> I0040Page:
    envelope = payload.get(SERVICE_ID)
    if not isinstance(envelope, dict):
        raise DataSourceError("I-0040 response object is missing")
    result = envelope.get("RESULT")
    code = str(result.get("CODE", "UNKNOWN")) if isinstance(result, dict) else "UNKNOWN"
    if code != "INFO-000":
        message = str(result.get("MSG", "")) if isinstance(result, dict) else ""
        raise DataSourceError(f"I-0040 returned {code}: {message}")
    try:
        total_count = int(envelope["total_count"])
    except (KeyError, TypeError, ValueError):
        raise DataSourceError("I-0040 total_count must be a non-negative integer") from None
    if total_count < 0:
        raise DataSourceError("I-0040 total_count must be a non-negative integer")
    rows = envelope.get("row", [])
    if not isinstance(rows, list):
        raise DataSourceError("I-0040 row must be a list")
    parsed = [_parse_row(row, index, retrieved_at) for index, row in enumerate(rows)]
    return I0040Page(
        total_count=total_count,
        approvals=tuple(item for item in parsed if item is not None),
        incomplete_count=sum(item is None for item in parsed),
    )


def _parse_row(row: object, index: int, retrieved_at: datetime) -> IngredientApproval | None:
    if not isinstance(row, dict):
        raise DataSourceError(f"I-0040 row {index} must be an object")
    name = str(row.get("APLC_RAWMTRL_NM") or "").strip()
    if not name:
        return None
    try:
        return IngredientApproval(
            approval_no=str(row.get("HF_FNCLTY_MTRAL_RCOGN_NO") or "").strip(),
            approved_on=str(row.get("PRMS_DT") or ""),
            company=str(row.get("BSSH_NM") or ""),
            ingredient_name=name,
            function_text=str(row.get("FNCLTY_CN") or ""),
            retrieved_at=retrieved_at,
        )
    except ValidationError:
        raise DataSourceError(f"I-0040 row {index} is invalid") from None


__all__ = ["SERVICE_ID", "I0040Client", "I0040Page", "IngredientApproval", "parse_i0040_payload"]
