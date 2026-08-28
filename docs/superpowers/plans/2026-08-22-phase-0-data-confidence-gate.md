# Phase 0 Data Confidence Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a testable Python data-confidence spike that measures whether the Food Safety Korea `C003` source can support exact product identification and claim verification before any UI work begins.

**Architecture:** A small domain package parses saved fixtures without network access, while an injected HTTP client performs an optional live audit. Product confirmation and verdict invariants are separate pure functions so a failed source, missing identity, or missing evidence can never become `confirmed`.

**Tech Stack:** Python 3.12, Pydantic 2, httpx, pytest, pytest-cov, Ruff

## Global Constraints

- Never read or copy `C:\WORK\WORK\.env`; use only environment variables explicitly configured for this repository.
- Never commit API keys, raw user health data, or unsanitized live responses.
- `confirmed` requires a user-confirmed product identity and at least one traceable evidence record.
- Network access is forbidden in the default unit-test suite.
- A source error, schema error, timeout, or empty response must fail closed.
- No frontend, LangGraph workflow, vector database, or personalized health feature is added in Phase 0.
- Every task ends with fresh tests and a focused Git commit.

---

## Planned File Structure

```text
claim-ledger/
├─ pyproject.toml                         # Python tooling and dependencies
├─ .env.example                           # Variable names only
├─ src/claimledger/
│  ├─ __init__.py                         # Package marker
│  ├─ domain.py                           # Stable product, claim, evidence, verdict types
│  ├─ errors.py                           # Typed fail-closed errors
│  ├─ identity.py                         # User-confirmed product identity gate
│  ├─ decision.py                         # Minimal verdict invariants
│  ├─ evaluation.py                       # False-clearance metrics and 3/n bound
│  └─ sources/
│     ├─ __init__.py                      # Source package marker
│     └─ food_safety.py                   # C003 parser and injected HTTP client
├─ scripts/
│  └─ audit_c003.py                       # Live, sanitized coverage audit command
├─ tests/
│  ├─ fixtures/c003_success.json          # Synthetic response with real field names
│  ├─ test_domain.py
│  ├─ test_food_safety.py
│  ├─ test_identity.py
│  ├─ test_decision.py
│  └─ test_evaluation.py
└─ docs/evidence/
   └─ C003_COVERAGE_REPORT.md             # Generated or blocked-state audit record
```

## Task 1: Create the Python package and strict domain types

**Files:**

- Create: `pyproject.toml`
- Verify: `.env.example`
- Create: `src/claimledger/__init__.py`
- Create: `src/claimledger/domain.py`
- Create: `src/claimledger/errors.py`
- Create: `tests/test_domain.py`

**Interfaces:**

- Produces: `Verdict`, `ProductCandidate`, `ConfirmedProduct`, `Claim`, `EvidenceRecord`
- Produces: `DataSourceError`, `IdentityRequiredError`, `DecisionInvariantError`
- Consumes: no earlier task output

- [ ] **Step 1: Add the package configuration**

Create `pyproject.toml` with Python 3.12, runtime dependencies `pydantic>=2.8,<3` and `httpx>=0.27,<1`, and development dependencies `pytest>=8,<9`, `pytest-cov>=5,<7`, and `ruff>=0.6,<1`. Configure pytest with `testpaths = ["tests"]` and Ruff with `line-length = 100`. Verify that `.env.example` contains only the empty `FOODSAFETY_API_KEY=` declaration.

- [ ] **Step 2: Write the failing domain tests**

Create `tests/test_domain.py`:

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from claimledger.domain import Claim, ProductCandidate, Verdict


def test_public_verdict_values_are_stable() -> None:
    assert [item.value for item in Verdict] == [
        "confirmed",
        "mismatch",
        "insufficient",
        "unverifiable",
        "contradicted",
    ]


def test_product_candidate_rejects_blank_identity_fields() -> None:
    with pytest.raises(ValidationError):
        ProductCandidate(
            report_no="",
            name="루테인 테스트 제품",
            company="테스트 제조사",
            primary_function="눈 건강에 도움을 줄 수 있음",
            raw_materials="루테인지아잔틴복합추출물",
            intake_method="1일 1회",
            source_id="C003",
            retrieved_at=datetime.now(UTC),
        )


def test_claim_preserves_original_text() -> None:
    claim = Claim(original_text="눈 피로를 완전히 없앱니다", normalized_subject="눈 피로")
    assert claim.original_text == "눈 피로를 완전히 없앱니다"
```

- [ ] **Step 3: Run the tests and confirm the expected import failure**

Run: `python -m pytest tests/test_domain.py -q`

Expected: collection fails because `claimledger.domain` does not exist.

- [ ] **Step 4: Implement strict models and typed errors**

Implement `domain.py` with string-stripping Pydantic fields that reject blanks. Use this exact enum:

```python
from enum import StrEnum


class Verdict(StrEnum):
    CONFIRMED = "confirmed"
    MISMATCH = "mismatch"
    INSUFFICIENT = "insufficient"
    UNVERIFIABLE = "unverifiable"
    CONTRADICTED = "contradicted"
```

Define:

```python
class ProductCandidate(BaseModel):
    report_no: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    company: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    primary_function: str = ""
    raw_materials: str = ""
    intake_method: str = ""
    source_id: Literal["C003"]
    retrieved_at: datetime


class ConfirmedProduct(BaseModel):
    product: ProductCandidate
    confirmed_by_user: Literal[True]


class Claim(BaseModel):
    original_text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    normalized_subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class EvidenceRecord(BaseModel):
    evidence_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    source_url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    retrieved_at: datetime
    product_report_no: str | None = None
    supports_claim: bool
```

Define the three exception classes in `errors.py` without swallowing their messages.

- [ ] **Step 5: Run tests and static checks**

Run: `python -m pytest tests/test_domain.py -q`

Expected: `3 passed`.

Run: `python -m ruff check src tests`

Expected: exit code 0.

- [ ] **Step 6: Commit the domain foundation**

```powershell
git add pyproject.toml .env.example src/claimledger tests/test_domain.py
git commit -m "feat: define fail-closed claim domain"
```

## Task 2: Parse C003 responses without network access

**Files:**

- Create: `src/claimledger/sources/__init__.py`
- Create: `src/claimledger/sources/food_safety.py`
- Create: `tests/fixtures/c003_success.json`
- Create: `tests/test_food_safety.py`

**Interfaces:**

- Consumes: `ProductCandidate`, `DataSourceError`
- Produces: `C003Page(total_count: int, products: tuple[ProductCandidate, ...])`
- Produces: `parse_c003_payload(payload: dict, retrieved_at: datetime) -> C003Page`

- [ ] **Step 1: Add a synthetic fixture using the official field names**

Create `tests/fixtures/c003_success.json` with two invented products and this response shape:

```json
{
  "C003": {
    "RESULT": {"MSG": "정상처리되었습니다.", "CODE": "INFO-000"},
    "total_count": "2",
    "row": [
      {
        "PRDLST_REPORT_NO": "TEST-0001",
        "PRDLST_NM": "루테인 테스트 제품 A",
        "BSSH_NM": "테스트 제조사 A",
        "PRIMARY_FNCLTY": "눈 건강에 도움을 줄 수 있음",
        "RAWMTRL_NM": "루테인지아잔틴복합추출물",
        "NTK_MTHD": "1일 1회, 1회 1캡슐"
      },
      {
        "PRDLST_REPORT_NO": "TEST-0002",
        "PRDLST_NM": "오메가3 테스트 제품 B",
        "BSSH_NM": "테스트 제조사 B",
        "PRIMARY_FNCLTY": "혈중 중성지질 개선에 도움을 줄 수 있음",
        "RAWMTRL_NM": "EPA 및 DHA 함유 유지",
        "NTK_MTHD": "1일 1회, 1회 2캡슐"
      }
    ]
  }
}
```

The values are explicitly synthetic; only the field names and envelope shape model the API.

- [ ] **Step 2: Write parser failure and success tests**

Create tests for these exact behaviors:

```python
def test_parse_c003_success_fixture() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    page = parse_c003_payload(payload, retrieved_at=NOW)
    assert page.total_count == 2
    assert [product.report_no for product in page.products] == ["TEST-0001", "TEST-0002"]


def test_parse_c003_rejects_unapproved_service() -> None:
    payload = {"C003": {"RESULT": {"CODE": "INFO-110", "MSG": "활용신청 내역이 없습니다."}}}
    with pytest.raises(DataSourceError, match="INFO-110"):
        parse_c003_payload(payload, retrieved_at=NOW)


def test_parse_c003_rejects_missing_report_number() -> None:
    payload = success_payload_with_first_row(PRDLST_REPORT_NO="")
    with pytest.raises(DataSourceError, match="PRDLST_REPORT_NO"):
        parse_c003_payload(payload, retrieved_at=NOW)
```

- [ ] **Step 3: Run the parser tests and confirm failure**

Run: `python -m pytest tests/test_food_safety.py -q`

Expected: import or symbol failures because the parser is not implemented.

- [ ] **Step 4: Implement a strict parser**

In `food_safety.py`, define an immutable dataclass:

```python
@dataclass(frozen=True)
class C003Page:
    total_count: int
    products: tuple[ProductCandidate, ...]
```

`parse_c003_payload` must:

1. Require a `C003` object.
2. Require `RESULT.CODE == "INFO-000"`; otherwise raise `DataSourceError` containing the returned code and message.
3. Convert `total_count` to a non-negative integer.
4. Require `row` to be a list.
5. Map only the six named C003 fields into `ProductCandidate`.
6. Wrap Pydantic row validation failures in `DataSourceError` with the row index and failing field.
7. Never replace a missing official report number, product name, or company with guessed text.

- [ ] **Step 5: Run focused and full tests**

Run: `python -m pytest tests/test_food_safety.py -q`

Expected: all parser tests pass.

Run: `python -m pytest -q`

Expected: all Task 1 and Task 2 tests pass.

- [ ] **Step 6: Commit the parser**

```powershell
git add src/claimledger/sources tests/fixtures tests/test_food_safety.py
git commit -m "feat: parse C003 product records strictly"
```

## Task 3: Add a live C003 client and sanitized coverage audit

**Files:**

- Modify: `src/claimledger/sources/food_safety.py`
- Create: `scripts/audit_c003.py`
- Modify: `tests/test_food_safety.py`
- Create: `docs/evidence/C003_COVERAGE_REPORT.md` when the live command runs

**Interfaces:**

- Consumes: `parse_c003_payload`
- Produces: `C003Client.fetch_page(start: int, end: int) -> C003Page`
- Produces: `audit_products(products: Sequence[ProductCandidate]) -> CoverageAudit`
- Produces: a Markdown report containing counts and rates but no API key or raw response

- [ ] **Step 1: Write injected-client tests**

Use `httpx.MockTransport` so tests perform no external network call. Cover:

```python
def test_client_builds_expected_c003_path() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(200, json=SUCCESS_PAYLOAD)

    client = C003Client(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    page = client.fetch_page(1, 100)
    assert requested_paths == ["/api/test-key/C003/json/1/100"]
    assert page.total_count == 2


def test_client_converts_timeout_to_data_source_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = C003Client(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(DataSourceError, match="timeout"):
        client.fetch_page(1, 100)
```

Also test that a blank key is rejected before any request and that HTTP non-200 responses raise `DataSourceError`.

- [ ] **Step 2: Run tests and confirm missing-client failures**

Run: `python -m pytest tests/test_food_safety.py -q`

Expected: failures naming `C003Client` and `audit_products`.

- [ ] **Step 3: Implement the injected client**

Implement `C003Client` with:

- Base URL `https://openapi.foodsafetykorea.go.kr`
- Request path `/api/{api_key}/C003/json/{start}/{end}`
- Default timeout of 30 seconds
- Constructor injection of `httpx.Client`
- Validation `start >= 1` and `end >= start`
- Typed conversion of HTTP and parse failures
- No logging of the URL because the API key is embedded in the path

- [ ] **Step 4: Implement deterministic coverage statistics**

Define `CoverageAudit` with:

```python
class CoverageAudit(BaseModel):
    record_count: int
    unique_report_count: int
    duplicate_report_count: int
    missing_name_count: int
    missing_company_count: int
    missing_primary_function_count: int
    missing_raw_materials_count: int
    missing_intake_method_count: int
    candidate_counts: dict[str, int]
```

Candidate keys are fixed to `lutein_zeaxanthin`, `omega3`, and `probiotics`. Matching is a disclosed case-insensitive substring baseline over `name`, `primary_function`, and `raw_materials`; the report must state that it measures candidate coverage, not clinical equivalence.

- [ ] **Step 5: Add the live audit command**

`scripts/audit_c003.py` must:

1. Read `FOODSAFETY_API_KEY` from the process environment.
2. Fetch page 1–100 to obtain `total_count`.
3. Fetch remaining records in pages of 1000 without exceeding `total_count`.
4. Deduplicate only by exact official report number and count duplicates rather than silently dropping evidence.
5. Write `docs/evidence/C003_COVERAGE_REPORT.md` with retrieval time, source code, total count, fetched count, duplicate count, field completeness counts/rates, candidate counts, and one of `PASS`, `LIMITED`, `BLOCKED`.
6. Write no raw rows and no API key.
7. Exit non-zero with a clear message when the service returns `INFO-110`, the key is absent, or fetched counts do not reconcile.

- [ ] **Step 6: Run offline verification**

Run: `python -m pytest -q`

Expected: all tests pass without a network call.

Run: `python -m ruff check src scripts tests`

Expected: exit code 0.

- [ ] **Step 7: Run the authorized live audit**

Run only after the user has configured this repository's environment:

```powershell
python scripts/audit_c003.py
```

Expected successful evidence: exit code 0 and a report whose fetched count equals the API total count.

Expected blocked evidence: a non-zero exit with the exact official API code such as `INFO-110`; record `BLOCKED` without fabricating coverage values.

- [ ] **Step 8: Inspect the report for secret leakage**

Run:

```powershell
Select-String -Path 'docs/evidence/C003_COVERAGE_REPORT.md' -Pattern 'FOODSAFETY_API_KEY|/api/.+/C003|test-key'
```

Expected: no matches.

- [ ] **Step 9: Commit the client and audit evidence**

```powershell
git add src/claimledger/sources/food_safety.py scripts/audit_c003.py tests/test_food_safety.py docs/evidence/C003_COVERAGE_REPORT.md
git commit -m "feat: audit C003 product data coverage"
```

## Task 4: Enforce user-confirmed product identity

**Files:**

- Create: `src/claimledger/identity.py`
- Create: `tests/test_identity.py`

**Interfaces:**

- Consumes: `ProductCandidate`, `ConfirmedProduct`, `IdentityRequiredError`
- Produces: `confirm_candidate(candidates, selected_report_no) -> ConfirmedProduct`
- Produces: `require_confirmed_product(product) -> ConfirmedProduct`

- [ ] **Step 1: Write identity-gate tests**

```python
def test_exact_report_number_can_be_user_confirmed() -> None:
    confirmed = confirm_candidate([PRODUCT_A, PRODUCT_B], "TEST-0002")
    assert confirmed.confirmed_by_user is True
    assert confirmed.product.report_no == "TEST-0002"


def test_unknown_report_number_is_not_guessed() -> None:
    with pytest.raises(IdentityRequiredError, match="not present"):
        confirm_candidate([PRODUCT_A, PRODUCT_B], "TEST-9999")


def test_blank_selection_is_rejected() -> None:
    with pytest.raises(IdentityRequiredError, match="selection"):
        confirm_candidate([PRODUCT_A], "")
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `python -m pytest tests/test_identity.py -q`

Expected: import failure for `claimledger.identity`.

- [ ] **Step 3: Implement exact-match confirmation**

Implement one exact report-number lookup. Do not add fuzzy matching, automatic first-result selection, or fallback by product name. Reject duplicate report numbers in the candidate list because that indicates a source-normalization error.

- [ ] **Step 4: Run tests and commit**

Run: `python -m pytest tests/test_identity.py -q`

Expected: all identity tests pass.

Run: `python -m pytest -q`

Expected: the full offline suite passes.

```powershell
git add src/claimledger/identity.py tests/test_identity.py
git commit -m "feat: require user-confirmed product identity"
```

## Task 5: Add fail-closed verdict invariants and false-clearance metrics

**Files:**

- Create: `src/claimledger/decision.py`
- Create: `src/claimledger/evaluation.py`
- Create: `tests/test_decision.py`
- Create: `tests/test_evaluation.py`

**Interfaces:**

- Consumes: `Claim`, `ConfirmedProduct`, `EvidenceRecord`, `Verdict`
- Produces: `decide_supported_claim(claim, product, evidence) -> Verdict`
- Produces: `false_clearance_rate(expected, actual) -> float`
- Produces: `zero_error_upper_bound(sample_size: int) -> float`

- [ ] **Step 1: Write the decision-invariant tests**

```python
def test_missing_confirmed_product_cannot_clear_claim() -> None:
    with pytest.raises(IdentityRequiredError):
        decide_supported_claim(CLAIM, None, [SUPPORTING_EVIDENCE])


def test_empty_evidence_cannot_clear_claim() -> None:
    assert decide_supported_claim(CLAIM, CONFIRMED_PRODUCT, []) is Verdict.UNVERIFIABLE


def test_product_specific_evidence_must_match_report_number() -> None:
    other_product_evidence = SUPPORTING_EVIDENCE.model_copy(
        update={"product_report_no": "TEST-9999"}
    )
    assert decide_supported_claim(
        CLAIM, CONFIRMED_PRODUCT, [other_product_evidence]
    ) is Verdict.UNVERIFIABLE


def test_traceable_matching_support_can_confirm() -> None:
    assert decide_supported_claim(
        CLAIM, CONFIRMED_PRODUCT, [SUPPORTING_EVIDENCE]
    ) is Verdict.CONFIRMED
```

The Task 5 function is intentionally narrow. It proves only the invariant path; semantic claim matching is planned after the evidence-card schema is approved.

- [ ] **Step 2: Write evaluation tests**

```python
def test_false_clearance_rate_counts_only_harmful_direction() -> None:
    expected = [Verdict.MISMATCH, Verdict.UNVERIFIABLE, Verdict.CONFIRMED]
    actual = [Verdict.CONFIRMED, Verdict.UNVERIFIABLE, Verdict.MISMATCH]
    assert false_clearance_rate(expected, actual) == 0.5


def test_zero_error_bound_for_one_hundred_examples() -> None:
    assert zero_error_upper_bound(100) == pytest.approx(0.03)


def test_empty_evaluation_set_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        false_clearance_rate([], [])
```

For the primary metric, the denominator is expected non-confirmed claims. A false clearance occurs when one of those claims is predicted `confirmed`. False rejection is reported separately and must not dilute this metric.

- [ ] **Step 3: Run tests and confirm failure**

Run: `python -m pytest tests/test_decision.py tests/test_evaluation.py -q`

Expected: import failures for the two new modules.

- [ ] **Step 4: Implement the smallest invariant engine and metrics**

`decide_supported_claim` must return `confirmed` only when:

- the product is a `ConfirmedProduct`;
- evidence is not empty;
- every supporting product-specific evidence record either has no product report number or exactly matches the confirmed report number;
- at least one evidence record has `supports_claim is True` and a non-blank source URL.

Return `unverifiable` when these preconditions are not met. Do not infer `mismatch` or `contradicted` in this narrow function.

`zero_error_upper_bound` returns `3 / sample_size` and rejects values below 1.

- [ ] **Step 5: Run the complete offline quality gate**

Run: `python -m pytest --cov=claimledger --cov-report=term-missing -q`

Expected: all tests pass and the new Phase 0 modules show executed decision branches.

Run: `python -m ruff check src scripts tests`

Expected: exit code 0.

Run: `git diff --check`

Expected: exit code 0 and no whitespace errors.

- [ ] **Step 6: Commit verdict invariants and metrics**

```powershell
git add src/claimledger/decision.py src/claimledger/evaluation.py tests/test_decision.py tests/test_evaluation.py
git commit -m "feat: enforce false-clearance safety invariants"
```

## Task 6: Record the Phase 0 decision and synchronize the wiki

**Files:**

- Modify: `docs/CODEX_HANDOFF.md`
- Modify: `docs/PROJECT_BRIEF.md`
- Modify: `docs/evidence/C003_COVERAGE_REPORT.md`
- External update: `C:\Users\Donga\Desktop\AI-Agent-Wiki\AI-Sessions\wiki\projects\근거있어.md`
- External update: `C:\Users\Donga\Desktop\AI-Agent-Wiki\log.md`

**Interfaces:**

- Consumes: live C003 report and full offline test output
- Produces: one explicit decision, `CONTINUE_PRODUCT_MVP` or `LIMIT_TO_USER_SUPPLIED_LABELS`

- [ ] **Step 1: Apply the decision rule**

Choose `CONTINUE_PRODUCT_MVP` only when all are true:

- live C003 response is `INFO-000`;
- fetched count equals the API `total_count`;
- official report number, product name, and company are non-blank for every retained record;
- at least three candidate ingredient groups have enough distinct products to construct the planned evaluation set;
- duplicate official report numbers are zero after exact parsing.

Otherwise choose `LIMIT_TO_USER_SUPPLIED_LABELS`. This fallback accepts label text supplied by the user, marks it as user-provided evidence, and never describes it as an independently verified official product record.

- [ ] **Step 2: Update the handoff with measured values**

Replace the implementation-prep state in `docs/CODEX_HANDOFF.md` with the selected decision, exact audit timestamp, record counts, completeness rates, candidate counts, test command, pass count, and current commit hash. Do not copy the API key or raw response.

- [ ] **Step 3: Synchronize the AI-Agent-Wiki**

Read the existing wiki project page first. Append the measured result, source timestamp, decision, and project commit. Update the wiki `index.md` only if a new canonical document was created, and append one line to `log.md`. Commit the wiki separately from this repository.

- [ ] **Step 4: Run final verification before the Phase 0 completion claim**

Run:

```powershell
python -m pytest --cov=claimledger --cov-report=term-missing -q
python -m ruff check src scripts tests
git diff --check
git status --short --branch
```

Expected: tests and Ruff exit 0; diff check is clean; status contains only intentionally uncommitted evidence or documentation updates.

- [ ] **Step 5: Commit the Phase 0 record**

```powershell
git add docs/CODEX_HANDOFF.md docs/PROJECT_BRIEF.md docs/evidence/C003_COVERAGE_REPORT.md
git commit -m "docs: record C003 data confidence decision"
```

After this commit, create a separate implementation plan for the chosen path. Do not start the React UI or RAG pipeline under this Phase 0 plan.

## Self-Review Results

- Spec coverage: the plan covers source access, schema validation, product identity, fail-closed verdicts, harmful-error measurement, evidence recording, and wiki synchronization.
- Deliberate exclusions: OCR, LLM extraction, RAG, FastAPI, React, personalized health, and production deployment remain outside Phase 0 because they depend on the data decision.
- Type consistency: all tasks use the same `ProductCandidate`, `ConfirmedProduct`, `EvidenceRecord`, and `Verdict` names.
- Safety check: no step reads the parent `.env`, logs the key-bearing request URL, or turns source failure into a successful verdict.
