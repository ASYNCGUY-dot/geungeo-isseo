import re

from claimledger.domain import (
    OfficialFieldStatus,
    OfficialFunctionStatement,
    OfficialProductCaution,
    ProductCandidate,
)

FUNCTION_PARSER_VERSION = "official-function-v1"
CAUTION_PARSER_VERSION = "official-caution-v1"

# Semicolons and line breaks are the only reviewed separators. In particular, commas
# and middle dots can join terms within a single official statement and are not split.
_REVIEWED_DELIMITER = re.compile(r";|\r\n|\n")
_FUNCTION_VOCABULARY: dict[str, tuple[str, str]] = {
    "눈 건강에 도움을 줄 수 있음": ("eye_health_support", "support"),
    "혈중 중성지질 개선에 도움을 줄 수 있음": (
        "blood_triglyceride_improvement",
        "improvement",
    ),
    "혈행 개선에 도움을 줄 수 있음": ("blood_circulation_improvement", "improvement"),
    "건조한 눈을 개선하여 눈 건강에 도움을 줄 수 있음": (
        "dry_eye_health_improvement",
        "improvement",
    ),
    "유산균 증식 및 유해균 억제에 도움을 줄 수 있음": (
        "intestinal_microbiota_support",
        "support",
    ),
    "배변활동 원활에 도움을 줄 수 있음": ("bowel_movement_support", "support"),
}
_CAUTION_MARKERS = (
    "섭취에 주의",
    "과다 섭취",
    "알레르기",
    "의약품 복용",
    "전문가와 상담",
    "이상 사례 발생",
)
_RAW_MATERIAL_CAUTION_MARKERS = (
    "난류 함유",
    "우유 함유",
    "대두 함유",
    "땅콩 함유",
    "알레르기",
)


def _split_reviewed_segments(source_text: str) -> tuple[str, ...] | None:
    segments = tuple(_REVIEWED_DELIMITER.split(source_text))
    if not segments or any(not segment.strip() for segment in segments):
        return None
    return segments


def parse_official_functions(product: ProductCandidate) -> tuple[OfficialFunctionStatement, ...]:
    source_text = product.primary_function
    if not source_text.strip():
        return (
            OfficialFunctionStatement(
                status=OfficialFieldStatus.MISSING,
                original_text=source_text,
                parser_version=FUNCTION_PARSER_VERSION,
            ),
        )

    segments = _split_reviewed_segments(source_text)
    if segments is None:
        return (
            OfficialFunctionStatement(
                status=OfficialFieldStatus.UNVERIFIABLE,
                original_text=source_text,
                parser_version=FUNCTION_PARSER_VERSION,
            ),
        )

    statements: list[OfficialFunctionStatement] = []
    for segment in segments:
        structured_meaning = _FUNCTION_VOCABULARY.get(segment)
        if structured_meaning is None:
            statements.append(
                OfficialFunctionStatement(
                    status=OfficialFieldStatus.UNVERIFIABLE,
                    original_text=segment,
                    parser_version=FUNCTION_PARSER_VERSION,
                )
            )
            continue
        effect_key, expression_strength = structured_meaning
        statements.append(
            OfficialFunctionStatement(
                status=OfficialFieldStatus.VERIFIED,
                original_text=segment,
                effect_key=effect_key,
                expression_strength=expression_strength,
                parser_version=FUNCTION_PARSER_VERSION,
            )
        )
    return tuple(statements)


def _caution_status(source_text: str) -> OfficialFieldStatus:
    if not source_text.strip():
        return OfficialFieldStatus.MISSING
    if any(marker in source_text for marker in _CAUTION_MARKERS):
        return OfficialFieldStatus.VERIFIED
    return OfficialFieldStatus.UNVERIFIABLE


def extract_official_cautions(product: ProductCandidate) -> tuple[OfficialProductCaution, ...]:
    source_text = product.intake_method
    segments = _split_reviewed_segments(source_text) if source_text.strip() else (source_text,)
    if segments is None:
        return (
            OfficialProductCaution(
                status=OfficialFieldStatus.UNVERIFIABLE,
                source_field="intake_method",
                original_text=source_text,
                parser_version=CAUTION_PARSER_VERSION,
            ),
        )
    cautions = [
        OfficialProductCaution(
            status=_caution_status(segment),
            source_field="intake_method",
            original_text=segment,
            parser_version=CAUTION_PARSER_VERSION,
        )
        for segment in segments
    ]
    if any(marker in product.raw_materials for marker in _RAW_MATERIAL_CAUTION_MARKERS):
        cautions.append(
            OfficialProductCaution(
                status=OfficialFieldStatus.VERIFIED,
                source_field="raw_materials",
                original_text=product.raw_materials,
                parser_version=CAUTION_PARSER_VERSION,
            )
        )
    return tuple(cautions)


__all__ = [
    "OfficialFieldStatus",
    "OfficialFunctionStatement",
    "OfficialProductCaution",
    "extract_official_cautions",
    "parse_official_functions",
]
