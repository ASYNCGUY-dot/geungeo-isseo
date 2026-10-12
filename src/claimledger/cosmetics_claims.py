"""Advertisement claims about functional cosmetics: extraction and the wording that may be confirmed.

Keyword cues only propose what a sentence is about. A claim can be confirmed only when the whole
sentence is one of a few allowlisted forms about whitening or wrinkle improvement, with no subject
other than the product itself: the official efficacy belongs to the product, not to an ingredient.
The medical and guarantee cues are a conservative development policy, not a legal determination.

A sentence that is neither a claim nor a recognized disclaimer is kept as unread text: nothing in
it was judged, and a confirmation is withheld while such text stands beside a recognized sentence.
A cue that stands before a denial, a caution to the reader or a question mark is set aside: Korean
puts what is denied before the denial, so that cue may be the thing denied.

Around a claim form a sentence may carry shop language: an invitation to use or buy the product,
or what the seller says about the page, the purchase and the delivery ("…제품으로 저녁 루틴을
마무리해 보세요", "드디어 입고된 …"). Such text is read word by word against a closed vocabulary
that has no number, target, condition, comparison, denial or effect word in it; one word outside it
leaves the sentence unread. A sentence made only of that vocabulary and ending in one of its
predicates is a neutral sentence: it is read, claims nothing, and does not withhold a confirmation
beside it.
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from typing import Literal, NamedTuple

from pydantic import BaseModel

from claimledger.claims_v1 import ExpressionStrength, _literal, _sentence_spans
from claimledger.cosmetics_official import CosmeticFunction
from claimledger.official_v2 import _compact

COSMETIC_CLAIM_VERSION = "cosmetic-claim-v1.3"
# The sentence splitter is quadratic on long runs of one character.
MAX_AD_TEXT_LENGTH = 5000

# Cues on whitespace-free NFKC, casefolded text. A wrinkle cue after "입술" is the lip function,
# and "선크림" inside "주름개선크림" is not a sunscreen.
_FUNCTION_CUES: tuple[tuple[CosmeticFunction, re.Pattern[str]], ...] = (
    (CosmeticFunction.WHITENING, re.compile(r"미백|화이트닝|멜라닌|기미|주근깨")),
    (CosmeticFunction.WRINKLE, re.compile(r"(?<!입술)(?<!입술의)주름|링클")),
    (CosmeticFunction.LIP_WRINKLE, re.compile(r"입술(?:의)?주름")),
    (CosmeticFunction.SUNSCREEN, re.compile(r"자외선|spf|(?<!개)선크림|(?<!개)선블록|썬크림|썬블록")),
    (CosmeticFunction.HAIR_DYE, re.compile(r"염모|염색")),
    (CosmeticFunction.HAIR_BLEACH, re.compile(r"탈색")),
    (CosmeticFunction.HAIR_REMOVAL, re.compile(r"제모")),
    (CosmeticFunction.HAIR_LOSS, re.compile(r"탈모")),
    (CosmeticFunction.ACNE, re.compile(r"여드름")),
    (CosmeticFunction.SKIN_BARRIER, re.compile(r"피부장벽|가려움")),
    (CosmeticFunction.STRETCH_MARK, re.compile(r"튼살")),
)
# Words with an everyday sense count only in their medical or absolute one: "저자극 처방" is a
# formulation, "재생 플라스틱" a material, "링클 필러 크림" a product type, "부작용이 있으면" a caution,
# "향이 좋아요" a liking, and "즉시 흡수" is not an effect.
_PRESCRIBER = r"(?:의사|전문의|피부과|병원|의원|약사|약국|한의사|한의원)"
_REGROWN = r"(?:피부|세포|진피|조직|상처|모발|모근|콜라겐)"
# "개선" is a strength only as a verb: "주름개선" and "주름 개선 효과" name the function.
_VERBAL = (
    r"(?:합니다|한다|해요|해줍|해주|해드|해서|했|하는|하고|하며|하여|하세요"
    r"|됩니다|된다|돼요|됐|되는|되고|되며|되어|시켜|시킵|시키)"
)
_STRENGTH_CUES: tuple[tuple[ExpressionStrength, re.Pattern[str]], ...] = (
    (
        ExpressionStrength.TREATMENT_PREVENTION,
        re.compile(
            r"치료|완치|특효|낫게|낫는|낫습|질병|질환|항염|염증|아토피|피부염|습진|건선|흉터"
            r"|약효|보톡스|시술|필러(?:를|을)?(?:맞|시술|주사|효과|대신)"
            rf"|{_PRESCRIBER}(?:의|가|이|에서)?처방|처방받"
            rf"|{_REGROWN}(?:의|을|를)?재생|재생(?:크림|효과|력|케어|시켜|시킵|시키)"
        ),
    ),
    (
        ExpressionStrength.GUARANTEE,
        re.compile(
            r"보장|100%|100퍼|백퍼|확실|반드시|무조건|완벽|단번에|하루만에|기적|영구"
            r"|\d+(?:일|주|개월)만에|부작용(?:이|은|도|걱정)?(?:전혀|하나도|일절)?(?:없|제로)|무부작용"
        ),
    ),
    (ExpressionStrength.SUPPORT, re.compile(r"도움|기능성")),
    (
        ExpressionStrength.IMPROVEMENT,
        re.compile(
            rf"개선(?={_VERBAL})|향상|좋아(?:지|집|져|졌)|회복|되살|강화|해결|해소|없애|사라지|사라집|제거"
            r"|지워|펴주|펴줍|펴집|하얗게|하얘|밝아|환해|엷게|옅게|완화|줄여|줄어|감소"
        ),
    ),
    (ExpressionStrength.POSSIBILITY, re.compile(r"수있")),
)
_STRONG = frozenset({
    ExpressionStrength.IMPROVEMENT, ExpressionStrength.GUARANTEE, ExpressionStrength.TREATMENT_PREVENTION,
})

# A denial ("아닙니다", "않는", "없는", "못합니다"), a prohibition or caution to the reader ("마세요",
# "사용을 중지", "상담", "…이 있는 부위") or a question mark. A cue before one of these is not asserted.
# "없애다" and "없어지다" are effects, not denials.
_NON_ASSERTION = re.compile(
    r"\?"
    r"|않|아니|아닌|아닙|아님|못(?:하|해|한|함|합)|없(?!애|앨|앱|앴|어지|어집|어져|어졌)"
    r"|말것|마세요|마십시오|금지|다릅니다|달라요|다르다"
    r"|사용을?(?:중지|중단|자제|삼가|피하|피해)|피해주|피하세|피하십|상담|상의"
    r"|있(?:는|으신|을)(?:분|경우|부위)|있으면|생기면"
)
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
_CATEGORY = r"기능성(?:화장품|제품)?"
_COPULA = r"(?:입니다|이에요|예요)"
# "…에 도움을 주는 제품": the claim describes the product named after it.
_DESCRIBES = r"에도움(?:을(?:주는|줄수있는|드리는|드릴수있는)|이(?:되는|될수있는))"
_PRODUCT = (
    r",?(?:매일(?:쓰는|사용하는|바르는))?(?:이|본)?(?:기능성|데일리|스킨케어|기초|케어)*"
    r"(?:제품|화장품|상품|아이템|크림|세럼|에센스|앰플|로션|토너|마스크팩)"
)
# What may join the product to shop language after it. Not "과", "보다", "만", "처럼": those bring in
# another product, a comparison or an exclusion. The last three are about the reader, not the effect.
_LINK = (
    rf"(?:{_COPULA},|,|으로|로|을|를|은|는|이|가|에|의|도|이라서|라서|이라|라|이니|니"
    r"|(?:이|가)(?:필요하|궁금하)(?:다면|시다면|셨다면)"
    r"|(?:을|를)(?:찾으신다면|찾는다면|찾고계신다면|찾고계셨다면|찾고있다면|찾으셨다면)"
    r"|에관심이있(?:으시)?다면)?"
)
# A complete claim that shop language may follow after a comma.
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
    *_forms(rf"{_CATEGORY}{_COPULA}?", counted=True),
    *_forms(rf"{_DESCRIBES}{_PRODUCT}{_COPULA}?"),
)
_NAMED_OPENING = (
    *_forms(rf"{_DESCRIBES}{_PRODUCT}{_LINK}"),
    *_forms(rf"기능성(?:화장품|제품){_LINK}", counted=True),
)
_STATED_WHOLE = _forms(_HELP)
_STATED_OPENING = _forms(_STATED)

# The closed vocabulary of shop language: what a seller says around a claim about buying, the page,
# delivery and daily use. It holds no number, body part, skin type, effect, degree of effect,
# condition on the effect, comparison, denial or third-party endorsement. Every entry is written
# without spaces; up to three adjacent words are tried run together, so spacing does not matter.
_NOUN_WORDS = (
    # the product
    "제품", "화장품", "기능성", "상품", "아이템", "필수템", "추천템", "신상", "신제품", "새상품",
    # care and routine
    "스킨케어", "케어", "피부관리", "관리", "루틴", "습관", "일상", "하루", "아침", "저녁", "밤", "데일리",
    "단계", "마무리", "시작", "준비", "기초", "사용", "사용방법", "보관", "보관방법", "방법",
    "장바구니", "화장대", "파우치", "선반",
    # the page
    "상세페이지", "상세설명", "상세정보", "상세안내", "상세", "페이지", "설명", "안내문", "안내", "정보", "내용",
    "사진", "이미지", "영상", "소개글", "소개", "글", "이야기", "소식", "목록", "링크", "버튼", "댓글", "문의",
    # buying and delivery
    "구매", "주문서", "주문", "결제", "무료배송", "배송", "선물세트", "선물", "포장", "세트", "사은품", "쿠폰",
    "적립금", "혜택", "이벤트", "세일", "특가", "행사", "입고", "입점", "출시", "오픈",
    "매장", "온라인", "오프라인", "상점", "코너", "채널", "라이브방송", "라이브", "고객센터",
    "쇼핑몰", "공식몰", "홈페이지", "기획전", "게시판", "위시리스트", "재고", "샘플", "회원", "포인트", "상자",
    "선물상자", "서랍", "진열대", "배너", "알림", "신청", "완료",
    "여기", "이곳", "아래", "하단",
    # the reader
    "많은관심", "관심", "취향", "마음", "선택", "기회", "순간", "후기", "리뷰",
)
_NOUN = "|".join(_NOUN_WORDS)
_PARTICLE = r"(?:을|를|이|가|은|는|에|에서|으로|로|의|부터|도|까지|과|와)"
_MODIFIER_WORDS = (
    "지금바로", "지금", "바로", "오늘부터", "오늘의", "오늘", "이번에", "이번", "매일매일", "매일", "꾸준히", "꾸준한",
    "간편한", "간편하게", "가볍게", "편하게", "쉽게", "꼼꼼하게", "꼼꼼한", "천천히", "찬찬히", "자세히", "자세한",
    "직접", "한번", "한단계더", "더", "이", "그", "마지막", "첫", "나만의", "새로", "새롭게", "드디어", "다시", "꼭",
    "먼저", "함께", "마음껏", "정성껏", "미리", "이제", "요즘", "언제든지", "언제든", "전에", "전",
    "고객님께", "고객님에게", "여러분께",
    # about the reader, not about the effect
    "마음에드셨다면", "마음에드신다면", "마음에든다면", "궁금하다면", "궁금하시다면", "궁금하셨다면",
    "필요하다면", "필요하시다면", "필요할때",
)
_MODIFIER = "|".join(_MODIFIER_WORDS)
_ITEM = re.compile(rf"(?:(?:{_NOUN}){{1,3}}{_PARTICLE}?|{_MODIFIER}),?")
_BARE_NOUN = re.compile(rf"(?:{_NOUN}){{1,3}}")
# Shop language ends in one of these: an invitation, what the seller does, or a noun with a copula.
_ACT = (
    "써|사용해|발라|만나|경험해|시작해|마무리해|완성해|담아|더해|챙겨|만들어|준비해|관리해|신경써|확인해|살펴"
    "|눈여겨|읽어|참고해|구매해|주문해|저장해|공유해|찜해|올려|떠올려|눌러|열어|펼쳐|넣어|받아|남겨|둘러"
    "|구경해|들러|방문해|문의해|물어|꺼내|채워|추가해|둘러보고|살펴보고|구경하고"
)
_PREDICATE = re.compile(
    rf"(?:{_ACT})(?:보세요|보십시오|봐요|주세요|주십시오|두세요|가세요|봤어요|봤습니다|뒀어요|두었어요"
    r"|보실수있습니다|보실수있어요)"
    r"|(?:시작|마무리|완성|준비|관리|사용|추천|경험|확인|참고|구매|주문|저장|공유|소개|안내|문의|방문|구경|추가|결제|선물)"
    r"(?:하세요|하십시오|해요|합니다|해주세요|해드립니다|해드려요|해드릴게요|해보세요)"
    r"|(?:준비|구매|주문|저장|추가|결제)(?:했습니다|했어요)"
    r"|추천드립니다|추천드려요|권합니다|권해요|만나세요|담으세요|더하세요|챙기세요|선보입니다|선보여요"
    r"|모았습니다|모았어요|기다립니다|기다려요|환영합니다|부탁드립니다|드립니다|드려요|드릴게요"
    r"|알려드립니다|알려드려요|알려드릴게요|보내드립니다|보내드려요|알맞습니다|알맞아요|어울립니다|어울려요"
    r"|입고되었습니다|입고됐습니다|입고됐어요|도착했습니다|도착했어요|들어왔습니다|들어왔어요|들여왔습니다"
    r"|들여왔어요|등록되었습니다|올라왔어요|있습니다|있어요|판매합니다|판매중입니다|판매중|진행중입니다"
    r"|행사중입니다|재입고되었습니다|재입고됐습니다|재입고됐어요|가능합니다|가능해요|오세요|보러오세요"
    r"|구경하러오세요|놀러오세요|만나요|둘러보세요|살펴보세요|서두르세요|열렸습니다|열렸어요"
    r"|오픈했습니다|오픈했어요|준비해두었습니다|모아두었습니다"
    rf"|(?:{_NOUN}){{1,3}}(?:입니다|이에요|예요|이랍니다|랍니다)"
)
# How the product got to the shop, said before it: "드디어 입고된 …", "이 페이지에서 만나는 …".
_ARRIVED = re.compile(
    r"입고된|새로입고된|재입고된|준비한|들어온|새로나온|나온|올라온|소개할|소개하는|소개중인|만나는"
    r"|만나보실수있는|선보이는|출시된|등록된|도착한|판매중인|행사중인|진행중인"
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
    extraction_version: Literal["cosmetic-claim-v1.3"] = COSMETIC_CLAIM_VERSION


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


def normalize_ad_text(text: str) -> str:
    """Drop a leading byte order mark and compose decomposed Hangul (NFD); spans index the result."""
    return unicodedata.normalize("NFC", text.removeprefix("\ufeff"))


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


def _item_ends(words: Sequence[str]) -> list[bool]:
    """For each length, whether that many leading words are vocabulary items; linear in the words."""
    ends = [True] + [False] * len(words)
    for start in range(len(words)):
        if ends[start]:
            for size in (1, 2, 3):
                if start + size <= len(words) and _ITEM.fullmatch("".join(words[start : start + size])):
                    ends[start + size] = True
    return ends


def _closes(words: Sequence[str], pattern: re.Pattern[str], sizes: Sequence[int]) -> bool:
    """Whether the words are vocabulary items and then the pattern over their last few words."""
    ends = _item_ends(words)
    return any(
        size <= len(words) and ends[len(words) - size] and pattern.fullmatch("".join(words[-size:]))
        for size in sizes
    )


def _invites(words: Sequence[str]) -> bool:
    """Whether the words are shop language that ends in a predicate, in the closed vocabulary only."""
    return _closes(words, _PREDICATE, (1, 2, 3, 4))


def _follows(words: Sequence[str]) -> bool:
    """Whether the words may follow a product: shop language ending in a predicate or a noun."""
    return _invites(words) or _closes(words, _BARE_NOUN, (1, 2, 3))


def _asserted(sentence: str) -> frozenset[CosmeticFunction] | None:
    words = _words(sentence)
    stated = _matched((*_STATED_WHOLE, *_NAMED_WHOLE), "".join(words))
    if stated is not None or not 1 < len(words) <= _MAX_WORDS:
        return stated
    for start in range(min(len(words), _MAX_LEAD_WORDS + 1)):
        lead = words[:start]
        # Before the claim: nothing, shop language closed by a comma, or how the product arrived.
        after_comma = bool(lead) and lead[-1].endswith(",") and _invites([*lead[:-1], lead[-1][:-1]])
        arrived = bool(lead) and _closes(lead, _ARRIVED, (1, 2))
        if lead and not after_comma and not arrived:
            continue
        whole = _NAMED_WHOLE if arrived else (*_STATED_WHOLE, *_NAMED_WHOLE)
        opening = _NAMED_OPENING if arrived else (*_STATED_OPENING, *_NAMED_OPENING)
        for end in range(start + 1, min(len(words), start + _MAX_CORE_WORDS) + 1):
            core, rest = "".join(words[start:end]), words[end:]
            found = _matched(opening, core) if rest else _matched(whole, core)
            if found is not None and (not rest or _follows(rest)):
                return found
    return None


def _neutral(sentence: str) -> bool:
    words = _words(sentence)
    return 0 < len(words) <= _MAX_WORDS and _invites(words)


def asserted_functions(claim: CosmeticClaim) -> frozenset[CosmeticFunction] | None:
    """Functions asserted by a fully recognized sentence, or None when any part of it is unread."""
    return _asserted(claim.text)


def _classify(sentence: str) -> _Reading:
    compact, positions = _compact(sentence)
    function_matches = [
        (function, match) for function, pattern in _FUNCTION_CUES for match in pattern.finditer(compact)
    ]
    strength_matches = [
        (level, match) for level, pattern in _STRENGTH_CUES for match in pattern.finditer(compact)
    ]
    cue_spans = [match.span() for _, match in (*function_matches, *strength_matches)]
    # A denial inside a cue ("부작용 없는") belongs to that cue.
    markers = [
        marker.start() for marker in _NON_ASSERTION.finditer(compact)
        if not any(start < marker.end() and marker.start() < end for start, end in cue_spans)
    ]
    last_marker = max(markers, default=-1)

    def asserted(match: re.Match[str]) -> bool:
        return match.end() > last_marker

    functions = {function for function, match in function_matches if asserted(match)}
    function_cues = [_literal(sentence, positions, match) for _, match in function_matches if asserted(match)]
    strength: ExpressionStrength | None = None
    strength_cues: list[str] = []
    for level, _ in _STRENGTH_CUES:
        found = [match for candidate, match in strength_matches if candidate is level and asserted(match)]
        if found:
            strength, strength_cues = level, [_literal(sentence, positions, match) for match in found]
            break
    denied = [
        (match.start(), _literal(sentence, positions, match), kind)
        for kind, match in (*function_matches, *strength_matches) if not asserted(match)
    ]
    return _Reading(
        functions=tuple(function for function in CosmeticFunction if function in functions),
        function_cues=tuple(dict.fromkeys(function_cues)),
        strength=strength,
        strength_cues=tuple(strength_cues),
        set_aside=tuple(dict.fromkeys(literal for _, literal, _ in sorted(denied, key=lambda item: item[0]))),
        substance_set_aside=any(isinstance(kind, CosmeticFunction) or kind in _STRONG for _, _, kind in denied),
    )


def _read(
    text: str,
) -> tuple[tuple[CosmeticClaim, ...], tuple[UnreadSentence, ...], tuple[NeutralSentence, ...]]:
    text = normalize_ad_text(text)
    if len(text) > MAX_AD_TEXT_LENGTH:
        raise ValueError(f"the advertisement text is longer than {MAX_AD_TEXT_LENGTH} characters")
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
    "neutral_sentences",
    "normalize_ad_text",
    "unread_sentences",
]
