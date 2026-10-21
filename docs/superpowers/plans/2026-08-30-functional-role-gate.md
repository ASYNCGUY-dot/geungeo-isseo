# 기능성 역할 증거 게이트 v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 C003 제품 검토 v2를 변경하지 않고, 다섯 비교 원료가 제품의 실제 기능성 역할을 하는지 결정론적으로 판정·감사하여 원료별 `ROLE_ELIGIBLE` 또는 `ROLE_INSUFFICIENT`를 재현 가능한 근거와 함께 산출한다.

**Approved amendment (2026-08-31):** 공식 기능 문구가 다른 영양성분과 중복되는
규칙은 `require_explicit_target_wording=true`로 두고 기능성 문자열의 목표 원료명
직접 연결까지 요구한다.

**Architecture:** 새 `claimledger.functional_role` 모듈이 현재 시행 중인 공식 원료·기능 규칙 레지스트리와 실패 폐쇄형 판정기를 담당한다. 새 `claimledger.functional_role_review` 모듈은 완료된 v2 pack을 입력으로 기존 100행 보존, 오매핑 보충, 그룹별 기계 긍정 최대 35행의 결정적 감사 표본, 사람 라벨 계약, pack 무결성, 지표와 자격 판정을 담당한다. 두 CLI는 생성과 검증만 감싸며, 공식 원문 획득·사람 검토 전에는 성공을 추정하지 않는다. 광고 근거와 최종 추천은 이 계획에서 구현하지 않고 계속 차단한다.

**Tech Stack:** Python 3.12+, Pydantic 2.x, Python 표준 라이브러리 `csv`·`hashlib`·`json`·`math`·`urllib.parse`, pytest 8.x, pytest-cov, Ruff. 새 런타임 의존성, LLM 판정, RAG, LangGraph, FastAPI, React는 추가하지 않는다.

## Global Constraints

- 작업 위치는 `%USERPROFILE%\Desktop\DONGA AI LAB\DONGA KDT 3RD PROJECT\geungeo-isseo\.worktrees\phase-0-c003-data-gate`와 브랜치 `phase-0-c003-data-gate`다.
- 설계 정본은 `docs/superpowers/specs/2026-08-30-extension-recommendation-evidence-gates-design.md`이며 상태는 사용자 서면 승인 완료다.
- 이번 구현 범위는 `A — functional-role-gate`뿐이다. `B — official-ad-evidence-gate`와 `C — extension-recommendation-finalization`의 코드·데이터·상태 해제는 금지한다.
- `build/extension-review-v2/`의 네 파일, v2 라벨 100행, 역사적 v1 pack을 삭제·덮어쓰기·자동 수정하지 않는다.
- `ReviewValidationResult`의 `advertising_evidence_status=NOT_MEASURED`, `extension_recommendation_status=BLOCKED`, `finalized=false`를 유지한다.
- 기능성 역할 pack은 `build/functional-role-review-v1/`에 정확히 네 파일만 생성하고 Git에서 계속 제외한다.
- 공식 원본과 추출 중간 파일은 `build/functional-role-sources-v1/`에 보존하고 커밋하지 않는다. 검증된 최소 규칙 레지스트리만 `data/reference/functional-role-rules-v1.json`에 추적한다.
- 공식 원문을 열 수 없거나 다섯 그룹 중 하나의 원료형·기능 문구·원문 위치를 확인할 수 없으면 `BLOCKED_SOURCE_UNAVAILABLE` 또는 `BLOCKED_EXPERT_REVIEW`로 멈춘다. 빈 규칙, 검색 요약, 추정 문구로 통과시키지 않는다.
- 제품명은 기능성 역할 긍정 근거가 아니다. 원재료 alias만 일치하거나 목표 기능이 연결되지 않으면 `functional_confirmed`를 만들지 않는다.
- 사람 라벨을 에이전트가 임의로 대량 확정하지 않는다. 공식 원문과 제품 원문으로 결정 가능한 행만 증거 후보를 제시하고, 모호한 행은 `uncertain` 또는 사용자 확인 대상으로 남긴다.
- 빈 값, 판단 불가, 표본 부족을 수치 `0` 또는 성공으로 바꾸지 않는다.
- 사람 입력이 전부 빈 행만 `PENDING`이다. 일부 필드만 입력된 행, 서로 모순되는 행, 미래 시각, 변조된 기계 판정은 `INVALID`다.
- 실제 API 키, 쿠키, C003 envelope, 사용자 건강정보, 판매자 원문 전체를 추적 fixture·summary·문서에 넣지 않는다.
- 모든 표본 선택은 입력 순서와 무관한 SHA-256 순위로 결정하며 Python `hash()`나 실행 후 수동 선별을 사용하지 않는다.
- 각 코드 단위는 실패 테스트를 먼저 작성하고 실제 RED를 확인한 뒤 최소 구현을 작성한다.
- 각 커밋 전 focused test, 관련 회귀, Ruff, `git diff --check`, 비밀정보 검사를 새로 실행한다.
- 병합, 원격 저장소 생성·이름 변경, push, PR 생성, worktree 삭제는 이 계획에 포함하지 않는다.

## File Responsibility Map

| 파일 | 책임 |
|---|---|
| `src/claimledger/functional_role.py` | 공식 기능성 역할 규칙 모델·로더, 정규화·문구 탐색, 실패 폐쇄형 기계 판정 |
| `src/claimledger/functional_role_review.py` | 표본·라벨·manifest·summary 모델, 결정적 표본 생성, pack 기록·검증, 지표와 원료 자격 |
| `scripts/build_functional_role_review.py` | source/v2/rules 입력을 받는 생성 CLI와 오류 종료 |
| `scripts/validate_functional_role_review.py` | pack 검증 CLI, `COMPLETE=0`·`PENDING=2`·`INVALID=3`, COMPLETE summary 원자적 기록 |
| `tests/test_functional_role.py` | 규칙 계약과 판정기 단위·경계·보안 테스트 |
| `tests/test_functional_role_review.py` | 표본, pack, 라벨, 변조, 지표, CLI 상태 테스트 |
| `tests/fixtures/functional_role_rules.json` | 다섯 비교군을 모두 포함하는 합성 공식-도메인 규칙 fixture |
| `data/reference/functional-role-rules-v1.json` | 현재 시행 공식 원문에서 사람이 확인한 다섯 비교군 규칙 레지스트리 |
| `docs/evidence/functional-role-summary-v1.json` | COMPLETE일 때만 추적하는 원문 비포함 집계·해시 summary |
| `README.md` | v2 완료 상태, 기능성 역할 pack 생성·검증 명령과 차단 경계 |
| `AGENTS.md` | 현재 첫 작업과 fail-closed 운영 규칙 |
| `docs/CODEX_HANDOFF.md` | 실제 구현·실측·사람 검토·미구현 경계 |
| `docs/evidence/PHASE_1_EXTENSION_REVIEW.md` | v2 완료 증거와 기능성 역할 게이트의 실제 상태·해시 |
| `%USERPROFILE%\Desktop\AI-Agent-Wiki\AI-Sessions\wiki\projects\근거있어.md` | 프로젝트 정본 상태와 다음 작업 |
| `%USERPROFILE%\Desktop\AI-Agent-Wiki\AI-Sessions\conversations\2026-08-22-근거있어-코덱스-핸드오프.md` | 세션 인계 |
| `%USERPROFILE%\Desktop\AI-Agent-Wiki\index.md` | 기존 근거있어 항목의 상태 갱신 |
| `%USERPROFILE%\Desktop\AI-Agent-Wiki\log.md` | 날짜가 있는 저장 기록 한 줄 |

## Locked Public Contracts

### `functional_role.py`

```python
FUNCTIONAL_ROLE_RULE_CONTRACT_VERSION = "functional-role-rules-v1"
FUNCTIONAL_ROLE_RULE_VERSION = "functional-role-rule-v1"
ROLE_RULE_MAX_AGE_DAYS = 7


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


class FunctionalRoleRule(BaseModel):
    group: IngredientGroup
    canonical_ingredient: NonBlankText
    accepted_functional_forms: tuple[NonBlankText, ...]
    recognized_function_texts: tuple[NonBlankText, ...]
    known_nonfunctional_forms: tuple[NonBlankText, ...] = ()
    require_explicit_target_wording: bool = False
    source_id: NonBlankText
    source_url: NonBlankText
    promulgated_at: date
    effective_from: date
    effective_to: date | None
    retrieved_at: AwareDatetime
    verified_current_at: AwareDatetime
    status: FunctionalRoleRuleStatus
    source_locator: NonBlankText
    content_sha256: str
    rule_version: NonBlankText
    extracted_by: NonBlankText
    reviewed_by: NonBlankText
    reviewed_at_iso8601: AwareDatetime


class FunctionalRoleRuleRegistry(BaseModel):
    contract_version: Literal["functional-role-rules-v1"]
    rules: tuple[FunctionalRoleRule, ...]


class MachineRoleDecision(BaseModel):
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


load_functional_role_registry(
    path: Path,
    *,
    evaluated_at: AwareDatetime,
) -> FunctionalRoleRuleRegistry


classify_functional_role(
    product: ExtensionReviewProduct,
    group: IngredientGroup,
    registry: FunctionalRoleRuleRegistry,
) -> MachineRoleDecision
```

### `functional_role_review.py`

```python
FUNCTIONAL_ROLE_CONTRACT_VERSION = "c003-functional-role-v1"
DEFAULT_GENERAL_AUDIT_SIZE = 20
DEFAULT_POSITIVE_AUDIT_SIZE = 35
POSITIVE_WILSON_LOWER_THRESHOLD = 0.90


class HumanRoleVerdict(StrEnum):
    FUNCTIONAL_CONFIRMED = "functional_confirmed"
    PRESENT_NONFUNCTIONAL = "present_nonfunctional"
    UNCERTAIN = "uncertain"
    EXCLUDED_MAPPING_ERROR = "excluded_mapping_error"


class FunctionalRoleReasonCode(StrEnum):
    EXPLICIT_TARGET_FUNCTION = "explicit_target_function"
    EXPLICIT_NONFUNCTIONAL_ROLE = "explicit_nonfunctional_role"
    INSUFFICIENT_LINKAGE = "insufficient_linkage"
    COMBINATION_AMBIGUOUS = "combination_ambiguous"
    NEEDS_EXPERT = "needs_expert"
    INHERITED_MAPPING_ERROR = "inherited_mapping_error"
    OTHER = "other"


class SampleOrigin(StrEnum):
    V2_ORIGINAL = "v2_original"
    GENERAL_REPLACEMENT = "general_replacement"
    POSITIVE_PRECISION = "positive_precision"


class RoleEligibility(StrEnum):
    ROLE_ELIGIBLE = "ROLE_ELIGIBLE"
    ROLE_INSUFFICIENT = "ROLE_INSUFFICIENT"


class EligibilityReasonCode(StrEnum):
    POSITIVE_POOL_TOO_SMALL = "POSITIVE_POOL_TOO_SMALL"
    POSITIVE_SAMPLE_TOO_SMALL = "POSITIVE_SAMPLE_TOO_SMALL"
    GENERAL_AUDIT_CONFLICT = "GENERAL_AUDIT_CONFLICT"
    FALSE_CONFIRMATION = "FALSE_CONFIRMATION"
    FALSE_EXCLUSION = "FALSE_EXCLUSION"
    UNRESOLVED_POSITIVE = "UNRESOLVED_POSITIVE"
    OVERCONFIDENT_DECISION = "OVERCONFIDENT_DECISION"
    POSITIVE_WILSON_BELOW_THRESHOLD = "POSITIVE_WILSON_BELOW_THRESHOLD"
    NO_ADDRESSABLE_PRODUCTS = "NO_ADDRESSABLE_PRODUCTS"


class FunctionalRoleSample(BaseModel):
    seed: Literal[20260823]
    group: IngredientGroup
    report_no: NonBlankText
    name: NonBlankText
    company: NonBlankText
    primary_function: str
    raw_materials: str
    intake_method: str
    mapping_status: MappingStatus
    mapping_rule_version: NonBlankText
    audit_round: Literal[1, 2]
    sample_origin: SampleOrigin
    is_general_audit: bool
    is_positive_audit: bool
    machine_verdict: MachineRoleVerdict
    machine_reason_code: MachineRoleReasonCode
    machine_evidence_field: RoleEvidenceField
    machine_evidence_excerpt: str
    functional_role_rule_version: NonBlankText


class FunctionalRoleLabel(BaseModel):
    group: IngredientGroup
    report_no: NonBlankText
    audit_round: Literal[1, 2]
    machine_verdict: MachineRoleVerdict
    human_verdict: HumanRoleVerdict
    reason_code: FunctionalRoleReasonCode
    evidence_field: RoleEvidenceField
    evidence_excerpt: str
    rule_version: NonBlankText
    review_note: str
    reviewer: NonBlankText
    reviewed_at_iso8601: AwareDatetime


class FunctionalRoleGroupCounts(BaseModel):
    group: IngredientGroup
    original_v2_count: int
    inherited_mapping_error_count: int
    general_replacement_count: int
    general_evaluable_count: int
    positive_pool_count: int
    positive_sample_count: int
    total_unique_rows: int


class FunctionalRoleManifest(BaseModel):
    contract_version: Literal["c003-functional-role-v1"]
    seed: Literal[20260823]
    general_size_per_group: Literal[20]
    positive_size_per_group: Literal[35]
    generated_at: AwareDatetime
    source_export_sha256: str
    product_review_manifest_sha256: str
    product_review_samples_sha256: str
    product_review_labels_sha256: str
    rules_sha256: str
    samples_sha256: str
    mapping_rule_versions: tuple[NonBlankText, ...]
    functional_role_rule_versions: tuple[NonBlankText, ...]
    group_counts: tuple[FunctionalRoleGroupCounts, ...]


class RoleConfusionCell(BaseModel):
    machine_verdict: MachineRoleVerdict
    human_verdict: HumanRoleVerdict
    row_count: int


class FunctionalRoleGroupSummary(BaseModel):
    group: IngredientGroup
    audited_row_count: int
    addressable_product_count: int
    general_evaluable_count: int
    positive_pool_count: int
    positive_sample_count: int
    true_functional_confirmed_count: int
    false_confirmation_count: int
    unresolved_positive_count: int
    false_exclusion_count: int
    overconfident_decision_count: int
    avoidable_unverifiable_count: int
    positive_precision: float | None
    positive_precision_wilson_95: WilsonInterval | None
    decidable_agreement_rate: float | None
    decision_coverage: float | None
    unverifiable_rate: float | None
    human_uncertainty_rate: float | None
    confusion_matrix: tuple[RoleConfusionCell, ...]
    eligibility: RoleEligibility
    eligibility_reasons: tuple[EligibilityReasonCode, ...]


class FunctionalRoleSummary(BaseModel):
    contract_version: Literal["c003-functional-role-v1"]
    generated_at: AwareDatetime
    validated_at: AwareDatetime
    source_export_sha256: str
    product_review_labels_sha256: str
    rules_sha256: str
    samples_sha256: str
    functional_role_labels_sha256: str
    audited_row_count: int
    groups: tuple[FunctionalRoleGroupSummary, ...]
    advertising_evidence_status: Literal["NOT_MEASURED"]
    extension_recommendation_status: Literal["BLOCKED"]
    finalized: Literal[False]


class FunctionalRoleValidationResult(BaseModel):
    status: ReviewGateStatus
    expected_label_count: int | None
    valid_label_count: int | None
    pending_label_count: int | None
    issues: tuple[ReviewIssue, ...]
    summary: FunctionalRoleSummary | None
    advertising_evidence_status: Literal["NOT_MEASURED"]
    extension_recommendation_status: Literal["BLOCKED"]
    finalized: Literal[False]


derive_sample_seed(
    base_seed: int,
    group: IngredientGroup,
    scope: Literal["general-replacement", "positive"],
) -> int


build_functional_role_samples(
    products: tuple[ExtensionReviewProduct, ...],
    *,
    product_review_pack_dir: Path,
    registry: FunctionalRoleRuleRegistry,
    base_seed: int = 20260823,
    general_size: int = 20,
    positive_size: int = 35,
) -> tuple[FunctionalRoleSample, ...]


write_functional_role_review_pack(
    output_dir: Path,
    *,
    products: tuple[ExtensionReviewProduct, ...],
    source_export_path: Path,
    product_review_pack_dir: Path,
    rules_path: Path,
    registry: FunctionalRoleRuleRegistry,
    generated_at: AwareDatetime,
    base_seed: int = 20260823,
    general_size: int = 20,
    positive_size: int = 35,
) -> FunctionalRoleManifest


validate_functional_role_review_pack(
    pack_dir: Path,
    source_export_path: Path,
    product_review_pack_dir: Path,
    rules_path: Path,
    *,
    validated_at: AwareDatetime,
) -> FunctionalRoleValidationResult
```

The new validator imports and reuses `ReviewGateStatus`, `ReviewIssue`, `WilsonInterval`, `sha256_file`, and `wilson_interval` from `claimledger.product_review`. It must not copy the Wilson formula or redefine pack status semantics.

### CSV evidence encoding

`functional_role_labels.csv` uses exactly these columns, in this order:

```text
group,report_no,audit_round,machine_verdict,human_verdict,reason_code,evidence_field,evidence_excerpt,rule_version,review_note,reviewer,reviewed_at_iso8601
```

- `evidence_field=raw_materials` or `primary_function`: `evidence_excerpt` must be one literal contiguous substring of that source field.
- `evidence_field=both`: `evidence_excerpt` must be compact JSON with exactly the keys `raw_materials` and `primary_function`. Both values must be nonblank literal substrings of their respective fields.
- `evidence_field=none`: `evidence_excerpt` must be empty.
- `functional_confirmed` requires `explicit_target_function`, `both`, and both literal excerpts.
- `present_nonfunctional` requires `explicit_nonfunctional_role` and `raw_materials` or `both`.
- `uncertain` requires one of `insufficient_linkage`, `combination_ambiguous`, `needs_expert`, `other`. `needs_expert` and `other` require a nonblank note.
- `excluded_mapping_error` requires `inherited_mapping_error`, `none`, and an empty excerpt.

---

### Task 1: Reconcile the Completed v2 Evidence Before Building A

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/CODEX_HANDOFF.md`
- Modify: `docs/evidence/PHASE_1_EXTENSION_REVIEW.md`

**Interfaces:**
- Consumes: untouched `data/c003-products.jsonl` and `build/extension-review-v2/`.
- Produces: tracked documentation that states the current v2 result and leaves advertisement/recommendation blocking intact.
- Contract: no code or generated pack change; observed values replace stale `PENDING 0/100` prose.

- [ ] **Step 1: Prove the current v2 pack again**

Run:

```powershell
.venv\Scripts\python.exe scripts\validate_product_review.py `
  --pack-dir build\extension-review-v2 `
  --source-export data\c003-products.jsonl
$validatorExit = $LASTEXITCODE
Get-FileHash -Algorithm SHA256 -LiteralPath 'build\extension-review-v2\product_review_labels.csv'
```

Expected: exit `0`, status `COMPLETE`, valid labels `100`, pending labels `0`, mapping `99 correct / 1 incorrect / 0 uncertain`, function usable `100/100`, label SHA-256 `A00B3C1A038DBFD06484A89A6C1B41AAA63837D3BD87FAC29E2AF5DF0E011CC1`. If any value differs, stop and investigate instead of editing prose.

- [ ] **Step 2: Write a documentation regression check and verify it fails**

Run:

```powershell
rg -n '현재.*PENDING|유효.*0 / 100|PENDING 0 / 100|사람 라벨 100건 검토 대기' `
  README.md AGENTS.md docs\CODEX_HANDOFF.md docs\evidence\PHASE_1_EXTENSION_REVIEW.md
```

Expected: stale claims are found, proving the tracked documentation is inconsistent with the live v2 pack.

- [ ] **Step 3: Update only the four tracked documents**

Record the observed v2 counts, the one `red_ginseng` alias-collision error, the exact label hash, and the distinction between:

- v2 product mapping/function-text review: `COMPLETE`;
- functional-role review A: not yet built;
- advertisement evidence: `NOT_MEASURED`;
- extension recommendation: `BLOCKED`;
- finalized: `false`.

Do not say that `function_text_status=usable` proves an ingredient caused the function.

- [ ] **Step 4: Verify the stale claim is gone and the blocking boundary remains**

Rewrite any intentionally retained past result so the matching line itself
contains `역사적`, `과거`, or `2026-08-28 당시`. Then run:

```powershell
$unmarkedPastClaims = @(
  rg -n '현재.*PENDING|유효.*0 / 100|PENDING 0 / 100|사람 라벨 100건 검토 대기' `
    README.md AGENTS.md docs\CODEX_HANDOFF.md docs\evidence\PHASE_1_EXTENSION_REVIEW.md |
    Where-Object { $_ -notmatch '역사적|과거|2026-08-28 당시' }
)
if ($unmarkedPastClaims.Count -ne 0) {
  $unmarkedPastClaims
  throw 'Unmarked stale current-status claims remain.'
}
rg -n 'COMPLETE|99|incorrect|NOT_MEASURED|BLOCKED|finalized=false' `
  README.md AGENTS.md docs\CODEX_HANDOFF.md docs\evidence\PHASE_1_EXTENSION_REVIEW.md
if ($LASTEXITCODE -ne 0) {
  throw 'Required current completion and blocking facts are missing.'
}
git diff --check
```

Expected: a broad search may retain explicitly historical evidence, but
`$unmarkedPastClaims` is empty; the required-fact search finds the completed-v2 and
blocked-downstream facts.

- [ ] **Step 5: Commit the evidence reconciliation**

```powershell
git add README.md AGENTS.md docs\CODEX_HANDOFF.md docs\evidence\PHASE_1_EXTENSION_REVIEW.md
git diff --cached --check
git commit -m "docs: reconcile completed C003 review"
```

---

### Task 2: Define and Validate the Official Functional-Role Rule Contract

**Files:**
- Create: `src/claimledger/functional_role.py`
- Create: `tests/test_functional_role.py`
- Create: `tests/fixtures/functional_role_rules.json`

**Interfaces:**
- Consumes: one UTF-8 JSON registry and an aware evaluation time.
- Produces: immutable `FunctionalRoleRuleRegistry` with exactly one active rule for each member of `COMPARISON_GROUPS`.
- Contract: only current, fresh, official HTTP(S) sources can become active rules.

- [ ] **Step 1: Create the exact synthetic five-rule fixture**

Use `contract_version=functional-role-rules-v1` and one rule per group. Use test-only source IDs `TEST-MILK-THISTLE`, `TEST-VITAMIN-D`, `TEST-RED-GINSENG`, `TEST-COQ10`, and `TEST-MAGNESIUM`; source URLs under `https://www.mfds.go.kr/synthetic-fixture/`; `status=active`; `effective_from=2026-01-01`; `effective_to=null`; `retrieved_at` and `verified_current_at` equal to `2026-08-30T00:00:00Z`; uppercase 64-character synthetic hashes; `rule_version=functional-role-rule-v1`; and `extracted_by=reviewed_by=synthetic-test-reviewer`.

Use one accepted form and one recognized function phrase per group so sorted-unique validation is unambiguous:

| group | accepted form | recognized function text | known nonfunctional form |
|---|---|---|---|
| `milk_thistle` | `밀크씨슬추출물` | `간 건강` | empty |
| `vitamin_d` | `비타민 D` | `칼슘과 인의 흡수` | empty |
| `red_ginseng` | `홍삼농축액` | `면역력 증진` | `홍삼향분말` |
| `coenzyme_q10` | `코엔자임 Q10` | `항산화` | empty |
| `magnesium` | `산화마그네슘` | `에너지 이용` | `스테아린산 마그네슘` |

The fixture is synthetic test data and must never be copied to the tracked real registry.

- [ ] **Step 2: Write failing rule-loader tests**

Add tests named:

- `test_load_functional_role_registry_accepts_exact_current_five_group_contract`
- `test_registry_rejects_a_missing_or_duplicate_comparison_group`
- `test_registry_rejects_proposed_expired_or_not_yet_effective_rules`
- `test_registry_rejects_stale_or_future_verification_times`
- `test_registry_rejects_non_official_or_non_http_sources`
- `test_registry_rejects_lowercase_or_non_sha256_content_hashes`
- `test_registry_rejects_empty_unsorted_or_duplicate_phrase_lists`
- `test_registry_rejects_formula_prefixes_and_secret_patterns`
- `test_registry_rejects_extra_fields_and_naive_datetimes`

Allowed hosts are the exact host or a subdomain of `mfds.go.kr`, `foodsafetykorea.go.kr`, or `law.go.kr`. A hostname merely ending in those characters, such as `mfds.go.kr.attacker.example`, must fail.

- [ ] **Step 3: Run the focused tests and verify RED**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_functional_role.py -q
```

Expected: collection fails because `claimledger.functional_role` does not exist. A malformed fixture is not the required RED.

- [ ] **Step 4: Implement the immutable rule models and loader**

Implement the locked public contracts. Normalize URL hosts with `urllib.parse.urlsplit`, reject embedded credentials and fragments, require `http` or `https`, validate date ordering, and require:

```python
0 <= (evaluated_at - rule.verified_current_at).total_seconds() <= 7 * 24 * 60 * 60
rule.effective_from <= evaluated_at.date()
rule.effective_to is None or evaluated_at.date() <= rule.effective_to
rule.status is FunctionalRoleRuleStatus.ACTIVE
```

Require tuple fields to equal `tuple(sorted(set(values)))` after Unicode NFKC and whitespace normalization. Require exact group order to follow `COMPARISON_GROUPS` in serialized registry output.

- [ ] **Step 5: Run focused tests, Ruff, and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_functional_role.py -q
.venv\Scripts\ruff.exe check src\claimledger\functional_role.py tests\test_functional_role.py
git diff --check
git add src\claimledger\functional_role.py tests\test_functional_role.py tests\fixtures\functional_role_rules.json
git diff --cached --check
git commit -m "feat: define functional role rules"
```

---

### Task 3: Implement the Fail-Closed Functional-Role Classifier

**Files:**
- Modify: `src/claimledger/functional_role.py`
- Modify: `tests/test_functional_role.py`

**Interfaces:**
- Consumes: `ExtensionReviewProduct`, one comparison `IngredientGroup`, validated registry.
- Produces: one immutable `MachineRoleDecision` with source-field excerpts and rule version.
- Contract: product name is never read for a positive result; no LLM or score participates.

- [ ] **Step 1: Write the classifier decision-table tests**

Add these named cases:

- `test_classifier_confirms_a_single_target_form_with_its_recognized_function`
- `test_classifier_does_not_use_product_name_as_role_evidence`
- `test_classifier_returns_unverifiable_for_form_without_function`
- `test_classifier_returns_unverifiable_for_function_without_form`
- `test_classifier_returns_unverifiable_for_unlinked_combination_product`
- `test_classifier_accepts_explicit_target_linkage_in_a_combination_product`
- `test_classifier_requires_explicit_target_wording_when_rule_policy_is_enabled`
- `test_classifier_never_confirms_red_ginseng_flavor_powder`
- `test_classifier_marks_an_explicitly_registered_nonfunctional_form`
- `test_classifier_does_not_infer_nonfunctional_role_from_missing_function_text`
- `test_classifier_returns_unverifiable_for_conflicting_functional_and_nonfunctional_forms`
- `test_classifier_preserves_literal_excerpts_and_rule_version`
- `test_classifier_is_invariant_to_nfkc_case_and_repeated_whitespace`

Two magnesium fixtures are mandatory:

1. `raw_materials="스테아린산 마그네슘"` with the synthetic explicit nonfunctional-form rule yields `present_nonfunctional`, never `functional_confirmed`.
2. The same product under a rule without that explicit nonfunctional form yields `unverifiable`, not an inferred negative.

- [ ] **Step 2: Run the new tests and verify RED**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_functional_role.py -q
```

Expected: failures report missing `MachineRoleDecision` or `classify_functional_role` behavior.

- [ ] **Step 3: Implement exact deterministic matching**

Apply this precedence:

1. Search only `raw_materials` for accepted functional forms and explicit nonfunctional forms.
2. Search only `primary_function` for recognized target functions and explicit target ingredient wording.
3. Scan all registry groups' accepted forms in `raw_materials` to detect combination products.
4. Return `functional_confirmed` only when the target functional form and target function both match and either the target is the sole matched functional group or `primary_function` explicitly names the target ingredient/form. When `require_explicit_target_wording=true`, the explicit target name is mandatory even if the target is the sole matched comparison group.
5. If functional and nonfunctional evidence conflict, return `unverifiable/conflicting_role_evidence`.
6. Return `present_nonfunctional` only for an explicit `known_nonfunctional_forms` match with no functional-role pair.
7. All remaining cases return one of the documented `unverifiable` reasons.

Use Unicode NFKC, `casefold()`, and collapsed whitespace for matching. Return literal source slices, not normalized or generated prose. Match ties use longest phrase first, then lexical order, so the same input always selects the same excerpt.

- [ ] **Step 4: Run focused and ingredient-mapping regressions**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_functional_role.py tests\test_ingredients.py -q
.venv\Scripts\ruff.exe check src\claimledger\functional_role.py tests\test_functional_role.py
git diff --check
```

Expected: all pass; existing `ingredient-map-v1` behavior is unchanged.

- [ ] **Step 5: Commit the classifier**

```powershell
git add src\claimledger\functional_role.py tests\test_functional_role.py
git diff --cached --check
git commit -m "feat: classify functional ingredient roles"
```

---

### Task 4: Define Sample, Human-Label, Manifest, and Result Contracts

**Files:**
- Create: `src/claimledger/functional_role_review.py`
- Create: `tests/test_functional_role_review.py`

**Interfaces:**
- Consumes: typed machine decisions and CSV values.
- Produces: frozen sample, label, manifest, group-count, issue, metrics, eligibility, summary, and validation-result models.
- Contract: model validation handles row-level semantics; pack-level source equality is added in Task 7.

- [ ] **Step 1: Write failing row-contract tests**

Create tests for:

- `test_functional_role_label_accepts_confirmed_both_field_evidence`
- `test_label_rejects_machine_and_human_enum_misspellings`
- `test_confirmed_requires_explicit_target_reason_and_both_excerpts`
- `test_nonfunctional_requires_explicit_nonfunctional_reason`
- `test_uncertain_requires_a_compatible_reason`
- `test_needs_expert_and_other_require_a_note`
- `test_excluded_mapping_error_requires_empty_evidence`
- `test_label_rejects_formula_prefixes_and_secret_patterns_in_all_free_text`
- `test_label_rejects_naive_datetime_and_audit_round_outside_one_or_two`
- `test_manifest_rejects_unsorted_versions_bad_hashes_and_inconsistent_counts`
- `test_validation_result_preserves_not_measured_blocked_and_false`

Use compact canonical JSON for `both` evidence:

```json
{"raw_materials":"산화마그네슘","primary_function":"에너지 이용"}
```

Generate it exactly with:

```python
json.dumps(
    {
        "raw_materials": raw_materials_excerpt,
        "primary_function": primary_function_excerpt,
    },
    ensure_ascii=False,
    separators=(",", ":"),
)
```

The insertion order shown above is mandatory. Any extra key, non-string value,
different spacing/order, or empty excerpt must fail.

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_functional_role_review.py -q
```

Expected: collection fails because `claimledger.functional_role_review` does not exist.

- [ ] **Step 3: Implement the locked enums and immutable models**

`FunctionalRoleSample` must include:

```text
seed,group,report_no,name,company,primary_function,raw_materials,intake_method,
mapping_status,mapping_rule_version,audit_round,sample_origin,is_general_audit,
is_positive_audit,machine_verdict,machine_reason_code,machine_evidence_field,
machine_evidence_excerpt,functional_role_rule_version
```

For machine `both` evidence, `machine_evidence_excerpt` uses the same canonical JSON rule as human evidence. `FunctionalRoleManifest` must bind:

```text
contract_version,seed,general_size_per_group,positive_size_per_group,generated_at,
source_export_sha256,product_review_manifest_sha256,product_review_samples_sha256,
product_review_labels_sha256,rules_sha256,samples_sha256,mapping_rule_versions,
functional_role_rule_versions,group_counts
```

Each group-count record must include `group`, `original_v2_count`, `inherited_mapping_error_count`, `general_replacement_count`, `general_evaluable_count`, `positive_pool_count`, `positive_sample_count`, and `total_unique_rows`.

`FunctionalRoleValidationResult` reuses `ReviewGateStatus` and always carries:

```python
advertising_evidence_status: Literal["NOT_MEASURED"] = "NOT_MEASURED"
extension_recommendation_status: Literal["BLOCKED"] = "BLOCKED"
finalized: Literal[False] = False
```

- [ ] **Step 4: Run focused tests, Ruff, and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_functional_role_review.py -q
.venv\Scripts\ruff.exe check src\claimledger\functional_role_review.py tests\test_functional_role_review.py
git diff --check
git add src\claimledger\functional_role_review.py tests\test_functional_role_review.py
git diff --cached --check
git commit -m "feat: define functional role review contracts"
```

---

### Task 5: Build Deterministic General-Replacement and Positive-Audit Samples

**Files:**
- Modify: `src/claimledger/functional_role_review.py`
- Modify: `tests/test_functional_role_review.py`

**Interfaces:**
- Consumes: the full source product tuple, the completed v2 pack, and the validated registry.
- Produces: one ordered tuple of unique `FunctionalRoleSample` rows.
- Contract: the first 100 rows preserve v2 order, keys, and product fields; additional rows are selected before any recommendation exists.

- [ ] **Step 1: Build synthetic source and v2-pack helpers**

In `tests/test_functional_role_review.py`, create a five-group synthetic source with:

- exactly 20 v2 rows per group;
- one inherited `red_ginseng` mapping error matching `홍삼향분말`;
- at least 21 additional correctly mapped products in every group for general replacement;
- 40 machine-positive products per group except a dedicated magnesium-small-pool fixture with 34;
- shuffled-source variants containing the same rows.

The test helper must write a real v2 manifest, samples, and labels and call `validate_product_review_pack`; do not bypass the existing validator with a mock.

- [ ] **Step 2: Write failing deterministic-sampling tests**

Add:

- `test_sampling_refuses_a_non_complete_v2_pack`
- `test_first_100_rows_preserve_v2_order_keys_and_product_fields`
- `test_inherited_mapping_error_is_preserved_and_replaced_deterministically`
- `test_each_group_has_exactly_20_evaluable_general_rows`
- `test_positive_audit_selects_at_most_35_machine_positive_unique_products`
- `test_existing_general_positive_is_marked_without_a_duplicate_row`
- `test_positive_pool_below_35_keeps_all_rows_for_insufficient_status`
- `test_group_and_report_number_are_unique_across_the_pack`
- `test_sampling_is_invariant_to_source_order`
- `test_sampling_changes_when_the_seed_changes`
- `test_every_group_uses_the_same_scope_specific_hash_rule`
- `test_non_machine_positive_products_never_enter_positive_audit_only_rows`

- [ ] **Step 3: Run the focused tests and verify RED**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_functional_role_review.py -q
```

Expected: failures point to missing sampling functions, not an invalid synthetic v2 pack.

- [ ] **Step 4: Implement hash-derived ranking and sample merging**

`derive_sample_seed` uses:

```python
material = (
    f"c003-functional-role-v1|{base_seed}|{group.value}|{scope}"
).encode("utf-8")
return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
```

Candidate rank uses:

```python
rank_material = (
    f"{derived_seed}|{group.value}|{scope}|{product.report_no}"
).encode("utf-8")
rank = hashlib.sha256(rank_material).digest()
```

Sort by `(rank, report_no, name, company)`. Never use `random.sample`, collection insertion order, or Python `hash()`.

Apply these merge rules exactly:

1. Parse and preserve the 100 v2 sample rows in existing file order.
2. A v2 label with `mapping_verdict != correct` remains in the pack, gets machine `unverifiable/inherited_mapping_error`, and is excluded from the 20-row evaluable general denominator.
3. Select one `general_replacement` per excluded row from the same group, excluding every existing `(group, report_no)` key; replacement `audit_round=1` and `is_general_audit=true`.
4. Compute all source products that map to the group and classify them. The positive pool contains only machine `functional_confirmed` rows and excludes inherited non-correct v2 keys.
5. Select the first 35 ranked positive keys, or the whole pool if fewer than 35.
6. If a selected positive key already exists, change only `is_positive_audit` to `true`; retain its first-inclusion `audit_round` and origin.
7. New positive-only rows use `sample_origin=positive_precision`, `audit_round=2`, `is_general_audit=false`, `is_positive_audit=true`.
8. Append general replacements in `COMPARISON_GROUPS` order, then positive-only rows in the same group order and hash rank.

The original excluded row remains `sample_origin=v2_original` and `is_general_audit=true`; metrics omit it via its human `excluded_mapping_error`, leaving 20 evaluable general rows after replacement.

- [ ] **Step 5: Run focused tests, full sampling regressions, and commit**

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\test_functional_role_review.py `
  tests\test_product_review.py `
  tests\test_extension_selection.py -q
.venv\Scripts\ruff.exe check `
  src\claimledger\functional_role_review.py `
  tests\test_functional_role_review.py
git diff --check
git add src\claimledger\functional_role_review.py tests\test_functional_role_review.py
git diff --cached --check
git commit -m "feat: sample functional role audits"
```

---

### Task 6: Write the Four-File Pack and Build CLI

**Files:**
- Modify: `src/claimledger/functional_role_review.py`
- Create: `scripts/build_functional_role_review.py`
- Modify: `tests/test_functional_role_review.py`

**Interfaces:**
- Consumes: source export, completed v2 directory, rule registry, output directory, fixed seed and sample sizes.
- Produces: exactly `README.md`, `manifest.json`, `samples.csv`, and `functional_role_labels.csv`.
- Contract: output creation is all-or-nothing and never modifies an existing directory.

- [ ] **Step 1: Write failing pack-writer and CLI tests**

Add:

- `test_writer_creates_exactly_four_files_with_lf_utf8`
- `test_writer_refuses_an_existing_output_directory`
- `test_writer_removes_a_partially_created_directory_after_failure`
- `test_manifest_binds_source_v2_rules_and_samples_hashes`
- `test_manifest_records_exact_per_group_pool_and_sample_counts`
- `test_label_template_has_one_row_for_every_sample_key`
- `test_inherited_mapping_error_label_copies_v2_reviewer_and_time`
- `test_all_non_inherited_label_rows_are_completely_blank_human_inputs`
- `test_pack_readme_states_pending_not_measured_blocked_and_not_finalized`
- `test_builder_refuses_nondefault_general_or_positive_sizes`
- `test_build_cli_returns_zero_only_after_a_complete_write`
- `test_build_cli_returns_a_nonzero_error_without_a_partial_pack`

The inherited row must be:

```text
human_verdict=excluded_mapping_error
reason_code=inherited_mapping_error
evidence_field=none
evidence_excerpt=
reviewer=the exact reviewer value from the matching validated v2 label
reviewed_at_iso8601=the exact timestamp from the matching validated v2 label
```

Its deterministic review note is produced by:

```python
(
    "Inherited c003-product-review-v2 mapping verdict: "
    f"{v2_label.mapping_verdict.value}/{v2_label.mapping_reason_code.value}."
)
```

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_functional_role_review.py -q
```

Expected: failures report missing writer or CLI.

- [ ] **Step 3: Implement pack serialization**

Use `csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")`, JSON with `ensure_ascii=False`, `indent=2`, `sort_keys=True`, and a terminal newline. `samples.csv` uses the exact model-field order locked in Task 4. `functional_role_labels.csv` uses the exact 12-column order locked above.

Before creating the output directory:

1. run the existing v2 validator and require `COMPLETE`;
2. load all products;
3. load and freshness-check the registry;
4. build the full in-memory sample tuple and manifest;
5. reject nondefault seed or sizes.

After creating the directory, catch every exception, remove only that newly created exact output directory, and raise `FunctionalRoleBuildError`. Do not remove a directory that existed before the command.

- [ ] **Step 4: Implement the build CLI**

`scripts/build_functional_role_review.py` accepts:

```text
--source-export PATH
--product-review-pack PATH
--rules PATH
--output-dir PATH
--seed INT                 default 20260823
--general-size INT         default 20
--positive-size INT        default 35
```

Reuse `load_products` from `scripts.build_extension_review` in the CLI layer only. Package code must not import from `scripts`.

Example command:

```powershell
.venv\Scripts\python.exe scripts\build_functional_role_review.py `
  --source-export data\c003-products.jsonl `
  --product-review-pack build\extension-review-v2 `
  --rules data\reference\functional-role-rules-v1.json `
  --output-dir build\functional-role-review-v1
```

- [ ] **Step 5: Run focused tests, CLI regressions, and commit**

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\test_functional_role_review.py `
  tests\test_extension_selection.py `
  tests\test_product_review.py -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
git add `
  src\claimledger\functional_role_review.py `
  scripts\build_functional_role_review.py `
  tests\test_functional_role_review.py
git diff --cached --check
git commit -m "feat: build functional role review packs"
```

---

### Task 7: Validate Pack Identity, Security, and Human Review State

**Files:**
- Modify: `src/claimledger/functional_role_review.py`
- Modify: `tests/test_functional_role_review.py`

**Interfaces:**
- Consumes: a generated pack and the three authoritative input locations.
- Produces: `FunctionalRoleValidationResult` in `PENDING`, `INVALID`, or `COMPLETE` after Task 8 metrics are present.
- Contract: the validator independently recomputes every load-bearing value; it does not trust manifest or CSV machine columns.

- [ ] **Step 1: Write the mutation matrix**

Start from one valid blank synthetic pack and mutate one item at a time. Add:

- `test_validator_returns_pending_for_a_clean_incomplete_pack`
- `test_validator_rejects_missing_extra_or_renamed_pack_files`
- `test_validator_rejects_source_export_hash_or_product_text_changes`
- `test_validator_rejects_any_v2_manifest_sample_or_label_hash_change`
- `test_validator_rejects_rules_hash_rule_version_or_freshness_change`
- `test_validator_rejects_sample_add_delete_duplicate_or_reordering`
- `test_validator_rejects_changed_audit_round_origin_or_scope_flags`
- `test_validator_rejects_changed_machine_verdict_reason_or_evidence`
- `test_validator_rejects_label_keys_not_equal_to_sample_keys`
- `test_validator_rejects_a_partial_human_label_row`
- `test_validator_rejects_evidence_not_literal_in_the_declared_source_field`
- `test_validator_rejects_noncanonical_both_evidence_json`
- `test_validator_rejects_future_review_times`
- `test_validator_rejects_formula_prefixes_and_secret_patterns`
- `test_invalid_result_hides_progress_counts_and_has_sorted_issues`

Also mutate only the C003 input line order. Because source SHA is an identity boundary, that must be `INVALID` even though deterministic sampling itself is order-invariant.

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_functional_role_review.py -q
```

Expected: new cases fail because pack validation is absent or incomplete.

- [ ] **Step 3: Implement independent validation in this order**

1. Require the exact four-file set.
2. Read UTF-8 with bounded, explicit error issues; reject NULs and possible secrets.
3. Parse manifest with `extra=forbid`.
4. Recompute source, v2 manifest, v2 samples, v2 labels, rules, and role-samples SHA-256 values.
5. Rerun the v2 validator and require `COMPLETE`.
6. Reload the registry at `validated_at` and require active, effective, not-future, at-most-seven-day verification.
7. Rebuild expected samples in memory and compare row count, order, keys, product fields, mapping fields, audit fields, machine decision, evidence, and rule versions.
8. Parse labels with exact headers and exactly one key per sample.
9. Treat a non-inherited row with all six human decision inputs empty as pending. Treat any partially filled row as invalid.
10. Require inherited mapping-error rows to equal the deterministic prefilled values.
11. Validate completed evidence excerpts against literal source fields and require `reviewed_at_iso8601 <= validated_at`.
12. Sort issues by line number, code, group, report number, and message before returning.

`PENDING` requires no issues, at least one pending row, no summary, and exact valid/pending counts summing to the generated sample count. `INVALID` exposes neither progress counts nor summary. Both preserve `NOT_MEASURED`, `BLOCKED`, and `false`.

- [ ] **Step 4: Run focused tests and existing security regressions**

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\test_functional_role_review.py `
  tests\test_product_review.py `
  tests\test_safety.py -q
.venv\Scripts\ruff.exe check src\claimledger\functional_role_review.py tests\test_functional_role_review.py
git diff --check
```

- [ ] **Step 5: Commit identity and state validation**

```powershell
git add src\claimledger\functional_role_review.py tests\test_functional_role_review.py
git diff --cached --check
git commit -m "feat: validate functional role review packs"
```

---

### Task 8: Compute Accuracy Metrics and Fail-Closed Group Eligibility

**Files:**
- Modify: `src/claimledger/functional_role_review.py`
- Modify: `tests/test_functional_role_review.py`

**Interfaces:**
- Consumes: all valid human labels, sample scope flags, and full source pool counts.
- Produces: redacted overall/group summaries, confusion counts, Wilson interval, and one eligibility per group.
- Contract: pack completion and group eligibility are separate; a fully reviewed but weak group is `ROLE_INSUFFICIENT`.

- [ ] **Step 1: Lock exact metric definitions in tests**

For non-excluded rows:

```text
true_functional_confirmed =
  machine functional_confirmed AND human functional_confirmed

false_confirmation =
  machine functional_confirmed AND human present_nonfunctional

unresolved_positive =
  machine functional_confirmed AND human uncertain

false_exclusion =
  machine present_nonfunctional AND human functional_confirmed

overconfident_decision =
  machine in {functional_confirmed,present_nonfunctional} AND human uncertain

avoidable_unverifiable =
  machine unverifiable AND human in {functional_confirmed,present_nonfunctional}
```

Define:

```text
positive_precision =
  true_functional_confirmed / positive_audit_machine_functional_confirmed

decidable_agreement_rate =
  equal machine/human decisive verdicts / rows where both are decisive

decision_coverage =
  machine decisive rows / all non-excluded audited rows

unverifiable_rate =
  machine unverifiable rows / all non-excluded audited rows

human_uncertainty_rate =
  human uncertain rows / all non-excluded audited rows
```

When a denominator is zero, return `null`, never `0`.

- [ ] **Step 2: Write the eligibility and metric tests**

Add:

- `test_wilson_35_of_35_lower_is_09010990076755959`
- `test_all_clean_complete_groups_are_role_eligible`
- `test_pack_can_be_complete_with_a_role_insufficient_group`
- `test_positive_pool_or_sample_below_35_is_insufficient`
- `test_one_false_confirmation_is_insufficient`
- `test_one_false_exclusion_is_insufficient`
- `test_one_unresolved_positive_is_insufficient`
- `test_one_overconfident_machine_decision_is_insufficient`
- `test_general_audit_conflict_is_insufficient_even_outside_positive_scope`
- `test_wilson_lower_below_point_nine_is_insufficient`
- `test_zero_addressable_products_is_insufficient`
- `test_avoidable_unverifiable_reduces_coverage_without_becoming_false_positive`
- `test_uncertain_is_reported_separately_from_incorrect`
- `test_excluded_mapping_errors_are_not_metric_denominators`
- `test_summary_contains_no_product_names_raw_text_excerpts_notes_or_reviewer_ids`

Assert the reused `wilson_interval(35, 35).lower` with `pytest.approx(0.9010990076755959)`.

- [ ] **Step 3: Run the metric tests and verify RED**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_functional_role_review.py -q
```

Expected: failures identify missing metrics and eligibility calculation.

- [ ] **Step 4: Implement group summaries and reasoned eligibility**

Each group summary includes counts, rates, the full 3×4 machine/human confusion matrix, `positive_precision_wilson_95`, `addressable_product_count`, `eligibility`, and a sorted tuple of any of these reason codes:

```text
POSITIVE_POOL_TOO_SMALL
POSITIVE_SAMPLE_TOO_SMALL
GENERAL_AUDIT_CONFLICT
FALSE_CONFIRMATION
FALSE_EXCLUSION
UNRESOLVED_POSITIVE
OVERCONFIDENT_DECISION
POSITIVE_WILSON_BELOW_THRESHOLD
NO_ADDRESSABLE_PRODUCTS
```

`ROLE_ELIGIBLE` requires no reason codes, exactly 20 evaluable general rows, at least 35 audited machine positives, Wilson lower at least `0.90`, and positive addressable count. All other complete groups are `ROLE_INSUFFICIENT`.

The overall summary contains only contract version, input/pack hashes, generation and validation times, row and verdict counts, group summaries, and downstream blocking constants. It excludes product fields, excerpts, notes, reviewer identifiers, and raw labels.

- [ ] **Step 5: Run focused tests, prove the independent Wilson value, and commit**

```powershell
.venv\Scripts\python.exe -c "from claimledger.product_review import wilson_interval; print(wilson_interval(35, 35).lower)"
.venv\Scripts\python.exe -m pytest `
  tests\test_functional_role_review.py `
  tests\test_product_review.py -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
git add src\claimledger\functional_role_review.py tests\test_functional_role_review.py
git diff --cached --check
git commit -m "feat: gate functional roles by measured accuracy"
```

Expected Wilson output: `0.9010990076755959`.

---

### Task 9: Add the Validation CLI and Atomic Redacted Summary

**Files:**
- Create: `scripts/validate_functional_role_review.py`
- Modify: `tests/test_functional_role_review.py`

**Interfaces:**
- Consumes: the same four input paths as the package validator and an optional summary path.
- Produces: JSON to stdout, exit `0/2/3`, and an atomic summary file only for the current `COMPLETE` result.
- Contract: PENDING or INVALID never overwrites a prior file and stdout contains no raw product evidence.

- [ ] **Step 1: Write failing CLI tests**

Add:

- `test_validate_cli_exit_codes_are_complete_zero_pending_two_invalid_three`
- `test_validate_cli_prints_the_exact_result_as_sorted_utf8_json`
- `test_validate_cli_writes_summary_only_for_complete`
- `test_pending_or_invalid_does_not_create_or_overwrite_summary_output`
- `test_complete_summary_replaces_atomically_and_leaves_no_temp_file`
- `test_write_failure_cleans_the_temp_file_and_preserves_previous_summary`
- `test_cli_summary_contains_no_product_text_excerpt_note_or_reviewer`

Use a preexisting sentinel summary in the non-COMPLETE tests and assert its bytes remain unchanged. This avoids deleting an arbitrary user-provided path while proving the current run did not publish success.

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_functional_role_review.py -q
```

Expected: import or behavior failures identify the missing CLI.

- [ ] **Step 3: Implement CLI arguments and atomic write**

Arguments:

```text
--pack-dir PATH
--source-export PATH
--product-review-pack PATH
--rules PATH
--summary-output PATH
```

Use:

```python
EXIT_CODES = {
    ReviewGateStatus.COMPLETE: 0,
    ReviewGateStatus.PENDING: 2,
    ReviewGateStatus.INVALID: 3,
}
```

Serialize `result.model_dump(mode="json")` with sorted keys and one terminal newline. For COMPLETE only, create the temporary path with `path.with_name(f".{path.name}.{uuid4().hex}.tmp")` in the same directory and call `os.replace`; always remove that temporary path in `finally`.

- [ ] **Step 4: Run focused tests, Ruff, and commit**

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\test_functional_role_review.py `
  tests\test_product_review.py -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
git add scripts\validate_functional_role_review.py tests\test_functional_role_review.py
git diff --cached --check
git commit -m "feat: expose functional role validation CLI"
```

---

### Task 10: Acquire the Current Official Standard and Build the Real Rule Registry

**Files:**
- Create: `data/reference/functional-role-rules-v1.json`
- Local only: `build/functional-role-sources-v1/`
- Modify when extraction rules need regression coverage: `tests/test_functional_role.py`

**Interfaces:**
- Consumes: the current official MFDS `건강기능식품의 기준 및 규격` notice and attachment.
- Produces: one tracked five-rule registry whose values are literal extractions with locators and source hash.
- Contract: search snippets and this plan's synthetic phrases are not evidence for the real file.

- [ ] **Step 1: Re-verify the current official notice on execution day**

Open the official MFDS page:

`https://www.mfds.go.kr/brd/m_205/view.do?company_cd=&company_nm=&itm_seq_1=0&itm_seq_2=0&multi_itm_seq=0&page=2&seq=14973&srchFr=&srchTo=&srchTp=&srchWord=`

Confirm on the official page itself:

- title `건강기능식품의 기준 및 규격`;
- notice number `제2026-43호`;
- notice date `2026-06-11`;
- an accessible current full-text attachment;
- no newer effective notice superseding it.

If any item differs, use the newer official effective notice and record its actual metadata. Do not use an administrative preview or search-result text as the registry source.

- [ ] **Step 2: Preserve the official source locally and hash it**

Create only `build/functional-role-sources-v1/`, download the official attachment there, preserve its original filename, and compute:

```powershell
$officialSourceFiles = @(
  Get-ChildItem -LiteralPath 'build\functional-role-sources-v1' -File
)
if ($officialSourceFiles.Count -ne 1) {
  throw 'Expected exactly one verified official source attachment.'
}
Get-FileHash -Algorithm SHA256 -LiteralPath $officialSourceFiles[0].FullName
```

The directory is already ignored through `build/`. Never commit the archive, HWP/HWPX/PDF, extracted XML, or converted text.

- [ ] **Step 3: Extract and double-check exactly five rule records**

For each comparison group, copy only:

- canonical ingredient heading;
- accepted functional raw-material form expressions;
- recognized function text expressions;
- explicit nonfunctional forms only when the official source directly labels that role;
- an explicit-target policy: set `require_explicit_target_wording=true` when official function
  text overlaps another ingredient and target attribution otherwise produces an observed false
  confirmation;
- section/table/item locator sufficient for a second reader to find the same text.

Populate every provenance field from the same official source. `content_sha256` is the downloaded attachment hash, not a hash of generated JSON. `extracted_by` identifies the person who performed the extraction. `reviewed_by` identifies the person who performed the deliberate second check, and `reviewed_at_iso8601` records that check time; neither is inferred from file metadata.

Do not copy `홍삼향분말` or `스테아린산 마그네슘` into `known_nonfunctional_forms` merely because the synthetic tests contain them. Add either only when the official source directly supports the nonfunctional interpretation. Otherwise leave the tuple empty and let the classifier return `unverifiable`.

- [ ] **Step 4: Apply the mandatory human/source checkpoint**

For any phrase whose scope, combination-product applicability, or locator is ambiguous, present the exact short excerpt and locator to the user and pause that rule as `BLOCKED_EXPERT_REVIEW`. If the attachment cannot be opened or hashed, report `BLOCKED_SOURCE_UNAVAILABLE`.

The tracked registry is created only when all five groups pass this checkpoint. It must never contain `proposed`, `expired`, guessed, blank, or synthetic rule values.

- [ ] **Step 5: Validate the real registry and run adversarial classifier cases**

Run with the actual verification time:

```powershell
.venv\Scripts\python.exe -c "from datetime import UTC, datetime; from pathlib import Path; from claimledger.functional_role import load_functional_role_registry; registry = load_functional_role_registry(Path(r'data/reference/functional-role-rules-v1.json'), evaluated_at=datetime.now(UTC)); print(registry.contract_version, len(registry.rules))"
.venv\Scripts\python.exe -m pytest tests\test_functional_role.py -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
git check-ignore -v build\functional-role-sources-v1\*
git status --short
```

Expected: `functional-role-rules-v1 5`; all tests pass; official source files are ignored; only the real registry and any justified regression-test edit are tracked.

- [ ] **Step 6: Commit the verified registry**

Before staging, inspect the complete JSON and verify no secret, full product record, or unsupported phrase is present. Then:

```powershell
git add data\reference\functional-role-rules-v1.json tests\test_functional_role.py
git diff --cached --check
git commit -m "data: register verified functional role rules"
```

If `tests/test_functional_role.py` was not changed in this task, omit it from `git add`.

---

### Task 11: Generate the Real Pack, Prove PENDING, and Synchronize Project Evidence

**Files:**
- Local only: `build/functional-role-review-v1/README.md`
- Local only: `build/functional-role-review-v1/manifest.json`
- Local only: `build/functional-role-review-v1/samples.csv`
- Local only: `build/functional-role-review-v1/functional_role_labels.csv`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/CODEX_HANDOFF.md`
- Modify: `docs/evidence/PHASE_1_EXTENSION_REVIEW.md`

**Interfaces:**
- Consumes: actual source export, completed v2 pack, and verified rule registry.
- Produces: the first real local role pack and tracked evidence of its exact PENDING boundary.
- Contract: no role is declared eligible before people finish every selected row.

- [ ] **Step 1: Record pre-build v2 hashes**

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath `
  'build\extension-review-v2\manifest.json', `
  'build\extension-review-v2\samples.csv', `
  'build\extension-review-v2\product_review_labels.csv', `
  'data\c003-products.jsonl', `
  'data\reference\functional-role-rules-v1.json'
```

Verify the v2 labels hash still equals `A00B3C1A038DBFD06484A89A6C1B41AAA63837D3BD87FAC29E2AF5DF0E011CC1`.

- [ ] **Step 2: Generate the pack once**

```powershell
.venv\Scripts\python.exe scripts\build_functional_role_review.py `
  --source-export data\c003-products.jsonl `
  --product-review-pack build\extension-review-v2 `
  --rules data\reference\functional-role-rules-v1.json `
  --output-dir build\functional-role-review-v1
```

Expected: exit `0`, exactly four files, and no tracked build artifact. If the positive pool for any group is smaller than 35, preserve the observed count; do not loosen the rule or resample.

- [ ] **Step 3: Validate the untouched template and capture the real exit**

```powershell
.venv\Scripts\python.exe scripts\validate_functional_role_review.py `
  --pack-dir build\functional-role-review-v1 `
  --source-export data\c003-products.jsonl `
  --product-review-pack build\extension-review-v2 `
  --rules data\reference\functional-role-rules-v1.json
$roleValidatorExit = $LASTEXITCODE
```

Expected: `PENDING`, exit `2`, exact valid/pending counts that sum to the generated label-row count, and downstream `NOT_MEASURED/BLOCKED/false`. The inherited mapping-error row is valid at creation; therefore do not predetermine `valid=0`.

- [ ] **Step 4: Prove preservation, uniqueness, and ignored status**

Run the focused integration tests and inspect generated facts:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_functional_role_review.py -q
Get-FileHash -Algorithm SHA256 -LiteralPath `
  'build\functional-role-review-v1\manifest.json', `
  'build\functional-role-review-v1\samples.csv', `
  'build\functional-role-review-v1\functional_role_labels.csv'
git check-ignore -v build\functional-role-review-v1\manifest.json
git status --short
```

Use the tested comparison helper to assert the first 100 sample keys and six source product fields equal v2. Do not rely on visual inspection of CSV.

- [ ] **Step 5: Update project documentation with observed values only**

Record:

- rule source ID, notice date, official URL, retrieval/check time, and source hash;
- real total sample and label count;
- per-group original, inherited-error, replacement, positive-pool, positive-sample, and unique-row counts;
- all three pack file hashes plus every bound input hash;
- actual validator `PENDING` counts and exit `2`;
- no eligibility result yet;
- advertising `NOT_MEASURED`, recommendation `BLOCKED`, finalized `false`;
- next action: human role review, not advertisement scoring or final selection.

- [ ] **Step 6: Run the complete project verification**

```powershell
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
git status --short --branch
```

Expected: all tests pass; coverage does not regress below the current 97%; Ruff and diff checks pass; generated directories remain ignored. Report exact fresh counts.

- [ ] **Step 7: Commit the PENDING evidence**

```powershell
git add README.md AGENTS.md docs\CODEX_HANDOFF.md docs\evidence\PHASE_1_EXTENSION_REVIEW.md
git diff --cached --check
git commit -m "docs: record functional role review readiness"
```

---

### Task 12: Complete Human Review, Publish the Redacted Summary, and Sync the Wiki

**Files:**
- Local human input: `build/functional-role-review-v1/functional_role_labels.csv`
- Create only on COMPLETE: `docs/evidence/functional-role-summary-v1.json`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/CODEX_HANDOFF.md`
- Modify: `docs/evidence/PHASE_1_EXTENSION_REVIEW.md`
- Modify: `%USERPROFILE%\Desktop\AI-Agent-Wiki\AI-Sessions\wiki\projects\근거있어.md`
- Modify: `%USERPROFILE%\Desktop\AI-Agent-Wiki\AI-Sessions\conversations\2026-08-22-근거있어-코덱스-핸드오프.md`
- Modify: `%USERPROFILE%\Desktop\AI-Agent-Wiki\index.md`
- Modify: `%USERPROFILE%\Desktop\AI-Agent-Wiki\log.md`

**Interfaces:**
- Consumes: every sampled product row, its machine decision, literal source fields, active rule, and human judgment.
- Produces: completed local labels, a redacted tracked summary, documented role eligibility, and a separate wiki commit.
- Contract: a false confirmation, unresolved positive, false exclusion, overconfident decision, small pool, or low Wilson bound remains visible and blocks that group.

- [ ] **Step 1: Review in deterministic batches without changing machine columns**

For each row, lock `group`, `report_no`, `audit_round`, `machine_verdict`, and `rule_version`. Fill only the six human-controlled fields:

```text
human_verdict,reason_code,evidence_field,evidence_excerpt,review_note,reviewer,reviewed_at_iso8601
```

Use the row's exact `raw_materials`, `primary_function`, and bound official rule. The agent may prepare candidate excerpts, but the user or designated reviewer confirms the verdict. When linkage remains ambiguous, use `uncertain`; do not choose the machine verdict merely to improve a metric.

- [ ] **Step 2: Validate after each batch**

```powershell
.venv\Scripts\python.exe scripts\validate_functional_role_review.py `
  --pack-dir build\functional-role-review-v1 `
  --source-export data\c003-products.jsonl `
  --product-review-pack build\extension-review-v2 `
  --rules data\reference\functional-role-rules-v1.json
```

- Exit `2/PENDING`: continue from the reported pending rows.
- Exit `3/INVALID`: repair only the listed row/contract problem; never bulk-reset labels.
- Exit `0/COMPLETE`: proceed to summary publication.

If the same source ambiguity recurs and requires professional interpretation, preserve `uncertain` and continue. This can produce `ROLE_INSUFFICIENT` without making the pack invalid.

- [ ] **Step 3: Publish only a COMPLETE redacted summary**

First remove no files and run to a fresh temporary destination:

```powershell
.venv\Scripts\python.exe scripts\validate_functional_role_review.py `
  --pack-dir build\functional-role-review-v1 `
  --source-export data\c003-products.jsonl `
  --product-review-pack build\extension-review-v2 `
  --rules data\reference\functional-role-rules-v1.json `
  --summary-output docs\evidence\functional-role-summary-v1.json
```

Require exit `0` and then scan the summary to prove it has no `name`, `company`, `raw_materials`, `primary_function`, `evidence_excerpt`, `review_note`, `reviewer`, API-key pattern, or formula prefix. If status is not COMPLETE, the tracked summary must not exist.

- [ ] **Step 4: Evaluate results without relabeling to pass**

For each group, report:

- positive pool/sample and Wilson interval;
- false confirmation, false exclusion, unresolved positive, overconfident, and avoidable-unverifiable counts;
- general audit conflicts and human uncertainty;
- `ROLE_ELIGIBLE` or `ROLE_INSUFFICIENT`;
- every insufficiency reason code.

If a rule error caused any failed condition, create a new rule version and regenerate a new pack from the beginning. Do not alter labels to make the old rule pass. Preserve the failed pack locally as regression evidence under a versioned ignored directory.

Even if two or more groups are `ROLE_ELIGIBLE`, this task still leaves advertising evidence `NOT_MEASURED`, extension recommendation `BLOCKED`, and finalized `false`. Do not implement B or C here.

- [ ] **Step 5: Update tracked project evidence and commit**

Update the four project documents with exact final hashes, counts, metrics, and group statuses. Then:

```powershell
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
git add `
  README.md `
  AGENTS.md `
  docs\CODEX_HANDOFF.md `
  docs\evidence\PHASE_1_EXTENSION_REVIEW.md `
  docs\evidence\functional-role-summary-v1.json
git diff --cached --check
git commit -m "docs: record measured functional role gate"
```

Report exact fresh test count and coverage, not the pre-plan baseline.

- [ ] **Step 6: Re-read and update the Obsidian wiki**

From `%USERPROFILE%\Desktop\AI-Agent-Wiki`, read `AGENTS.md`, the two target notes, `index.md`, and the tail of `log.md` before editing. Use:

```powershell
git -c safe.directory=%USERPROFILE%/Desktop/AI-Agent-Wiki status --short --branch
```

If unrelated user changes overlap any target, stop before editing that file. Update only verified project facts, the current gate status, per-group eligibility, all downstream blocks, source/rule versions, project commit IDs, and the next task. Update the existing index entry rather than adding a duplicate. Append one dated `save` line to `log.md`.

- [ ] **Step 7: Verify and commit the wiki separately**

```powershell
git -c safe.directory=%USERPROFILE%/Desktop/AI-Agent-Wiki diff --check
git -c safe.directory=%USERPROFILE%/Desktop/AI-Agent-Wiki diff --name-status
git -c safe.directory=%USERPROFILE%/Desktop/AI-Agent-Wiki status --short --branch
git -c safe.directory=%USERPROFILE%/Desktop/AI-Agent-Wiki add -- `
  'AI-Sessions/conversations/2026-08-22-근거있어-코덱스-핸드오프.md' `
  'AI-Sessions/wiki/projects/근거있어.md' `
  'index.md' `
  'log.md'
git -c safe.directory=%USERPROFILE%/Desktop/AI-Agent-Wiki diff --cached --check
git -c safe.directory=%USERPROFILE%/Desktop/AI-Agent-Wiki commit `
  -m "save: record functional role evidence gate"
```

Do not modify global `safe.directory`.

- [ ] **Step 8: Perform final repository proof**

In the project worktree:

```powershell
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
git status --porcelain=v1
git log -12 --oneline
```

Also prove:

- v2 label SHA is unchanged;
- current role pack validator exits `0/COMPLETE`;
- summary SHA and every bound input SHA match;
- generated source and role pack remain ignored;
- project and wiki worktrees are clean;
- no merge, remote mutation, push, PR, or worktree deletion occurred.

- [ ] **Step 9: Report the exact completion boundary**

Report code/data/doc/wiki commits, fresh tests and coverage, registry source and check time, pack size and hashes, per-group metrics and statuses, and unresolved risks. State explicitly:

- A is complete only if the role pack is `COMPLETE`;
- `ROLE_INSUFFICIENT` is a valid measured outcome, not a failed validator;
- B official advertising evidence is not implemented;
- C extension recommendation and final selection remain blocked;
- no expert healthcare or advertising conclusion has been automated.

Do not invoke `finishing-a-development-branch`; broader project work remains.

## Self-Review Checklist

- [x] Every approved §7 A requirement in the design has a task and a named test.
- [x] No B/C implementation, UI, RAG, LangGraph, FastAPI, React, or LLM verdict entered scope.
- [x] v2 exact files and downstream blocking constants remain immutable.
- [x] Product identity, rule source, source locator, retrieval/check time, rule version, and all hashes are bound.
- [x] General 20, inherited-error replacement, positive 35, uniqueness, overlap, and input-order invariance are explicit.
- [x] `functional_confirmed`, `present_nonfunctional`, `unverifiable`, all four human verdicts, and reason compatibility are explicit.
- [x] Wilson threshold, zero-error conditions, small-pool handling, and addressable count are explicit.
- [x] PENDING, INVALID, COMPLETE, ROLE_ELIGIBLE, and ROLE_INSUFFICIENT are not conflated.
- [x] Secret, formula, future-time, URL-host, stale-rule, source mutation, and CSV mutation tests exist.
- [x] COMPLETE summary contains no product text, evidence excerpt, note, or reviewer identifier.
- [x] Every implementation task has RED, GREEN, regression, verification, and commit steps.
- [x] There is no unresolved marker, omitted interface, guessed official phrase, or unbounded error-handling step.

## Execution Handoff

Execute tasks strictly in numeric order. Stop only at a documented fail-closed source/expert checkpoint or when user judgment is materially required. The recommended execution method is subagent-driven development with a review after each task; inline execution is the supported alternative.
