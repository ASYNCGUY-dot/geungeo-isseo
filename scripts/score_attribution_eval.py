"""Score attribution evaluation labels against the frozen manifest.

For attributed strata a "no" label is a false attribution (the parser would let a claim be
confirmed on another ingredient's evidence); for held strata a "yes" label is a missed attribution
(coverage loss only). Wilson 95% intervals are reported. Strata are recomputed with the current
parser; a changed stratum is listed as drift instead of silently re-bucketing the item.
"""

import argparse
import csv
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from claimledger.attribution_eval import ATTRIBUTED_STRATA, Stratum, classify_pair
from claimledger.domain import IngredientGroup
from claimledger.official_v2 import OFFICIAL_FUNCTION_V2_VERSION, EffectKey
from claimledger.product_review import wilson_interval
from claimledger.snapshot import parse_aware_datetime

_LABELS = {"yes", "no", "unclear", ""}


class ScoreError(ValueError):
    pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score the attribution evaluation")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--source-export", type=Path, required=True)
    parser.add_argument("--source-retrieved-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-zero-false-attribution", action="store_true")
    return parser.parse_args(argv)


def _interval(count: int, total: int) -> list[float] | None:
    interval = wilson_interval(count, total)
    return None if interval is None else [round(interval.lower, 4), round(interval.upper, 4)]


def _read_labels(path: Path, item_ids: set[str]) -> dict[str, dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    labels = {}
    for row in rows:
        label = (row.get("label") or "").strip()
        if label not in _LABELS:
            raise ScoreError(f"unknown label {label!r} for {row.get('item_id')}")
        if row.get("item_id") not in item_ids:
            raise ScoreError(f"label for unknown item {row.get('item_id')!r}")
        labels[row["item_id"]] = {"label": label, "labeler": (row.get("labeler") or "").strip()}
    return labels


def score(manifest: dict, labels: dict[str, dict], rows: dict[str, dict]) -> dict:
    strata: dict[str, dict] = {}
    drift, drift_false, unlabeled = [], [], 0
    now_attributed = {"n": 0, "no": 0, "unclear": 0}
    for item in manifest["items"]:
        row = rows[item["report_no"]]
        current = classify_pair(
            row.get("primary_function") or "", IngredientGroup(item["group"]), EffectKey(item["effect"]),
            row.get("raw_materials") or "",
        )
        if current.value != item["stratum"]:
            drift.append({"item_id": item["item_id"], "manifest": item["stratum"], "current": current.value})
        label = labels.get(item["item_id"], {}).get("label", "")
        if not label:
            unlabeled += 1
            continue
        # The current parser's attributions are scored as a group too; a frozen held item that is
        # attributed now and labelled "no" is also listed on its own.
        if current in ATTRIBUTED_STRATA:
            now_attributed["n"] += 1
            if label in ("no", "unclear"):
                now_attributed[label] += 1
            if Stratum(item["stratum"]) not in ATTRIBUTED_STRATA and label == "no":
                drift_false.append(item["item_id"])
        bucket = strata.setdefault(item["stratum"], {"n": 0, "yes": 0, "no": 0, "unclear": 0})
        bucket["n"] += 1
        bucket[label] += 1
    summary: dict[str, dict] = {}
    attributed_n = attributed_no = 0
    for stratum in Stratum:
        counts = strata.get(stratum.value)
        if counts is None:
            continue
        if stratum in ATTRIBUTED_STRATA:
            attributed_n += counts["n"]
            attributed_no += counts["no"]
            summary[stratum.value] = {
                "n": counts["n"],
                "correct": counts["yes"],
                "false_attribution": counts["no"],
                "unclear": counts["unclear"],
                "false_attribution_wilson": _interval(counts["no"], counts["n"]),
            }
        else:
            summary[stratum.value] = {
                "n": counts["n"],
                "missed_attribution": counts["yes"],
                "correctly_held": counts["no"],
                "unclear": counts["unclear"],
                "missed_attribution_wilson": _interval(counts["yes"], counts["n"]),
            }
    return {
        "eval_id": manifest["eval_id"],
        "parser_version": OFFICIAL_FUNCTION_V2_VERSION,
        "manifest_parser_version": manifest["parser_version"],
        "labelers": sorted({value["labeler"] for value in labels.values() if value["label"]}),
        "strata": summary,
        "attributed_overall": {
            "n": attributed_n,
            "false_attribution": attributed_no,
            "false_attribution_wilson": _interval(attributed_no, attributed_n),
        },
        "current_attributed": {
            "n": now_attributed["n"],
            "false_attribution": now_attributed["no"],
            "unclear": now_attributed["unclear"],
            "false_attribution_wilson": _interval(now_attributed["no"], now_attributed["n"]),
        },
        "unlabeled": unlabeled,
        "stratum_drift": drift,
        "drift_false_attribution": drift_false,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        parse_aware_datetime(args.source_retrieved_at, "--source-retrieved-at")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        data = args.source_export.read_bytes()
        if hashlib.sha256(data).hexdigest().upper() != manifest["source"]["sha256"]:
            raise ScoreError("source export does not match the manifest snapshot hash")
        labels = _read_labels(args.labels, {item["item_id"] for item in manifest["items"]})
        rows = {
            row["report_no"]: row
            for row in (json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip())
        }
        summary = score(manifest, labels, rows)
    except (ScoreError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}")
        return 3
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    overall = summary["attributed_overall"]
    print(f"attributed n={overall['n']} false_attribution={overall['false_attribution']} "
          f"unlabeled={summary['unlabeled']} drift={len(summary['stratum_drift'])} "
          f"drift_false_attribution={len(summary['drift_false_attribution'])} "
          f"current_attributed={summary['current_attributed']['n']}/"
          f"false={summary['current_attributed']['false_attribution']}")
    failed = (
        overall["false_attribution"]
        or summary["drift_false_attribution"]
        or summary["current_attributed"]["false_attribution"]
    )
    if args.require_zero_false_attribution and failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
