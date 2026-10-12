"""End-to-end check of a cosmetics advertisement against an exported MFDS list (synthetic export)."""

import json
from pathlib import Path

import pytest

from claimledger.cosmetics_receipt import COSMETIC_REASON_MESSAGES
from claimledger.cosmetics_verdict import CosmeticVerdictReason
from claimledger.sources.functional_cosmetics import EXPORT_FIELDS, REPORTED, load_cosmetics_export
from scripts import check_cosmetic_ad

RETRIEVED_AT = "2026-10-11T05:18:59.490402+00:00"
BOTH = "피부의 미백에 도움을 준다. 피부의 주름개선에 도움을 준다."


def _row(record_id: str, name: str, effect_name: str = BOTH, **extra: object) -> dict:
    row = dict.fromkeys(EXPORT_FIELDS, "")
    row.update({
        "record_id": record_id, "item_name": name, "company": "합성 화장품", "registered_on": "20250102",
        "effect_name": effect_name, "effect_code": "3", "effect_doc_unreadable": False,
        "whitening": None, "wrinkle": None, "sunscreen": None, "withdrawn": False,
    })
    row.update(extra)
    return row


def _export(tmp_path: Path, rows: list[dict]) -> Path:
    stem = tmp_path / "functional-cosmetics-reported"
    stem.with_suffix(".jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    stem.with_suffix(".audit.json").write_text(
        json.dumps({"retrieved_at": RETRIEVED_AT, "total_count": len(rows)}), encoding="utf-8"
    )
    return tmp_path


ROWS = [
    _row("2026030397", "합성 리프팅 크림"),
    _row("2026030396", "합성 토너패드", effect_name="피부의 미백에 도움을 준다.", effect_code="1"),
    _row("2013000001", "합성 오래된 크림", effect_name="", effect_code=""),
]


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict]:
    code = check_cosmetic_ad.main(list(argv))
    output = capsys.readouterr().out
    return code, json.loads(output) if output.lstrip().startswith("{") else {"text": output}


def test_the_export_loader_keeps_identity_source_and_retrieval_time(tmp_path: Path) -> None:
    total, items = load_cosmetics_export(_export(tmp_path, ROWS), REPORTED)
    assert total == 3 and [item.record_id for item in items] == ["2026030397", "2026030396", "2013000001"]
    assert items[0].source_id == "data.go.kr:15095680" and items[0].retrieved_at.isoformat() == RETRIEVED_AT
    assert items[0].statement == BOTH


def test_a_search_lists_candidates_without_any_verdict(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, body = _run(capsys, "--export-dir", str(_export(tmp_path, ROWS)), "--query", "합성 크림")
    assert code == 0 and "claims" not in body
    assert [item["record_id"] for item in body["candidates"]] == ["2026030397", "2013000001"]
    assert body["candidates"][0]["official_statement"] == BOTH
    assert body["candidates"][0]["company"] == "합성 화장품" and body["candidates"][0]["registered_on"] == "20250102"


def test_a_confirmed_record_gets_a_receipt_with_reasons_and_quotes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    ad = tmp_path / "ad.txt"
    ad.write_text("미백과 주름개선에 도움을 줍니다.\n주름을 100% 없애줍니다.\n피부 재생 크림", encoding="utf-8")
    code, body = _run(
        capsys, "--export-dir", str(_export(tmp_path, ROWS)), "--record-id", "2026030397",
        "--ad-text-file", str(ad), "--confirm-claims", "all",
    )

    assert code == 0
    assert body["product"] == {
        "record_id": "2026030397", "item_name": "합성 리프팅 크림", "company": "합성 화장품",
        "registered_on": "20250102", "source_id": "data.go.kr:15095680",
        # JSON output writes the UTC offset as "Z".
        "retrieved_at": RETRIEVED_AT.replace("+00:00", "Z"),
        # The official wording is shown whatever the verdicts are, so a mismatch can be checked.
        "official_statement": BOTH,
    }
    verdicts = [(claim["verdict"], claim["verdict_label"], claim["reason_code"]) for claim in body["claims"]]
    assert verdicts == [
        ("confirmed", "확인됨", "MATCHES_OFFICIAL_EFFICACY"),
        ("mismatch", "근거 불일치", "EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL"),
        ("mismatch", "근거 불일치", "MEDICAL_CLAIM_BEYOND_COSMETIC_SCOPE"),
    ]
    assert body["claims"][0]["official_quotes"] == [
        "피부의 미백에 도움을 준다.", "피부의 주름개선에 도움을 준다.",
    ]
    assert body["claims"][1]["official_quotes"] == [] and body["claims"][0]["reason_message"]
    assert body["claims"][1]["strength_cues"] == ["100%"] and body["claims"][1]["function_cues"] == ["주름"]
    assert body["unread_text"] == []
    assert body["rule_versions"] == ["cosmetic-claim-v1.1", "cosmetic-efficacy-v1.0", "cosmetic-verdict-v1.1"]
    assert body["limitations"] and body["generated_at"]


def test_unjudged_text_is_listed_and_withholds_the_confirmation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    code, body = _run(
        capsys, "--export-dir", str(_export(tmp_path, ROWS)), "--record-id", "2026030397",
        "--ad-text", "단 2주. 미백에 도움을 줍니다.", "--confirm-claims", "all",
    )
    assert code == 0 and body["unread_text"] == ["단 2주."]
    assert [(claim["verdict"], claim["reason_code"]) for claim in body["claims"]] == [
        ("unverifiable", "AD_TEXT_NOT_FULLY_READ"),
    ]
    assert body["claims"][0]["official_quotes"] == [] and body["product"]["official_statement"] == BOTH


def test_claims_are_listed_for_confirmation_before_any_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    # No export is needed to see what would be judged.
    code, body = _run(
        capsys, "--export-dir", str(tmp_path / "absent"), "--ad-text", "단 2주. 미백에 도움을 줍니다.\n주름 100% 제거",
    )
    assert code == 0 and "claims" not in body and "verdict" not in json.dumps(body)
    assert body["extracted_claims"] == [
        {"claim_id": "C1", "text": "미백에 도움을 줍니다."}, {"claim_id": "C2", "text": "주름 100% 제거"},
    ]
    assert body["unread_text"] == ["단 2주."]


def test_unconfirmed_claims_and_untrusted_records_stay_unverifiable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    export = str(_export(tmp_path, ROWS))
    code, body = _run(
        capsys, "--export-dir", export, "--record-id", "2026030397",
        "--ad-text", "미백에 도움을 줍니다. 주름개선에 도움을 줍니다.", "--confirm-claims", "C2",
    )
    assert code == 0
    assert [claim["reason_code"] for claim in body["claims"]] == ["CLAIM_UNCONFIRMED", "MATCHES_OFFICIAL_EFFICACY"]

    code, body = _run(
        capsys, "--export-dir", export, "--record-id", "2013000001",
        "--ad-text", "미백에 도움을 줍니다.", "--confirm-claims", "all",
    )
    assert code == 0 and body["claims"][0]["reason_code"] == "OFFICIAL_EFFICACY_MISSING"
    assert body["claims"][0]["verdict_label"] == "검증 불가"


@pytest.mark.parametrize("extra", [
    ["--record-id", "0000000000", "--ad-text", "미백에 도움을 줍니다.", "--confirm-claims", "all"],
    ["--record-id", "2026030397", "--ad-text", "미백에 도움을 줍니다.", "--confirm-claims", "C9"],
    ["--record-id", "2026030397", "--ad-text", "   ", "--confirm-claims", "all"],
    ["--record-id", "2026030397"],
    ["--ad-text", "미백에 도움을 줍니다.", "--confirm-claims", "all"],
    ["--ad-text", "   "],
    ["--query", "  "],
    [],
])
def test_input_errors_exit_with_three_and_no_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str],
) -> None:
    code, body = _run(capsys, "--export-dir", str(_export(tmp_path, ROWS)), *extra)
    assert code == 3 and "claims" not in body


def test_a_missing_export_exits_with_three(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _ = _run(capsys, "--export-dir", str(tmp_path / "absent"), "--query", "크림")
    assert code == 3


def test_every_reason_has_a_message() -> None:
    assert set(COSMETIC_REASON_MESSAGES) == set(CosmeticVerdictReason)
