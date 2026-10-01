"""Build the frozen attribution evaluation sample from a C003 snapshot.

Pairs of (product, ingredient group, effect) are stratified by parser path, sampled with a fixed seed
(round-robin over groups, at most one pair per product), and shuffled into item ids. The manifest
(identifiers, strata, source hash) is tracked; the review sheet with product text hides the stratum
and must stay in an ignored path such as build/.
"""

import argparse
import csv
import hashlib
import json
import random
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from claimledger.attribution_eval import TARGET_GROUPS, Stratum, candidate_pairs
from claimledger.domain import IngredientGroup
from claimledger.official_v2 import OFFICIAL_FUNCTION_V2_VERSION
from claimledger.receipt import EFFECT_LABELS
from claimledger.snapshot import parse_aware_datetime

DEFAULT_QUOTAS = {
    Stratum.ATTRIBUTED_CANONICAL: 20,
    Stratum.ATTRIBUTED_VARIANT_HEADER: 20,
    Stratum.ATTRIBUTED_EXTENDED_FORMAT: 20,
    Stratum.HELD_UNDER_TARGET_HEADER: 15,
    Stratum.HELD_HEADERLESS: 15,
    Stratum.HELD_OTHER: 10,
}
GROUP_LABELS = {
    IngredientGroup.LUTEIN_ZEAXANTHIN: "루테인·지아잔틴",
    IngredientGroup.OMEGA3: "오메가3(EPA·DHA 함유 유지)",
    IngredientGroup.PROBIOTICS: "프로바이오틱스",
}
LABEL_FIELDS = ("item_id", "label", "labeler", "note")


class EvalBuildError(ValueError):
    pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the attribution evaluation sample")
    parser.add_argument("--source-export", type=Path, required=True)
    parser.add_argument("--source-retrieved-at", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--quota", action="append", default=[], help="stratum=count")
    parser.add_argument("--eval-id", default="attribution-eval-v1")
    parser.add_argument("--item-prefix", default="AE")
    parser.add_argument(
        "--exclude-manifest", type=Path, action="append", default=[],
        help="earlier manifest whose products are not sampled again",
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--review-sheet", type=Path, required=True)
    parser.add_argument("--labels-template", type=Path, required=True)
    return parser.parse_args(argv)


def _quotas(values: Sequence[str]) -> dict[Stratum, int]:
    if not values:
        return dict(DEFAULT_QUOTAS)
    quotas: dict[Stratum, int] = {}
    for value in values:
        name, _, count = value.partition("=")
        try:
            quotas[Stratum(name)] = int(count)
        except ValueError:
            raise EvalBuildError(f"invalid quota: {value}") from None
    return quotas


def sample(pairs, quotas: dict[Stratum, int], seed: int):
    rng = random.Random(seed)
    chosen, used = [], set()
    for stratum in Stratum:
        if stratum not in quotas:
            continue
        pool = sorted(
            (pair for pair in pairs if pair.stratum is stratum),
            key=lambda pair: (pair.group.value, pair.report_no, pair.effect.value),
        )
        rng.shuffle(pool)
        queues = {group: [pair for pair in pool if pair.group is group] for group in TARGET_GROUPS}
        picked = 0
        while picked < quotas[stratum] and any(queues.values()):
            for group in TARGET_GROUPS:
                queue = queues[group]
                while queue and queue[0].report_no in used:
                    queue.pop(0)
                if queue and picked < quotas[stratum]:
                    pair = queue.pop(0)
                    chosen.append(pair)
                    used.add(pair.report_no)
                    picked += 1
    rng.shuffle(chosen)
    return chosen


def _review_sheet(eval_id: str, items: list[dict], rows: dict[str, dict]) -> str:
    lines = [
        f"# {eval_id} 귀속 검토지",
        "",
        "각 항목에서 공식 기능성 원문과 원재료만 보고 답합니다. 판정 질문: 이 제품의 공식 기능성 문구는",
        "대상 원료군에 해당 효과가 있다고 말하는가?",
        "",
        "- yes: 그렇다(대상 원료의 문구로 적혀 있거나, 원문과 원재료상 다른 해석이 없음).",
        "- no: 아니다(다른 원료의 문구이거나 해당 효과가 대상 원료에 대해 적혀 있지 않음).",
        "- unclear: 원문만으로 판단할 수 없다.",
        "",
    ]
    for item in items:
        row = rows[item["report_no"]]
        lines += [
            f"## {item['item_id']}",
            "",
            f"- 제품: {row.get('name', '')} ({row.get('company', '')}), 신고번호 {item['report_no']}",
            f"- 대상 원료군: {GROUP_LABELS[IngredientGroup(item['group'])]}",
            f"- 효과: {EFFECT_LABELS[item['effect']]}",
            f"- 원재료: {row.get('raw_materials', '')}",
            "",
            "```text",
            row.get("primary_function", ""),
            "```",
            "",
        ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        retrieved_at = parse_aware_datetime(args.source_retrieved_at, "--source-retrieved-at")
        quotas = _quotas(args.quota)
        data = args.source_export.read_bytes()
        rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
        excluded_manifests, excluded = [], set()
        for path in args.exclude_manifest:
            raw = path.read_bytes()
            earlier = json.loads(raw.decode("utf-8"))
            products = {item["report_no"] for item in earlier["items"]}
            excluded |= products
            excluded_manifests.append({
                "eval_id": earlier["eval_id"],
                "file_name": path.name,
                "sha256": hashlib.sha256(raw).hexdigest().upper(),
                "products": len(products),
            })
    except (ValueError, OSError, KeyError) as exc:
        print(f"error: {exc}")
        return 3
    by_report = {row["report_no"]: row for row in rows}
    pairs = [pair for pair in candidate_pairs(rows) if pair.report_no not in excluded]
    chosen = sample(pairs, quotas, args.seed)
    items = [
        {
            "item_id": f"{args.item_prefix}-{index:03d}",
            "report_no": pair.report_no,
            "group": pair.group.value,
            "effect": pair.effect.value,
            "stratum": pair.stratum.value,
        }
        for index, pair in enumerate(chosen, start=1)
    ]
    manifest = {
        "eval_id": args.eval_id,
        "question": "Does the official function text say that the ingredient group has the effect?",
        "labeling": "Labels are added later in labels.csv with the labeler recorded; see the evidence record.",
        "seed": args.seed,
        "source": {
            "source_id": "C003",
            "file_name": args.source_export.name,
            "sha256": hashlib.sha256(data).hexdigest().upper(),
            "retrieved_at": retrieved_at.isoformat(),
        },
        "parser_version": OFFICIAL_FUNCTION_V2_VERSION,
        "excluded_manifests": excluded_manifests,
        "quotas": {stratum.value: count for stratum, count in quotas.items()},
        "frame_counts": dict(sorted(Counter(pair.stratum.value for pair in pairs).items())),
        "items": items,
    }
    for path in (args.manifest, args.review_sheet, args.labels_template):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    args.review_sheet.write_text(
        _review_sheet(args.eval_id, items, by_report), encoding="utf-8", newline="\n"
    )
    with args.labels_template.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_FIELDS, lineterminator="\n")
        writer.writeheader()
        for item in items:
            writer.writerow({"item_id": item["item_id"], "label": "", "labeler": "", "note": ""})
    print(f"{len(items)} items sampled from {len(pairs)} candidate pairs -> {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
