import re
import unicodedata
from datetime import date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from claimledger.domain import ExtensionReviewProduct, IngredientGroup, NonBlankText
from claimledger.extension_selection import COMPARISON_GROUPS

FUNCTIONAL_ROLE_RULE_CONTRACT_VERSION = "functional-role-rules-v1"
FUNCTIONAL_ROLE_RULE_VERSION = "functional-role-rule-v1"
ROLE_RULE_MAX_AGE_DAYS = 7

_SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_OFFICIAL_SOURCE_HOSTS = (
    "mfds.go.kr",
    "foodsafetykorea.go.kr",
    "law.go.kr",
)
_SECRET_PATTERNS = (
    re.compile(r"\b(?:OPENAI|FOOD_?SAFETY|TAVILY|ANTHROPIC)_API_KEY\b", re.IGNORECASE),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(
        r'''["']?(?:api[_-]?key|access[_-]?token|client[_-]?secret)["']?'''
        r'''\s*[:=]\s*["']?(?!redacted\b|placeholder\b|dummy\b|test\b)'''
        r"[A-Za-z0-9_./+=-]{8,}",
        re.IGNORECASE,
    ),
)


class FunctionalRoleRuleStatus(StrEnum):
    ACTIVE = "active"
    PROPOSED = "proposed"
    EXPIRED = "expired"


class MachineRoleVerdict(StrEnum):
    FUNCTIONAL_CONFIRMED = "functional_confirmed"
    PRESENT_NONFUNCTIONAL = "present_nonfunctional"
    UNVERIFIABLE = "unverifiable"


class MachineRoleReasonCode(StrEnum):
    FUNCTION_AND_FORM_LINKED = "function_and_form_linked"
    EXPLICIT_NONFUNCTIONAL_FORM = "explicit_nonfunctional_form"
    FORM_WITHOUT_FUNCTION = "form_without_function"
    FUNCTION_WITHOUT_FORM = "function_without_form"
    COMBINATION_LINKAGE_AMBIGUOUS = "combination_linkage_ambiguous"
    CONFLICTING_ROLE_EVIDENCE = "conflicting_role_evidence"
    NO_APPLICABLE_EVIDENCE = "no_applicable_evidence"
    INHERITED_MAPPING_ERROR = "inherited_mapping_error"


class RoleEvidenceField(StrEnum):
    PRIMARY_FUNCTION = "primary_function"
    RAW_MATERIALS = "raw_materials"
    BOTH = "both"
    NONE = "none"


def _normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _reject_unsafe_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be text")
    retained_value = value.strip()
    if retained_value.startswith(_SPREADSHEET_FORMULA_PREFIXES):
        raise ValueError(f"{field_name} starts with a spreadsheet formula prefix")
    if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
        raise ValueError(f"{field_name} contains a possible secret")
    return value


def _validate_normalized_phrase_list(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a tuple-compatible list")
    values: list[str] = []
    for item in value:
        text = _reject_unsafe_text(item, field_name)
        normalized = _normalize_text(text)
        if not normalized or text != normalized:
            raise ValueError(f"{field_name} values must already be normalized and nonblank")
        values.append(text)
    normalized_values = tuple(values)
    if normalized_values != tuple(sorted(set(normalized_values))):
        raise ValueError(f"{field_name} must be sorted and unique")
    return normalized_values


def _is_official_source_url(source_url: str) -> bool:
    try:
        parsed = urlsplit(source_url)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        return False
    host = hostname.casefold().rstrip(".")
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in _OFFICIAL_SOURCE_HOSTS)


class FunctionalRoleRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    group: IngredientGroup
    canonical_ingredient: NonBlankText
    accepted_functional_forms: tuple[NonBlankText, ...]
    recognized_function_texts: tuple[NonBlankText, ...]
    known_nonfunctional_forms: tuple[NonBlankText, ...] = ()
    source_id: NonBlankText
    source_url: NonBlankText
    promulgated_at: date
    effective_from: date
    effective_to: date | None
    retrieved_at: AwareDatetime
    verified_current_at: AwareDatetime
    status: FunctionalRoleRuleStatus
    source_locator: NonBlankText
    content_sha256: str = Field(pattern=r"^[0-9A-F]{64}$")
    rule_version: NonBlankText
    extracted_by: NonBlankText
    reviewed_by: NonBlankText
    reviewed_at_iso8601: AwareDatetime

    @field_validator(
        "canonical_ingredient",
        "source_id",
        "source_url",
        "source_locator",
        "rule_version",
        "extracted_by",
        "reviewed_by",
        mode="before",
    )
    @classmethod
    def _reject_unsafe_scalar_text(cls, value: object, info: object) -> str:
        return _reject_unsafe_text(value, getattr(info, "field_name", "text"))

    @field_validator(
        "accepted_functional_forms",
        "recognized_function_texts",
        "known_nonfunctional_forms",
        mode="before",
    )
    @classmethod
    def _require_normalized_phrase_lists(cls, value: object, info: object) -> tuple[str, ...]:
        return _validate_normalized_phrase_list(value, getattr(info, "field_name", "phrases"))

    @model_validator(mode="after")
    def _validate_rule_contract(self) -> "FunctionalRoleRule":
        if not self.accepted_functional_forms:
            raise ValueError("accepted functional forms must not be empty")
        if not self.recognized_function_texts:
            raise ValueError("recognized function texts must not be empty")
        if self.promulgated_at > self.effective_from:
            raise ValueError("promulgated date must not follow effective_from")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")
        if not _is_official_source_url(self.source_url):
            raise ValueError("source URL must be an official HTTP(S) source without credentials or fragment")
        return self


class FunctionalRoleRuleRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    contract_version: Literal["functional-role-rules-v1"]
    rules: tuple[FunctionalRoleRule, ...]

    @model_validator(mode="after")
    def _require_exact_comparison_group_order(self) -> "FunctionalRoleRuleRegistry":
        if tuple(rule.group for rule in self.rules) != COMPARISON_GROUPS:
            raise ValueError("rules must contain each comparison group exactly once in comparison-group order")
        return self


class MachineRoleDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    group: IngredientGroup
    report_no: NonBlankText
    verdict: MachineRoleVerdict
    reason_code: MachineRoleReasonCode
    evidence_field: RoleEvidenceField
    raw_materials_excerpt: str
    primary_function_excerpt: str
    matched_functional_form: str
    matched_function_text: str
    matched_nonfunctional_form: str
    rule_version: NonBlankText


def _require_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def load_functional_role_registry(
    path: Path,
    *,
    evaluated_at: AwareDatetime,
) -> FunctionalRoleRuleRegistry:
    _require_aware_datetime(evaluated_at, "evaluated_at")
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationError.from_exception_data(
            "FunctionalRoleRuleRegistry",
            [
                {
                    "type": "value_error",
                    "loc": ("path",),
                    "input": str(path),
                    "ctx": {"error": ValueError("registry file is unreadable")},
                }
            ],
        ) from exc
    try:
        registry = FunctionalRoleRuleRegistry.model_validate_json(contents)
    except (ValidationError, ValueError) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError.from_exception_data(
            "FunctionalRoleRuleRegistry",
            [
                {
                    "type": "value_error",
                    "loc": ("registry",),
                    "input": contents,
                    "ctx": {"error": exc},
                }
            ],
        ) from exc

    for rule in registry.rules:
        verification_age = evaluated_at - rule.verified_current_at
        if verification_age < timedelta() or verification_age > timedelta(days=ROLE_RULE_MAX_AGE_DAYS):
            raise ValueError("rule verification must be current and no more than seven days old")
        if rule.effective_from > evaluated_at.date():
            raise ValueError("rule is not yet effective")
        if rule.effective_to is not None and evaluated_at.date() > rule.effective_to:
            raise ValueError("rule is no longer effective")
        if rule.status is not FunctionalRoleRuleStatus.ACTIVE:
            raise ValueError("only active rules may be loaded")
    return registry


def classify_functional_role(
    product: ExtensionReviewProduct,
    group: IngredientGroup,
    registry: FunctionalRoleRuleRegistry,
) -> MachineRoleDecision:
    raise NotImplementedError("functional-role classification is implemented in Task 3")
