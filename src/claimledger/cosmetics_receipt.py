"""Evidence receipt for claims about a confirmed functional cosmetic.

Each claim keeps its verdict, the reason, the words the rules reacted to, the official sentences
that support a confirmation, the official source and retrieval time, and the rule versions that
produced the verdict. The record's official wording and the sentences that were not judged are
shown whatever the verdicts are.
"""

from datetime import datetime

from pydantic import AwareDatetime, BaseModel

from claimledger.claims_v1 import ExpressionStrength
from claimledger.cosmetics_claims import COSMETIC_CLAIM_VERSION, normalize_ad_text, unread_sentences
from claimledger.cosmetics_official import COSMETIC_EFFICACY_VERSION, CosmeticFunction
from claimledger.cosmetics_verdict import (
    COSMETIC_VERDICT_VERSION,
    ConfirmedCosmetic,
    CosmeticDecision,
    CosmeticVerdictReason,
    decide_cosmetic_ad,
)
from claimledger.domain import Verdict
from claimledger.receipt import PUBLIC_VERDICT_LABELS, STRENGTH_LABELS

COSMETIC_FUNCTION_LABELS: dict[CosmeticFunction, str] = {
    CosmeticFunction.WHITENING: "피부 미백",
    CosmeticFunction.WRINKLE: "피부 주름개선",
    CosmeticFunction.LIP_WRINKLE: "입술 주름개선",
    CosmeticFunction.SUNSCREEN: "자외선 차단",
    CosmeticFunction.HAIR_DYE: "모발 염모",
    CosmeticFunction.HAIR_BLEACH: "모발 탈색",
    CosmeticFunction.HAIR_REMOVAL: "제모",
    CosmeticFunction.HAIR_LOSS: "탈모 증상 완화",
    CosmeticFunction.ACNE: "여드름성 피부 완화",
    CosmeticFunction.SKIN_BARRIER: "피부장벽·가려움 개선",
    CosmeticFunction.STRETCH_MARK: "튼살 붉은 선 완화",
    CosmeticFunction.DYE_OXIDANT: "염모·탈색 산화제",
    CosmeticFunction.DYE_OXIDANT_AID: "염모·탈색 산화보조제",
}
COSMETIC_REASON_MESSAGES: dict[CosmeticVerdictReason, str] = {
    CosmeticVerdictReason.PRODUCT_IDENTITY_UNCONFIRMED: "제품이 확정되지 않았습니다.",
    CosmeticVerdictReason.CLAIM_UNCONFIRMED: "사용자가 확인하지 않은 주장입니다.",
    CosmeticVerdictReason.CLAIM_NOT_PLAINLY_ASSERTED: (
        "효과를 나타내는 단어가 부정·금지·주의 표현이나 물음표 앞에 있어, 그 효과를 주장한 것으로 보지 않았습니다."
    ),
    CosmeticVerdictReason.MEDICAL_CLAIM_BEYOND_COSMETIC_SCOPE: (
        "질병 치료나 의료 시술의 효과처럼 읽히는 표현입니다. 화장품의 공식 효능효과는 이런 표현을 담지 않습니다."
    ),
    CosmeticVerdictReason.CLAIM_OUTSIDE_RULE_SCOPE: (
        "판정 규칙이 다루는 기능(미백, 주름개선)에 해당하는 주장을 찾지 못했습니다."
    ),
    CosmeticVerdictReason.FUNCTION_RULE_NOT_READY: (
        "이 기능은 아직 판정 규칙이 없습니다. 현재는 미백과 주름개선만 판정합니다."
    ),
    CosmeticVerdictReason.CLAIM_STRENGTH_UNCLEAR: "효과를 어느 정도로 말하는지 읽을 수 없습니다.",
    CosmeticVerdictReason.OFFICIAL_RECORD_WITHDRAWN: (
        "공식 기록에 취소·취하 표시가 있어 이 기록의 효능효과를 근거로 쓰지 않았습니다."
    ),
    CosmeticVerdictReason.OFFICIAL_EFFICACY_MISSING: "이 제품 기록에는 공식 효능효과 문구가 없습니다.",
    CosmeticVerdictReason.OFFICIAL_EFFICACY_TEMPLATE_REMNANT: (
        "공식 문서에 작성 양식의 안내 문구가 남아 있어, 적힌 효능효과를 근거로 쓸 수 없습니다."
    ),
    CosmeticVerdictReason.OFFICIAL_EFFICACY_CONFLICTING: (
        "공식 기록의 효능효과 항목이 서로 달라 근거로 쓸 수 없습니다."
    ),
    CosmeticVerdictReason.OFFICIAL_EFFICACY_UNRECOGNIZED: (
        "공식 효능효과 문구를 규칙이 끝까지 읽지 못해 근거로 쓰지 않았습니다."
    ),
    CosmeticVerdictReason.FUNCTION_NOT_IN_OFFICIAL_EFFICACY: (
        "이 제품의 공식 효능효과에 없는 기능을 말하고 있습니다."
    ),
    CosmeticVerdictReason.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL: (
        "공식 효능효과('도움을 준다')보다 강한 표현입니다."
    ),
    CosmeticVerdictReason.CLAIM_SCOPE_UNRESOLVED: (
        "미백·주름개선에 관한 단어는 있지만 문장 전체가 무엇을 주장하는지(주체·조건·범위) 규칙으로 확정할 수 없어 보류했습니다."
    ),
    CosmeticVerdictReason.AD_TEXT_NOT_FULLY_READ: (
        "이 문장만 보면 공식 효능효과와 같은 표현입니다. 다만 같은 광고문에 규칙이 끝까지 읽지 못한 문장이 있어 "
        "앞뒤 문장이 뜻을 바꾸는지 확인할 수 없으므로 확인됨으로 표시하지 않았습니다."
    ),
    CosmeticVerdictReason.MATCHES_OFFICIAL_EFFICACY: "공식 효능효과와 같은 범위·강도로 표현했습니다.",
}
COSMETIC_LIMITATIONS: tuple[str, ...] = (
    "이 결과는 광고 사전점검이며 공식 심의 통과나 법적 판단이 아닙니다.",
    "식약처에 보고·심사된 기능성화장품의 공식 효능효과와만 대조합니다. 목록에 없는 일반 화장품은 확인할 수 없습니다.",
    "미백과 주름개선 주장만 판정합니다. 자외선 차단 등 다른 기능은 아직 판정하지 않습니다.",
    (
        "문장 단위로 판정합니다. 정해진 문형이나 의약품이 아니라는 고지 문구로 끝까지 읽지 못한 문장이 광고문에 "
        "하나라도 있으면, 그 문장이 근거 불일치로 판정됐더라도 다른 문장을 확인됨으로 표시하지 않습니다. "
        "주장으로 읽지 않은 문장은 따로 보여 줍니다."
    ),
    (
        "근거 불일치는 문장에 들어 있는 단어를 보고 판정합니다. 그 단어가 다른 것을 꾸미는 문장에서는 틀릴 수 있어 "
        "판정에 쓴 단어를 함께 보여 줍니다. 부정·주의 표현이나 물음표 앞의 단어는 판정에 쓰지 않습니다."
    ),
    "성분의 함량·안전성과 개인 피부에 대한 효과는 판단하지 않습니다.",
    "제품은 사용자가 확정한 기록 기준입니다. 같은 이름의 다른 보고 기록이 있을 수 있습니다.",
)


class CosmeticReceiptProduct(BaseModel):
    model_config = {"frozen": True}

    record_id: str
    item_name: str
    company: str
    registered_on: str
    source_id: str
    retrieved_at: AwareDatetime
    official_statement: str


class CosmeticReceiptClaim(BaseModel):
    model_config = {"frozen": True}

    claim_id: str
    ad_text: str
    verdict: Verdict
    verdict_label: str
    reason_code: CosmeticVerdictReason
    reason_message: str
    functions: tuple[str, ...]
    function_cues: tuple[str, ...]
    strength: ExpressionStrength | None
    strength_label: str | None
    strength_cues: tuple[str, ...]
    set_aside_cues: tuple[str, ...]
    official_quotes: tuple[str, ...]


class CosmeticReceipt(BaseModel):
    model_config = {"frozen": True}

    product: CosmeticReceiptProduct
    ad_text: str
    claims: tuple[CosmeticReceiptClaim, ...]
    unread_text: tuple[str, ...]
    rule_versions: tuple[str, ...]
    generated_at: AwareDatetime
    limitations: tuple[str, ...]


def build_cosmetic_receipt(
    ad_text: str,
    product: ConfirmedCosmetic,
    decisions: tuple[CosmeticDecision, ...] | list[CosmeticDecision],
    generated_at: datetime,
) -> CosmeticReceipt:
    row = product.product
    ad_text = normalize_ad_text(ad_text)
    decisions = tuple(decisions)
    if decisions != decide_cosmetic_ad(ad_text, [decision.claim for decision in decisions], product):
        raise ValueError("the decisions are not the ones made for this advertisement text and product")
    return CosmeticReceipt(
        product=CosmeticReceiptProduct(
            record_id=row.record_id, item_name=row.item_name, company=row.company,
            registered_on=row.registered_on, source_id=row.source_id, retrieved_at=row.retrieved_at,
            official_statement=row.statement,
        ),
        ad_text=ad_text,
        claims=tuple(
            CosmeticReceiptClaim(
                claim_id=decision.claim.claim_id,
                ad_text=decision.claim.text,
                verdict=decision.verdict,
                verdict_label=PUBLIC_VERDICT_LABELS[decision.verdict],
                reason_code=decision.reason,
                reason_message=COSMETIC_REASON_MESSAGES[decision.reason],
                functions=tuple(COSMETIC_FUNCTION_LABELS[item] for item in decision.claim.function_candidates),
                function_cues=decision.claim.function_cues,
                strength=decision.claim.strength,
                strength_label=STRENGTH_LABELS[decision.claim.strength] if decision.claim.strength else None,
                strength_cues=decision.claim.strength_cues,
                set_aside_cues=decision.claim.set_aside_cues,
                official_quotes=tuple(sentence.text for sentence in decision.official_sentences),
            )
            for decision in decisions
        ),
        unread_text=tuple(sentence.text for sentence in unread_sentences(ad_text)),
        rule_versions=(COSMETIC_CLAIM_VERSION, COSMETIC_EFFICACY_VERSION, COSMETIC_VERDICT_VERSION),
        generated_at=generated_at,
        limitations=COSMETIC_LIMITATIONS,
    )


__all__ = [
    "COSMETIC_FUNCTION_LABELS",
    "COSMETIC_LIMITATIONS",
    "COSMETIC_REASON_MESSAGES",
    "CosmeticReceipt",
    "CosmeticReceiptClaim",
    "CosmeticReceiptProduct",
    "build_cosmetic_receipt",
]
