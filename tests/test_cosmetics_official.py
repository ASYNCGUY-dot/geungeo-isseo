"""Official efficacy of functional cosmetics (wording observed in the 2026-10-11 export; synthetic rows)."""

import pytest

from claimledger.cosmetics_official import (
    COSMETIC_EFFICACY_VERSION,
    CosmeticFunction,
    EfficacyStatus,
    parse_cosmetic_efficacy,
)

F = CosmeticFunction
WHITENING = "피부의 미백에 도움을 준다."
WRINKLE = "피부의 주름개선에 도움을 준다."


def _functions(document: str = "", sentence: str = "") -> set[CosmeticFunction]:
    efficacy = parse_cosmetic_efficacy(document, sentence)
    assert efficacy.status is EfficacyStatus.READABLE, efficacy.status
    return set(efficacy.functions)


def test_the_reported_efficacy_sentence_is_read() -> None:
    efficacy = parse_cosmetic_efficacy("", f"{WHITENING} {WRINKLE}")

    assert efficacy.status is EfficacyStatus.READABLE and efficacy.version == COSMETIC_EFFICACY_VERSION
    assert efficacy.functions == frozenset({F.WHITENING, F.WRINKLE})
    assert [(item.function, item.text, item.source) for item in efficacy.sentences] == [
        (F.WHITENING, "피부의 미백에 도움을 준다.", "effect_name"),
        (F.WRINKLE, "피부의 주름개선에 도움을 준다.", "effect_name"),
    ]


def test_document_lines_with_markers_and_sunscreen_indexes_are_read() -> None:
    document = (
        "1. 피부의 미백에 도움을 준다.\n"
        "-. 피부 주름개선에 도움을 줍니다\n"
        "· 자외선으로부터 피부를 보호한다. (SPF50+, PA++++)"
    )
    efficacy = parse_cosmetic_efficacy(document, "")

    assert efficacy.functions == frozenset({F.WHITENING, F.WRINKLE, F.SUNSCREEN})
    assert efficacy.sentences[2].text == "자외선으로부터 피부를 보호한다. (SPF50+, PA++++)"
    assert efficacy.sentences[2].source == "document"


@pytest.mark.parametrize(("line", "function"), [
    ("피부 미백에 도움을 준다.", F.WHITENING),
    ("피부의 미백에 도움을 줍니다.", F.WHITENING),
    ("피부주름개선에 도움을 준다", F.WRINKLE),
    ("입술의 주름개선에 도움을 준다.", F.LIP_WRINKLE),
    ("자외선으로부터 피부를 보호한다(SPF50+, PA++++).", F.SUNSCREEN),
    ("자외선으로부터 피부를 보호한다.(SPF50+ PA+++, 지속내수성)", F.SUNSCREEN),
    ("자외선으로부터 피부를 보호한다. (SPF 45)", F.SUNSCREEN),
    # Index separators seen in the export: a middle dot, a period, or none before 내수성.
    ("자외선으로부터 피부를 보호한다.(SPF 27 ⋅ PA++)", F.SUNSCREEN),
    ("자외선으로부터 피부를 보호한다. (SPF30‧PA+++)", F.SUNSCREEN),
    ("자외선으로부터 피부를 보호한다(SPF50+.PA++++)", F.SUNSCREEN),
    ("자외선으로부터 피부를 보호한다. (SPF 50+, PA++++내수성)", F.SUNSCREEN),
    ("자외선으로부터 피부를 보호한다.", F.SUNSCREEN),
    ("자외선으로부터 피부를 보호하는데 도움을 준다.", F.SUNSCREEN),
    ("모발의 염모", F.HAIR_DYE),
    ("모발(백모)의 염모(흑색)", F.HAIR_DYE),
    ("모발의 탈색", F.HAIR_BLEACH),
    ("제모(체모의 제거)", F.HAIR_REMOVAL),
    ("탈모 증상의 완화에 도움을 준다.", F.HAIR_LOSS),
    ("탈모증상 완화에 도움을 준다.", F.HAIR_LOSS),
    ("탈모 증상 완화에 도움을 줍니다.", F.HAIR_LOSS),
    ("염모제의 산화제 또는 탈색제·탈염제의 산화제", F.DYE_OXIDANT),
    ("여드름성 피부를 완화하는 데 도움을 준다.", F.ACNE),
    ("피부장벽의 기능을 회복하여 가려움 등의 개선에 도움을 준다.", F.SKIN_BARRIER),
    ("튼살로 인한 붉은 선을 엷게 하는 데 도움을 준다.", F.STRETCH_MARK),
    ("염모제의 산화제 또는 탈색ㆍ탈염제의 산화제", F.DYE_OXIDANT),
    ("염모제의 산화보조제 또는 탈색 · 탈염제의 산화보조제", F.DYE_OXIDANT_AID),
])
def test_each_allowlisted_sentence_form_maps_to_one_function(line: str, function: CosmeticFunction) -> None:
    assert _functions(document=line) == {function}
    assert _functions(sentence=line) == {function}


def test_lip_wrinkle_is_not_skin_wrinkle() -> None:
    assert F.WRINKLE not in _functions(document="입술의 주름개선에 도움을 준다.")


@pytest.mark.parametrize("statement", [
    "피부에 미백에 도움을 준다.",
    "피부의 미백에 도움은 준다.",
    "피부의 주름개선에 더움을 준다.",
    "피부의 주름개선과 미백에 도움을 준다.",
    "피부 미백에 도움을 주고 피부의 주름개선에 도움을 준다.",
    "피부의 미백에 도움을 주지 않는다.",
    "피부의 미백에 도움을 준다 (임상시험 완료)",
    "피부의 미백에 도움을 준다, 피부결 개선",
    "피부의 미백에 도움을 준다.\n효능효과",
    "피부의 미백에 도움을 준다.\n가",
    "자외선으로부터 피부를 보호한다(SP33, PA+++).",
    "자외선으로부터 피부를 보호한다. (SFP40, PA+++)",
    "자외선으로부터 피부를 보호한다. (SPF50+, PA+++++)",
    "자외선으로부터 피부를 보호한다(SPF50+PA+++).효능효과",
    "피부의 미백개선에 도움을 준다.",
    "자외선으로부터 피부를 보호한다.(SPF: SPF50+, PA: ++++ )",
    "자외선으로부터 피부를 보호한다. (SPF50+, PA++++",
    "자외선으로부타 피부를 보호한다.",
    "피부의 미백에 도움을 준다.\n확인시험 : 다음 시험법에 따라 시험할 때 이에 적합하여야 한다.",
    "기심사 품목과 주성분 종류와 분량이 동일하며 제형이 변경된 제품임",
])
def test_wording_outside_the_allowlist_holds_the_whole_product(statement: str) -> None:
    for efficacy in (parse_cosmetic_efficacy(statement, ""), parse_cosmetic_efficacy("", statement)):
        assert efficacy.status is EfficacyStatus.UNRECOGNIZED_WORDING
        assert efficacy.functions == frozenset() and efficacy.sentences == ()


@pytest.mark.parametrize("statement", [
    # Misspelt indexes and wording outside the forms, seen in the export.
    "자외선으로부터 피부를 보호한다. (SFP40, PA+++)",
    "자외선으로부터 피부를 보호한다,(SPF50+,PA+++)",
    "자외선으로부터 피부를 보호한다(SPF50+PA+++).효능효과",
    "1。자외선으로부터 피부를 보호한다.(SPF 17)",
    "모발의 염색(갈색)",
    "백발의 염색(황갈색)",
    "모발(백모)의 염색 (진갈색)",
    "염모제의 산화제",
    "탈색제, 탈염제의 산화보조제",
    "자외선으로부터 피부를 보호한다. (SFP40, PA+++)\n유첨 : 자외선 차단지수(SPF) 평가시험 자료",
])
def test_an_unread_statement_about_other_functions_grants_neither_judged_function(statement: str) -> None:
    for efficacy in (parse_cosmetic_efficacy(statement, ""), parse_cosmetic_efficacy("", statement)):
        assert efficacy.status is EfficacyStatus.UNRECOGNIZED_WORDING and efficacy.functions == frozenset()
        assert efficacy.grants_no_whitening_or_wrinkle


@pytest.mark.parametrize("statement", [
    # The function is named, in whatever wording.
    "피부의 미백개선에 도움을 준다.",
    "자외선으로부터 피부를 보호하고 미백에 도움을 준다.",
    "자외선으로부터 피부를 보호한다. (SFP40, PA+++)\n피부의 주름개선에 도움은 준다.",
    "자외선으로부터 피부를 보호한다. (SFP40, PA+++)\n화이트닝",
    "자외선으로부터 피부를 보호한다. (SFP40, PA+++), 멜라닌 색소 침착 방지",
    # A misspelt function word still stands beside "도움을 준다".
    "자외선으로부터 피부를 보호한다. 피부의 미벡에 도움을 준다.",
    "자외선으로부터 피부를 보호한다. 피부의 주룸개선에 도웅을 준다.",
    "피부의 자외선 차단에 도움을 준다(SPF 10)",
    "탈모 증상에 완화에 도움을 준다",
    # A line that names no function at all says nothing about what was granted.
    "효능효과",
    "기심사 품목과 주성분 종류와 분량이 동일하며 제형이 변경된 제품임",
    "자외선으로부터 피부를 보호한다. (SFP40, PA+++)\n별첨 참조",
    "모발의 염색(갈색)\n1호(자연흑갈색)",
])
def test_an_unread_statement_that_may_grant_a_judged_function_is_not_marked(statement: str) -> None:
    for efficacy in (parse_cosmetic_efficacy(statement, ""), parse_cosmetic_efficacy("", statement)):
        assert efficacy.status is EfficacyStatus.UNRECOGNIZED_WORDING
        assert not efficacy.grants_no_whitening_or_wrinkle


def test_the_mark_is_only_for_wording_that_was_not_read() -> None:
    sunscreen = "자외선으로부터 피부를 보호한다."
    # A readable statement lists its functions; held data of the other kinds proves nothing.
    assert not parse_cosmetic_efficacy("", sunscreen).grants_no_whitening_or_wrinkle
    assert not parse_cosmetic_efficacy("", "").grants_no_whitening_or_wrinkle
    template = parse_cosmetic_efficacy(f"{sunscreen}\n※ 해당하는 효능효과 이외에는 모두 삭제하시기 바랍니다.", "")
    assert template.status is EfficacyStatus.TEMPLATE_REMNANT and not template.grants_no_whitening_or_wrinkle
    # Both fields count: the readable sentence beside an unread document names whitening.
    beside = parse_cosmetic_efficacy("자외선으로부터 피부를 보호한다. (SFP40, PA+++)", WHITENING)
    assert beside.status is EfficacyStatus.UNRECOGNIZED_WORDING and not beside.grants_no_whitening_or_wrinkle


def test_missing_efficacy_is_its_own_status() -> None:
    efficacy = parse_cosmetic_efficacy("  ", "")
    assert efficacy.status is EfficacyStatus.MISSING and efficacy.functions == frozenset()


@pytest.mark.parametrize("document", [
    f"{WHITENING}\n{WRINKLE}\n※ 해당하는 효능효과 이외에는 모두 삭제하시기 바랍니다.",
    f"※해당하는 효능효과 이외에는 모두 삭제하시기 바랍니다\n{WHITENING}",
])
def test_the_form_instruction_holds_the_product(document: str) -> None:
    # The list may be the unedited form, so even a well-formed sentence above it proves nothing.
    efficacy = parse_cosmetic_efficacy(document, "")
    assert efficacy.status is EfficacyStatus.TEMPLATE_REMNANT and efficacy.functions == frozenset()


def test_disagreeing_official_fields_hold_the_product() -> None:
    document = "자외선으로부터 피부를 보호한다.(SPF50+, PA+++)"
    conflict = parse_cosmetic_efficacy(document, f"{WHITENING} {WRINKLE}")
    assert conflict.status is EfficacyStatus.CONFLICTING_FIELDS and conflict.functions == frozenset()

    superset = parse_cosmetic_efficacy(f"{WHITENING}\n{WRINKLE}\n{document}", f"{WHITENING} {WRINKLE}")
    assert superset.status is EfficacyStatus.CONFLICTING_FIELDS

    agreeing = parse_cosmetic_efficacy(f"- {WHITENING}\n- {WRINKLE}", f"{WHITENING} {WRINKLE}")
    assert agreeing.status is EfficacyStatus.READABLE
    assert agreeing.functions == frozenset({F.WHITENING, F.WRINKLE})
    assert {item.source for item in agreeing.sentences} == {"document"}


def test_an_unreadable_field_beside_a_readable_one_still_holds() -> None:
    efficacy = parse_cosmetic_efficacy("피부의 미백에 도움은 준다.", WHITENING)
    assert efficacy.status is EfficacyStatus.UNRECOGNIZED_WORDING
