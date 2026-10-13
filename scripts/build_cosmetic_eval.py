"""Build and score the frozen evaluation set for cosmetics claims (whitening and wrinkle improvement).

Four steps keep the sentence writer, the labelers and the engine apart:

- sample: real records from the local MFDS export are stratified by how the efficacy reader sees
  them (both functions, one function, with sunscreen, another function only, and the four kinds of
  held data) and given a claim type with a fixed seed. The generation sheet names only the subject,
  the topic and the wording style. The second allocation adds two claim types that should not be
  mismatches: the other function named beside the claim, and the cover of make-up.
- sheet: the labeling sheet shows each sentence with the record's official efficacy fields as
  published, without stratum or claim type. Product text stays in an ignored path.
- cases: two label files are merged. Agreed labels form the main case file; the strict file keeps
  every case with a non-confirmed label wherever a labeler gave one.
- score: the engine judges each case; a confirmed verdict where the label is not confirmed is a
  false clearance. Exit codes: 0 done, 1 false clearance with --require-zero-false-clearance,
  3 input error.
"""

import argparse
import csv
import json
import random
from collections.abc import Sequence
from pathlib import Path

from claimledger.cosmetics_claims import (
    COSMETIC_CLAIM_VERSION,
    confirm_cosmetic_claims,
    extract_cosmetic_claims,
)
from claimledger.cosmetics_official import (
    COSMETIC_EFFICACY_VERSION,
    CosmeticFunction,
    EfficacyStatus,
    parse_cosmetic_efficacy,
)
from claimledger.cosmetics_verdict import (
    COSMETIC_VERDICT_VERSION,
    ConfirmedCosmetic,
    decide_cosmetic_ad,
)
from claimledger.domain import Verdict
from claimledger.errors import DataSourceError
from claimledger.evaluation import confirmed_recall, false_clearance_rate
from claimledger.sources.functional_cosmetics import (
    SOURCES,
    FunctionalCosmetic,
    export_stem,
    load_cosmetics_export,
)

W, R, S = CosmeticFunction.WHITENING, CosmeticFunction.WRINKLE, CosmeticFunction.SUNSCREEN
# Stratum -> claim type -> count (100 in total).
ALLOCATION: dict[str, dict[str, int]] = {
    "both": {"official": 14, "exaggerated": 6, "medical": 4, "ingredient": 5, "out_of_scope": 5},
    "whitening_only": {"official": 5, "absent": 4, "exaggerated": 3},
    "wrinkle_only": {"official": 5, "absent": 4, "exaggerated": 3},
    "with_sunscreen": {"official": 5, "exaggerated": 2, "medical": 1, "out_of_scope": 2},
    "other_function": {"absent": 9, "out_of_scope": 3},
    "held_missing": {"official": 6, "exaggerated": 2},
    "held_template": {"official": 4, "medical": 1},
    "held_unrecognized": {"official": 4, "exaggerated": 1},
    "held_conflicting": {"official": 2},
}
# Sentences that name a function without claiming it for the product ("bystander") or speak of
# make-up cover ("makeup") show whether a mismatch is given where nothing contradicts the record.
ALLOCATIONS: dict[str, dict[str, dict[str, int]]] = {
    "claims-v1": ALLOCATION,
    "claims-v2": {
        "both": {"official": 12, "exaggerated": 7, "medical": 4, "ingredient": 4, "out_of_scope": 4, "makeup": 3},
        "whitening_only": {"official": 3, "absent": 4, "exaggerated": 3, "bystander": 2},
        "wrinkle_only": {"official": 3, "absent": 4, "exaggerated": 3, "bystander": 2},
        "with_sunscreen": {"official": 4, "exaggerated": 2, "medical": 1, "out_of_scope": 1, "makeup": 2},
        "other_function": {"absent": 9, "out_of_scope": 3},
        "held_missing": {"official": 6, "exaggerated": 2},
        "held_template": {"official": 4, "medical": 1},
        "held_unrecognized": {"official": 4, "exaggerated": 1},
        "held_conflicting": {"official": 2},
    },
}
_HELD = {
    EfficacyStatus.MISSING: "held_missing",
    EfficacyStatus.TEMPLATE_REMNANT: "held_template",
    EfficacyStatus.UNRECOGNIZED_WORDING: "held_unrecognized",
    EfficacyStatus.CONFLICTING_FIELDS: "held_conflicting",
}
TOPIC_TEXT = {(W,): "피부 미백", (R,): "피부 주름개선", (W, R): "피부 미백과 주름개선"}
OUT_OF_SCOPE_TOPICS = ("자외선 차단", "피부 보습", "피부 탄력", "모공 관리", "피부결 정돈")
MAKEUP_TOPIC = "바른 직후의 톤업·커버"
ASIDE_TEXT = {W: "미백", R: "주름개선"}
INGREDIENTS = {(W,): "나이아신아마이드", (R,): "아데노신", (W, R): "레티놀"}
MEDICAL_HINTS = {(W,): "기미·잡티 치료", (R,): "피부 재생", (W, R): "피부 재생·염증 완화"}
STYLE_TEXT = {
    "support": "공식 인정 수준의 완곡한 표현('~에 도움을 줍니다', '~에 도움을 줄 수 있습니다' 정도)",
    "improvement": "효과를 단정하는 표현('~을 개선합니다', '~이 사라집니다' 등)",
    "guarantee": "효과를 보장하거나 기간을 약속하는 표현('100%', '확실하게', '7일 만에' 등)",
    "medical": "질병 치료나 의료 시술의 효과처럼 말하는 표현",
    "makeup": "바른 직후 피부 톤이 밝아 보이거나 잡티가 가려지는 메이크업 효과로 말하는 표현(미백 기능이나 피부 자체의 변화로 말하지 않음)",
}
AD_FIELDS = ("case_id", "ad_text")
LABEL_FIELDS = ("case_id", "label", "labeler", "note")
SOURCE_LABELS = {"reported": "보고품목", "reviewed": "심사품목"}


class CosmeticEvalError(ValueError):
    pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and score the cosmetics claim evaluation set")
    commands = parser.add_subparsers(dest="command", required=True)

    sample = commands.add_parser("sample", help="sample records and claim types")
    sample.add_argument("--export-dir", type=Path, default=Path("build/cosmetics"))
    sample.add_argument("--seed", type=int, required=True)
    sample.add_argument("--eval-id", default="cosmetic-eval-v1")
    sample.add_argument("--case-prefix", default="CC")
    sample.add_argument("--allocation", choices=sorted(ALLOCATIONS), default="claims-v1")
    sample.add_argument("--manifest", type=Path, required=True)
    sample.add_argument("--generation-sheet", type=Path, required=True)
    sample.add_argument("--ads-template", type=Path, required=True)
    sample.add_argument(
        "--exclude-manifest", type=Path, action="append", default=[],
        help="manifest of an earlier set whose records are not sampled again",
    )

    sheet = commands.add_parser("sheet", help="write the blind labeling sheet")
    sheet.add_argument("--manifest", type=Path, required=True)
    sheet.add_argument("--ads", type=Path, required=True)
    sheet.add_argument("--export-dir", type=Path, default=Path("build/cosmetics"))
    sheet.add_argument("--labeling-sheet", type=Path, required=True)
    sheet.add_argument("--labels-template", type=Path, required=True)

    cases = commands.add_parser("cases", help="merge two label files into case files")
    cases.add_argument("--manifest", type=Path, required=True)
    cases.add_argument("--ads", type=Path, required=True)
    cases.add_argument("--labels", type=Path, action="append", required=True)
    cases.add_argument("--output", type=Path, required=True)
    cases.add_argument("--strict-output", type=Path)
    cases.add_argument("--disagreements", type=Path, required=True)

    score = commands.add_parser("score", help="judge the cases with the engine")
    score.add_argument("--cases", type=Path, required=True)
    score.add_argument("--export-dir", type=Path, default=Path("build/cosmetics"))
    score.add_argument("--output", type=Path)
    score.add_argument("--require-zero-false-clearance", action="store_true")
    return parser.parse_args(argv)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _load(directory: Path) -> dict[str, dict[str, FunctionalCosmetic]]:
    return {
        key: {item.record_id: item for item in load_cosmetics_export(directory, source)[1]}
        for key, source in SOURCES.items()
    }


def stratum_of(item: FunctionalCosmetic) -> tuple[str, tuple[CosmeticFunction, ...]]:
    """Sampling stratum and the judged functions the reader sees for the record."""
    efficacy = parse_cosmetic_efficacy(item.effect_text, item.effect_name)
    if efficacy.status is not EfficacyStatus.READABLE:
        return _HELD[efficacy.status], ()
    judged = tuple(function for function in (W, R) if function in efficacy.functions)
    if not judged:
        return "other_function", ()
    if S in efficacy.functions:
        return "with_sunscreen", judged
    return {(W, R): "both", (W,): "whitening_only", (R,): "wrinkle_only"}[judged], judged


def _claim(rng: random.Random, claim_type: str, judged: tuple[CosmeticFunction, ...]) -> dict:
    """Topic, subject, style and hint for one case."""
    subsets = [(W,), (R,), (W, R)]
    plain = {"subject": "제품", "style": "support", "hint": None, "aside": None}
    if claim_type == "out_of_scope":
        return {"topic": [], "topic_text": rng.choice(OUT_OF_SCOPE_TOPICS), **plain}
    if claim_type == "makeup":
        return {"topic": [], "topic_text": MAKEUP_TOPIC, **plain, "style": "makeup"}
    if claim_type == "bystander":
        # The product's own function is claimed; the one it lacks is only named beside it.
        (own,) = judged
        (other,) = {W, R} - {own}
        return {"topic": [own.value], "topic_text": TOPIC_TEXT[judged], **plain, "aside": ASIDE_TEXT[other]}
    if claim_type == "absent":
        topic = rng.choice([subset for subset in subsets if set(subset) - set(judged)])
    elif judged:
        topic = rng.choice([subset for subset in subsets if set(subset) <= set(judged)])
    else:
        topic = rng.choice(subsets)
    style = {"exaggerated": rng.choice(("improvement", "guarantee")), "medical": "medical"}.get(claim_type, "support")
    return {
        "topic": [function.value for function in topic],
        "topic_text": TOPIC_TEXT[topic],
        "subject": INGREDIENTS[topic] if claim_type == "ingredient" else "제품",
        "style": style,
        "hint": MEDICAL_HINTS[topic] if claim_type == "medical" else None,
        "aside": None,
    }


def sample_items(
    records: dict[str, dict[str, FunctionalCosmetic]], seed: int, prefix: str,
    excluded: frozenset[tuple[str, str]] = frozenset(),
    allocation: dict[str, dict[str, int]] = ALLOCATION,
) -> tuple[list[dict], dict[str, int]]:
    rng = random.Random(seed)
    pools: dict[str, dict[str, list[tuple[str, tuple[CosmeticFunction, ...]]]]] = {
        stratum: {key: [] for key in SOURCES} for stratum in allocation
    }
    for key in SOURCES:
        for record_id in sorted(records[key]):
            if (key, record_id) in excluded:
                continue
            stratum, judged = stratum_of(records[key][record_id])
            pools[stratum][key].append((record_id, judged))
    chosen: list[dict] = []
    for stratum, claim_types in allocation.items():
        for queue in pools[stratum].values():
            rng.shuffle(queue)
        turn = 0
        for claim_type, count in claim_types.items():
            for _ in range(count):
                if not any(pools[stratum].values()):
                    raise CosmeticEvalError(f"not enough {stratum} records for {claim_type}")
                # Alternate between the two lists; fall back to the other when one is exhausted.
                keys = list(SOURCES)
                key = keys[turn % len(keys)] if pools[stratum][keys[turn % len(keys)]] else keys[(turn + 1) % len(keys)]
                turn += 1
                record_id, judged = pools[stratum][key].pop()
                chosen.append({
                    "source": key, "record_id": record_id, "stratum": stratum, "claim_type": claim_type,
                    **_claim(rng, claim_type, judged),
                })
    rng.shuffle(chosen)
    items = [{"case_id": f"{prefix}-{index:03d}", **item} for index, item in enumerate(chosen, start=1)]
    frame = {stratum: sum(len(queue) for queue in pools[stratum].values()) + sum(allocation[stratum].values()) for stratum in allocation}
    return items, frame


def _generation_sheet(eval_id: str, items: list[dict]) -> str:
    lines = [
        f"# {eval_id} 광고 문장 생성지",
        "",
        "사례마다 한국어 화장품 광고 문장을 **한 문장** 씁니다.",
        "",
        "- 주어가 '제품'이면 제품을 주어로 하거나('이 제품은 …') 주어 없이 씁니다. 성분명이 지정되면 그 성분을 주어로 씁니다.",
        "- 지정된 주제 하나만 말합니다. 다른 효과·성분·제품명·브랜드명을 덧붙이지 않습니다.",
        "- 지정된 표현 방식의 강도를 지킵니다. 그 안에서는 실제 쇼핑몰·상세페이지·SNS 광고처럼 자연스럽게, 사례마다 어휘와 문장 구조를 바꿔 씁니다.",
        "- 의료 표현 사례는 괄호 안의 예시와 비슷한 내용을 문장에 넣습니다.",
        "- 표현 방식 칸에 '함께 언급'이 적힌 사례만 예외로, 적힌 낱말을 지시대로 문장에 넣습니다.",
        "- 결과는 ads.csv의 ad_text 칸에 씁니다. 쉼표가 들어가면 큰따옴표로 감쌉니다.",
        "",
        "| case_id | 주어 | 주제 | 표현 방식 |",
        "|---|---|---|---|",
    ]
    for item in items:
        style = STYLE_TEXT[item["style"]] + (f" (예: {item['hint']})" if item["hint"] else "")
        if item.get("aside"):
            style += (
                f" 함께 언급: '{item['aside']}'이라는 말을 이 제품의 효과가 아니라 함께 쓰는 다른 제품·라인의 이름이나"
                " 읽는 사람의 고민으로만 넣습니다."
            )
        lines.append(f"| {item['case_id']} | {item['subject']} | {item['topic_text']} | {style} |")
    return "\n".join(lines) + "\n"


def _labeling_sheet(
    eval_id: str, items: list[dict], ads: dict[str, str], records: dict[str, dict[str, FunctionalCosmetic]],
) -> str:
    lines = [
        f"# {eval_id} 기대 판정 라벨지",
        "",
        "각 사례의 광고 문장 하나를, 그 제품의 식약처 기능성화장품 공식 효능효과만 보고 판정합니다.",
        "공식 효능효과는 제품 단위입니다. 그 제품이 어떤 기능으로 보고·심사됐는지를 말합니다.",
        "아래 순서대로 적용하고 처음 해당하는 판정을 고릅니다.",
        "",
        "1. 질병 치료·예방이나 의료 시술의 효과처럼 말하면 `mismatch`(근거 불일치). 화장품은 이런 표현을 할 수 없습니다.",
        "   다만 그런 효과를 부인하는 문장(예: '치료 목적의 제품이 아닙니다')은 `unverifiable`입니다.",
        "2. 광고가 주장하는 기능이 '피부 미백'이나 '피부 주름개선'이 아니거나, 다른 기능이 함께 섞여 있거나,",
        "   효과를 어느 정도로 말하는지 알 수 없으면 `unverifiable`(검증 불가). 지금은 이 두 기능만 판정합니다.",
        "3. 공식 효능효과를 근거로 쓸 수 없으면 `unverifiable`. 다음 경우입니다.",
        "   - 공식 효능효과가 비어 있다.",
        "   - 문서에 작성 양식의 안내 문구('해당하는 효능효과 이외에는 모두 삭제하시기 바랍니다')가 남아 있다.",
        "   - 효능효과명과 효능효과 문서가 서로 다른 기능을 말한다.",
        "   - 문구에 오기가 있거나 문장이 불완전해 무엇을 인정했는지 확실하지 않다.",
        "4. 광고가 주장한 기능이 공식 효능효과에 없으면 `mismatch`. 공식에 '입술의 주름개선'만 있는데 광고가",
        "   피부 주름개선을 말하면 범위가 달라 `unverifiable`입니다.",
        "5. 표현이 공식 수준('도움을 준다')보다 강하면 `mismatch`. 단정('개선합니다', '없애줍니다'), 보장('100%', '확실하게'),",
        "   기간·속도 약속('7일 만에')이 해당합니다. '도움을 줍니다', '도움을 줄 수 있습니다'는 공식 수준 이내입니다.",
        "6. 주어가 제품이 아니라 성분이거나, 대상자·조건·비교·인증처럼 공식 효능효과에 없는 내용이 붙어 있으면 `unverifiable`.",
        "   공식 효능효과는 제품에 대한 것이라 성분이 그 효과를 낸다는 주장은 이 자료로 확인할 수 없습니다.",
        "   사용 방법이나 횟수를 효과의 조건으로 건 문장('꾸준히 바르면 …에 도움을 줍니다', '하루 두 번 바르면 …')도 조건이 붙은 것입니다.",
        "7. 그 외(제품의 공식 효능효과에 있는 기능을, 공식 수준 이내로, 덧붙인 내용 없이 말함)는 `confirmed`(확인됨).",
        "",
        "labels.csv의 label 칸에 confirmed / mismatch / unverifiable 중 하나를 쓰고, note에 근거를 한 줄로 적습니다.",
        "",
    ]
    for item in items:
        record = records[item["source"]][item["record_id"]]
        lines += [
            f"## {item['case_id']}",
            "",
            f"- 광고 문장: {ads[item['case_id']]}",
            f"- 제품: {record.item_name} ({record.company}), {SOURCE_LABELS[item['source']]} 기록 {record.record_id}, 등록일 {record.registered_on}",
            f"- 효능효과명: {record.effect_name or '(없음)'}",
            "- 효능효과 문서:",
            "",
            "```text",
            record.effect_text or "(없음)",
            "```",
            "",
        ]
    return "\n".join(lines)


def _read_csv(path: Path, fields: Sequence[str]) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not set(fields) <= set(reader.fieldnames):
            raise CosmeticEvalError(f"{path.name}: columns must include {', '.join(fields)}")
        return list(reader)


def _ads(path: Path, items: list[dict]) -> dict[str, str]:
    ads = {row["case_id"]: (row["ad_text"] or "").strip() for row in _read_csv(path, AD_FIELDS)}
    missing = [item["case_id"] for item in items if not ads.get(item["case_id"])]
    if missing or len(ads) != len(items):
        raise CosmeticEvalError(f"advertisement file must cover every case exactly once (missing: {missing[:5]})")
    return ads


def _labels(path: Path, items: list[dict]) -> tuple[str, dict[str, str]]:
    rows = _read_csv(path, LABEL_FIELDS)
    labels: dict[str, str] = {}
    for row in rows:
        try:
            labels[row["case_id"]] = Verdict(row["label"].strip()).value
        except ValueError:
            raise CosmeticEvalError(f"{path.name}: invalid label {row['label']!r} for {row['case_id']}") from None
    names = {row["labeler"].strip() for row in rows}
    if len(names) != 1 or "" in names:
        raise CosmeticEvalError(f"{path.name}: one non-empty labeler name is required")
    if set(labels) != {item["case_id"] for item in items} or len(rows) != len(items):
        raise CosmeticEvalError(f"{path.name}: labels must cover every case exactly once")
    return names.pop(), labels


def _write_csv(path: Path, fields: Sequence[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _sample(args: argparse.Namespace) -> int:
    records = _load(args.export_dir)
    earlier = [json.loads(path.read_text(encoding="utf-8")) for path in args.exclude_manifest]
    excluded = frozenset((item["source"], item["record_id"]) for manifest in earlier for item in manifest["items"])
    items, frame = sample_items(records, args.seed, args.case_prefix, excluded, ALLOCATIONS[args.allocation])
    sources = {}
    for key, source in SOURCES.items():
        audit = json.loads(export_stem(args.export_dir, source).with_suffix(".audit.json").read_text(encoding="utf-8"))
        sources[key] = {
            "source_id": source.source_id, "retrieved_at": audit["retrieved_at"],
            "sha256": audit.get("sha256"), "rows": len(records[key]),
        }
    _write_json(args.manifest, {
        "eval_id": args.eval_id,
        "question": "What verdict should the advertisement sentence get against the record's official efficacy?",
        "labeling": "Two blind AI labelers label the frozen sentences later; see the evidence record.",
        "seed": args.seed,
        "sources": sources,
        "engine_versions": [COSMETIC_CLAIM_VERSION, COSMETIC_EFFICACY_VERSION, COSMETIC_VERDICT_VERSION],
        "allocation_id": args.allocation,
        "allocation": ALLOCATIONS[args.allocation],
        "frame_counts": frame,
        **({"excluded_evals": [manifest["eval_id"] for manifest in earlier]} if earlier else {}),
        "items": items,
    })
    args.generation_sheet.parent.mkdir(parents=True, exist_ok=True)
    args.generation_sheet.write_text(_generation_sheet(args.eval_id, items), encoding="utf-8", newline="\n")
    _write_csv(args.ads_template, AD_FIELDS, [{"case_id": item["case_id"], "ad_text": ""} for item in items])
    print(f"{len(items)} cases sampled ({frame}) -> {args.manifest}")
    return 0


def _sheet(args: argparse.Namespace) -> int:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    items = manifest["items"]
    ads = _ads(args.ads, items)
    args.labeling_sheet.parent.mkdir(parents=True, exist_ok=True)
    args.labeling_sheet.write_text(
        _labeling_sheet(manifest["eval_id"], items, ads, _load(args.export_dir)), encoding="utf-8", newline="\n"
    )
    _write_csv(args.labels_template, LABEL_FIELDS, [
        {"case_id": item["case_id"], "label": "", "labeler": "", "note": ""} for item in items
    ])
    print(f"labeling sheet for {len(items)} cases -> {args.labeling_sheet}")
    return 0


def _case_file(manifest: dict, cases: list[dict], labelers: list[str], strict: bool) -> dict:
    rule = "a non-confirmed label where the labelers disagree" if strict else "agreed labels only"
    return {
        "dataset_id": manifest["eval_id"] + ("-strict" if strict else ""),
        "purpose": "frozen claim evaluation for functional cosmetics; AI-written sentences for real MFDS records",
        "labeling": (
            f"Expected verdicts are blind AI labels ({', '.join(labelers)}), {rule}. "
            "They are not human or expert labels."
        ),
        "sources": manifest["sources"],
        "cases": cases,
    }


def _cases(args: argparse.Namespace) -> int:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    items = manifest["items"]
    ads = _ads(args.ads, items)
    if len(args.labels) != 2:
        raise CosmeticEvalError("exactly two label files are required")
    labelled = [_labels(path, items) for path in args.labels]
    labelers = [name for name, _ in labelled]
    agreed, strict, disagreements = [], [], []
    for item in items:
        case_id = item["case_id"]
        values = [labels[case_id] for _, labels in labelled]
        case = {"case_id": case_id, "source": item["source"], "record_id": item["record_id"], "ad_text": ads[case_id]}
        if values[0] == values[1]:
            agreed.append({**case, "expected_verdict": values[0], "note": ""})
            strict.append({**case, "expected_verdict": values[0], "note": ""})
            continue
        disagreements.append({"case_id": case_id, "labels": dict(zip(labelers, values, strict=True))})
        conservative = next(value for value in values if value != Verdict.CONFIRMED.value)
        strict.append({
            **case, "expected_verdict": conservative,
            "note": "labelers disagree: " + ", ".join(f"{n}={v}" for n, v in zip(labelers, values, strict=True)),
        })
    _write_json(args.output, _case_file(manifest, agreed, labelers, strict=False))
    if args.strict_output is not None:
        _write_json(args.strict_output, _case_file(manifest, strict, labelers, strict=True))
    _write_json(args.disagreements, disagreements)
    print(f"{len(agreed)} agreed cases, {len(disagreements)} disagreements -> {args.output}")
    return 0


def _judge(case: dict, records: dict[str, dict[str, FunctionalCosmetic]]) -> dict:
    try:
        record = records[case["source"]][case["record_id"]]
        expected = Verdict(case["expected_verdict"])
    except (KeyError, ValueError):
        raise CosmeticEvalError(f"{case.get('case_id')}: unknown source, record or expected verdict") from None
    product = ConfirmedCosmetic(product=record, confirmed_by_user=True)
    claims = confirm_cosmetic_claims(extract_cosmetic_claims(case["ad_text"]), "all")
    decisions = decide_cosmetic_ad(case["ad_text"], claims, product)
    if len(decisions) != 1:
        # No claim means no judgment was made. Several claims count as confirmed if any is.
        confirmed = any(decision.verdict is Verdict.CONFIRMED for decision in decisions)
        actual = Verdict.CONFIRMED if confirmed else Verdict.UNVERIFIABLE
        reason, outcome = ("CLAIM_NOT_EXTRACTED" if not decisions else "MULTIPLE_CLAIMS"), "claim_count_error"
    else:
        actual, reason = decisions[0].verdict, decisions[0].reason.value
        outcome = "agree" if actual is expected else "disagree"
    return {
        "case_id": case["case_id"], "source": case["source"], "record_id": case["record_id"],
        "expected_verdict": expected.value, "actual_verdict": actual.value, "reason_code": reason,
        "claim_count": len(decisions), "outcome": outcome,
    }


def _score(args: argparse.Namespace) -> int:
    cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]
    records = _load(args.export_dir)
    results = [_judge(case, records) for case in cases]
    expected = [row["expected_verdict"] for row in results]
    actual = [row["actual_verdict"] for row in results]
    false_clearances = sum(1 for exp, act in zip(expected, actual, strict=True) if exp != "confirmed" and act == "confirmed")
    summary = {
        "case_count": len(results),
        "judged_case_count": len(results),
        "exact_agreement_count": sum(1 for row in results if row["outcome"] == "agree"),
        "false_clearance_count": false_clearances,
        "false_clearance_rate": false_clearance_rate(expected, actual) if results else 0.0,
        "confirmed_recall": confirmed_recall(expected, actual) if results else 0.0,
        "coverage": sum(1 for value in actual if value != "unverifiable") / len(results) if results else 0.0,
        "claim_extraction_error_count": sum(1 for row in results if row["outcome"] == "claim_count_error"),
        "rule_versions": [COSMETIC_CLAIM_VERSION, COSMETIC_EFFICACY_VERSION, COSMETIC_VERDICT_VERSION],
        "results": results,
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    print(text, end="")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
    return 1 if args.require_zero_false_clearance and false_clearances else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    command = {"sample": _sample, "sheet": _sheet, "cases": _cases, "score": _score}[args.command]
    try:
        return command(args)
    except (CosmeticEvalError, DataSourceError, ValueError, OSError, KeyError) as exc:
        print(f"error: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
