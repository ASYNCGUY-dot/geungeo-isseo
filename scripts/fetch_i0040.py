"""Fetch every I-0040 row (individually approved functional ingredients) into a local JSONL file.

The API key comes from FOOD_SAFETY_API_KEY (or FOODSAFETY_API_KEY) in the environment or, if
absent, from that single variable in --env-file.
The key is never printed. The output keeps approval identity and function text only and must stay
in an ignored path (for example build/); a manifest records the retrieval time, count and SHA-256.
"""

import argparse
import hashlib
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

from claimledger.errors import DataSourceError
from claimledger.sources.ingredient_approvals import SERVICE_ID, I0040Client, IngredientApproval

# The C003 audit reads FOOD_SAFETY_API_KEY; the project .env spells it FOODSAFETY_API_KEY.
_KEY_NAMES = ("FOOD_SAFETY_API_KEY", "FOODSAFETY_API_KEY")
_FIELDS = ("approval_no", "approved_on", "company", "ingredient_name", "function_text")


def _http_client() -> httpx.Client:
    return httpx.Client(timeout=30.0)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Food Safety Korea I-0040")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--page-size", type=int, default=1000)
    return parser.parse_args(argv)


def _api_key(env_file: Path | None) -> str:
    for name in _KEY_NAMES:
        if key := os.environ.get(name, "").strip():
            return key
    if env_file is None:
        return ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() in _KEY_NAMES and value.strip():
            return value.strip().strip("\"'")
    return ""


def fetch_all(client: I0040Client, page_size: int) -> list[IngredientApproval]:
    approvals: list[IngredientApproval] = []
    total = None
    while total is None or len(approvals) < total:
        page = client.fetch_page(len(approvals) + 1, len(approvals) + page_size)
        total = page.total_count if total is None else total
        if not page.approvals:
            break
        approvals.extend(page.approvals)
    if total is None or len(approvals) != total:
        raise DataSourceError(f"I-0040 returned {len(approvals)} rows, expected {total}")
    return approvals


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        client = I0040Client(_api_key(args.env_file), _http_client())
        approvals = fetch_all(client, args.page_size)
    except (DataSourceError, OSError) as exc:
        print(f"error: {exc}")
        return 3
    text = "".join(
        json.dumps({field: getattr(item, field) for field in _FIELDS}, ensure_ascii=False) + "\n"
        for item in approvals
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8", newline="\n")
    manifest = {
        "source_id": SERVICE_ID,
        "retrieved_at": (approvals[0].retrieved_at if approvals else datetime.now(UTC)).isoformat(),
        "total_count": len(approvals),
        "row_count": len(approvals),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest().upper(),
    }
    args.output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"{len(approvals)} I-0040 rows -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
