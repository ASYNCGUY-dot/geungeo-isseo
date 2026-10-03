"""Build the frozen claim-level evaluation set (one advertisement sentence per real C003 product).

Three steps keep the generator and the labelers blind to each other and to the engine:

- sample: products are stratified by the engine path for one target group (header attribution,
  headerless attribution, held, no effect of the group in the text) and given a claim type with a
  fixed seed. The manifest is tracked; the generation sheet names only the ingredient, the topic
  and the wording style, never the stratum, the claim type or the official text.
- sheet: after the advertisement sentences are written, the labeling sheet shows each sentence with
  the product's official function text and raw materials, without stratum or claim type. Product
  text stays in an ignored path such as build/.
- cases: two label files are merged into the evaluate_dev_cases.py format. Agreed labels form the
  main case file; disagreements are listed, and the optional strict file keeps every case with a
  non-confirmed label wherever a labeler gave one.
"""

import argparse
import csv
import hashlib
import json
import random
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from claimledger.attribution_eval import (
    ATTRIBUTED_STRATA,
    TARGET_GROUPS,
    Stratum,
    candidate_pairs,
    in_raw_materials,
)
from claimledger.claims_v1 import CLAIM_EXTRACTION_VERSION
from claimledger.domain import IngredientGroup, Verdict
from claimledger.headerless import HEADERLESS_ATTRIBUTION_VERSION
from claimledger.official_v2 import (
    EFFECT_GROUP,
    OFFICIAL_FUNCTION_V2_VERSION,
    EffectKey,
    effect_mentioned,
)
from claimledger.receipt import EFFECT_LABELS
from claimledger.snapshot import parse_aware_datetime
from claimledger.verdict_v1 import CLAIM_VERDICT_VERSION

HEADER_ATTRIBUTED = "header_attributed"
HEADERLESS_ATTRIBUTED = "headerless_attributed"
HELD = "held"
NO_EFFECT = "no_effect"
# Stratum -> claim type -> count (100 in total). Official wording on attributed products is the
# expected confirmed set; every other cell is a chance for a false clearance.
ALLOCATION: dict[str, dict[str, int]] = {
    HEADER_ATTRIBUTED: {"official": 14, "exaggerated": 8, "disease": 6, "other_effect": 6, "out_of_scope": 6},
    HEADERLESS_ATTRIBUTED: {"official": 11, "exaggerated": 5, "disease": 4, "other_effect": 3, "out_of_scope": 2},
    HELD: {"official": 10, "exaggerated": 4, "disease": 3, "other_effect": 3},
    NO_EFFECT: {"official": 9, "exaggerated": 3, "disease": 3},
}
OUT_OF_SCOPE_TOPICS = ("피로 회복", "면역력", "피부 건강", "수면의 질")
DISEASE_HINTS = {
    EffectKey.MACULAR_PIGMENT_EYE_HEALTH: "황반변성",
    EffectKey.BLOOD_TRIGLYCERIDE: "고지혈증",
    EffectKey.BLOOD_CIRCULATION: "혈전·뇌졸중",
    EffectKey.MEMORY: "치매",
    EffectKey.DRY_EYE_EYE_HEALTH: "안구건조증",
    EffectKey.PROBIOTIC_GROWTH_HARMFUL_INHIBITION: "장염",
    EffectKey.BOWEL_MOVEMENT: "변비",
    EffectKey.GUT_HEALTH: "과민성대장증후군",
}
SUBJECTS = {
    IngredientGroup.LUTEIN_ZEAXANTHIN: "루테인",
    IngredientGroup.OMEGA3: "오메가3",
    IngredientGroup.PROBIOTICS: "프로바이오틱스",
}
STYLE_TEXT = {
    "support": "공식 인정 수준의 완곡한 표현('~에 도움을 줄 수 있습니다' 정도)",
    "improvement": "효과를 단정하는 표현('~을 개선합니다', '~이 좋아집니다' 등)",
    "guarantee": "효과를 보장하는 표현('반드시', '100%', '확실하게' 등)",
    "disease": "질병의 예방·치료·완화를 말하는 표현",
}
AD_FIELDS = ("case_id", "ad_text")
LABEL_FIELDS = ("case_id", "label", "labeler", "note")


class ClaimEvalError(ValueError):
    pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the frozen claim-level evaluation set")
    commands = parser.add_subparsers(dest="command", required=True)

    sample = commands.add_parser("sample", help="sample products and claim types")
    sample.add_argument("--source-export", type=Path, required=True)
    sample.add_argument("--source-retrieved-at", required=True)
    sample.add_argument("--seed", type=int, required=True)
    sample.add_argument("--eval-id", default="claim-eval-v1")
    sample.add_argument("--case-prefix", default="CE")
    sample.add_argument(
        "--exclude-manifest", type=Path, action="append", default=[],
        help="earlier evaluation manifest whose products are not sampled again",
    )
    sample.add_argument(
        "--exclude-cases", type=Path, action="append", default=[],
        help="case file whose products are not sampled again",
    )
    sample.add_argument("--manifest", type=Path, required=True)
    sample.add_argument("--generation-sheet", type=Path, required=True)
    sample.add_argument("--ads-template", type=Path, required=True)

    sheet = commands.add_parser("sheet", help="write the blind labeling sheet")
    sheet.add_argument("--manifest", type=Path, required=True)
    sheet.add_argument("--ads", type=Path, required=True)
    sheet.add_argument("--source-export", type=Path, required=True)
    sheet.add_argument("--labeling-sheet", type=Path, required=True)
    sheet.add_argument("--labels-template", type=Path, required=True)

    cases = commands.add_parser("cases", help="merge two label files into a case file")
    cases.add_argument("--manifest", type=Path, required=True)
    cases.add_argument("--ads", type=Path, required=True)
    cases.add_argument("--labels", type=Path, action="append", required=True)
    cases.add_argument("--output", type=Path, required=True)
    cases.add_argument("--strict-output", type=Path)
    cases.add_argument("--disagreements", type=Path, required=True)
    return parser.parse_args(argv)


def _rows(path: Path) -> tuple[bytes, list[dict]]:
    data = path.read_bytes()
    return data, [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _frame(rows: list[dict], excluded: set[str]) -> dict[str, list[tuple[str, IngredientGroup, EffectKey | None]]]:
    """(report number, group, effect) candidates per stratum; the effect is None for no_effect."""
    frame: dict[str, list] = {stratum: [] for stratum in ALLOCATION}
    for pair in candidate_pairs(rows):
        if pair.report_no in excluded:
            continue
        if pair.stratum is Stratum.ATTRIBUTED_HEADERLESS:
            stratum = HEADERLESS_ATTRIBUTED
        elif pair.stratum in ATTRIBUTED_STRATA:
            stratum = HEADER_ATTRIBUTED
        else:
            stratum = HELD
        frame[stratum].append((pair.report_no, pair.group, pair.effect))
    for row in rows:
        text = row.get("primary_function") or ""
        if row["report_no"] in excluded or not text.strip():
            continue
        for group in TARGET_GROUPS:
            effects = [effect for effect in EffectKey if EFFECT_GROUP[effect] is group]
            if in_raw_materials(row.get("raw_materials") or "", group) and not any(
                effect_mentioned(text, effect) for effect in effects
            ):
                frame[NO_EFFECT].append((row["report_no"], group, None))
    return frame


def _claim(
    rng: random.Random, claim_type: str, group: IngredientGroup, effect: EffectKey | None, text: str,
) -> dict:
    if claim_type == "out_of_scope":
        return {"effect": None, "topic": rng.choice(OUT_OF_SCOPE_TOPICS), "style": "support", "disease_hint": None}
    if claim_type == "other_effect":
        absent = [item for item in EffectKey if not effect_mentioned(text, item)]
        same_group = [item for item in absent if EFFECT_GROUP[item] is group]
        effect = rng.choice(same_group or absent)
    elif effect is None:
        effect = rng.choice([item for item in EffectKey if EFFECT_GROUP[item] is group])
    style = {"official": "support", "other_effect": "support", "disease": "disease"}.get(claim_type)
    if style is None:
        style = rng.choice(("improvement", "guarantee"))
    return {
        "effect": effect.value,
        "topic": EFFECT_LABELS[effect],
        "style": style,
        "disease_hint": DISEASE_HINTS[effect] if claim_type == "disease" else None,
    }


def sample_items(rows: list[dict], excluded: set[str], seed: int, prefix: str) -> tuple[list[dict], dict]:
    rng = random.Random(seed)
    by_report = {row["report_no"]: row for row in rows}
    frame = _frame(rows, excluded)
    chosen, used = [], set()
    for stratum, allocation in ALLOCATION.items():
        pool = sorted(
            frame[stratum],
            key=lambda item: (item[1].value, item[0], item[2].value if item[2] else ""),
        )
        rng.shuffle(pool)
        queues = {group: [item for item in pool if item[1] is group] for group in TARGET_GROUPS}
        turn = 0
        for claim_type, count in allocation.items():
            picked = 0
            while picked < count:
                if not any(queue for queue in queues.values()):
                    raise ClaimEvalError(f"not enough {stratum} products for {claim_type}")
                group = TARGET_GROUPS[turn % len(TARGET_GROUPS)]
                turn += 1
                queue = queues[group]
                while queue and queue[0][0] in used:
                    queue.pop(0)
                if not queue:
                    continue
                report_no, _, effect = queue.pop(0)
                used.add(report_no)
                text = by_report[report_no].get("primary_function") or ""
                chosen.append({
                    "report_no": report_no,
                    "group": group.value,
                    "stratum": stratum,
                    "claim_type": claim_type,
                    "subject": SUBJECTS[group],
                    **_claim(rng, claim_type, group, effect, text),
                })
                picked += 1
    rng.shuffle(chosen)
    items = [{"case_id": f"{prefix}-{index:03d}", **item} for index, item in enumerate(chosen, start=1)]
    frame_counts = {stratum: len(frame[stratum]) for stratum in ALLOCATION}
    return items, frame_counts


def _generation_sheet(eval_id: str, items: list[dict]) -> str:
    lines = [
        f"# {eval_id} 광고 문장 생성지",
        "",
        "사례마다 한국어 건강기능식품 광고 문장을 **한 문장** 씁니다.",
        "",
        "- 주어는 지정된 원료명으로 씁니다(예: '루테인은 …').",
        "- 지정된 주제 하나만 말합니다. 다른 효과·성분·제품명을 덧붙이지 않습니다.",
        "- 지정된 표현 방식을 따르되, 실제 광고처럼 자연스럽게 쓰고 사례마다 어휘를 조금씩 바꿉니다.",
        "- 질병 표현 사례는 지정된 질병명을 문장에 넣습니다.",
        "- 결과는 ads.csv의 ad_text 칸에 씁니다. 쉼표가 들어가면 큰따옴표로 감쌉니다.",
        "",
        "| case_id | 원료명(주어) | 주제 | 표현 방식 |",
        "|---|---|---|---|",
    ]
    for item in items:
        style = STYLE_TEXT[item["style"]]
        if item["disease_hint"]:
            style += f": {item['disease_hint']}"
        lines.append(f"| {item['case_id']} | {item['subject']} | {item['topic']} | {style} |")
    return "\n".join(lines) + "\n"


def _labeling_sheet(eval_id: str, items: list[dict], ads: dict[str, str], rows: dict[str, dict]) -> str:
    lines = [
        f"# {eval_id} 기대 판정 라벨지",
        "",
        "각 사례의 광고 문장 하나를, 그 제품의 공식 기능성 원문(식품안전나라 C003)과 원재료만 보고 판정합니다.",
        "아래 순서대로 적용하고 처음 해당하는 판정을 고릅니다.",
        "",
        "1. 질병의 예방·치료·완화(예: 황반변성 예방, 변비 치료)를 말하면 `mismatch`(근거 불일치).",
        "   건강기능식품은 질병 표현을 할 수 없으므로 원문 내용과 관계없이 적용합니다.",
        "2. 주장하는 기능이 판정 규칙이 다루는 기능 8개 밖이면 `unverifiable`(검증 불가). 8개는 황반색소밀도 유지·눈 건강,",
        "   혈중 중성지질 개선, 혈행 개선, 기억력 개선, 건조한 눈 개선, 유산균 증식·유해균 억제, 배변활동 원활, 장 건강입니다.",
        "   어느 원료가 주어인지와 관계없이 이 목록으로 판단합니다(예: 다른 원료를 주어로 '혈행 개선'을 말해도 범위 안이며 3·4번으로 판단).",
        "   광고 문장이 무슨 기능을 주장하는지 불분명할 때도 `unverifiable`입니다.",
        "3. 공식 원문 어디에도 그 기능이 없으면 `mismatch`.",
        "4. 원문에 그 기능이 있지만 광고 주어(원료)의 기능인지 원문과 원재료만으로 확정할 수 없으면 `unverifiable`.",
        "   예: 다른 원료 이름 아래 적힌 문구, 원료 표시 없이 나열됐고 다른 원료의 기능일 수 있는 문구.",
        "5. 광고 원료의 기능으로 확정되지만 표현이 '도움을 줄 수 있음'보다 강하면(단정·보장) `mismatch`.",
        "6. 그 외(광고 원료의 기능으로 확정, '도움' 수준 이하, 질병 표현 없음)는 `confirmed`(확인됨).",
        "",
        "labels.csv의 label 칸에 confirmed / mismatch / unverifiable 중 하나를 쓰고, note에 근거를 한 줄로 적습니다.",
        "",
    ]
    for item in items:
        row = rows[item["report_no"]]
        lines += [
            f"## {item['case_id']}",
            "",
            f"- 광고 문장: {ads[item['case_id']]}",
            f"- 제품: {row.get('name', '')} ({row.get('company', '')}), 신고번호 {item['report_no']}",
            f"- 원재료: {row.get('raw_materials', '')}",
            "",
            "```text",
            row.get("primary_function", ""),
            "```",
            "",
        ]
    return "\n".join(lines)


def _read_csv(path: Path, fields: Sequence[str]) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not set(fields) <= set(reader.fieldnames):
            raise ClaimEvalError(f"{path.name}: columns must include {', '.join(fields)}")
        return list(reader)


def _ads(path: Path, items: list[dict]) -> dict[str, str]:
    ads = {row["case_id"]: (row["ad_text"] or "").strip() for row in _read_csv(path, AD_FIELDS)}
    missing = [item["case_id"] for item in items if not ads.get(item["case_id"])]
    if missing or len(ads) != len(items):
        raise ClaimEvalError(f"advertisement file must cover every case exactly once (missing: {missing[:5]})")
    return ads


def _labels(path: Path, items: list[dict]) -> tuple[str, dict[str, str]]:
    rows = _read_csv(path, LABEL_FIELDS)
    labels: dict[str, str] = {}
    for row in rows:
        try:
            labels[row["case_id"]] = Verdict(row["label"].strip()).value
        except ValueError:
            raise ClaimEvalError(f"{path.name}: invalid label {row['label']!r} for {row['case_id']}") from None
    names = {row["labeler"].strip() for row in rows}
    if len(names) != 1 or "" in names:
        raise ClaimEvalError(f"{path.name}: one non-empty labeler name is required")
    if set(labels) != {item["case_id"] for item in items} or len(rows) != len(items):
        raise ClaimEvalError(f"{path.name}: labels must cover every case exactly once")
    return names.pop(), labels


def _case_file(manifest: dict, cases: list[dict], labelers: list[str], strict: bool) -> dict:
    rule = "a non-confirmed label where the labelers disagree" if strict else "agreed labels only"
    return {
        "dataset_id": manifest["eval_id"] + ("-strict" if strict else ""),
        "purpose": "frozen claim-level evaluation; AI-generated advertisement sentences for real C003 products",
        "labeling": (
            f"Expected verdicts are blind AI labels ({', '.join(labelers)}), {rule}. "
            "They are not human or expert labels."
        ),
        "source_snapshot": f"C003 JSONL retrieved {manifest['source']['retrieved_at']}",
        "cases": cases,
    }


def _sample(args: argparse.Namespace) -> int:
    retrieved_at = parse_aware_datetime(args.source_retrieved_at, "--source-retrieved-at")
    data, rows = _rows(args.source_export)
    excluded, sources = set(), []
    for path, kind in [(path, "manifest") for path in args.exclude_manifest] + [
        (path, "cases") for path in args.exclude_cases
    ]:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        entries = payload["items"] if kind == "manifest" else payload["cases"]
        products = {entry["report_no"] for entry in entries if entry.get("report_no")}
        excluded |= products
        sources.append({
            "id": payload.get("eval_id") or payload.get("dataset_id"),
            "file_name": path.name,
            "sha256": _sha(raw),
            "products": len(products),
        })
    items, frame_counts = sample_items(rows, excluded, args.seed, args.case_prefix)
    manifest = {
        "eval_id": args.eval_id,
        "question": "What verdict should the advertisement sentence get against the product's official function text?",
        "labeling": "Two blind AI labelers label the frozen sentences later; see the evidence record.",
        "seed": args.seed,
        "source": {
            "source_id": "C003",
            "file_name": args.source_export.name,
            "sha256": _sha(data),
            "retrieved_at": retrieved_at.isoformat(),
        },
        "engine_versions": {
            "parser": OFFICIAL_FUNCTION_V2_VERSION,
            "headerless": HEADERLESS_ATTRIBUTION_VERSION,
            "extraction": CLAIM_EXTRACTION_VERSION,
            "verdict": CLAIM_VERDICT_VERSION,
        },
        "excluded_sources": sources,
        "excluded_products": len(excluded),
        "allocation": ALLOCATION,
        "frame_counts": frame_counts,
        "group_counts": dict(sorted(Counter(item["group"] for item in items).items())),
        "items": items,
    }
    _write_json(args.manifest, manifest)
    args.generation_sheet.parent.mkdir(parents=True, exist_ok=True)
    args.generation_sheet.write_text(_generation_sheet(args.eval_id, items), encoding="utf-8", newline="\n")
    args.ads_template.parent.mkdir(parents=True, exist_ok=True)
    with args.ads_template.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AD_FIELDS, lineterminator="\n")
        writer.writeheader()
        for item in items:
            writer.writerow({"case_id": item["case_id"], "ad_text": ""})
    print(f"{len(items)} cases sampled ({frame_counts}) -> {args.manifest}")
    return 0


def _sheet(args: argparse.Namespace) -> int:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    items = manifest["items"]
    ads = _ads(args.ads, items)
    rows = {row["report_no"]: row for row in _rows(args.source_export)[1]}
    args.labeling_sheet.parent.mkdir(parents=True, exist_ok=True)
    args.labeling_sheet.write_text(
        _labeling_sheet(manifest["eval_id"], items, ads, rows), encoding="utf-8", newline="\n"
    )
    with args.labels_template.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_FIELDS, lineterminator="\n")
        writer.writeheader()
        for item in items:
            writer.writerow({"case_id": item["case_id"], "label": "", "labeler": "", "note": ""})
    print(f"labeling sheet for {len(items)} cases -> {args.labeling_sheet}")
    return 0


def _cases(args: argparse.Namespace) -> int:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    items = manifest["items"]
    ads = _ads(args.ads, items)
    if len(args.labels) != 2:
        raise ClaimEvalError("exactly two label files are required")
    labelled = [_labels(path, items) for path in args.labels]
    labelers = [name for name, _ in labelled]
    agreed, strict, disagreements = [], [], []
    for item in items:
        case_id = item["case_id"]
        values = [labels[case_id] for _, labels in labelled]
        case = {"case_id": case_id, "report_no": item["report_no"], "ad_text": ads[case_id]}
        if values[0] == values[1]:
            agreed.append({**case, "expected_verdict": values[0], "note": ""})
            strict.append({**case, "expected_verdict": values[0], "note": ""})
            continue
        disagreements.append({"case_id": case_id, "labels": dict(zip(labelers, values, strict=True))})
        conservative = next(value for value in values if value != Verdict.CONFIRMED.value)
        strict.append({
            **case,
            "expected_verdict": conservative,
            "note": "labelers disagree: " + ", ".join(f"{n}={v}" for n, v in zip(labelers, values, strict=True)),
        })
    _write_json(args.output, _case_file(manifest, agreed, labelers, strict=False))
    if args.strict_output is not None:
        _write_json(args.strict_output, _case_file(manifest, strict, labelers, strict=True))
    _write_json(args.disagreements, disagreements)
    print(f"{len(agreed)} agreed cases, {len(disagreements)} disagreements -> {args.output}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    command = {"sample": _sample, "sheet": _sheet, "cases": _cases}[args.command]
    try:
        return command(args)
    except (ClaimEvalError, ValueError, OSError, KeyError) as exc:
        print(f"error: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
