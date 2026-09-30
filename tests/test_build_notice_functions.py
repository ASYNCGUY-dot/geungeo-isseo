import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from scripts import build_notice_functions


def _hwpx(paragraphs: list[str]) -> bytes:
    body = "".join(f'<hp:p id="{i}"><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>' for i, text in enumerate(paragraphs))
    xml = f'<hs:sec xmlns:hs="s" xmlns:hp="p">{body}</hs:sec>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as inner:
        inner.writestr("Contents/section0.xml", xml)
    return buffer.getvalue()


def _notice(path: Path) -> Path:
    standards = [
        "제3. 개별 기준 및 규격",
        "1-1 비타민 A",
        "3) 제품의 요건",
        "(1) 기능성 내용",
        "(가) 어두운 곳에서 시각 적응을 위해 필요",
        "(나) 피부와 점막을 형성하고 기능을 유지하는데 필요",
        "(2) 일일섭취량 : 210~1,000 μg RE",
        "2-16",
        "EPA 및 DHA 함유 유지",
        "3) 최종제품의 요건",
        "(1) 기능성 내용 : 혈중 중성지질 개선･혈행 개선･기억력 개선에 도움을 줄 수 있음",
        "(2) 일일섭취량 : EPA와 DHA의 합으로서 0.5~2 g",
        "2-51 프로바이오틱스",
        "(1) 기능성 내용 : 유산균 증식 및 유해균 억제･배변활동 원활･장 건강에 도움을 줄 수 있음",
        "(2) 일일섭취량 : 1억~100억 CFU",
        "2-61 라피노스",
        "(1) 기능성 내용",
        "(가) 장내 유익균의 증식과 유해균의 억제에 도움을 줄 수 있음",
        "(나) 배변활동을 원활히 하는데 도움을 줄 수 있음",
        "(2) 일일섭취량",
    ]
    with zipfile.ZipFile(path, "w") as outer:
        outer.writestr("notice/standards_(제1~제3).hwpx", _hwpx(standards))
        outer.writestr("notice/methods_(제4).hwpx", _hwpx(["시험법", "기능성 없음"]))
        outer.writestr("notice/readme.txt", "not a notice document")
    return path


def _run(tmp_path: Path) -> tuple[int, dict]:
    output = tmp_path / "functions.json"
    code = build_notice_functions.main([
        "--notice-zip", str(_notice(tmp_path / "notice.zip")),
        "--source-url", "https://www.mfds.go.kr/brd/m_211/view.do?seq=14973",
        "--notice", "제2026-43호 (2026.6.11.)",
        "--output", str(output),
    ])
    return code, json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}


def test_extracts_each_notified_ingredient_function_text(tmp_path: Path) -> None:
    code, payload = _run(tmp_path)

    assert code == 0
    items = {item["number"]: item for item in payload["items"]}
    assert list(items) == ["1-1", "2-16", "2-51", "2-61"]
    assert items["1-1"]["name"] == "비타민 A"
    assert items["1-1"]["function_text"] == (
        "(가) 어두운 곳에서 시각 적응을 위해 필요 (나) 피부와 점막을 형성하고 기능을 유지하는데 필요"
    )
    assert items["2-16"]["name"] == "EPA 및 DHA 함유 유지"
    assert items["2-16"]["function_text"].startswith("혈중 중성지질 개선")
    assert items["2-16"]["effects"] == ["blood_triglyceride", "blood_circulation", "memory"]
    assert items["2-51"]["effects"] == [
        "probiotic_growth_harmful_inhibition", "bowel_movement", "gut_health",
    ]
    assert items["1-1"]["effects"] == []


def test_broadly_mentioned_effects_keep_differently_worded_carriers(tmp_path: Path) -> None:
    _, payload = _run(tmp_path)
    raffinose = next(item for item in payload["items"] if item["number"] == "2-61")

    assert raffinose["effects"] == []
    assert raffinose["mentioned_effects"] == [
        "probiotic_growth_harmful_inhibition", "bowel_movement", "gut_health",
    ]


def test_output_records_source_and_is_deterministic(tmp_path: Path) -> None:
    _, payload = _run(tmp_path)
    first = (tmp_path / "functions.json").read_bytes()
    _run(tmp_path)

    assert (tmp_path / "functions.json").read_bytes() == first
    source = payload["source"]
    assert source["notice"] == "제2026-43호 (2026.6.11.)"
    assert source["file_sha256"] == hashlib.sha256((tmp_path / "notice.zip").read_bytes()).hexdigest().upper()
    assert payload["item_count"] == 4


def test_repeated_function_block_of_one_item_is_merged() -> None:
    items = build_notice_functions.parse_functions([
        "2-49 키토산/키토올리고당",
        "(1) 기능성 내용 : 혈중 콜레스테롤 개선에 도움을 줄 수 있음",
        "(2) 일일섭취량",
        "(1) 기능성 내용",
        "(가) 체지방 감소에 도움을 줄 수 있음",
        "(2) 일일섭취량",
    ])
    assert items == [{
        "number": "2-49",
        "name": "키토산/키토올리고당",
        "function_text": "혈중 콜레스테롤 개선에 도움을 줄 수 있음 (가) 체지방 감소에 도움을 줄 수 있음",
    }]


def test_function_text_at_the_end_of_the_document_is_kept() -> None:
    items = build_notice_functions.parse_functions([
        "2-69 콜레우스포스콜리 추출물", "(1) 기능성 내용 : 체지방 감소에 도움을 줄 수 있음",
    ])
    assert items[0]["function_text"] == "체지방 감소에 도움을 줄 수 있음"


def test_one_number_for_two_ingredients_is_rejected() -> None:
    with pytest.raises(build_notice_functions.NoticeError, match="2-9"):
        build_notice_functions.parse_functions([
            "2-9 코엔자임Q10", "(1) 기능성 내용 : 항산화에 도움", "(2) 일일섭취량",
            "2-9 다른 원료", "(1) 기능성 내용 : 혈압에 도움", "(2) 일일섭취량",
        ])


def test_missing_or_ambiguous_notice_is_an_input_error(tmp_path: Path) -> None:
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as outer:
        outer.writestr("notice/methods_(제4).hwpx", _hwpx(["시험법"]))
    code = build_notice_functions.main([
        "--notice-zip", str(empty), "--source-url", "u", "--notice", "n", "--output", str(tmp_path / "o.json"),
    ])
    assert code == 3
    assert not (tmp_path / "o.json").exists()
