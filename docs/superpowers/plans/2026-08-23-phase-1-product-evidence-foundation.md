# Phase 1 Product Evidence Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tested, fail-closed vertical slice that normalizes C003 products, presents deterministic product candidates for user confirmation, maps the three core and five comparison ingredients with auditable rules, structures official functions and cautions, and produces reproducible extension-candidate and evaluation reports.

**Architecture:** Keep C003 transport/parsing separate from pure product normalization, candidate search, ingredient mapping, official-statement parsing, and reporting. Each pure module consumes immutable Pydantic models and returns explicit verified, ambiguous, or unverifiable states; no search or mapping function may produce a confirmed product. A vertical-slice service composes these modules and requires `ConfirmedProduct` before exposing product-level evidence.

**Tech Stack:** Python 3.12, Pydantic 2, httpx, pytest 8, pytest-cov, Ruff, standard-library `csv`, `hashlib`, `json`, `random`, and `unicodedata`.

## Global Constraints

- Work only in the `phase-0-c003-data-gate` worktree; do not merge to `main` or push.
- Use C003 `report_no` as the canonical product identifier.
- Product name and company normalization may rank candidates but may never confirm identity.
- Missing or conflicting required data must become `ambiguous` or `unverifiable`; never infer a positive result.
- Keep public verdict values exactly `confirmed`, `mismatch`, `insufficient`, `unverifiable`, and `contradicted`.
- LLMs and live external APIs are not required by the default test suite.
- Preserve source identifier, retrieval time, normalization or rule version, and matched source text.
- Do not store API keys, raw live API responses, user health details, reviews, or Q&A in fixtures or reports.
- A `SafetySignal` is general official information only and must always have `is_safety_clearance == false`.
- Every implementation task follows red, green, refactor, full verification, and a focused commit.
- Before every commit run the task test, the complete test suite, Ruff, `git diff --check`, and a secret-pattern scan over staged files.

## Scope Boundary and Follow-up Plans

This plan covers the first independently reviewable subsystem from the approved product MVP design. It deliberately does not scaffold FastAPI, React, OCR, URL crawling, LLM claim extraction, or scientific-paper RAG.

After this plan passes its review gate, create separate plans in this order:

1. Phase 2: image OCR, immutable source spans, and user confirmation.
2. Phase 3: isolated seller-page URL ingestion, origin classification, and SSRF defenses.
3. Phase 4: LLM atomic-claim extraction and claim confirmation.
4. Phase 5: scientific RAG and evidence-applicability classification.
5. Phase 6: complete deterministic verdict rules and frozen evaluation set.
6. Phase 7: FastAPI workflow, persistence, auth, audit events, and SSE.
7. Phase 8: React confirmation flow, evidence receipt, accessibility, and comprehension tests.
8. Phase 9: end-to-end hardening and staged release gates.

---

## File Map

### Existing files to modify

- `src/claimledger/domain.py`: shared immutable domain models and stable enums.
- `src/claimledger/identity.py`: user-confirmed candidate boundary only.
- `src/claimledger/decision.py`: product-evidence readiness gate; no full ad verdict expansion yet.
- `src/claimledger/evaluation.py`: false-clearance and confirmed-recall metrics.
- `src/claimledger/sources/food_safety.py`: C003 transport and strict source parsing only.
- `docs/CODEX_HANDOFF.md`: verified Phase 1 outcome after all tasks pass.

### Files to create

- `src/claimledger/products.py`: deterministic text normalization, search documents, and candidate ranking.
- `src/claimledger/ingredients.py`: versioned ingredient lexicon and auditable mapping.
- `src/claimledger/official.py`: official function and caution parsing without semantic invention.
- `src/claimledger/product_evidence.py`: vertical-slice composition and readiness result.
- `src/claimledger/safety.py`: official caution signals that cannot express clearance.
- `src/claimledger/extension_selection.py`: deterministic comparison-pool scoring and sample selection.
- `scripts/build_extension_review.py`: offline CSV/Markdown review-pack generator.
- `tests/fixtures/product_records.json`: synthetic, secret-free product fixtures covering core and comparison ingredients.
- `tests/fixtures/extension_review_labels.csv`: reviewer-label template with explicit allowed values.
- `tests/test_products.py`: normalization and candidate search tests.
- `tests/test_ingredients.py`: verified, ambiguous, and unverifiable mapping tests.
- `tests/test_official.py`: official function and caution preservation tests.
- `tests/test_product_evidence.py`: composed fail-closed vertical-slice tests.
- `tests/test_safety.py`: no-clearance safety invariant tests.
- `tests/test_extension_selection.py`: deterministic sample and scoring tests.
- `tests/test_evaluation_dataset.py`: frozen-evaluation manifest and metric tests.
- `docs/evidence/PHASE_1_EXTENSION_REVIEW.md`: generated comparison-pool review summary after real review data exists.

---

### Task 1: Lock Evaluation Contracts and Dataset Manifest

**Files:**
- Modify: `src/claimledger/domain.py`
- Modify: `src/claimledger/evaluation.py`
- Create: `tests/test_evaluation_dataset.py`
- Modify: `tests/test_evaluation.py`

**Interfaces:**
- Consumes: existing `Verdict` enum.
- Produces: `EvaluationCase`, `EvaluationSummary`, `evaluate_verdicts(cases, actual)`, and `confirmed_recall(expected, actual)`.

- [ ] **Step 1: Write the failing domain and metric tests**

```python
from claimledger.domain import EvaluationCase, Verdict
from claimledger.evaluation import confirmed_recall, evaluate_verdicts


def test_evaluation_case_requires_frozen_identity_and_expected_verdict() -> None:
    case = EvaluationCase(
        case_id="core-lutein-001",
        ingredient_group="lutein_zeaxanthin",
        expected_verdict=Verdict.MISMATCH,
        frozen=True,
    )
    assert case.frozen is True


def test_evaluation_reports_false_clearance_recall_and_coverage_separately() -> None:
    cases = [
        EvaluationCase(case_id="a", ingredient_group="omega3", expected_verdict=Verdict.CONFIRMED, frozen=True),
        EvaluationCase(case_id="b", ingredient_group="omega3", expected_verdict=Verdict.MISMATCH, frozen=True),
        EvaluationCase(case_id="c", ingredient_group="omega3", expected_verdict=Verdict.UNVERIFIABLE, frozen=True),
    ]
    summary = evaluate_verdicts(
        cases,
        [Verdict.CONFIRMED, Verdict.UNVERIFIABLE, Verdict.UNVERIFIABLE],
    )
    assert summary.false_clearance_rate == 0.0
    assert summary.confirmed_recall == 1.0
    assert summary.coverage == 2 / 3
    assert summary.unverifiable_count == 2
```

- [ ] **Step 2: Run the focused tests and confirm red**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_evaluation.py tests\test_evaluation_dataset.py -q
```

Expected: collection fails because `EvaluationCase`, `EvaluationSummary`, `confirmed_recall`, and `evaluate_verdicts` do not exist.

- [ ] **Step 3: Add immutable evaluation models and pure metrics**

Add to `domain.py`:

```python
class EvaluationCase(BaseModel):
    model_config = {"frozen": True}
    case_id: NonBlankText
    ingredient_group: NonBlankText
    expected_verdict: Verdict
    frozen: Literal[True]


class EvaluationSummary(BaseModel):
    model_config = {"frozen": True}
    sample_size: int
    false_clearance_rate: float
    confirmed_recall: float
    coverage: float
    unverifiable_count: int
```

Implement `confirmed_recall` as confirmed predictions divided by expected confirmed cases, returning `0.0` when the denominator is zero. Implement coverage as the fraction whose actual verdict is not `UNVERIFIABLE`. Reject empty input, duplicate case IDs, length mismatches, and any non-frozen case.

- [ ] **Step 4: Run focused and full verification**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_evaluation.py tests\test_evaluation_dataset.py -q
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
```

Expected: all commands pass; evaluation output exposes harmful errors, recall, coverage, and unverifiable count separately.

- [ ] **Step 5: Commit the evaluation contract**

```cmd
git add src\claimledger\domain.py src\claimledger\evaluation.py tests\test_evaluation.py tests\test_evaluation_dataset.py
git commit -m "feat: define frozen evaluation contracts"
```

---

### Task 2: Normalize Product Search Without Auto-confirmation

**Files:**
- Modify: `src/claimledger/domain.py`
- Create: `src/claimledger/products.py`
- Create: `tests/test_products.py`
- Create: `tests/fixtures/product_records.json`

**Interfaces:**
- Consumes: `ProductCandidate` from C003 parsing.
- Produces: `ProductSearchDocument`, `ProductSearchResult`, `normalize_search_text(text)`, `build_search_document(product)`, and `search_products(products, query, limit=10)`.

- [ ] **Step 1: Add failing normalization and ranking tests**

```python
def test_normalization_preserves_digits_but_unifies_spacing_and_width() -> None:
    assert normalize_search_text(" 오메가－3  1000 mg ") == "오메가-3 1000 mg"


def test_search_returns_candidates_without_confirming_identity() -> None:
    results = search_products([PRODUCT_A, PRODUCT_B], "테스트 제조사 오메가3")
    assert results[0].candidate.report_no == PRODUCT_A.report_no
    assert results[0].matched_fields == ("name", "company")
    assert not hasattr(results[0], "confirmed_by_user")


def test_blank_query_and_tied_identity_are_not_guessed() -> None:
    with pytest.raises(ValueError, match="query"):
        search_products([PRODUCT_A], " ")
    tied = search_products([PRODUCT_A, PRODUCT_A.model_copy(update={"report_no": "B"})], "오메가3")
    assert [item.candidate.report_no for item in tied] == ["A", "B"]
```

- [ ] **Step 2: Run the focused test and confirm red**

Run: `.venv\Scripts\python.exe -m pytest tests\test_products.py -q`

Expected: import fails because `claimledger.products` does not exist.

- [ ] **Step 3: Implement deterministic normalization and ranking**

Use Unicode NFKC normalization, trim and collapse whitespace, case-fold Latin text, and preserve digits, dosage units, punctuation relevant to product identity, and original source strings. Rank exact report number first, then exact normalized name plus company, then token overlap. Use report number as the final deterministic tie-breaker. Return evidence of matched fields and the constant `normalization_version="product-search-v1"`; never return `ConfirmedProduct`.

- [ ] **Step 4: Verify normalization edge cases and the full suite**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_products.py tests\test_identity.py -q
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
```

Expected: candidate ranking is stable across repeated runs and user confirmation remains exclusively in `identity.confirm_candidate`.

- [ ] **Step 5: Commit product search**

```cmd
git add src\claimledger\domain.py src\claimledger\products.py tests\test_products.py tests\fixtures\product_records.json
git commit -m "feat: rank product candidates deterministically"
```

---

### Task 3: Add Auditable Ingredient Mapping

**Files:**
- Modify: `src/claimledger/domain.py`
- Create: `src/claimledger/ingredients.py`
- Create: `tests/test_ingredients.py`

**Interfaces:**
- Consumes: `ProductCandidate` and normalized source fields.
- Produces: `IngredientGroup`, `MappingStatus`, `IngredientMatchEvidence`, `IngredientMapping`, and `map_ingredients(product)`.

- [ ] **Step 1: Write failing verified, ambiguous, and unverifiable tests**

```python
def test_mapping_records_exact_source_field_text_and_rule_version() -> None:
    mapping = map_ingredients(LUTEIN_PRODUCT)
    assert mapping.status is MappingStatus.VERIFIED
    assert mapping.groups == (IngredientGroup.LUTEIN_ZEAXANTHIN,)
    assert mapping.evidence[0].source_field == "raw_materials"
    assert mapping.evidence[0].matched_text == "루테인지아잔틴복합추출물"
    assert mapping.rule_version == "ingredient-map-v1"


def test_multiple_incompatible_groups_are_ambiguous_not_inferred() -> None:
    mapping = map_ingredients(MIXED_PRODUCT)
    assert mapping.status is MappingStatus.AMBIGUOUS


def test_missing_source_fields_are_unverifiable() -> None:
    mapping = map_ingredients(MISSING_PRODUCT)
    assert mapping.status is MappingStatus.UNVERIFIABLE
```

- [ ] **Step 2: Run the focused test and confirm red**

Run: `.venv\Scripts\python.exe -m pytest tests\test_ingredients.py -q`

Expected: import fails because ingredient mapping types do not exist.

- [ ] **Step 3: Implement the versioned lexicon and mapping state machine**

Define exactly eight groups: `lutein_zeaxanthin`, `omega3`, `probiotics`, `milk_thistle`, `vitamin_d`, `red_ginseng`, `coenzyme_q10`, and `magnesium`. Match only explicit, reviewed Korean and English aliases in product name, official function, and raw materials. Store every matched field and literal source span. If no required source text exists return `UNVERIFIABLE`; if matches cannot establish one reviewable group return `AMBIGUOUS`; otherwise return `VERIFIED`. Do not treat substring coverage as clinical equivalence.

- [ ] **Step 4: Verify false-positive guard cases and full suite**

Include fixtures where `DHA` appears only in unrelated prose, generic `유산균` and explicit `프로바이오틱스` differ, and `홍삼맛` is not sufficient to verify red ginseng functional ingredient mapping.

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_ingredients.py -q
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
```

- [ ] **Step 5: Commit ingredient mapping**

```cmd
git add src\claimledger\domain.py src\claimledger\ingredients.py tests\test_ingredients.py
git commit -m "feat: map ingredient groups with audit evidence"
```

---

### Task 4: Structure Official Functions Without Inventing Meaning

**Files:**
- Modify: `src/claimledger/domain.py`
- Create: `src/claimledger/official.py`
- Create: `tests/test_official.py`

**Interfaces:**
- Consumes: `ProductCandidate.primary_function`, `raw_materials`, and `intake_method`.
- Produces: `OfficialFieldStatus`, `OfficialFunctionStatement`, `OfficialProductCaution`, `parse_official_functions(product)`, and `extract_official_cautions(product)`.

- [ ] **Step 1: Write failing preservation and missing-data tests**

```python
def test_official_function_preserves_literal_text_and_expression_strength() -> None:
    statements = parse_official_functions(PRODUCT)
    assert statements[0].original_text == "눈 건강에 도움을 줄 수 있음"
    assert statements[0].effect_key == "eye_health_support"
    assert statements[0].expression_strength == "support"
    assert statements[0].parser_version == "official-function-v1"


def test_unknown_wording_is_unverifiable_not_rewritten() -> None:
    result = parse_official_functions(UNKNOWN_FUNCTION_PRODUCT)
    assert result[0].status is OfficialFieldStatus.UNVERIFIABLE
    assert result[0].original_text == UNKNOWN_FUNCTION_PRODUCT.primary_function


def test_blank_required_fields_remain_explicitly_missing() -> None:
    assert parse_official_functions(MISSING_FUNCTION_PRODUCT)[0].status is OfficialFieldStatus.MISSING
```

- [ ] **Step 2: Run the focused test and confirm red**

Run: `.venv\Scripts\python.exe -m pytest tests\test_official.py -q`

Expected: import fails because `claimledger.official` does not exist.

- [ ] **Step 3: Implement rule-first parsing**

Split source text only on reviewed delimiters, retain each literal segment, and recognize a minimal vocabulary needed for the three core groups. Map expression strength to `possibility`, `support`, `improvement`, `guarantee`, or `treatment_prevention`. Unknown or malformed text remains `UNVERIFIABLE`; blank text remains `MISSING`. Do not summarize or paraphrase source text in this task.

- [ ] **Step 4: Verify exact text preservation and full suite**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_official.py tests\test_food_safety.py -q
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
```

- [ ] **Step 5: Commit official statement parsing**

```cmd
git add src\claimledger\domain.py src\claimledger\official.py tests\test_official.py
git commit -m "feat: structure official product statements"
```

---

### Task 5: Enforce General Caution Signals Without Safety Clearance

**Files:**
- Modify: `src/claimledger/domain.py`
- Create: `src/claimledger/safety.py`
- Create: `tests/test_safety.py`

**Interfaces:**
- Consumes: `ConfirmedProduct`, `OfficialProductCaution`, and source-backed `InteractionEvidence`.
- Produces: `SafetySignal` and `build_safety_signals(product, product_cautions, interaction_evidence)`.

- [ ] **Step 1: Write failing no-clearance and source-required tests**

```python
def test_safety_signal_can_never_express_clearance() -> None:
    signal = SafetySignal(
        kind="official_product_caution",
        message="의약품 복용 시 전문가와 상담하십시오.",
        source_id="C003",
        source_url="https://example.test/official/TEST-0001",
        retrieved_at=NOW,
    )
    assert signal.is_safety_clearance is False
    with pytest.raises(ValidationError):
        SafetySignal(
            kind="official_product_caution",
            message="의약품 복용 시 전문가와 상담하십시오.",
            source_id="C003",
            source_url="https://example.test/official/TEST-0001",
            retrieved_at=NOW,
            is_safety_clearance=True,
        )


def test_absent_interaction_evidence_does_not_create_no_interaction_message() -> None:
    assert build_safety_signals(CONFIRMED_PRODUCT, [], []) == ()
```

- [ ] **Step 2: Run the focused test and confirm red**

Run: `.venv\Scripts\python.exe -m pytest tests\test_safety.py -q`

Expected: import or model construction fails because the safety module is absent.

- [ ] **Step 3: Implement immutable source-backed safety models**

Set `is_safety_clearance: Literal[False] = False`. Require nonblank source identifier, source URL or official identifier, retrieval time, literal source text, and user-facing message. The builder may surface official warnings but must never emit `safe`, `no interaction`, `can take`, or individualized recommendations. Reject evidence whose product report number conflicts with the confirmed product.

- [ ] **Step 4: Verify prohibited phrases and full suite**

Add a parameterized test over `안전합니다`, `상호작용 없음`, `복용해도 됩니다`, and `부작용이 없습니다` and require model validation to reject them.

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_safety.py -q
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
```

- [ ] **Step 5: Commit safety boundaries**

```cmd
git add src\claimledger\domain.py src\claimledger\safety.py tests\test_safety.py
git commit -m "feat: expose source-backed caution signals"
```

---

### Task 6: Compose the Product Evidence Vertical Slice

**Files:**
- Create: `src/claimledger/product_evidence.py`
- Modify: `src/claimledger/decision.py`
- Create: `tests/test_product_evidence.py`
- Modify: `tests/test_decision.py`

**Interfaces:**
- Consumes: `ConfirmedProduct`, `IngredientMapping`, official functions, official cautions, and safety signals.
- Produces: `ProductEvidenceStatus`, `ProductEvidenceBundle`, `build_product_evidence(product)`, and `require_product_evidence_ready(bundle)`.

- [ ] **Step 1: Write failing vertical-slice tests**

```python
def test_confirmed_product_with_complete_official_data_builds_ready_bundle() -> None:
    bundle = build_product_evidence(CONFIRMED_CORE_PRODUCT)
    assert bundle.status is ProductEvidenceStatus.READY
    assert bundle.report_no == CONFIRMED_CORE_PRODUCT.product.report_no
    assert bundle.ingredient_mapping.status is MappingStatus.VERIFIED
    assert bundle.rule_versions == (
        "ingredient-map-v1",
        "official-function-v1",
    )


@pytest.mark.parametrize("field", ["primary_function", "raw_materials", "intake_method"])
def test_missing_required_official_field_fails_closed(field: str) -> None:
    product = CONFIRMED_CORE_PRODUCT.model_copy(
        update={"product": CONFIRMED_CORE_PRODUCT.product.model_copy(update={field: ""})}
    )
    bundle = build_product_evidence(product)
    assert bundle.status is ProductEvidenceStatus.UNVERIFIABLE
    assert f"MISSING_{field.upper()}" in bundle.reason_codes
```

- [ ] **Step 2: Run the focused tests and confirm red**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_product_evidence.py tests\test_decision.py -q
```

Expected: collection fails because the composed service and readiness types do not exist.

- [ ] **Step 3: Implement fail-closed composition**

`build_product_evidence` accepts only `ConfirmedProduct`. It invokes mapping and official parsers, records all rule versions and source timestamps, and returns `READY`, `AMBIGUOUS`, or `UNVERIFIABLE`. Any missing required core field, ambiguous ingredient mapping, report-number conflict, or unparsed official function prevents readiness. `require_product_evidence_ready` raises a domain error with stable reason codes rather than converting failure to a positive verdict.

Update `decision.py` only enough to require a ready bundle before existing matching evidence can return `CONFIRMED`. Do not implement OCR, claim-strength, or scientific-applicability rules in this phase.

- [ ] **Step 4: Verify the vertical slice and regressions**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_product_evidence.py tests\test_decision.py tests\test_identity.py -q
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
```

Expected: no code path reaches `CONFIRMED` without a user-confirmed product and ready official evidence bundle.

- [ ] **Step 5: Commit the vertical slice**

```cmd
git add src\claimledger\product_evidence.py src\claimledger\decision.py tests\test_product_evidence.py tests\test_decision.py
git commit -m "feat: gate decisions on product evidence readiness"
```

---

### Task 7: Generate a Deterministic Extension Review Pack

**Files:**
- Create: `src/claimledger/extension_selection.py`
- Create: `scripts/build_extension_review.py`
- Create: `tests/test_extension_selection.py`
- Create: `tests/fixtures/extension_review_labels.csv`

**Interfaces:**
- Consumes: parsed `ProductCandidate` records and `IngredientMapping` results.
- Produces: `ExtensionCandidateStats`, `ReviewSample`, `select_review_sample(products, group, size=20, seed=20260823)`, `score_extension_candidate(stats)`, and Markdown/CSV review files.

- [ ] **Step 1: Write failing deterministic sample and balance tests**

```python
def test_review_sample_is_reproducible_and_has_unique_report_numbers() -> None:
    first = select_review_sample(PRODUCTS, IngredientGroup.RED_GINSENG, size=20, seed=20260823)
    second = select_review_sample(PRODUCTS, IngredientGroup.RED_GINSENG, size=20, seed=20260823)
    assert first == second
    assert len({item.report_no for item in first}) == 20


def test_extension_score_keeps_data_risk_diversity_and_feasibility_separate() -> None:
    stats = ExtensionCandidateStats(
        group=IngredientGroup.MILK_THISTLE,
        product_count=100,
        complete_record_rate=0.95,
        verified_mapping_rate=0.90,
        advertising_risk_score=3,
        functional_diversity_score=4,
        implementation_feasibility_score=5,
    )
    scored = score_extension_candidate(stats)
    assert scored.components["data_quality"] == pytest.approx(0.925)
    assert set(scored.components) == {
        "data_quality",
        "advertising_risk",
        "functional_diversity",
        "implementation_feasibility",
    }
```

- [ ] **Step 2: Run the focused test and confirm red**

Run: `.venv\Scripts\python.exe -m pytest tests\test_extension_selection.py -q`

Expected: import fails because the selection module does not exist.

- [ ] **Step 3: Implement reproducible sampling and transparent scoring**

Deduplicate by report number, sort before seeded sampling, and reject pools smaller than the requested sample instead of sampling with replacement. Keep component scores visible and use equal 25% weights for the approved balanced strategy. Human-entered advertising risk, diversity, and feasibility scores must be integers from 1 through 5 with reviewer and reviewed-at fields. The tool recommends one clarity candidate and one high-risk/high-value candidate but does not silently finalize them.

- [ ] **Step 4: Add the offline report command and verify it**

Command contract:

```cmd
.venv\Scripts\python.exe scripts\build_extension_review.py --input data\c003-products.jsonl --output-dir build\extension-review --seed 20260823
```

The script must refuse to run if input is absent, contains duplicate report numbers, contains live API keys, or cannot produce 20 unique samples per comparison group. Generated artifacts under `build/` remain untracked. Only the reviewed, redacted final summary belongs in `docs/evidence/`.

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_extension_selection.py -q
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
```

- [ ] **Step 5: Commit the review-pack generator**

```cmd
git add src\claimledger\extension_selection.py scripts\build_extension_review.py tests\test_extension_selection.py tests\fixtures\extension_review_labels.csv
git commit -m "feat: build deterministic extension review packs"
```

---

### Task 8: Run Live Review Input Preparation Without Committing Raw C003 Data

**Files:**
- Modify: `docs/evidence/PHASE_1_EXTENSION_REVIEW.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: a user-supplied C003 key from the local environment and Task 7's offline generator.
- Produces: an untracked local JSONL dataset, an untracked review pack, and a tracked redacted review summary that clearly distinguishes measured values from pending human labels.

- [ ] **Step 1: Add a failing ignore-policy check**

Run before modifying `.gitignore`:

```cmd
git check-ignore -v data\c003-products.jsonl
```

Expected: exit code 1 and no matching rule, demonstrating that the raw live-data path could be staged accidentally. The existing `/build/` rule already protects generated review packs.

- [ ] **Step 2: Add narrow ignore rules**

Append only these project-local generated paths:

```gitignore
/data/c003-products.jsonl
```

Do not ignore the entire `data/` directory because future redacted fixtures may be intentionally tracked.

- [ ] **Step 3: Verify ignore rules before any live command**

Run:

```cmd
git check-ignore -v data\c003-products.jsonl build\extension-review\samples.csv
```

Expected: the raw JSONL path identifies the new rule and the review-pack path identifies the existing `/build/` rule.

- [ ] **Step 4: Add or extend an export mode with a failing test first**

Add a test to `tests/test_audit_c003.py` proving the live export contains only the six allowed fields `report_no`, `name`, `company`, `primary_function`, `raw_materials`, and `intake_method`, and never contains the API key or response envelope. Then minimally extend `scripts/audit_c003.py` or create a focused exporter invoked by it. Run the test red before implementation and green after implementation.

- [ ] **Step 5: Run the live export only when the key is present**

In CMD, the user or authorized operator runs:

```cmd
set FOOD_SAFETY_API_KEY=your-local-key
.venv\Scripts\python.exe scripts\audit_c003.py --export-products data\c003-products.jsonl
```

Step 4 must make this exact command the tested CLI contract. Do not echo the key and do not redirect raw API output.

- [ ] **Step 6: Generate and inspect the review pack**

Run:

```cmd
.venv\Scripts\python.exe scripts\build_extension_review.py --input data\c003-products.jsonl --output-dir build\extension-review --seed 20260823
```

Inspect that each comparison group has 20 unique report numbers and that no raw API envelope, key, or user data exists. Record measured counts, completeness, mapping states, seed, review status, and unresolved ambiguities in `docs/evidence/PHASE_1_EXTENSION_REVIEW.md`. Do not state final extensions until all 100 samples receive human labels.

- [ ] **Step 7: Verify and commit only policy, exporter code, tests, and redacted summary**

Run:

```cmd
git status --short
git check-ignore -v data\c003-products.jsonl build\extension-review\samples.csv
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
```

Confirm `data/c003-products.jsonl` and `build/extension-review/` are absent from `git status`. Then commit:

```cmd
git add .gitignore scripts\audit_c003.py tests\test_audit_c003.py docs\evidence\PHASE_1_EXTENSION_REVIEW.md
git commit -m "feat: prepare redacted extension review data"
```

---

### Task 9: Phase 1 Verification and Handoff

**Files:**
- Modify: `docs/CODEX_HANDOFF.md`
- Modify: `README.md` only if it currently misstates supported functionality or verification commands.

**Interfaces:**
- Consumes: all Phase 1 implementations and fresh verification output.
- Produces: an evidence-backed handoff that distinguishes implemented code, live measured data, pending human review, and future phases.

- [ ] **Step 1: Run the complete offline verification from a clean prompt**

```cmd
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
git status --short --branch
```

Expected: all tests pass, Ruff and diff checks pass, and only intended handoff edits remain.

- [ ] **Step 2: Run the explicit invariant tests**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_identity.py tests\test_ingredients.py tests\test_official.py tests\test_product_evidence.py tests\test_safety.py tests\test_evaluation_dataset.py -q
```

Expected: all identity, mapping, source-preservation, no-clearance, and evaluation invariants pass.

- [ ] **Step 3: Scan tracked and staged content for prohibited data**

Run a repository-local scan for key-like assignments and health-detail fixture fields. Manually inspect every match; do not treat zero matches from a simplistic regex as proof by itself. Confirm generated live data remains ignored and untracked.

- [ ] **Step 4: Update the handoff with verified facts only**

Record:

- exact test count and coverage from Step 1;
- exact commit range for Phase 1;
- whether the live export ran;
- comparison-group counts and mapping-state rates if measured;
- whether all 100 samples were human-reviewed;
- selected extensions only if the review is complete;
- otherwise, the precise next review action;
- explicit statements that OCR, URL crawling, LLM, RAG, FastAPI, React, auth, merge, and push are not complete.

- [ ] **Step 5: Commit the verified handoff**

```cmd
git add docs\CODEX_HANDOFF.md README.md
git commit -m "docs: record Phase 1 product evidence status"
```

If `README.md` did not need changes, omit it from `git add`.

- [ ] **Step 6: Report without merging or pushing**

Provide the user with:

- worktree and branch status;
- full Phase 1 commit list;
- fresh test, coverage, Ruff, diff, and secret-scan results;
- measured extension-review status;
- any unresolved ambiguity;
- confirmation that `main` is unchanged and no remote push occurred.

Stop for user review before writing or executing the Phase 2 plan.
