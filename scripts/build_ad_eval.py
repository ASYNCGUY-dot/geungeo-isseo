"""Build the frozen multi-sentence advertisement evaluation set (claim-eval-v3).

claim-eval-v1 and v2 hold one sentence per case, so the gates that read across sentences (the
neighbour gate, the subject gate and the notice lines) were never measured on them. Each case here
is one advertisement of two to four sentences for one real C003 product:

- sample: a scenario fixes the sentence roles (claims with a subject, topic and style; context
  sentences such as the notice or usage) and a layout, with a fixed seed. The generation sheet names
  the roles only, never the scenario, the stratum or the official text.
- sheet: the written sentences are joined by the layout (one line, one sentence per line, lines
  without periods, the first claim wrapped over two lines) and every sentence keeps its span. The
  labeling sheet shows each advertisement with the product's official function text and raw
  materials; labelers judge every sentence, `none` for a sentence that claims no function.
- cases: two label files are merged per sentence. A disagreement leaves the sentence unlabeled in the
  main file; the strict file keeps a non-confirmed label wherever a labeler gave one.
"""

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
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
from claimledger.domain import IngredientGroup
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
TWO_EFFECTS = "two_attributed_effects"
TWO_GROUPS = "two_attributed_groups"
# (scenario, stratum, claim type, count), 100 in total. "honest", "two_claims" and "modifier" use
# official wording on attributed products; "carryover" follows an ingredient's claim with a
# subject-less claim of another ingredient's function; "unsupported" holds claims the rules should
# not confirm. Context sentences decide whether the rules may read the whole advertisement.
CELLS: tuple[tuple[str, str, str, int], ...] = (
    ("honest", HEADER_ATTRIBUTED, "official", 18),
    ("honest", HEADERLESS_ATTRIBUTED, "official", 12),
    ("modifier", HEADER_ATTRIBUTED, "official", 10),
    ("modifier", HEADERLESS_ATTRIBUTED, "official", 6),
    ("two_claims", TWO_EFFECTS, "official", 12),
    ("carryover", TWO_GROUPS, "official", 14),
    ("unsupported", HEADER_ATTRIBUTED, "exaggerated", 4),
    ("unsupported", HEADER_ATTRIBUTED, "disease", 3),
    ("unsupported", HEADER_ATTRIBUTED, "other_effect", 3),
    ("unsupported", HEADER_ATTRIBUTED, "out_of_scope", 3),
    ("unsupported", HEADERLESS_ATTRIBUTED, "exaggerated", 2),
    ("unsupported", HEADERLESS_ATTRIBUTED, "disease", 2),
    ("unsupported", HEADERLESS_ATTRIBUTED, "other_effect", 2),
    ("unsupported", HELD, "official", 3),
    ("unsupported", HELD, "exaggerated", 1),
    ("unsupported", NO_EFFECT, "official", 3),
    ("unsupported", NO_EFFECT, "disease", 2),
)
LAYOUTS = ("inline", "lines", "lines_no_period", "wrapped")
MODIFIERS = ("target", "period", "guarantee", "comparison")
SUBJECT_MODES = ("ingredient", "ingredient", "product", "omitted")
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
SUBJECT_TEXT = {
    "ingredient": "원료명 '{subject}'을(를) 주어로 씀",
    "product": "'이 제품'을 주어로 씀",
    "omitted": "주어를 쓰지 않음",
}
CONTEXT_TEXT = {
    "intro": "제품 소개(브랜드·원료 품질·제형·맛 등). 건강 효과나 기능은 말하지 않음",
    "usage": "섭취 방법 안내(언제·어떻게 먹는지). 건강 효과는 말하지 않음",
    "notice": "의약품이 아니라는 고지 문구(건강기능식품 광고에 흔히 붙는 문장)",
    "target": "누구에게 권하는지 대상자를 특정하는 문장. 새로운 건강 효과는 말하지 않음",
    "period": "섭취 기간과 효과가 나타나는 시점을 연결하는 문장(예: 몇 주 만에 달라짐)",
    "guarantee": "효과를 약속·보장하는 문장(예: 효과가 없으면 환불)",
    "comparison": "다른 제품이나 원료보다 효과가 낫다고 비교하는 문장",
}
LABELS = ("confirmed", "mismatch", "unverifiable", "none")
SEGMENT_FIELDS = ("case_id", "seg_no", "text")
LABEL_FIELDS = ("case_id", "seg_no", "label", "labeler", "note")


class AdEvalError(ValueError):
    pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the frozen multi-sentence advertisement evaluation set")
    commands = parser.add_subparsers(dest="command", required=True)

    sample = commands.add_parser("sample", help="sample products, sentence roles and layouts")
    sample.add_argument("--source-export", type=Path, required=True)
    sample.add_argument("--source-retrieved-at", required=True)
    sample.add_argument("--seed", type=int, required=True)
    sample.add_argument("--eval-id", default="claim-eval-v3")
    sample.add_argument("--case-prefix", default="C3")
    sample.add_argument(
        "--exclude-manifest", type=Path, action="append", default=[],
        help="earlier evaluation manifest whose products are not sampled again",
    )
    sample.add_argument("--manifest", type=Path, required=True)
    sample.add_argument("--generation-sheet", type=Path, required=True)
    sample.add_argument("--segments-template", type=Path, required=True)

    sheet = commands.add_parser("sheet", help="compose the advertisements and write the blind labeling sheet")
    sheet.add_argument("--manifest", type=Path, required=True)
    sheet.add_argument("--segments", type=Path, required=True)
    sheet.add_argument("--source-export", type=Path, required=True)
    sheet.add_argument("--ads-output", type=Path, required=True)
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


def _frame(rows: list[dict], excluded: set[str]) -> dict[str, list[tuple]]:
    """Candidates per stratum: (report number, group, effect) for single claims, (report number,
    attributed (group, effect) pairs) for the two-claim strata. The effect is None for no_effect."""
    frame: dict[str, list] = defaultdict(list)
    attributed: dict[str, set[tuple[IngredientGroup, EffectKey]]] = defaultdict(set)
    for pair in candidate_pairs(rows):
        if pair.report_no in excluded:
            continue
        if pair.stratum is Stratum.ATTRIBUTED_HEADERLESS:
            frame[HEADERLESS_ATTRIBUTED].append((pair.report_no, pair.group, pair.effect))
        elif pair.stratum in ATTRIBUTED_STRATA:
            frame[HEADER_ATTRIBUTED].append((pair.report_no, pair.group, pair.effect))
        else:
            frame[HELD].append((pair.report_no, pair.group, pair.effect))
        if pair.stratum in ATTRIBUTED_STRATA:
            attributed[pair.report_no].add((pair.group, pair.effect))
    for report_no, pairs in sorted(attributed.items()):
        ordered = tuple(sorted(pairs, key=lambda pair: (pair[0].value, pair[1].value)))
        if len({effect for _, effect in pairs}) >= 2:
            frame[TWO_EFFECTS].append((report_no, ordered))
        if len({group for group, _ in pairs}) >= 2:
            frame[TWO_GROUPS].append((report_no, ordered))
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


def _subject_mode(rng: random.Random) -> str:
    return rng.choice(SUBJECT_MODES)


def _claim(
    rng: random.Random, claim_type: str, group: IngredientGroup, effect: EffectKey | None, text: str,
    subject_mode: str,
) -> dict:
    base = {"role": "claim", "group": group.value, "subject_mode": subject_mode, "claim_type": claim_type}
    if claim_type == "out_of_scope":
        topic = rng.choice(OUT_OF_SCOPE_TOPICS)
        return {**base, "effect": None, "topic": topic, "style": "support", "disease_hint": None}
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
        **base,
        "effect": effect.value,
        "topic": EFFECT_LABELS[effect],
        "style": style,
        "disease_hint": DISEASE_HINTS[effect] if claim_type == "disease" else None,
    }


def _context(kind: str) -> dict:
    return {"role": "context", "kind": kind}


def _plain_context(rng: random.Random, claims: list[dict]) -> list[dict]:
    """The claims with plain context: an intro before, usage after, the notice last (at least one)."""
    notice = rng.random() < 2 / 3
    extra = rng.sample(("intro", "usage"), rng.choice((0, 1)) if notice else 1)
    before = [_context("intro")] if "intro" in extra else []
    after = [_context("usage")] if "usage" in extra else []
    return before + claims + after + ([_context("notice")] if notice else [])


def _with_notice(rng: random.Random, segments: list[dict]) -> list[dict]:
    return segments + ([_context("notice")] if rng.random() < 0.5 else [])


def _segments(
    rng: random.Random, scenario: str, claim_type: str, index: int, entry: tuple, text: str,
) -> list[dict]:
    if scenario in {"two_claims", "carryover"}:
        pairs = entry[1]
        first = rng.choice(pairs)
        if scenario == "two_claims":
            second = rng.choice([pair for pair in pairs if pair[1] is not first[1]])
            modes = (_subject_mode(rng), _subject_mode(rng))
        else:
            second = rng.choice([pair for pair in pairs if pair[0] is not first[0]])
            modes = ("ingredient", "omitted")
        claims = [
            _claim(rng, claim_type, group, effect, text, mode)
            for (group, effect), mode in zip((first, second), modes, strict=True)
        ]
        return _with_notice(rng, claims)
    _, group, effect = entry
    claim = _claim(rng, claim_type, group, effect, text, _subject_mode(rng))
    if scenario == "modifier":
        kind = MODIFIERS[index % len(MODIFIERS)]
        segments = [_context(kind), claim] if kind == "target" else [claim, _context(kind)]
        return _with_notice(rng, segments)
    return _plain_context(rng, [claim])


def sample_items(rows: list[dict], excluded: set[str], seed: int, prefix: str) -> tuple[list[dict], dict]:
    rng = random.Random(seed)
    by_report = {row["report_no"]: row for row in rows}
    frame = _frame(rows, excluded)
    queues: dict[str, dict] = {}
    for stratum in sorted({cell[1] for cell in CELLS}):
        pool = sorted(frame[stratum], key=lambda item: (item[0], repr(item[1:])))
        rng.shuffle(pool)
        if stratum in {TWO_EFFECTS, TWO_GROUPS}:
            queues[stratum] = {None: pool}
        else:
            queues[stratum] = {group: [item for item in pool if item[1] is group] for group in TARGET_GROUPS}
    chosen, used, in_scenario = [], set(), Counter()
    for scenario, stratum, claim_type, count in CELLS:
        groups = list(queues[stratum])
        turn = picked = 0
        while picked < count:
            if not any(queues[stratum].values()):
                raise AdEvalError(f"not enough {stratum} products for {scenario}/{claim_type}")
            queue = queues[stratum][groups[turn % len(groups)]]
            turn += 1
            while queue and queue[0][0] in used:
                queue.pop(0)
            if not queue:
                continue
            entry = queue.pop(0)
            used.add(entry[0])
            text = by_report[entry[0]].get("primary_function") or ""
            chosen.append({
                "report_no": entry[0],
                "scenario": scenario,
                "stratum": stratum,
                "claim_type": claim_type,
                "segments": _segments(rng, scenario, claim_type, in_scenario[scenario], entry, text),
            })
            picked += 1
            in_scenario[scenario] += 1
    # Every scenario meets every layout about equally often.
    for scenario in dict.fromkeys(cell[0] for cell in CELLS):
        offset = rng.randrange(len(LAYOUTS))
        for index, item in enumerate(item for item in chosen if item["scenario"] == scenario):
            item["layout"] = LAYOUTS[(offset + index) % len(LAYOUTS)]
    rng.shuffle(chosen)
    items = []
    for index, item in enumerate(chosen, start=1):
        segments = [{"seg_no": number, **segment} for number, segment in enumerate(item.pop("segments"), start=1)]
        items.append({"case_id": f"{prefix}-{index:03d}", **item, "segments": segments})
    frame_counts = {stratum: len(frame[stratum]) for stratum in sorted({cell[1] for cell in CELLS})}
    return items, frame_counts


def _generation_sheet(eval_id: str, items: list[dict]) -> str:
    lines = [
        f"# {eval_id} 광고 생성지",
        "",
        "사례마다 한국어 건강기능식품 광고 한 편을, 아래에 번호가 붙은 문장 순서대로 씁니다.",
        "",
        "- 번호 하나에 한 문장을 씁니다. 한 칸 안에서 줄을 바꾸지 않고, 문장은 마침표나 느낌표 등으로 끝냅니다.",
        "- 사례 안의 문장들이 한 광고로 자연스럽게 이어지게 씁니다. 실제 쇼핑몰 상세페이지나 SNS 광고처럼 쓰고,",
        "  사례마다 어휘와 문장 구조를 다르게 합니다. 생성지 문구를 글자 그대로 옮길 필요는 없습니다.",
        "- 주장 문장은 지정된 주어 방식, 주제, 표현 방식을 지킵니다. 지정된 주제 하나만 말하고 다른 효과·성분·제품명을",
        "  덧붙이지 않습니다. 질병 표현 사례는 지정된 질병명을 문장에 넣습니다.",
        "- 맥락 문장은 지정된 종류대로 씁니다. '건강 효과는 말하지 않음'이 적힌 문장에는 건강 효과를 넣지 않습니다.",
        "- 결과는 segments.csv의 text 칸에 씁니다(행 하나가 문장 하나). 쉼표가 들어가면 큰따옴표로 감쌉니다.",
        "",
    ]
    for item in items:
        lines += [f"## {item['case_id']}", ""]
        for segment in item["segments"]:
            if segment["role"] == "context":
                lines.append(f"{segment['seg_no']}. 맥락 문장: {CONTEXT_TEXT[segment['kind']]}")
                continue
            subject = SUBJECT_TEXT[segment["subject_mode"]].format(
                subject=SUBJECTS[IngredientGroup(segment["group"])]
            )
            style = STYLE_TEXT[segment["style"]]
            if segment["disease_hint"]:
                style += f": {segment['disease_hint']}"
            lines.append(f"{segment['seg_no']}. 주장 문장: {subject} / 주제: {segment['topic']} / 표현 방식: {style}")
        lines.append("")
    return "\n".join(lines)


def compose(layout: str, texts: Sequence[str], wrap: int | None) -> tuple[str, list[tuple[int, int]]]:
    """Join the sentences by the layout; the span of each sentence in the advertisement text.

    "wrapped" breaks sentence `wrap` at the space closest to its middle, as a narrow layout would."""
    if layout not in LAYOUTS:
        raise AdEvalError(f"unknown layout {layout!r}")
    pieces = []
    for index, text in enumerate(texts):
        if layout == "lines_no_period" and text.endswith(".") and not text.endswith(".."):
            text = text[:-1]
        if layout == "wrapped" and index == wrap:
            spaces = [position for position, char in enumerate(text) if char == " "]
            if spaces:
                cut = min(spaces, key=lambda position: (abs(position - len(text) / 2), position))
                text = text[:cut] + "\n" + text[cut + 1:]
        pieces.append(text)
    separator = " " if layout == "inline" else "\n"
    spans, position = [], 0
    for piece in pieces:
        spans.append((position, position + len(piece)))
        position += len(piece) + len(separator)
    return separator.join(pieces), spans


def _read_csv(path: Path, fields: Sequence[str]) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not set(fields) <= set(reader.fieldnames):
            raise AdEvalError(f"{path.name}: columns must include {', '.join(fields)}")
        return list(reader)


def _keys(items: list[dict]) -> list[tuple[str, int]]:
    return [(item["case_id"], segment["seg_no"]) for item in items for segment in item["segments"]]


def _keyed(path: Path, fields: Sequence[str], items: list[dict]) -> dict[tuple[str, int], dict]:
    rows = _read_csv(path, fields)
    keyed = {}
    for row in rows:
        try:
            keyed[(row["case_id"], int(row["seg_no"]))] = row
        except ValueError:
            raise AdEvalError(f"{path.name}: invalid seg_no {row['seg_no']!r}") from None
    if set(keyed) != set(_keys(items)) or len(rows) != len(keyed):
        raise AdEvalError(f"{path.name}: rows must cover every sentence of every case exactly once")
    return keyed


def _compose_ads(items: list[dict], segments: dict[tuple[str, int], dict]) -> list[dict]:
    ads = []
    for item in items:
        texts = []
        for segment in item["segments"]:
            text = (segments[(item["case_id"], segment["seg_no"])]["text"] or "").strip()
            if not text or "\n" in text or "\r" in text:
                raise AdEvalError(f"{item['case_id']}/{segment['seg_no']}: one non-empty line is required")
            texts.append(text)
        wrap = next(index for index, segment in enumerate(item["segments"]) if segment["role"] == "claim")
        ad_text, spans = compose(item["layout"], texts, wrap)
        ads.append({
            "case_id": item["case_id"],
            "report_no": item["report_no"],
            "layout": item["layout"],
            "ad_text": ad_text,
            "segments": [
                {"seg_no": segment["seg_no"], "span": list(span), "text": ad_text[span[0]:span[1]]}
                for segment, span in zip(item["segments"], spans, strict=True)
            ],
        })
    return ads


def _labeling_sheet(eval_id: str, ads: list[dict], rows: dict[str, dict]) -> str:
    lines = [
        f"# {eval_id} 기대 판정 라벨지",
        "",
        "각 사례는 건강기능식품 광고 한 편입니다. 광고 전체를 읽은 뒤, 번호가 붙은 문장마다 그 제품의 공식 기능성",
        "원문(식품안전나라 C003)과 원재료만 보고 판정합니다. 문장마다 아래 순서대로 적용하고 처음 해당하는 판정을 고릅니다.",
        "",
        "0. 건강 효과·기능을 주장하지 않는 문장은 `none`. 예: 의약품이 아니라는 고지 문구, 제품 소개, 섭취 방법,",
        "   효과를 말하지 않는 대상자 권유. 의약품 아님 고지 문구 속 '질병의 예방 및 치료'는 질병 표현이 아닙니다.",
        "1. 질병의 예방·치료·완화(예: 황반변성 예방, 변비 치료)를 말하면 `mismatch`(근거 불일치).",
        "   건강기능식품은 질병 표현을 할 수 없으므로 원문 내용과 관계없이 적용합니다.",
        "2. 주장하는 기능이 판정 규칙이 다루는 기능 8개 밖이면 `unverifiable`(검증 불가). 8개는 황반색소밀도 유지·눈 건강,",
        "   혈중 중성지질 개선, 혈행 개선, 기억력 개선, 건조한 눈 개선, 유산균 증식·유해균 억제, 배변활동 원활, 장 건강입니다.",
        "   어느 원료가 주어인지와 관계없이 이 목록으로 판단합니다. 무슨 기능을 주장하는지 불분명할 때도 `unverifiable`입니다.",
        "3. 공식 원문 어디에도 그 기능이 없으면 `mismatch`.",
        "4. 원문에 그 기능이 있지만, 문장이 말하는 주체(원료 또는 제품)의 기능인지 원문과 원재료만으로 확정할 수 없으면",
        "   `unverifiable`. 예: 다른 원료 이름 아래 적힌 문구, 원료 표시 없이 나열됐고 다른 원료의 기능일 수 있는 문구.",
        "5. 주체의 기능으로 확정되지만 표현이 '도움을 줄 수 있음'보다 강하면(단정·보장) `mismatch`.",
        "6. 그 외(주체의 기능으로 확정, '도움' 수준 이하, 질병 표현 없음)는 `confirmed`(확인됨).",
        "",
        "광고 전체를 읽고 판단하는 방법:",
        "",
        "- 주어가 없는 문장은 광고 전체의 흐름에서 무엇에 대한 말인지 판단합니다. 그 주체가 원료인지 제품인지,",
        "  어느 원료인지 정할 수 없으면 4번에 따라 `unverifiable`입니다. '이 제품'처럼 제품이 주어이면 제품에 대한 말입니다.",
        "- 다른 문장이 이 문장의 주장에 대상자·기간·횟수·보장·비교를 덧붙이면, 이 문장도 그 말이 붙은 주장으로 읽습니다.",
        "  덧붙은 말까지 공식 원문의 인정 범위 안인지 확정할 수 없으면 `unverifiable`, 인정 수준보다 강해지면 `mismatch`입니다.",
        "- 줄바꿈은 문장의 끝이 아닐 수 있습니다. 판정은 번호가 붙은 문장 단위로 합니다.",
        "",
        "labels.csv의 label 칸에 confirmed / mismatch / unverifiable / none 중 하나를 쓰고, note에 근거를 한 줄로 적습니다.",
        "",
    ]
    for ad in ads:
        row = rows[ad["report_no"]]
        lines += [
            f"## {ad['case_id']}",
            "",
            f"- 제품: {row.get('name', '')} ({row.get('company', '')}), 신고번호 {ad['report_no']}",
            f"- 원재료: {row.get('raw_materials', '')}",
            "",
            "광고 원문(줄바꿈 그대로):",
            "",
            "```text",
            ad["ad_text"],
            "```",
            "",
            "판정할 문장(⏎는 원문의 줄바꿈):",
            "",
        ]
        lines += [f"{segment['seg_no']}. {segment['text'].replace(chr(10), '⏎')}" for segment in ad["segments"]]
        lines += [
            "",
            "공식 기능성 원문:",
            "",
            "```text",
            row.get("primary_function", ""),
            "```",
            "",
        ]
    return "\n".join(lines)


def _labels(path: Path, items: list[dict]) -> tuple[str, dict[tuple[str, int], str]]:
    keyed = _keyed(path, LABEL_FIELDS, items)
    labels = {}
    for key, row in keyed.items():
        label = (row["label"] or "").strip()
        if label not in LABELS:
            raise AdEvalError(f"{path.name}: invalid label {row['label']!r} for {key[0]}/{key[1]}")
        labels[key] = label
    names = {(row["labeler"] or "").strip() for row in keyed.values()}
    if len(names) != 1 or "" in names:
        raise AdEvalError(f"{path.name}: one non-empty labeler name is required")
    return names.pop(), labels


def _case_file(manifest: dict, cases: list[dict], labelers: list[str], strict: bool) -> dict:
    rule = "a non-confirmed label where the labelers disagree" if strict else "agreed labels; null where they disagree"
    return {
        "dataset_id": manifest["eval_id"] + ("-strict" if strict else ""),
        "purpose": "frozen multi-sentence advertisement evaluation; AI-written advertisements for real C003 products",
        "labeling": (
            f"Expected verdicts per sentence are blind AI labels ({', '.join(labelers)}), {rule}. "
            "They are not human or expert labels."
        ),
        "source_snapshot": f"C003 JSONL retrieved {manifest['source']['retrieved_at']}",
        "cases": cases,
    }


def _sample(args: argparse.Namespace) -> int:
    retrieved_at = parse_aware_datetime(args.source_retrieved_at, "--source-retrieved-at")
    data, rows = _rows(args.source_export)
    excluded, sources = set(), []
    for path in args.exclude_manifest:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        products = {entry["report_no"] for entry in payload["items"] if entry.get("report_no")}
        excluded |= products
        sources.append({"id": payload.get("eval_id"), "file_name": path.name, "sha256": _sha(raw), "products": len(products)})
    items, frame_counts = sample_items(rows, excluded, args.seed, args.case_prefix)
    manifest = {
        "eval_id": args.eval_id,
        "question": "What verdict should each sentence of the advertisement get against the product's official function text?",
        "labeling": "Two blind AI labelers label every sentence of the frozen advertisements later; see the evidence record.",
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
        "cells": [list(cell) for cell in CELLS],
        "frame_counts": frame_counts,
        "layout_counts": dict(sorted(Counter(item["layout"] for item in items).items())),
        "items": items,
    }
    _write_json(args.manifest, manifest)
    args.generation_sheet.parent.mkdir(parents=True, exist_ok=True)
    args.generation_sheet.write_text(_generation_sheet(args.eval_id, items), encoding="utf-8", newline="\n")
    args.segments_template.parent.mkdir(parents=True, exist_ok=True)
    with args.segments_template.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SEGMENT_FIELDS, lineterminator="\n")
        writer.writeheader()
        for case_id, seg_no in _keys(items):
            writer.writerow({"case_id": case_id, "seg_no": seg_no, "text": ""})
    print(f"{len(items)} cases sampled ({frame_counts}) -> {args.manifest}")
    return 0


def _sheet(args: argparse.Namespace) -> int:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    items = manifest["items"]
    ads = _compose_ads(items, _keyed(args.segments, SEGMENT_FIELDS, items))
    rows = {row["report_no"]: row for row in _rows(args.source_export)[1]}
    _write_json(args.ads_output, {"eval_id": manifest["eval_id"], "cases": ads})
    args.labeling_sheet.parent.mkdir(parents=True, exist_ok=True)
    args.labeling_sheet.write_text(_labeling_sheet(manifest["eval_id"], ads, rows), encoding="utf-8", newline="\n")
    with args.labels_template.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_FIELDS, lineterminator="\n")
        writer.writeheader()
        for case_id, seg_no in _keys(items):
            writer.writerow({"case_id": case_id, "seg_no": seg_no, "label": "", "labeler": "", "note": ""})
    print(f"labeling sheet for {len(items)} cases -> {args.labeling_sheet}")
    return 0


def _cases(args: argparse.Namespace) -> int:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    items = {item["case_id"]: item for item in manifest["items"]}
    ads = json.loads(args.ads.read_text(encoding="utf-8"))["cases"]
    if [ad["case_id"] for ad in ads] != list(items):
        raise AdEvalError("the advertisement file must hold the manifest cases in order")
    if len(args.labels) != 2:
        raise AdEvalError("exactly two label files are required")
    labelled = [_labels(path, manifest["items"]) for path in args.labels]
    labelers = [name for name, _ in labelled]
    agreed, strict, disagreements = [], [], []
    for ad in ads:
        item = items[ad["case_id"]]
        case = {key: ad[key] for key in ("case_id", "report_no")} | {
            "scenario": item["scenario"], "layout": ad["layout"], "ad_text": ad["ad_text"],
        }
        main_segments, strict_segments = [], []
        for segment in ad["segments"]:
            key = (ad["case_id"], segment["seg_no"])
            values = [labels[key] for _, labels in labelled]
            if values[0] == values[1]:
                main_segments.append({**segment, "expected": values[0]})
                strict_segments.append({**segment, "expected": values[0]})
                continue
            disagreements.append({
                "case_id": ad["case_id"], "seg_no": segment["seg_no"],
                "labels": dict(zip(labelers, values, strict=True)),
            })
            main_segments.append({**segment, "expected": None})
            strict_segments.append({**segment, "expected": next(value for value in values if value != "confirmed")})
        agreed.append({**case, "segments": main_segments})
        strict.append({**case, "segments": strict_segments})
    _write_json(args.output, _case_file(manifest, agreed, labelers, strict=False))
    if args.strict_output is not None:
        _write_json(args.strict_output, _case_file(manifest, strict, labelers, strict=True))
    _write_json(args.disagreements, disagreements)
    total = sum(len(ad["segments"]) for ad in ads)
    print(f"{total - len(disagreements)} of {total} sentences agreed -> {args.output}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    command = {"sample": _sample, "sheet": _sheet, "cases": _cases}[args.command]
    try:
        return command(args)
    except (AdEvalError, ValueError, OSError, KeyError) as exc:
        print(f"error: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
