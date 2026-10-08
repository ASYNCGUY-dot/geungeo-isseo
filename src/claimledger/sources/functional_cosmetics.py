"""MFDS functional cosmetics on data.go.kr: reported (보고) and reviewed (심사) products.

Field names follow the published Swagger specifications (read 2026-10-07). Only product identity,
the registration date and the official efficacy fields are kept; addresses and business
registration numbers are dropped at parse time. The specification documents `body.items.item`;
list forms common on data.go.kr are accepted too and anything else fails closed. The live shape
is measured by scripts/audit_cosmetics.py before any verdict rule relies on these fields.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote

import httpx
from pydantic import AwareDatetime, BaseModel, Field, ValidationError

from claimledger.errors import DataSourceError


@dataclass(frozen=True)
class CosmeticsSource:
    key: str
    source_id: str
    url: str
    date_field: str


REPORTED = CosmeticsSource(
    "reported",
    "data.go.kr:15095680",
    "https://apis.data.go.kr/1471000/FtnltCosmRptPrdlstInfoService01/getRptPrdlstInq01",
    "REPORT_DATE",
)
REVIEWED = CosmeticsSource(
    "reviewed",
    "data.go.kr:15056939",
    "https://apis.data.go.kr/1471057/FtnltCosmSrngPrdlstInfoService05/getSrngPrdlstInq05",
    "ITEM_PERMIT_DATE",
)
SOURCES = {source.key: source for source in (REPORTED, REVIEWED)}
# Gateway errors (key, quota, unknown service) carry an upper-case reason code. On 2026-10-09 they
# came as JSON with HTTP 403 or 400; the XML form is kept for the older gateway. Only the code is
# echoed, never free text.
_REASON_CODE = re.compile(r"[A-Z][A-Z_ ]{1,79}")
_XML_REASON = re.compile(r"<(?:returnAuthMsg|errMsg)>([A-Z][A-Z_ ]{1,79})</")


class FunctionalCosmetic(BaseModel):
    model_config = {"frozen": True}

    item_seq: str = Field(min_length=1)
    item_name: str = Field(min_length=1)
    company: str
    registered_on: str
    effect_text: str
    effect_code: str = ""
    effect_name: str = ""
    # Reported products only: the three flagged functions and withdrawal of the report.
    whitening: bool | None = None
    wrinkle: bool | None = None
    sunscreen: bool | None = None
    spf: str = ""
    pa: str = ""
    withdrawn: bool | None = None
    # Reviewed products only: notified or non-notified item class.
    notice_class: str = ""
    source_id: str
    retrieved_at: AwareDatetime


@dataclass(frozen=True)
class CosmeticsPage:
    total_count: int
    items: tuple[FunctionalCosmetic, ...]


class FunctionalCosmeticsClient:
    def __init__(
        self,
        source: CosmeticsSource,
        api_key: str,
        http_client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        key = api_key.strip()
        if not key:
            raise DataSourceError(f"{source.source_id} service key is required")
        self.source = source
        # data.go.kr issues the key in encoded and decoded forms; httpx encodes query values itself.
        self.api_key = unquote(key) if "%" in key else key
        self.http_client = http_client or httpx.Client(timeout=timeout)
        self.timeout = timeout

    def fetch_page(self, page_no: int, num_of_rows: int) -> CosmeticsPage:
        name = self.source.source_id
        if page_no < 1 or num_of_rows < 1:
            raise DataSourceError(f"{name} page number and size must be positive")
        params = {"serviceKey": self.api_key, "pageNo": page_no, "numOfRows": num_of_rows, "type": "json"}
        # The key is a query parameter. httpx errors quote the URL, so they are not chained.
        try:
            response = self.http_client.get(self.source.url, params=params, timeout=self.timeout)
            response.raise_for_status()
        except httpx.TimeoutException:
            raise DataSourceError(f"{name} request timeout") from None
        except httpx.HTTPStatusError as error:
            reason = _gateway_reason(error.response)
            status = f"{name} returned HTTP {error.response.status_code}"
            raise DataSourceError(f"{status}: {reason}" if reason else status) from None
        except httpx.HTTPError:
            raise DataSourceError(f"{name} request failed") from None
        try:
            payload = response.json()
        except ValueError:
            detail = _gateway_reason(response) or "response is not JSON"
            raise DataSourceError(f"{name} gateway error: {detail}") from None
        if not isinstance(payload, dict):
            raise DataSourceError(f"{name} response must be a JSON object")
        if "OpenAPI_ServiceResponse" in payload:
            detail = _gateway_reason(response) or "unknown reason"
            raise DataSourceError(f"{name} gateway error: {detail}")
        return parse_cosmetics_payload(payload, self.source, retrieved_at=datetime.now(UTC))


def _gateway_reason(response: httpx.Response) -> str | None:
    try:
        header = response.json()["OpenAPI_ServiceResponse"]["cmmMsgHeader"]
        code = str(header.get("errMsg") or "")
    except (ValueError, KeyError, TypeError, AttributeError):
        match = _XML_REASON.search(response.text)
        return match.group(1).strip() if match else None
    return code if _REASON_CODE.fullmatch(code) else None


def parse_cosmetics_payload(
    payload: dict[str, Any], source: CosmeticsSource, retrieved_at: datetime,
) -> CosmeticsPage:
    name = source.source_id
    envelope = payload["response"] if isinstance(payload.get("response"), dict) else payload
    header, body = envelope.get("header"), envelope.get("body")
    if not isinstance(header, dict) or not isinstance(body, dict):
        raise DataSourceError(f"{name} response lacks a header or body")
    code = str(header.get("resultCode", "UNKNOWN"))
    if code != "00":
        raise DataSourceError(f"{name} returned {code}: {header.get('resultMsg', '')}")
    try:
        total_count = int(body["totalCount"])
    except (KeyError, TypeError, ValueError):
        raise DataSourceError(f"{name} totalCount must be a non-negative integer") from None
    if total_count < 0:
        raise DataSourceError(f"{name} totalCount must be a non-negative integer")
    rows = _rows(body.get("items"), name)
    return CosmeticsPage(
        total_count=total_count,
        items=tuple(_parse_row(row, index, source, retrieved_at) for index, row in enumerate(rows)),
    )


def _rows(items: object, name: str) -> list[dict]:
    if items is None or items == "":
        return []
    if isinstance(items, dict):
        items = items.get("item")
        if isinstance(items, dict):
            return [items]
    if not isinstance(items, list):
        raise DataSourceError(f"{name} items has an unknown shape")
    rows: list[dict] = []
    for index, row in enumerate(items):
        if isinstance(row, dict) and set(row) == {"item"} and isinstance(row["item"], dict):
            row = row["item"]
        if not isinstance(row, dict):
            raise DataSourceError(f"{name} row {index} must be an object")
        rows.append(row)
    return rows


def _text(row: dict, key: str) -> str:
    return str(row.get(key) or "").strip()


def _flag(row: dict, key: str) -> bool | None:
    return {"Y": True, "N": False}.get(_text(row, key).upper())


def _parse_row(
    row: dict, index: int, source: CosmeticsSource, retrieved_at: datetime,
) -> FunctionalCosmetic:
    try:
        return FunctionalCosmetic(
            item_seq=_text(row, "ITEM_SEQ"),
            item_name=_text(row, "ITEM_NAME"),
            company=_text(row, "ENTP_NAME"),
            registered_on=_text(row, source.date_field),
            effect_text=_text(row, "EE_DOC_DATA"),
            effect_code=_text(row, "EE_CODE"),
            effect_name=_text(row, "EE_NAME"),
            whitening=_flag(row, "EFFECT_YN1"),
            wrinkle=_flag(row, "EFFECT_YN2"),
            sunscreen=_flag(row, "EFFECT_YN3"),
            spf=_text(row, "SPF"),
            pa=_text(row, "PA"),
            withdrawn=_flag(row, "CANCEL_APPROVAL_YN"),
            notice_class=_text(row, "COSMETIC_NOTICE_NAME"),
            source_id=source.source_id,
            retrieved_at=retrieved_at,
        )
    except ValidationError:
        raise DataSourceError(f"{source.source_id} row {index} lacks an item number or name") from None


__all__ = [
    "REPORTED",
    "REVIEWED",
    "SOURCES",
    "CosmeticsPage",
    "CosmeticsSource",
    "FunctionalCosmetic",
    "FunctionalCosmeticsClient",
    "parse_cosmetics_payload",
]
