"""Build the table of individually approved ingredients that carry a target function (I-0040).

The input is the output of scripts/fetch_i0040.py (an ignored build/ file and its manifest). The table keeps
only approvals whose function text mentions one of the eight target functions, by the same broad keywords
the notice table uses (`effect_mentioned`), with the approval number, name and function text. Headerless
attribution holds a statement when one of these ingredients may be in the raw materials, and its tests
check that every entry of this table is held (headerless-attribution-v4).

usage: build_individual_approvals.py --source build/i0040/<file>.jsonl --manifest <file>.manifest.json
                                     --output src/claimledger/reference/individual_approvals_v1.json
"""

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from claimledger.official_v2 import EffectKey, effect_mentioned

TABLE_VERSION = "individual-approvals-v1"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the I-0040 carrier table of target functions")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def carriers(rows: Sequence[dict]) -> list[dict]:
    items = []
    for row in rows:
        effects = [effect.value for effect in EffectKey if effect_mentioned(row["function_text"], effect)]
        if effects:
            items.append({
                "approval_no": row["approval_no"],
                "ingredient_name": row["ingredient_name"],
                "function_text": row["function_text"],
                "effects": effects,
            })
    return sorted(items, key=lambda item: (item["approval_no"], item["ingredient_name"]))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    raw = args.source.read_bytes()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(raw).hexdigest().upper() != str(manifest.get("sha256", "")).upper():
        print("error: the source does not match its manifest")
        return 3
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    items = carriers(rows)
    payload = {
        "table_version": TABLE_VERSION,
        "source": {
            key: manifest[key]
            for key in ("source_id", "retrieved_at", "total_count", "row_count", "incomplete_count", "sha256")
        },
        "criterion": (
            "Approvals whose function text mentions a target function by the broad keywords of the notice table "
            "(effect_mentioned). Rows without an ingredient name are left out by the fetcher."
        ),
        "row_count": len(rows),
        "carrier_count": len(items),
        "items": items,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(items)} of {len(rows)} approvals carry a target function -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
