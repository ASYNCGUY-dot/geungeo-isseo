import json
from pathlib import Path

from claimledger.claims_v1 import CLAIM_EXTRACTION_VERSION
from scripts import engine_diff

ENDINGS_SIZE = 289200  # the claim endings: 249,600 rows expect the claim as written, 39,600 the same text


def test_corpora_keep_their_recorded_sizes() -> None:
    # The sizes the evidence records cite: 276,480 (neighbour gate), 216,000 (notice lines),
    # 192,960 (notice variants), 192,960 (blank lines) and the claim endings (claim-extract-v1.13, v1.14).
    sizes = {name: sum(1 for _ in rows()) for name, rows in engine_diff.CORPORA.items()}

    assert sizes == {
        "neighbour": 276480, "notice-lines": 216000, "notice-variants": 192960, "blank-lines": 192960,
        "endings": ENDINGS_SIZE,
    }


def test_corpus_rows_name_the_text_and_a_known_product() -> None:
    for rows in engine_diff.CORPORA.values():
        row = next(iter(rows()))
        assert isinstance(row["text"], str) and row["product"] in engine_diff.PRODUCTS


def test_notice_variants_are_fixed() -> None:
    variants = engine_diff.notice_variants()

    assert len(variants) == 51 and variants == engine_diff.notice_variants()
    assert variants[-len(engine_diff.PLAIN_VARIANTS):] == engine_diff.PLAIN_VARIANTS


def test_endings_rewrite_only_the_claim() -> None:
    rows = list(engine_diff.ending_rows())

    assert {row["way"] for row in rows} == set(engine_diff.ENDING_WAYS)
    for row in rows:
        assert row["variant"] != row["core"]
        assert row["text"] == row["canonical"].replace(row["core"], row["variant"], 1)
    # Every way is applied to the claims it can rewrite, and the leading connectives to every claim.
    leads = {row["core"] for row in rows if row["way"] == "lead:또한"}
    assert leads == set(engine_diff.NEIGHBOUR_CORES + engine_diff.ENDING_INTAKE_CORES)
    assert next(row for row in rows if row["way"] == "에도")["variant"].count("에도 도움") == 1
    # A connective before an intake word or a verb phrase is left unread (claim-extract-v1.14): those rows
    # expect the reading of the same text by the engine before, every other row the claim as written.
    expect = {(row["way"].startswith(("lead:", "그리고+")), row["core"] in engine_diff.ENDING_LEAD_OUT, row["expect"])
              for row in rows}
    assert expect == {(True, True, "text"), (True, False, "canonical"), (False, True, "canonical"),
                      (False, False, "canonical")}


def test_compare_endings_takes_the_expected_reading_per_row(tmp_path: Path) -> None:
    cases = tmp_path / "cases.jsonl"
    cases.write_text("".join(json.dumps({"text": t, "expect": e}) + "\n" for t, e in
                             (("a", "canonical"), ("b", "text"), ("c", "text"))), encoding="utf-8")
    canon, old, new = (tmp_path / f"{name}.jsonl" for name in ("canon", "old", "new"))
    c, u = [["s", "confirmed", "R"]], [["s", "unverifiable", "R"]]
    canon.write_text("".join(json.dumps(x) + "\n" for x in (c, c, c)), encoding="utf-8")
    old.write_text("".join(json.dumps(x) + "\n" for x in (u, u, u)), encoding="utf-8")
    new.write_text("".join(json.dumps(x) + "\n" for x in (c, u, c)), encoding="utf-8")

    counts = engine_diff.compare_endings(cases, canon, old, new)["counts"]

    assert counts == {"canonical: as expected": 1, "text: as expected": 1, "text: NOT AS EXPECTED": 1}
    assert engine_diff.main(["compare-endings", str(cases), str(canon), str(old), str(new)]) == 1


def test_blank_lines_rewrite_only_blank_line_layouts() -> None:
    row = next(iter(engine_diff.blank_line_rows()))

    assert "\n\n" in row["base"] and row["text"] == row["base"].replace("\n\n", "\n" * 9)


def _cases(tmp_path: Path, texts: list[str]) -> Path:
    path = tmp_path / "cases.jsonl"
    path.write_text("".join(json.dumps({"text": t, "product": "OMEGA3"}, ensure_ascii=False) + "\n" for t in texts),
                    encoding="utf-8")
    return path


def test_judge_and_compare_report_differences(tmp_path: Path) -> None:
    cases = _cases(tmp_path, ["혈행 개선에 도움을 줄 수 있습니다.", "혈액순환이 좋아집니다."])
    judged = tmp_path / "a.jsonl"

    engine = engine_diff.judge(cases, judged, "text", None, False)

    assert engine.startswith(CLAIM_EXTRACTION_VERSION)
    rows = [json.loads(line) for line in judged.read_text(encoding="utf-8").splitlines()]
    assert [[d[1] for d in row] for row in rows] == [["confirmed"], ["mismatch"]]
    assert engine_diff.compare(cases, judged, judged)["counts"] == {"advertisements": 2, "same": 2}

    changed = tmp_path / "b.jsonl"
    changed.write_text(json.dumps([["x", "unverifiable", "AD_TEXT_NOT_FULLY_READ"]]) + "\n" + json.dumps(rows[1]) + "\n",
                       encoding="utf-8")
    result = engine_diff.compare(cases, changed, judged)
    assert result["counts"] == {"advertisements": 2, "same": 1, "different": 1, "newly confirmed in b": 1}
    assert engine_diff.main(["compare", str(cases), str(changed), str(judged), "--expect-same"]) == 1
    assert engine_diff.main(["compare", str(cases), str(judged), str(judged), "--expect-same"]) == 0


def test_period_lines_puts_a_period_where_the_engine_cuts_after_a_whole_claim_line(tmp_path: Path) -> None:
    cases = _cases(tmp_path, [
        "혈행 개선에 도움을 줄 수 있습니다\r\n눈 건강에 도움을 줄 수 있어요",
        "혈행 개선에\n도움을 줄 수 있습니다",
    ])
    output = tmp_path / "period.jsonl"

    engine_diff.period_lines(cases, output, None)

    texts = [json.loads(line)["text"] for line in output.read_text(encoding="utf-8").splitlines()]
    assert texts == ["혈행 개선에 도움을 줄 수 있습니다.\r\n눈 건강에 도움을 줄 수 있어요", "혈행 개선에\n도움을 줄 수 있습니다"]


def test_compare_variants_uses_the_canonical_reading_only_where_it_stands_alone(tmp_path: Path) -> None:
    rows = [
        {"text": "a", "kind": "variant"},     # canonical on its own: expect the canonical reading
        {"text": "b", "kind": "variant"},     # canonical inside another sentence: expect the same text
        {"text": "c", "kind": "near_miss"},   # near miss: expect the same text
        {"text": "d", "kind": "variant"},     # partly on its own: skipped
    ]
    cases = tmp_path / "cases.jsonl"
    cases.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    old, canon, new = (tmp_path / f"{name}.jsonl" for name in ("old", "canon", "new"))
    m, c = [["s", "mismatch", "R"]], [["s", "confirmed", "R"]]
    old.write_text("".join(json.dumps(x) + "\n" for x in (m, m, m, m)), encoding="utf-8")
    canon.write_text("".join(json.dumps(x) + "\n" for x in (c, c, c, c)), encoding="utf-8")
    (tmp_path / "canon.jsonl.isolated").write_text("1 1\n0 1\n1 1\n1 2\n", encoding="utf-8")
    new.write_text("".join(json.dumps(x) + "\n" for x in (c, m, c, c)), encoding="utf-8")

    counts = engine_diff.compare_variants(cases, old, canon, new)["counts"]

    assert counts["as expected"] == 2 and counts["NOT AS EXPECTED"] == 1
    assert counts["skipped (canonical notice partly on its own)"] == 1
