"""Advertisement claims about functional cosmetics: extraction and the wording that may be confirmed.

Keyword cues only propose what a sentence is about. A claim can be confirmed only when the whole
sentence is one of a few allowlisted forms about whitening or wrinkle improvement, with no subject
other than the product itself: the official efficacy belongs to the product, not to an ingredient.
The medical and guarantee cues are a conservative development policy, not a legal determination.

A sentence that is neither a claim nor a recognized disclaimer is kept as unread text: nothing in
it was judged, and a confirmation is withheld while such text stands beside a recognized sentence.

In a sentence that is not such a form, one reading still says which function is claimed: the
function named as what is helped ("미백과 주름개선에 도움을 …", "미백·주름개선 기능성"). It counts
only when the sentence holds one such phrase and no function word beside it names another
function. Two phrases, or another function beside the phrase, usually set this product against
another one, a set, a gift or what the product is not ("이 크림은 주름개선 기능성, 토너는 미백 기능성").

A cue is set aside when it is not asserted: a denial, a caution to the reader or a closing question
mark reaches every cue before it, because Korean puts what is denied before the denial, and a
condition ("염증이 생기면 …") reaches the disease words before it. What follows is still read.

Around a claim form a sentence may carry an invitation to the reader ("…제품으로 저녁 루틴을 마무리해
보세요") or a fixed statement by the seller ("…을 소개합니다"). An invitation is a few role-bound
words and an action: when, where, what. The lists hold no subject, so nothing can bring in a third
party or another product, and no noun that a time, an amount or an effect could attach to; "check"
needs the page or its information as what is checked. One word outside them leaves the sentence
unread. A sentence that is only an invitation is a neutral sentence: it is read and claims
nothing. One invitation does not withhold a confirmation beside it; two can add up to a promise
("한 번 발라 보세요. 바로 확인해 보세요."), so an advertisement with more than one is not confirmed.
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from functools import lru_cache
from typing import Literal, NamedTuple

from pydantic import BaseModel

from claimledger.claims_v1 import ExpressionStrength, _literal
from claimledger.cosmetics_official import CosmeticFunction
from claimledger.official_v2 import _compact

COSMETIC_CLAIM_VERSION = "cosmetic-claim-v1.11"
MAX_AD_TEXT_LENGTH = 5000
_CLOSING_MARKS = ".!?。…"

# Cues on whitespace-free NFKC, casefolded text: for each kind a pattern of single words, which
# must lie inside one word of the sentence ("후기 적립금" is not "기적"), and a pattern of phrases,
# which may run over several ("3일 만에", "피부 재생"). A wrinkle cue after "입술" is the lip
# function, and "선크림" inside "주름개선크림" is not a sunscreen.
_Cues = tuple[re.Pattern[str] | None, re.Pattern[str] | None]
_FUNCTION_CUES: tuple[tuple[CosmeticFunction, re.Pattern[str] | None, re.Pattern[str] | None], ...] = (
    (CosmeticFunction.WHITENING, re.compile(r"미백|화이트닝|멜라닌|기미|주근깨"), None),
    (CosmeticFunction.WRINKLE, re.compile(r"(?<!입술)(?<!입술의)주름|링클"), None),
    (CosmeticFunction.LIP_WRINKLE, None, re.compile(r"입술(?:의)?주름")),
    (CosmeticFunction.SUNSCREEN, re.compile(r"자외선|spf|(?<!개)선크림|(?<!개)선블록|썬크림|썬블록"), None),
    (CosmeticFunction.HAIR_DYE, re.compile(r"염모|염색"), None),
    (CosmeticFunction.HAIR_BLEACH, re.compile(r"탈색"), None),
    (CosmeticFunction.HAIR_REMOVAL, re.compile(r"제모"), None),
    (CosmeticFunction.HAIR_LOSS, re.compile(r"탈모"), None),
    (CosmeticFunction.ACNE, re.compile(r"여드름"), None),
    (CosmeticFunction.SKIN_BARRIER, re.compile(r"가려움"), re.compile(r"피부장벽")),
    (CosmeticFunction.STRETCH_MARK, re.compile(r"튼살"), None),
)
# Words with an everyday sense count only in their medical or absolute one: "저자극 처방" is a
# formulation, "재생 플라스틱" a material, "링클 필러 크림" a product type, "부작용이 있으면" a caution,
# "치료를 받으세요" advice, and "즉시 흡수" is not an effect.
_PRESCRIBER = r"(?:의사|전문의|피부과|병원|의원|약사|약국|한의사|한의원)"
_REGROWN = r"(?:피부|세포|진피|조직|상처|모발|모근|콜라겐)"
# "개선" is a strength only as a verb: "주름개선" and "주름 개선 효과" name the function.
_VERBAL = (
    r"(?:합니다|한다|해요|해줍|해주|해드|해서|했|하는|하고|하며|하여|하세요"
    r"|됩니다|된다|돼요|됐|되는|되고|되며|되어|시켜|시킵|시키)"
)
_STRENGTH_CUES: tuple[tuple[ExpressionStrength, re.Pattern[str] | None, re.Pattern[str] | None], ...] = (
    (
        ExpressionStrength.TREATMENT_PREVENTION,
        re.compile(
            r"치료(?!를?받)|완치|특효|낫게|낫는|낫습|질병|질환|항염|염증|아토피|피부염|습진|건선|흉터"
            r"|약효|보톡스|시술"
        ),
        re.compile(
            r"필러(?:를|을)?(?:맞|시술|주사|효과|대신)"
            rf"|{_PRESCRIBER}(?:의|가|이|에서)?처방|처방받"
            rf"|{_REGROWN}(?:의|을|를)?재생|재생(?:크림|효과|력|케어|시켜|시킵|시키)"
        ),
    ),
    (
        ExpressionStrength.GUARANTEE,
        re.compile(r"보장|확실|반드시|무조건|완벽|단번에|기적|영구|무부작용"),
        # A time of delivery or of selling out is not a time of the effect.
        re.compile(
            r"100%|100퍼|백퍼|(?:하루|\d+(?:일|주|개월))만에(?!도착|완판|재입고|품절|배송|매진)"
            r"|부작용(?:이|은|도|걱정)?(?:전혀|하나도|일절)?(?:없|제로)"
        ),
    ),
    (ExpressionStrength.SUPPORT, re.compile(r"도움|기능성"), None),
    (
        ExpressionStrength.IMPROVEMENT,
        re.compile(
            rf"개선(?={_VERBAL})|향상|좋아(?:지|집|져|졌)|회복|되살|강화|해결|해소|없애|없어지|없어집|없어져"
            r"|사라지|사라집|사라져|사라졌|사라진|제거(?!후|한뒤|한후)|지워|지우는|지웁|펴주|펴줍|펴집|펴져|펴지|하얗게|하얘"
            r"|밝아|환해|엷게|옅게|옅어지|옅어집|옅어져|완화|줄여|줄어|감소"
        ),
        None,
    ),
    (ExpressionStrength.POSSIBILITY, None, re.compile(r"수있")),
)
_STRONG = frozenset({
    ExpressionStrength.IMPROVEMENT, ExpressionStrength.GUARANTEE, ExpressionStrength.TREATMENT_PREVENTION,
})

# Other words that hold the letters of a cue: "정기적", "교환해", "살펴주세요", "보습진정".
_INNOCENT = re.compile(
    r"정기적|주기적|장기적|단기적|시기적절|교환해|전환해|변환해|순환해|반환해|소환해|귀환해"
    r"|살펴주|살펴줍|보습진정|취향상|방향상"
)
# A denial. "없애다" and "없어지다" are effects, "밖에 없다" means "only", and "않으면" or "없으면" set
# a condition ("사라지지 않으면 환불").
_DENIAL = re.compile(
    r"않(?!으면|는다면|을경우|을시)|못(?:하|해|한|함|합)|아니|아닌|아닙|아님"
    r"|(?<!밖에)없(?!애|앨|앱|앴|어지|어집|어져|어졌|으면|다면|을경우|을시)|다릅니다|달라요|다르다"
)
# "It is no dream", "it is no lie": the denial stresses the claim before it.
_RHETORICAL = re.compile(r"(?:꿈|거짓말|거짓|과장|농담|우연)(?:이|은|도)?(?:아니|아닙|아닌|아님)")
# A caution or prohibition addressed to the reader. A bare "마세요", "금지" or "상담" is not one:
# "놓치지 마세요", "무단 전재 금지" and "카톡 상담 환영" follow claims in ordinary advertising.
_CAUTION = re.compile(
    r"사용하지마|사용하지말|바르지마|바르지말|믿지마|사용을?(?:중지|중단|자제|삼가|피하|피해|금)|사용금지"
    r"|피해서|피해주|피하세|피하십|(?:부위|곳)(?:는|를|은)?피하"
    r"|(?:전문의|의사|약사|피부과)(?:등)?(?:와|과|에게|의)?(?:상담|상의)"
    r"|상담할것|있(?:는|으신|을)(?:분|경우|부위)"
)
# A disease word names a state, not a claim, in two cases. A procedure the reader has had: "시술
# 후에는", "시술 당일", "시술 받은 날" (not "시술 받은 듯", and not "치료 후 맑아진 피부"). And a
# symptom followed within a few letters, before any comma, by its condition: "염증이 생기면",
# "아토피 피부라면". Farther away the condition is about something else ("완치 크림, 마음에 들지
# 않으면 환불"); "…이라면" names the product and "낫지 않으면 환불" promises a cure.
_HAD_PROCEDURE = re.compile(r"(?:직)?후(?!기)|당일|(?:를|을)?(?:받은(?!듯|것같|것처럼)|받았다면|받으셨다면)")
_STATE_NEAR = re.compile(
    r"[^,]{0,10}?(?:있으면|있다면|있을경우|있을때|생기면|생긴다면|생길경우|생겼을때|생겼다면|나타나면"
    r"|계속되면|보이면|심해지면|심할때|남았다면|피부라면|가라앉지않으면|진정되지않으면|호전되지않으면)"
)
_QUESTION = re.compile(r"\?[.!。]*$")
# The disclaimer every cosmetic may carry; one closing mark at most, like the claim forms.
_DISCLAIMER = re.compile(
    r"(?:본제품은|이제품은)?(?:질병의예방및치료를위한)?의약품이(?:아닙니다|아니에요|아니다|아님)[.!。]?"
)

_DOT = "[ᆞ·・‧⋅∙]"
_SUBJECT = r"(?:(?:본제품|이제품|본품|해당제품|본상품|이상품|해당상품)(?:은|는|이|가))?"
_WHITENING = r"(?:피부(?:의)?)?미백"
_WRINKLE = r"(?:피부(?:의)?)?주름개선"
_JOIN = rf"(?:과|와|및|[,/]|{_DOT})"
# The effect a form names, the functions it asserts, and the word that may stand before "기능성".
# "미백 관리" and "미백 케어" say no more than "미백"; "이중 기능성" needs both functions named.
_EFFECTS: tuple[tuple[frozenset[CosmeticFunction], str, str], ...] = (
    (frozenset({CosmeticFunction.WHITENING}), rf"{_WHITENING}(?:관리|케어)?", ""),
    (frozenset({CosmeticFunction.WRINKLE}), rf"{_WRINKLE}(?:관리|케어)?", ""),
    (
        frozenset({CosmeticFunction.WHITENING, CosmeticFunction.WRINKLE}),
        rf"(?:{_WHITENING}{_JOIN}?{_WRINKLE}|{_WRINKLE}{_JOIN}?{_WHITENING})(?:모두)?(?:관리|케어)?",
        r"(?:2중|이중)?",
    ),
)
# "도움이 되다" says the same as "도움을 주다".
_HELP = (
    r"에도움(?:을(?:줄수(?:있음|있습니다|있어요)|줌|줍니다|준다)"
    r"|이(?:될수(?:있음|있습니다|있어요)|됨|됩니다|돼요|된다))?"
)
# A function as what is helped, or as what the product is functional for: its name, or a chain of
# names, right before "에 도움" or "기능성". The chain is looked for in the letters before that word.
# "도움" and "기능성" must each be one word ("주름에도 움직임", "기능 성분" are not), and the phrase
# must stand on one line: a line break joins the end of one line to the start of the next.
_NAME = r"(?:피부(?:의)?)?(?:미백|화이트닝|멜라닌|기미|주근깨|주름|링클)(?:개선|완화|관리|케어|효과)?"
_HELP_WORD = re.compile(r"에(?:도)?(도움)|(?:2중|이중)?(기능성)")
_HELPED_CHAIN = re.compile(rf"(?:{_NAME}{_JOIN}?)*{_NAME}\Z")
_MAX_CHAIN = 40
_COPULA = r"(?:입니다|이에요|예요)"
# "…에 도움을 주는 제품": the claim describes the product named after it. Only general words for
# the product: a kind such as "토너" cannot be checked against the record.
_DESCRIBES = r"에도움(?:을(?:주는|줄수있는|드리는|드릴수있는)|이(?:되는|될수있는))"
_PRODUCT = (
    r",?(?:매일(?:쓰는|사용하는|바르는))?(?:이|본)?(?:기능성|데일리|스킨케어|기초|케어)*"
    r"(?:제품|화장품|상품|아이템)"
)
# What may join the product to an invitation. Not "과", "보다", "만", "처럼": those bring in another
# product, a comparison or an exclusion.
_LINK = rf"(?:{_COPULA},|,|으로|로|을|를|은|는|이|가|이라서|라서|이라|라|이니|니)?"
# A complete claim that an invitation may follow after a comma.
_STATED = (
    r"에도움(?:을(?:줍니다|줄수있습니다|줄수있어요|줄수있어|주며|주고|드립니다|드리며)"
    r"|이(?:됩니다|될수있습니다|될수있어요|돼요)),"
)


def _forms(
    tail: str, counted: bool = False,
) -> tuple[tuple[frozenset[CosmeticFunction], re.Pattern[str]], ...]:
    return tuple(
        (functions, re.compile(rf"{_SUBJECT}{effect}{count if counted else ''}{tail}"))
        for functions, effect, count in _EFFECTS
    )


# Sentences and sentence openings, matched on the words run together without the one closing mark.
# "Named" forms end in a noun for the product, so a clause describing the product may precede them.
_NAMED_WHOLE = (
    *_forms(rf"기능성(?:화장품|제품)?{_COPULA}?", counted=True),
    *_forms(rf"{_DESCRIBES}{_PRODUCT}{_COPULA}?"),
)
_NAMED_OPENING = (
    *_forms(rf"{_DESCRIBES}{_PRODUCT}{_LINK}"),
    *_forms(rf"기능성(?:화장품|제품){_LINK}", counted=True),
)
_STATED_WHOLE = _forms(_HELP)
_STATED_OPENING = _forms(_STATED)


def _any(*phrases: str) -> str:
    return "(?:" + "|".join(phrases) + ")"


# An invitation, matched on the words of the sentence joined by single spaces; " ?" marks a space
# that may be left out. Each role has its own closed list. There is no subject role, and no list
# holds a number, a body part, a skin type, a person, an effect, a degree or a result.
_ROUTINE = r"(?:(?:저녁|아침|데일리|스킨케어) ?)?루틴"
_WHEN = _any(
    "지금 ?바로", "지금", "바로", "오늘 ?부터", "오늘", "이제", "먼저", "꼭", "다시", "한 ?번", "매일", "꾸준히",
    "천천히", "편하게", "가볍게", "간편하게", "미리", "드디어", "(?:구매|사용|결제) ?전(?:에)?",
)
_AT = r"(?:에서|에|으로|로)"
# The page and the shop, where a reader can look something up.
_PAGE_NOUN = _any(
    "상세 ?페이지", "이 ?페이지", "페이지", "온라인", "공식몰", "쇼핑몰", "홈페이지", "여기", "이곳", "아래", "하단",
    "링크",
)
_PAGE = _PAGE_NOUN + _AT
_PLACE = _any(
    _PAGE_NOUN, "장바구니", "오프라인", "매장", "화장대", "파우치", _ROUTINE, "일상", "고객 ?센터", "무료 ?배송",
) + _AT
_INFORMATION = (
    r"(?:자세한 )?" + _any("상세 ?정보", "상세 ?설명", "상세 ?페이지", "상세 ?안내", "안내", "정보", "내용")
    + r"(?:을|를|은|는)"
)
_THING = (
    _any(_ROUTINE, "스킨 ?케어", "하루", "일상", "화장대", "장바구니") + r"(?:을|를)"
    + r"|(?:이 ?제품|제품)(?:을|를)?"
)
_ARGUMENT = rf"(?:{_WHEN}|{_PLACE}|{_INFORMATION}|{_THING}),?"
_ENDING = r"(?:보세요|보십시오|봐요|주세요|주십시오|두세요)"
_POLITE = r"(?:하세요|하십시오|해 ?보세요|해 ?주세요)"
# What the reader is invited to do.
_ACTION = (
    r"(?:만나|써|사용해|발라|담아|더해|추가해|챙겨|시작해|마무리해|완성해|채워|구매해|주문해|저장해|공유해|찜해"
    rf"|들러|방문해|문의해|눌러|받아|넣어|올려) ?{_ENDING}"
    rf"|(?:시작|마무리|완성|구매|주문|저장|공유|문의|방문|추가|사용|결제){_POLITE}"
    r"|만나세요|담으세요|더하세요|챙기세요"
)
# Coming to browse is a look as well: with no argument, or at the page.
_BROWSE = (
    rf"(?:구경해|둘러) ?{_ENDING}|구경{_POLITE}|둘러보세요|(?:보러 ?|구경하러 ?|놀러 ?)?오세요"
)
# Looking something up needs the page or its information, and nothing else beside it: "바로 확인해
# 보세요" or "화장대에서 바로 확인해 보세요" after "한 번 발라 보세요" promises a result at once.
_LOOK = rf"(?:(?:확인해|살펴|읽어|참고해) ?{_ENDING}|(?:확인|참고){_POLITE}|살펴보세요)"
_LOOKED_AT = rf"(?:{_PAGE}|{_INFORMATION})"
# What the seller says of the product: a recommendation or introduction with no argument, or that
# it is in stock, with a place and one of a few neutral adverbs at most.
_SAYS = (
    r"추천드립니다|추천드려요|추천합니다|소개합니다|소개해 ?드립니다|소개해 ?드려요|소개해 ?드릴게요"
    r"|선보입니다|선보여요"
)
_NEWLY = r"(?:드디어|오늘|지금|이제|새로)"
_STOCKED = (
    r"(?:재)?입고(?:되었습니다|됐습니다|됐어요)|도착했습니다|도착했어요|들어왔습니다|들어왔어요"
    r"|출시되었습니다|출시됐어요|판매 ?중입니다|판매 ?중|판매합니다"
)
_INVITATION = re.compile(
    rf"(?:{_ARGUMENT} ){{0,5}}(?:{_ACTION})"
    rf"|(?:{_WHEN},? ){{0,2}}{_LOOKED_AT},? (?:(?:{_WHEN}|{_LOOKED_AT}),? ){{0,3}}{_LOOK}"
    rf"|(?:{_PAGE} )?(?:{_BROWSE})"
    rf"|{_SAYS}"
    rf"|(?:{_NEWLY} )?(?:{_PLACE} )?(?:{_STOCKED})"
)
# How the product got to the shop, said before it: "드디어 입고된 …", "이 페이지에서 만나는 …".
_ARRIVED = re.compile(
    rf"(?:{_NEWLY} )?(?:{_PLACE} )?"
    r"(?:(?:새로 ?|재)?입고된|새로 ?나온|출시된|도착한|들어온|판매 ?중인|만나는|선보이는|소개하는)"
)
# Reading is tried on sentences of ordinary length only; a claim and what joins it are short.
_MAX_WORDS, _MAX_CORE_WORDS, _MAX_LEAD_WORDS = 60, 14, 12


class CosmeticClaim(BaseModel):
    model_config = {"frozen": True}

    claim_id: str
    text: str
    span: tuple[int, int]
    function_candidates: tuple[CosmeticFunction, ...]
    function_cues: tuple[str, ...]
    strength: ExpressionStrength | None
    strength_cues: tuple[str, ...]
    # Cue words before a denial, a caution or a question: they propose nothing.
    set_aside_cues: tuple[str, ...] = ()
    confirmed_by_user: bool = False
    extraction_version: Literal["cosmetic-claim-v1.11"] = COSMETIC_CLAIM_VERSION


class UnreadSentence(BaseModel):
    model_config = {"frozen": True}

    text: str
    span: tuple[int, int]


class NeutralSentence(BaseModel):
    """An invitation to use or buy the product, read completely; it claims nothing."""

    model_config = {"frozen": True}

    text: str
    span: tuple[int, int]


class _Reading(NamedTuple):
    functions: tuple[CosmeticFunction, ...]
    function_cues: tuple[str, ...]
    strength: ExpressionStrength | None
    strength_cues: tuple[str, ...]
    set_aside: tuple[str, ...]
    # A function word or a strong word was set aside, so the sentence stays visible as a claim.
    substance_set_aside: bool
    # Functions named as what is helped, when one phrase names them and nothing beside it differs.
    helped: frozenset[CosmeticFunction]


def normalize_ad_text(text: str) -> str:
    """Drop a leading byte order mark and compose decomposed Hangul (NFD); spans index the result."""
    return unicodedata.normalize("NFC", text.removeprefix("\ufeff"))


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """Sentences end at closing marks followed by whitespace or the end; a line break alone is none.

    Same result as the shared splitter in claims_v1, in one pass: that one is quadratic on a long
    run of closing marks.
    """
    spans: list[tuple[int, int]] = []
    start = index = 0
    while index < len(text):
        if text[index] not in _CLOSING_MARKS:
            index += 1
            continue
        end = index
        while end < len(text) and text[end] in _CLOSING_MARKS:
            end += 1
        # A sentence needs a character before its closing mark.
        if (end == len(text) or text[end].isspace()) and end - start >= 2:
            spans.append((start, end))
            start = end
        index = end
    spans.append((start, len(text)))
    trimmed = []
    for first, last in spans:
        while first < last and text[first].isspace():
            first += 1
        while last > first and text[last - 1].isspace():
            last -= 1
        if first < last:
            trimmed.append((first, last))
    return trimmed


def _words(sentence: str) -> list[str]:
    """The words of a sentence without whitespace, NFKC and casefolded, less its one closing mark."""
    words = [_compact(word)[0] for word in sentence.split()]
    # One closing mark at most: "…" and "..." announce a continuation.
    if words and words[-1][-1:] in {".", "!", "。"}:
        words[-1] = words[-1][:-1]
    return [word for word in words if word]


def _matched(
    forms: tuple[tuple[frozenset[CosmeticFunction], re.Pattern[str]], ...], text: str,
) -> frozenset[CosmeticFunction] | None:
    return next((functions for functions, pattern in forms if pattern.fullmatch(text)), None)


def _invites(words: Sequence[str]) -> bool:
    """Whether the words are an invitation to the reader or a fixed statement by the seller."""
    return bool(words) and _INVITATION.fullmatch(" ".join(words)) is not None


def _asserted(sentence: str) -> tuple[frozenset[CosmeticFunction] | None, bool]:
    """The functions a fully read sentence asserts, and whether it carries an invitation."""
    words = _words(sentence)
    stated = _matched((*_STATED_WHOLE, *_NAMED_WHOLE), "".join(words))
    if stated is not None or not 1 < len(words) <= _MAX_WORDS:
        return stated, False
    for start in range(min(len(words), _MAX_LEAD_WORDS + 1)):
        lead = words[:start]
        # Before the claim: nothing, an invitation closed by a comma, or how the product arrived.
        after_comma = bool(lead) and lead[-1].endswith(",") and _invites([*lead[:-1], lead[-1][:-1]])
        arrived = bool(lead) and _ARRIVED.fullmatch(" ".join(lead)) is not None
        if lead and not after_comma and not arrived:
            continue
        whole = _NAMED_WHOLE if arrived else (*_STATED_WHOLE, *_NAMED_WHOLE)
        opening = _NAMED_OPENING if arrived else (*_STATED_OPENING, *_NAMED_OPENING)
        for end in range(start + 1, min(len(words), start + _MAX_CORE_WORDS) + 1):
            core, rest = "".join(words[start:end]), words[end:]
            # An invitation on one side only: two of them around a claim can add up to a promise.
            if rest and after_comma:
                continue
            found = _matched(opening, core) if rest else _matched(whole, core)
            if found is not None and (not rest or _invites(rest)):
                return found, after_comma or bool(rest)
    return None, False


def asserted_functions(claim: CosmeticClaim) -> frozenset[CosmeticFunction] | None:
    """Functions asserted by a fully recognized sentence, or None when any part of it is unread."""
    return _asserted(claim.text)[0]


def helped_functions(claim: CosmeticClaim) -> frozenset[CosmeticFunction]:
    """Functions the sentence names as what is helped, in its one such phrase; empty otherwise."""
    return _classify(claim.text).helped


def invitation_count(text: str, claims: Sequence[CosmeticClaim]) -> int:
    """Invitations in an advertisement: its neutral sentences and those inside claim sentences."""
    return len(neutral_sentences(text)) + sum(1 for claim in claims if _asserted(claim.text)[1])


def _neutral(sentence: str) -> bool:
    words = _words(sentence)
    return 0 < len(words) <= _MAX_WORDS and _invites(words)


def _classify(sentence: str) -> _Reading:
    compact, positions = _compact(sentence)
    size = len(compact)
    # Where a word begins in the whitespace-free text.
    begins = [index == 0 or positions[index] - positions[index - 1] > 1 for index in range(size)]

    def flagged(pattern: re.Pattern[str], inside_a_word: bool = False) -> list[bool]:
        marks = [False] * size
        for match in pattern.finditer(compact):
            if not inside_a_word or not any(begins[match.start() + 1 : match.end()]):
                marks[match.start() : match.end()] = [True] * (match.end() - match.start())
        return marks

    innocent = flagged(_INNOCENT, inside_a_word=True)

    def cues(patterns: Sequence[re.Pattern[str] | None]) -> list[re.Match[str]]:
        """Matches that are not the letters of another word; a single-word cue lies in one word."""
        words, phrases = patterns
        found = []
        for pattern, one_word in ((words, True), (phrases, False)):
            for match in pattern.finditer(compact) if pattern is not None else ():
                start, end = match.span()
                if not any(innocent[start:end]) and not (one_word and any(begins[start + 1 : end])):
                    found.append(match)
        return found

    function_matches = [
        (function, match) for function, *patterns in _FUNCTION_CUES for match in cues(patterns)
    ]
    strength_matches = [(level, match) for level, *patterns in _STRENGTH_CUES for match in cues(patterns)]
    in_cue = [False] * size
    for _, match in (*function_matches, *strength_matches):
        in_cue[match.start() : match.end()] = [True] * (match.end() - match.start())
    rhetorical = flagged(_RHETORICAL)
    # A denial inside a cue ("부작용 없는") belongs to that cue.
    not_asserted_before = max(
        (
            match.start() for match in _DENIAL.finditer(compact)
            if not any(in_cue[match.start() : match.end()]) and not rhetorical[match.start()]
        ),
        default=-1,
    )
    not_asserted_before = max(not_asserted_before, max((m.start() for m in _CAUTION.finditer(compact)), default=-1))
    if _QUESTION.search(compact):
        not_asserted_before = size

    def asserted(kind: CosmeticFunction | ExpressionStrength, match: re.Match[str]) -> bool:
        if match.end() <= not_asserted_before:
            return False
        if kind is not ExpressionStrength.TREATMENT_PREVENTION:
            return True
        if match.group() == "시술" and _HAD_PROCEDURE.match(compact, match.end()):
            return False
        return not _STATE_NEAR.match(compact, match.end())

    stated = [(function, match) for function, match in function_matches if asserted(function, match)]
    functions = {function for function, _ in stated}
    function_cues = [_literal(sentence, positions, match) for _, match in stated]
    phrases: list[tuple[int, int, bool]] = []
    for word in _HELP_WORD.finditer(compact):
        core_start, core_end = word.span(word.lastindex)
        offset = max(word.start() - _MAX_CHAIN, 0)
        chain = _HELPED_CHAIN.search(compact[offset : word.start()])
        if chain is None or any(begins[core_start + 1 : core_end]):
            continue
        first, last = offset + chain.start(), word.start()
        if any(first <= match.start() and match.end() <= last for _, match in stated):
            phrases.append((first, last, "\n" in sentence[positions[first] : positions[core_end - 1]]))
    helped: set[CosmeticFunction] = set()
    if len(phrases) == 1:
        ((first, last, broken),) = phrases
        inside = {function for function, match in stated if first <= match.start() and match.end() <= last}
        if not broken and all(function in inside for function, _ in stated):
            helped = inside
    live = {
        level: [match for candidate, match in strength_matches if candidate is level and asserted(level, match)]
        for level, *_ in _STRENGTH_CUES
    }
    support, improvement = live[ExpressionStrength.SUPPORT], live[ExpressionStrength.IMPROVEMENT]
    if support and improvement:
        # "…기능성 화장품으로 기미가 사라집니다": an effect verb right after its own function word,
        # past the support word, is the claim. "…기능성 화장품, 미백 라인 포장을 강화했습니다" is not.
        after_support = max(match.end() for match in support)
        named = [False] * (size + 1)
        for _, match in stated:
            if match.start() >= after_support:
                named[match.end()] = True
        if any(any(named[max(match.start() - 3, 0) : match.start() + 1]) for match in improvement):
            live[ExpressionStrength.SUPPORT] = []
    strength = next((level for level, *_ in _STRENGTH_CUES if live[level]), None)
    strength_cues = [_literal(sentence, positions, match) for match in live[strength]] if strength else []
    denied = [
        (match.start(), _literal(sentence, positions, match), kind)
        for kind, match in (*function_matches, *strength_matches) if not asserted(kind, match)
    ]
    return _Reading(
        functions=tuple(function for function in CosmeticFunction if function in functions),
        function_cues=tuple(dict.fromkeys(function_cues)),
        strength=strength,
        strength_cues=tuple(strength_cues),
        set_aside=tuple(dict.fromkeys(literal for _, literal, _ in sorted(denied, key=lambda item: item[0]))),
        substance_set_aside=any(isinstance(kind, CosmeticFunction) or kind in _STRONG for _, _, kind in denied),
        helped=frozenset(helped),
    )


@lru_cache(maxsize=16)
def _read_normalized(
    text: str,
) -> tuple[tuple[CosmeticClaim, ...], tuple[UnreadSentence, ...], tuple[NeutralSentence, ...]]:
    claims: list[CosmeticClaim] = []
    unread: list[UnreadSentence] = []
    neutral: list[NeutralSentence] = []
    for start, end in _sentence_spans(text):
        sentence = text[start:end]
        if _DISCLAIMER.fullmatch(_compact(sentence)[0]):
            continue
        reading = _classify(sentence)
        if not reading.functions and reading.strength not in _STRONG and not reading.substance_set_aside:
            if _neutral(sentence):
                neutral.append(NeutralSentence(text=sentence, span=(start, end)))
            else:
                unread.append(UnreadSentence(text=sentence, span=(start, end)))
            continue
        claims.append(
            CosmeticClaim(
                claim_id=f"C{len(claims) + 1}",
                text=sentence,
                span=(start, end),
                function_candidates=reading.functions,
                function_cues=reading.function_cues,
                strength=reading.strength,
                strength_cues=reading.strength_cues,
                set_aside_cues=reading.set_aside,
            )
        )
    return tuple(claims), tuple(unread), tuple(neutral)


def _read(
    text: str,
) -> tuple[tuple[CosmeticClaim, ...], tuple[UnreadSentence, ...], tuple[NeutralSentence, ...]]:
    text = normalize_ad_text(text)
    if len(text) > MAX_AD_TEXT_LENGTH:
        raise ValueError(f"the advertisement text is longer than {MAX_AD_TEXT_LENGTH} characters")
    # One advertisement is read several times on the way to a receipt.
    return _read_normalized(text)


def extract_cosmetic_claims(text: str) -> tuple[CosmeticClaim, ...]:
    return _read(text)[0]


def unread_sentences(text: str) -> tuple[UnreadSentence, ...]:
    """Sentences that are no claim, disclaimer or invitation: nothing in them was judged."""
    return _read(text)[1]


def neutral_sentences(text: str) -> tuple[NeutralSentence, ...]:
    """Invitations to use or buy the product that were read completely and claim nothing."""
    return _read(text)[2]


def confirm_cosmetic_claims(
    claims: Sequence[CosmeticClaim], claim_ids: Iterable[str] | Literal["all"]
) -> tuple[CosmeticClaim, ...]:
    known = {claim.claim_id for claim in claims}
    selected = known if claim_ids == "all" else set(claim_ids)
    unknown = selected - known
    if unknown:
        raise ValueError(f"unknown claim id: {', '.join(sorted(unknown))}")
    return tuple(
        claim.model_copy(update={"confirmed_by_user": claim.claim_id in selected}) for claim in claims
    )


__all__ = [
    "COSMETIC_CLAIM_VERSION",
    "MAX_AD_TEXT_LENGTH",
    "CosmeticClaim",
    "NeutralSentence",
    "UnreadSentence",
    "asserted_functions",
    "confirm_cosmetic_claims",
    "extract_cosmetic_claims",
    "helped_functions",
    "invitation_count",
    "neutral_sentences",
    "normalize_ad_text",
    "unread_sentences",
]
