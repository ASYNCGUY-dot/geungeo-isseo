import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel

from claimledger.claims_v1 import CLAIM_EXTRACTION_VERSION, ExpressionStrength
from claimledger.domain import ConfirmedProduct, Verdict
from claimledger.official_v2 import OFFICIAL_FUNCTION_V2_VERSION, EffectKey
from claimledger.verdict_v1 import CLAIM_VERDICT_VERSION, ClaimDecision, VerdictReason

RECEIPT_VERSION = "receipt-v1"

PUBLIC_VERDICT_LABELS: dict[Verdict, str] = {
    Verdict.CONFIRMED: "확인됨",
    Verdict.MISMATCH: "근거 불일치",
    Verdict.INSUFFICIENT: "근거 부족",
    Verdict.UNVERIFIABLE: "검증 불가",
    Verdict.CONTRADICTED: "직접 반박됨",
}

REASON_MESSAGES: dict[VerdictReason, str] = {
    VerdictReason.PRODUCT_IDENTITY_UNCONFIRMED: "제품이 확정되지 않았습니다. 신고번호로 제품을 먼저 확인해야 판정할 수 있습니다.",
    VerdictReason.CLAIM_UNCONFIRMED: "이 주장을 판정 대상으로 확인하지 않았습니다.",
    VerdictReason.DISEASE_CLAIM_BEYOND_FUNCTIONAL_SCOPE: (
        "질병의 치료·예방을 말하는 표현입니다. 건강기능식품의 공식 기능성 문구는 이런 표현을 담지 않습니다."
    ),
    VerdictReason.CLAIM_OUTSIDE_RULE_SCOPE: "현재 규칙이 다루는 기능성(핵심 원료 3종의 공식 기능) 밖의 표현이라 판단하지 않았습니다.",
    VerdictReason.CLAIM_STRENGTH_UNCLEAR: "표현이 얼마나 강한지(도움인지, 개선 단정인지) 문장에서 확인되지 않았습니다.",
    VerdictReason.CLAIM_SCOPE_UNRESOLVED: (
        "일부 단어는 공식 문구와 맞지만 문장 전체의 기능·원료 주체·수식 범위를 확인할 수 없습니다. "
        "복합 주장이나 부정·질문·추가 조건을 임의로 해석하지 않고 보류했습니다."
    ),
    VerdictReason.OFFICIAL_FUNCTION_MISSING: "공식 기능성 원문이 비어 있어 대조할 수 없습니다.",
    VerdictReason.EFFECT_NOT_IN_OFFICIAL_FUNCTIONS: "이 제품의 공식 기능성 원문에 해당 기능이 없습니다.",
    VerdictReason.OFFICIAL_ATTRIBUTION_AMBIGUOUS: (
        "공식 원문에 비슷한 기능 문구는 있지만, 대상 원료에 붙은 문구인지 원문만으로 확정할 수 없습니다."
    ),
    VerdictReason.EXPRESSION_STRENGTH_EXCEEDS_OFFICIAL: (
        "공식 문구는 '도움을 줄 수 있음'인데, 광고는 그보다 단정적이거나 강하게 표현했습니다."
    ),
    VerdictReason.MATCHES_OFFICIAL_FUNCTION: "공식 기능성 원문의 해당 원료 문구와 같은 범위·강도로 표현했습니다.",
}

EFFECT_LABELS: dict[EffectKey, str] = {
    EffectKey.MACULAR_PIGMENT_EYE_HEALTH: "황반색소밀도 유지로 눈 건강",
    EffectKey.BLOOD_TRIGLYCERIDE: "혈중 중성지질 개선",
    EffectKey.BLOOD_CIRCULATION: "혈행 개선",
    EffectKey.MEMORY: "기억력 개선",
    EffectKey.DRY_EYE_EYE_HEALTH: "건조한 눈 개선으로 눈 건강",
    EffectKey.PROBIOTIC_GROWTH_HARMFUL_INHIBITION: "유산균 증식 및 유해균 억제",
    EffectKey.BOWEL_MOVEMENT: "배변활동 원활",
    EffectKey.GUT_HEALTH: "장 건강",
}

STRENGTH_LABELS: dict[ExpressionStrength, str] = {
    ExpressionStrength.POSSIBILITY: "가능성",
    ExpressionStrength.SUPPORT: "도움",
    ExpressionStrength.IMPROVEMENT: "개선 단정",
    ExpressionStrength.GUARANTEE: "보장",
    ExpressionStrength.TREATMENT_PREVENTION: "치료·예방",
}

LIMITATIONS: tuple[str, ...] = (
    "공식 기능성 인정 범위와의 일치만 확인합니다. 효과, 안전, 개인에게 맞는지, 광고의 적법성은 판단하지 않습니다.",
    "과학 논문 근거는 이 버전에서 검토하지 않았습니다. 그래서 '근거 부족'과 '직접 반박됨' 판정은 만들지 않습니다.",
    "지원 원료는 루테인·지아잔틴, 오메가3, 프로바이오틱스의 공식 기능성뿐입니다.",
    "공식 정보는 C003 스냅샷의 조회 시각 기준입니다. 이후 신고 내용 변경은 반영되지 않았을 수 있습니다.",
    "광고 원문은 사용자가 입력한 텍스트이며, 광고 전체를 수집했다는 보장이 없습니다.",
)


class ReceiptProduct(BaseModel):
    model_config = {"frozen": True}

    report_no: str
    name: str
    company: str
    source_id: str
    retrieved_at: datetime


class ReceiptOfficialQuote(BaseModel):
    model_config = {"frozen": True}

    header: str | None
    statement_text: str
    statement_span: tuple[int, int]
    matched_text: str


class ReceiptClaim(BaseModel):
    model_config = {"frozen": True}

    claim_id: str
    ad_text: str
    ad_span: tuple[int, int]
    effect_candidates: tuple[EffectKey, ...]
    strength: ExpressionStrength | None
    verdict: Verdict
    verdict_label: str
    reason_code: VerdictReason
    reason_message: str
    official_quote: ReceiptOfficialQuote | None


class Receipt(BaseModel):
    model_config = {"frozen": True}

    receipt_version: Literal["receipt-v1"] = RECEIPT_VERSION
    generated_at: AwareDatetime
    ad_text: str
    ad_text_sha256: str
    product: ReceiptProduct | None
    claims: tuple[ReceiptClaim, ...]
    verdict_counts: dict[str, int]
    rule_versions: tuple[str, ...]
    limitations: tuple[str, ...]


def _receipt_claim(decision: ClaimDecision) -> ReceiptClaim:
    official = decision.official_effect
    quote = (
        ReceiptOfficialQuote(
            header=official.block_header,
            statement_text=official.statement_text,
            statement_span=official.statement_span,
            matched_text=official.matched_text,
        )
        if official is not None
        else None
    )
    return ReceiptClaim(
        claim_id=decision.claim.claim_id,
        ad_text=decision.claim.text,
        ad_span=decision.claim.span,
        effect_candidates=decision.claim.effect_candidates,
        strength=decision.claim.strength,
        verdict=decision.verdict,
        verdict_label=PUBLIC_VERDICT_LABELS[decision.verdict],
        reason_code=decision.reason,
        reason_message=REASON_MESSAGES[decision.reason],
        official_quote=quote,
    )


def build_receipt(
    ad_text: str,
    product: ConfirmedProduct | None,
    decisions: Sequence[ClaimDecision],
    generated_at: datetime,
) -> Receipt:
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must include a timezone")
    for decision in decisions:
        start, end = decision.claim.span
        if ad_text[start:end] != decision.claim.text:
            raise ValueError(f"claim text does not match the advertisement: {decision.claim.claim_id}")
    receipt_product = (
        ReceiptProduct(
            report_no=product.product.report_no,
            name=product.product.name,
            company=product.product.company,
            source_id=product.product.source_id,
            retrieved_at=product.product.retrieved_at,
        )
        if product is not None
        else None
    )
    counts = Counter(decision.verdict.value for decision in decisions)
    return Receipt(
        generated_at=generated_at,
        ad_text=ad_text,
        ad_text_sha256=hashlib.sha256(ad_text.encode("utf-8")).hexdigest(),
        product=receipt_product,
        claims=tuple(_receipt_claim(decision) for decision in decisions),
        verdict_counts=dict(sorted(counts.items())),
        rule_versions=(CLAIM_EXTRACTION_VERSION, OFFICIAL_FUNCTION_V2_VERSION, CLAIM_VERDICT_VERSION),
        limitations=LIMITATIONS,
    )


def receipt_to_json(receipt: Receipt) -> str:
    return json.dumps(receipt.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_markdown(receipt: Receipt) -> str:
    lines = ["# 근거영수증", ""]
    if receipt.product is None:
        lines.append("- 제품: 제품이 확정되지 않았습니다. 제품 수준 판정을 하지 않았습니다.")
    else:
        product = receipt.product
        lines += [
            f"- 제품: {product.name} ({product.company})",
            f"- 신고번호: {product.report_no}",
            f"- 공식 정보: {product.source_id} 건강기능식품 품목제조신고, 조회 시각 {product.retrieved_at.isoformat()}",
        ]
    lines += [
        f"- 광고 원문 SHA-256: `{receipt.ad_text_sha256}`",
        f"- 생성 시각: {receipt.generated_at.isoformat()}",
        f"- 규칙 버전: {', '.join(receipt.rule_versions)}",
        "",
        "## 주장별 결과",
        "",
    ]
    if not receipt.claims:
        lines += ["판정할 주장을 찾지 못했습니다.", ""]
    for claim in receipt.claims:
        effects = ", ".join(EFFECT_LABELS[effect] for effect in claim.effect_candidates) or "규칙 밖"
        strength = STRENGTH_LABELS[claim.strength] if claim.strength is not None else "확인 안 됨"
        lines += [
            f"### {claim.claim_id} · {claim.verdict_label}",
            "",
            f"> {claim.ad_text}",
            "",
            f"- 이유: {claim.reason_message}",
            f"- 읽은 기능: {effects} / 표현 강도: {strength}",
        ]
        if claim.official_quote is not None:
            header = f"[{claim.official_quote.header}] " if claim.official_quote.header else ""
            lines.append(f"- 공식 기능성 원문: {header}\"{claim.official_quote.statement_text}\"")
        lines.append("")
    lines += ["## 이 영수증의 한계", ""]
    lines += [f"- {item}" for item in receipt.limitations]
    return "\n".join(lines) + "\n"


__all__ = [
    "EFFECT_LABELS",
    "LIMITATIONS",
    "PUBLIC_VERDICT_LABELS",
    "REASON_MESSAGES",
    "RECEIPT_VERSION",
    "Receipt",
    "ReceiptClaim",
    "ReceiptOfficialQuote",
    "ReceiptProduct",
    "build_receipt",
    "receipt_to_json",
    "render_markdown",
]
