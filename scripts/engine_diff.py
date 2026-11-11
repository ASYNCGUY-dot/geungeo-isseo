"""Differential checks of the health-food engine on built advertisements.

Each change to how advertisements are split into sentences was checked by judging built corpora with the
engine before and after it. The corpora and the judge live here so the checks can be rerun (they used to
live in session scratch folders and were lost):

- neighbour: a claim between two neighbour sentences, joined by a space or a line break (claim-verdict-v1.4,
  the neighbour gate, and v1.5, the subject gate; 276,480 advertisements)
- notice-lines: a claim and the "not a medicine" notice on lines of their own (claim-extract-v1.5, v1.6; 216,000)
- notice-variants: allowed notice wordings and near-miss sentences in place of the notice, with the same
  advertisement holding the canonical notice instead (claim-extract-v1.7; 192,960)
- blank-lines: notice-variants laid out with one blank line, rewritten with longer blank-line runs; `base`
  holds the one-blank-line text (claim-extract-v1.8; 192,960)

Every corpus row has `text` (the advertisement) and `product` (a key of PRODUCTS). The judge loads
`claimledger` from --engine-src when given (export an older engine with `git archive <commit> src | tar -x -C
<dir>`; give a Windows path on Windows) and prints the engine it ran. A judged file holds one JSON list per
advertisement: [claim text, verdict, reason] per decision.

usage: engine_diff.py corpus <name> <cases.jsonl>
       engine_diff.py judge <cases.jsonl> <out.jsonl> [--field text] [--engine-src DIR]
       engine_diff.py period-lines <cases.jsonl> <out.jsonl> [--engine-src DIR]
       engine_diff.py compare <cases.jsonl> <a.jsonl> <b.jsonl> [--expect-same]
       engine_diff.py compare-variants <cases.jsonl> <old_text> <old_canonical> <new_text>

`compare` reports per advertisement whether the verdicts (verdict and reason per claim) differ. With
--expect-same any difference is a failure (exit 1). `compare-variants` checks claim-extract-v1.7's
expectation: an allowed variant is read as the old engine reads the canonical notice in its place where
the old engine reads that notice as a sentence of its own (judge the canonical field with --isolation),
otherwise as the old engine reads the same text; a near-miss sentence changes nothing. `period-lines`
writes the corpus with a period where an engine of claim-extract-v1.11 or later cuts a sentence after a
whole claim line: the engine before the cut must read that text as the new engine reads the original.
"""

import argparse
import itertools
import json
import random
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path

PRODUCTS = {
    "OMEGA3": "[EPA 및 DHA 함유 유지] 혈중 중성지질 개선·혈행 개선·건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음\n"
    "[은행잎 추출물] 기억력 개선에 도움을 줄 수 있음",
    "LUTEIN": "[루테인] 노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음",
    "PROBIOTICS": "[프로바이오틱스] 유산균 증식 및 유해균 억제·배변활동 원활·장 건강에 도움을 줄 수 있음",
    "HEADERLESS": "① 유산균 증식 및 유해균 억제･배변활동 원활･장 건강에 도움을 줄 수 있음",
    "OTHER": "[비타민C] 결합조직 형성과 기능유지에 필요",
    "THREE": "[EPA 및 DHA 함유 유지] 혈중 중성지질 개선·혈행 개선에 도움을 줄 수 있음\n"
    "[루테인] 노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음\n"
    "[프로바이오틱스] 유산균 증식 및 유해균 억제·배변활동 원활·장 건강에 도움을 줄 수 있음",
}

# neighbour
NEIGHBOUR_CORES = [
    "혈행 개선에 도움을 줄 수 있습니다", "혈행 개선에 도움을 줄 수 있어요", "오메가3는 혈행 개선에 도움을 줄 수 있습니다",
    "혈행을 개선하는 데 도움을 줄 수 있습니다", "혈중 중성지질 개선에 도움을 줄 수 있음", "기억력 개선에 도움을 줄 수 있습니다",
    "눈 건강에 도움을 줄 수 있어요", "황반색소밀도 유지에 도움을 줄 수 있습니다", "루테인은 눈 건강에 도움을 줄 수 있습니다",
    "장 건강에 도움을 줄 수 있어요", "배변활동 원활에 도움을 줄 수 있습니다", "프로바이오틱스는 장 건강에 도움을 줄 수 있습니다",
    "혈행을 개선합니다", "혈액순환이 좋아집니다", "고혈압을 예방합니다", "눈 건강 확실",
]
NEIGHBOUR_ENDINGS = [".", "", "!", "。", "..", "...", "…", "!!", "?", ".!"]
NEIGHBOURS = {
    "none": "",
    "disclaimer": "본 제품은 의약품이 아닙니다.",
    "disclaimer_long": "이 제품은 질병의 예방 및 치료를 위한 의약품이 아닙니다.",
    "period": "단 2주.",
    "invitation": "지금 구매하세요.",
    "dose": "하루 3캡슐이면 충분합니다.",
    "denial": "아래 문구는 사실이 아닙니다.",
    "caution": "개인차가 있을 수 있습니다.",
    "strong_claim": "혈액순환이 좋아집니다!",
    "disease_condition": "(고혈압 환자에 한함)",
    "support_claim": "장 건강에 도움을 줄 수 있습니다.",
    "eye_claim": "눈 건강에 도움을 줄 수 있어요.",
}

# notice-lines
LINE_NOTICES = {
    "short": "본 제품은 의약품이 아닙니다",
    "short.": "본 제품은 의약품이 아닙니다.",
    "long": "본 제품은 질병의 예방 및 치료를 위한 의약품이 아닙니다",
    "long.": "이 제품은 질병의 예방 및 치료를 위한 의약품이 아닙니다.",
    "wrapped": "이 제품은 질병의 예방 및 치료를 위한\n의약품이 아닙니다",
    "bare": "의약품이 아님",
}
LINE_OTHERS = {
    "none": None,
    "dose": "하루 3캡슐이면 충분합니다",
    "condition": "(고혈압 환자에 한함)",
    "claim": "장 건강에 도움을 줄 수 있습니다",
    "named": "루테인은 눈 건강에 도움을 줄 수 있습니다",
}
LINE_CORES = NEIGHBOUR_CORES + ["혈행 개선에\n도움을 줄 수 있습니다", "오메가3는\n혈행 개선에 도움을 줄 수 있습니다"]
LINE_ENDINGS = ["", ".", "…", "!!"]
LINE_LAYOUTS = ["notice_after", "notice_before", "notice_both", "notice_between", "no_notice"]
SEPARATORS = {"lf": "\n", "crlf": "\r\n", "blank": "\n\n", "space": " "}
_ENDS_SENTENCE = re.compile(r"[.!?。…]\s*$")

# notice-variants
CANONICAL = "본 제품은 의약품이 아닙니다"
MARKS = ["", "※ ", "* ", "• ", "· ", "- "]
WRAPS = ["", "()", "[]"]
SUBJECTS = [
    "", "본 제품은 ", "이 제품은 ", "해당 제품은 ", "본품은 ", "건강기능식품은 ", "본 제품은 건강기능식품이며, ",
    "이 제품은 건강기능식품으로서 ", "본 제품은 건강기능식품으로 ",
]
BODIES = [
    "의약품이 아닙니다", "질병의 예방 및 치료를 위한 의약품이 아닙니다", "질병 예방·치료를 위한 의약품이 아님",
    "질병의 예방과 치료를 목적으로 하는 의약품이 아니에요", "예방 또는 치료 목적의 의약품이 아니다",
    "질병의 예방 및 치료를 위한 의약품이 아닌 건강기능식품입니다", "의약품이 아닌 식품입니다",
    "질병의 예방 및 치료를 목적으로 하지 않습니다", "질병의 예방ㆍ치료를 위한 의약품이 아니예요",
]
PLAIN_VARIANTS = [
    "본 제품은 질병의 예방·치료를 위한 의약품이 아닙니다.", "본 제품은 건강기능식품이며, 질병의 예방 및 치료를 위한 의약품이 아닙니다.",
    "본품은 의약품이 아닌 건강기능식품입니다.", "건강기능식품은 의약품이 아닙니다.", "본 제품은 질병의 예방 및 치료를 목적으로 하지 않습니다",
    "해당 제품은 질병의 예방과 치료를 위한 의약품이 아니에요", "이 제품은 의약품이 아닌 식품입니다", "질병 예방 및 치료를 위한 의약품이 아님",
]
NEAR_MISSES = [
    "※ 본 제품은 의약품이 아니지만 효과는 확실합니다.", "본 제품은 의약품이 아닌 혈행 개선 식품입니다.",
    "본 제품은 의약품이 아닙니다만 혈행 개선에 탁월합니다.", "본 제품은 질병의 예방 및 치료에 도움을 주는 의약품이 아닙니다.",
    "질병의 예방 및 치료를 위한 의약품이 아닌 고지혈증 개선제입니다.", "※※ 본 제품은 의약품이 아닙니다.",
    "(본 제품은 의약품이 아닙니다.", "본 제품은 의약품이 아닙니다(단, 혈행 개선 효과는 보장).",
    "질병의 예방 및 치료를 목적으로 합니다.", "본 제품은 질병의 예방 및 치료를 위한 의약품입니다.",
    "본 제품은 건강기능식품이며 혈행 개선에 도움을 줄 수 있습니다.", "본 제품은 의약품이 아닙니다?",
    "※ 본 제품은 의약품이 아닙니다 ※", "건강기능식품은 의약품이 아닌 식품입니다만 효과 확실.",
    "본 제품은 고혈압의 예방 및 치료를 위한 의약품이 아닙니다.", "본 제품은 의약품이 아닙니다 (혈행 개선 확실)",
]
VARIANT_CORES = [
    "혈행 개선에 도움을 줄 수 있습니다", "오메가3는 혈행 개선에 도움을 줄 수 있습니다", "눈 건강에 도움을 줄 수 있어요",
    "혈액순환이 좋아집니다", "혈행 개선에\n도움을 줄 수 있습니다", "루테인은 눈 건강에 도움을 줄 수 있습니다",
]
VARIANT_LAYOUTS = ["notice_after", "notice_before", "notice_both", "notice_between"]
VARIANT_PRODUCTS = ["OMEGA3", "THREE", "OTHER"]

# blank-lines
BLANK_WAYS = {
    "between_9": lambda text: text.replace("\n\n", "\n" * 9),
    "between_crlf_8": lambda text: text.replace("\n\n", "\n" + " \r\n" * 8),
    "trailing_9": lambda text: text + "\n" * 9,
    "leading_9": lambda text: "\n" * 9 + text,
}


def _compact(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if not c.isspace())


def neighbour_rows() -> Iterator[dict]:
    for core, ending, (before, b), (after, a), sep, product in itertools.product(
        NEIGHBOUR_CORES, NEIGHBOUR_ENDINGS, NEIGHBOURS.items(), NEIGHBOURS.items(), (" ", "\n"), PRODUCTS,
    ):
        text = sep.join(part for part in (b, core + ending, a) if part)
        yield {"text": text, "product": product, "before": before, "after": after, "ending": ending, "core": core}


def _line_parts(layout: str, core: str, notice: str, other: str | None) -> list[str]:
    body = [core] + ([other] if other else [])
    if layout == "notice_after":
        return body + [notice]
    if layout == "notice_before":
        return [notice] + body
    if layout == "notice_both":
        return [notice] + body + [notice]
    if layout == "notice_between":
        return [core, notice] + ([other] if other else [])
    return body


def notice_line_rows() -> Iterator[dict]:
    for core, ending, (nk, notice), (ok, other), layout, (sk, sep), product in itertools.product(
        LINE_CORES, LINE_ENDINGS, LINE_NOTICES.items(), LINE_OTHERS.items(), LINE_LAYOUTS, SEPARATORS.items(),
        PRODUCTS,
    ):
        if layout == "no_notice" and nk != "short":
            continue
        parts = _line_parts(layout, core + ending, notice, other)
        notice_part = [layout != "no_notice" and part == notice for part in parts]
        period = parts[0]
        for left, right, left_notice, right_notice in zip(parts, parts[1:], notice_part, notice_part[1:]):
            mark = "." if (left_notice or right_notice) and not _ENDS_SENTENCE.search(left) else ""
            period += mark + sep + right
        yield {
            "text": sep.join(parts), "period": period, "product": product, "core": core, "ending": ending,
            "notice": nk, "other": ok, "layout": layout, "sep": sk,
        }


def notice_variants() -> list[str]:
    rng = random.Random(20261030)
    pool = []
    for mark, wrap, subject, body, end in itertools.product(MARKS, WRAPS, SUBJECTS, BODIES, ("", ".")):
        if subject.startswith("건강기능식품은") and "건강기능식품" in body:
            continue
        inner = subject + body + (end if wrap else "")
        text = mark + (wrap[0] + inner + wrap[1] if wrap else inner + end)
        if len(_compact(text)) <= 46:
            pool.append(text)
    rng.shuffle(pool)
    chosen: list[str] = []
    seen: Counter = Counter()
    for text in pool:  # cover every mark, wrap, subject and body before taking the rest
        keys = [("mark", next(m for m in reversed(MARKS) if text.startswith(m)))]
        keys += [("subject", s) for s in SUBJECTS if s and s.strip() in text]
        keys += [("body", b) for b in BODIES if b in text]
        if any(seen[key] < 3 for key in keys) or len(chosen) < 40:
            chosen.append(text)
            seen.update(keys)
        if len(chosen) >= 64:
            break
    return chosen + PLAIN_VARIANTS


def _variant_parts(layout: str, core: str, notice: str, other: str | None) -> list[str]:
    if layout == "notice_after":
        return [core] + ([other] if other else []) + [notice]
    if layout == "notice_before":
        return [notice, core] + ([other] if other else [])
    if layout == "notice_both":
        return [notice, core] + ([other] if other else []) + [notice]
    return [core, notice] + ([other] if other else [])


def notice_variant_rows() -> Iterator[dict]:
    notices = [(text, "variant") for text in notice_variants()] + [(text, "near_miss") for text in NEAR_MISSES]
    for (notice, kind), core, ending, (ok, other), layout, (sk, sep), product in itertools.product(
        notices, VARIANT_CORES, ("", "."), LINE_OTHERS.items(), VARIANT_LAYOUTS, SEPARATORS.items(), VARIANT_PRODUCTS,
    ):
        canonical_notice = CANONICAL + ("." if notice[-1] in ".!。" else "")
        yield {
            "text": sep.join(_variant_parts(layout, core + ending, notice, other)),
            "canonical": sep.join(_variant_parts(layout, core + ending, canonical_notice, other)),
            "canonical_notice": canonical_notice, "notice": notice, "kind": kind, "product": product, "core": core,
            "ending": ending, "other": ok, "layout": layout, "sep": sk,
        }


def blank_line_rows() -> Iterator[dict]:
    for case in notice_variant_rows():
        if case["sep"] != "blank":
            continue
        for way, rewrite in BLANK_WAYS.items():
            yield {"text": rewrite(case["text"]), "base": case["text"], "product": case["product"], "way": way,
                   "kind": case["kind"]}


CORPORA = {
    "neighbour": neighbour_rows,
    "notice-lines": notice_line_rows,
    "notice-variants": notice_variant_rows,
    "blank-lines": blank_line_rows,
}


def write_corpus(name: str, path: Path) -> int:
    count = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as out:
        for row in CORPORA[name]():
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def _load_engine(engine_src: Path | None):
    """The engine's claims_v1 and verdict_v1 (engine_src first on the path when given) and a line naming it."""
    if engine_src is not None:
        sys.path.insert(0, str(engine_src))
    from claimledger import claims_v1, verdict_v1

    if engine_src is not None and not Path(verdict_v1.__file__).resolve().is_relative_to(engine_src.resolve()):
        raise SystemExit(f"error: claimledger was loaded from {verdict_v1.__file__}, not from {engine_src}")
    engine = f"{claims_v1.CLAIM_EXTRACTION_VERSION} {verdict_v1.CLAIM_VERDICT_VERSION} {Path(verdict_v1.__file__).parent}"
    return claims_v1, verdict_v1, engine


def period_lines(cases: Path, output: Path, engine_src: Path | None) -> str:
    """Write the corpus with a period where the engine cuts a sentence after a whole claim line.

    claim-extract-v1.11 cuts a sentence after a line that reads whole as a claim; the engine before it must
    read the text with a period there as the new engine reads the text without it."""
    claims_v1, _, engine = _load_engine(engine_src)
    output.parent.mkdir(parents=True, exist_ok=True)
    with cases.open(encoding="utf-8") as rows, output.open("w", encoding="utf-8", newline="\n") as out:
        for line in rows:
            case = json.loads(line)
            text = case["text"]
            cuts = []
            for match in claims_v1._SENTENCE.finditer(text):
                for start, end in claims_v1._claim_lines(text, *match.span())[:-1]:
                    while end > start and text[end - 1].isspace():
                        end -= 1
                    cuts.append(end)
            for position in reversed(cuts):
                text = text[:position] + "." + text[position:]
            out.write(json.dumps({**case, "text": text}, ensure_ascii=False) + "\n")
    return engine


def judge(cases: Path, output: Path, field: str, engine_src: Path | None, isolation: bool) -> str:
    """Judge one field of every corpus row with the engine on the path (engine_src first when given)."""
    claims_v1, verdict_v1, engine = _load_engine(engine_src)
    from claimledger.domain import ConfirmedProduct, ProductCandidate

    at = datetime(2026, 8, 27, 12, 42, tzinfo=UTC)
    products = {
        key: ConfirmedProduct(product=ProductCandidate(
            report_no="200400000000001", name="테스트 제품", company="테스트 업체", primary_function=text,
            raw_materials="원재료", intake_method="1일 1회", source_id="C003", retrieved_at=at,
        ), confirmed_by_user=True)
        for key, text in PRODUCTS.items()
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with cases.open(encoding="utf-8") as rows, output.open("w", encoding="utf-8", newline="\n") as out:
        marks = output.with_name(output.name + ".isolated").open("w", encoding="utf-8", newline="\n") if isolation else None
        try:
            for line in rows:
                case = json.loads(line)
                text = case[field]
                claims = claims_v1.confirm_claims(claims_v1.extract_claims(text), "all")
                decisions = verdict_v1.decide_ad(text, claims, products[case["product"]])
                out.write(json.dumps([[d.claim.text, d.verdict.value, d.reason.value] for d in decisions],
                                     ensure_ascii=False) + "\n")
                if marks is not None:  # how many canonical notices this engine reads as sentences of their own
                    target = _compact(case["canonical_notice"])
                    own = sum(_compact(text[start:end]) == target for start, end in claims_v1._sentence_spans(text))
                    marks.write(f"{own} {text.count(case['canonical_notice'])}\n")
        finally:
            if marks is not None:
                marks.close()
    return engine


def _verdicts(decisions: list) -> list[tuple[str, str]]:
    return [(decision[1], decision[2]) for decision in decisions]


def compare(cases: Path, a: Path, b: Path, examples: int = 10) -> dict:
    counts: Counter = Counter()
    changes: Counter = Counter()
    shown = []
    with cases.open(encoding="utf-8") as rows, a.open(encoding="utf-8") as left, b.open(encoding="utf-8") as right:
        for case_line, a_line, b_line in zip(rows, left, right, strict=True):
            old, new = _verdicts(json.loads(a_line)), _verdicts(json.loads(b_line))
            counts["advertisements"] += 1
            if old == new:
                counts["same"] += 1
                continue
            counts["different"] += 1
            changes[(tuple(sorted({v for v, _ in old})), tuple(sorted({v for v, _ in new})))] += 1
            if any(v == "confirmed" for v, _ in new) and not any(v == "confirmed" for v, _ in old):
                counts["newly confirmed in b"] += 1
            if len(shown) < examples:
                shown.append({"text": json.loads(case_line)["text"], "a": old, "b": new})
    return {"counts": dict(counts), "changes": [[list(k[0]), list(k[1]), n] for k, n in changes.most_common()],
            "examples": shown}


def compare_variants(cases: Path, old_text: Path, old_canonical: Path, new_text: Path, examples: int = 10) -> dict:
    counts: Counter = Counter()
    shown = []
    isolation = old_canonical.with_name(old_canonical.name + ".isolated")
    with cases.open(encoding="utf-8") as rows, old_text.open(encoding="utf-8") as a, \
            old_canonical.open(encoding="utf-8") as b, isolation.open(encoding="utf-8") as iso, \
            new_text.open(encoding="utf-8") as c:
        for case_line, a_line, b_line, iso_line, c_line in zip(rows, a, b, iso, c, strict=True):
            case = json.loads(case_line)
            old, canon, new = (_verdicts(json.loads(x)) for x in (a_line, b_line, c_line))
            own, total = (int(x) for x in iso_line.split())
            if case["kind"] == "near_miss":
                expected, why = old, "near miss: same text"
            elif own == total:
                expected, why = canon, "variant read as its own sentence: canonical"
            elif own == 0:
                expected, why = old, "variant inside another sentence: same text"
            else:
                counts["skipped (canonical notice partly on its own)"] += 1
                continue
            counts[why] += 1
            if new != expected:
                counts["NOT AS EXPECTED"] += 1
                if len(shown) < examples:
                    shown.append({"why": why, "text": case["text"], "expected": expected, "new": new})
                continue
            counts["as expected"] += 1
            if any(v == "confirmed" for v, _ in new) and not any(v == "confirmed" for v, _ in old):
                counts["newly confirmed against the old engine on the same text"] += 1
    return {"counts": dict(counts), "examples": shown}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Differential checks of the health-food engine")
    commands = parser.add_subparsers(dest="command", required=True)
    corpus = commands.add_parser("corpus", help="write a built corpus")
    corpus.add_argument("name", choices=sorted(CORPORA))
    corpus.add_argument("output", type=Path)
    run = commands.add_parser("judge", help="judge one field of every row")
    run.add_argument("cases", type=Path)
    run.add_argument("output", type=Path)
    run.add_argument("--field", default="text")
    run.add_argument("--engine-src", type=Path, help="the src folder of the engine to load first")
    run.add_argument("--isolation", action="store_true", help="also count canonical notices read on their own")
    period = commands.add_parser("period-lines", help="put a period where the engine cuts after a whole claim line")
    period.add_argument("cases", type=Path)
    period.add_argument("output", type=Path)
    period.add_argument("--engine-src", type=Path, help="the src folder of the engine to load first")
    same = commands.add_parser("compare", help="compare two judged files per advertisement")
    same.add_argument("cases", type=Path)
    same.add_argument("a", type=Path)
    same.add_argument("b", type=Path)
    same.add_argument("--expect-same", action="store_true")
    variants = commands.add_parser("compare-variants", help="check the notice-variants expectation")
    variants.add_argument("cases", type=Path)
    variants.add_argument("old_text", type=Path)
    variants.add_argument("old_canonical", type=Path)
    variants.add_argument("new_text", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "corpus":
        print(f"{write_corpus(args.name, args.output)} advertisements -> {args.output}")
        return 0
    if args.command == "judge":
        print("engine", judge(args.cases, args.output, args.field, args.engine_src, args.isolation), file=sys.stderr)
        return 0
    if args.command == "period-lines":
        print("engine", period_lines(args.cases, args.output, args.engine_src), file=sys.stderr)
        return 0
    if args.command == "compare":
        result = compare(args.cases, args.a, args.b)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if args.expect_same and result["counts"].get("different") else 0
    result = compare_variants(args.cases, args.old_text, args.old_canonical, args.new_text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["counts"].get("NOT AS EXPECTED") else 0


if __name__ == "__main__":
    raise SystemExit(main())
