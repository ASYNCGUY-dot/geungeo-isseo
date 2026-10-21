# C003 사람 검토 계약 v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 C003 100건 표본을 그대로 보존하면서 원료 매핑과 기능성 원문 사용 가능성을 사람이 감사하고, 불완전·변조·모순된 검토가 확장 원료 추천으로 이어지지 않게 하는 v2 pack과 검증기를 만든다.

**Architecture:** 기존 `build_extension_review.py`는 결정적 5×20 표본 생성 책임을 유지하되 v2 manifest와 빈 제품 검토 라벨을 함께 만든다. 새 `claimledger.product_review` 모듈은 사람 라벨 계약, pack 무결성, 완료 통계와 Wilson 구간을 담당하고, 새 CLI는 `COMPLETE=0`, `PENDING=2`, `INVALID=3` 종료 코드를 제공한다. 광고 근거는 이 구현에 포함하지 않으며 모든 결과에서 `NOT_MEASURED`, 추천은 `BLOCKED`, `finalized=false`로 고정한다.

**Tech Stack:** Python 3.12+, Pydantic 2.x, Python 표준 라이브러리 `csv`·`hashlib`·`json`·`math`, pytest 8.x, pytest-cov, Ruff. 외부 네트워크와 새 패키지는 사용하지 않는다.

## Global Constraints

- 작업 위치는 `%USERPROFILE%\Desktop\DONGA AI LAB\DONGA KDT 3RD PROJECT\geungeo-isseo\.worktrees\phase-0-c003-data-gate`와 브랜치 `phase-0-c003-data-gate`다.
- 설계 기준 커밋은 `bdf95af docs: define C003 human review contract v2`이며, 구현은 이 계획 문서 커밋 위에서 시작한다. `main`의 `cd7095b`는 수정하지 않는다.
- 설계 정본은 `docs/superpowers/specs/2026-08-28-c003-human-review-contract-v2-design.md`다.
- 기존 `build/extension-review/`와 v1 `review_labels.csv`는 삭제하거나 덮어쓰지 않는다.
- 새 로컬 산출물은 `build/extension-review-v2/`에 만들고 계속 Git ignored 상태로 둔다.
- 동일 export·seed의 v2 `samples.csv`는 기존 v1 `samples.csv`와 바이트 단위로 같아야 한다.
- 빈 값과 판단 불가를 수치 `0`으로 변환하지 않는다.
- 사람 입력 필드가 모두 빈 템플릿 행만 `PENDING`으로 센다. 일부만 입력된 행은 재개 가능한 완료 상태로 추정하지 않고 `INVALID`로 차단한다.
- 실제 API 키, URL, C003 envelope, 사용자 건강정보와 판매자 원문을 pack·로그·fixture에 넣지 않는다.
- `PENDING`과 `INVALID`에서는 성공 summary와 추천 객체를 만들지 않는다.
- v2가 `COMPLETE`여도 `advertising_evidence_status=NOT_MEASURED`, `extension_recommendation_status=BLOCKED`, `finalized=false`다.
- 기능 구현은 실패 테스트를 먼저 작성하고 실제 RED를 확인한 뒤 최소 코드를 작성한다.
- 각 커밋 전 focused test, 관련 회귀, Ruff, `git diff --check`, 비밀정보 검사를 새로 실행한다.
- 병합, 원격 생성, push, worktree 삭제는 이 계획에 포함하지 않는다.

## File Responsibility Map

| 파일 | 책임 |
|---|---|
| `src/claimledger/product_review.py` | v2 enum·라벨·manifest·검증 결과·통계 모델, pack 검증, Wilson 구간 |
| `scripts/build_extension_review.py` | 기존 결정적 표본을 유지하면서 v2 네 파일 생성 |
| `scripts/validate_product_review.py` | pack 검증 CLI, 종료 코드, COMPLETE summary 원자적 저장 |
| `tests/test_product_review.py` | 라벨 계약, 무결성, 상태, 통계, CLI 회귀 |
| `tests/test_extension_selection.py` | v2 pack 생성과 기존 표본 결정성·보안 회귀 |
| `tests/fixtures/product_review_labels.csv` | 합성 v2 라벨 header fixture |
| `AGENTS.md` | 현재 첫 작업을 v2 사람 검토 준비로 갱신 |
| `README.md` | v1 점수 계약 폐기와 v2 실행 명령 기록 |
| `docs/CODEX_HANDOFF.md` | 구현·실측·미구현 경계와 다음 사람 작업 기록 |
| `docs/evidence/PHASE_1_EXTENSION_REVIEW.md` | v2 pack 해시·manifest·PENDING 0/100 증거 기록 |
| `AI-Agent-Wiki`의 기존 프로젝트·handoff·index·log | 다음 세션용 정본 동기화, 별도 Git 커밋 |

---

### Task 1: Freeze the v2 Human Label Contract

**Files:**
- Create: `src/claimledger/product_review.py`
- Create: `tests/test_product_review.py`

**Interfaces:**
- Consumes: `IngredientGroup`, `NonBlankText`, `AwareDatetime`, `COMPARISON_GROUPS`.
- Produces: `MappingVerdict`, `MappingReasonCode`, `FunctionTextStatus`, `FunctionReasonCode`, `ProductReviewLabel`.
- Contract: 라벨 모델은 한 행의 모순과 spreadsheet formula prefix를 거부하며 pack 전체 수·해시는 아직 다루지 않는다.

- [ ] **Step 1: Write the failing label-contract tests**

Create `tests/test_product_review.py` with this first slice:

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from claimledger.domain import IngredientGroup
from claimledger.product_review import ProductReviewLabel

NOW = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)


def valid_label_values() -> dict[str, object]:
    return {
        "group": IngredientGroup.MILK_THISTLE,
        "report_no": "TEST-001",
        "mapping_verdict": "correct",
        "mapping_reason_code": "none",
        "function_text_status": "usable",
        "function_reason_code": "none",
        "review_note": "",
        "reviewer": "reviewer-01",
        "reviewed_at_iso8601": NOW,
    }


def test_product_review_label_accepts_a_consistent_decision() -> None:
    label = ProductReviewLabel.model_validate(valid_label_values())

    assert label.mapping_verdict.value == "correct"
    assert label.function_text_status.value == "usable"
    assert label.reviewed_at_iso8601 == NOW


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"mapping_verdict": "correct", "mapping_reason_code": "wrong_group"},
            "correct mapping requires reason none",
        ),
        (
            {"mapping_verdict": "incorrect", "mapping_reason_code": "none"},
            "non-correct mapping requires a reason",
        ),
        (
            {"function_text_status": "usable", "function_reason_code": "missing_text"},
            "usable function text requires reason none",
        ),
        (
            {"function_text_status": "uncertain", "function_reason_code": "none"},
            "non-usable function text requires a reason",
        ),
        (
            {
                "mapping_verdict": "uncertain",
                "mapping_reason_code": "needs_expert",
                "review_note": "",
            },
            "needs_expert and other reasons require a review note",
        ),
        ({"reviewer": "=HYPERLINK(\"bad\")"}, "spreadsheet formula prefix"),
        ({"review_note": "+SUM(1,1)"}, "spreadsheet formula prefix"),
        ({"reviewed_at_iso8601": datetime(2026, 8, 28, 9, 0)}, "timezone"),
    ],
)
def test_product_review_label_rejects_inconsistent_or_unsafe_values(
    changes: dict[str, object], message: str
) -> None:
    values = valid_label_values()
    values.update(changes)

    with pytest.raises(ValidationError, match=message):
        ProductReviewLabel.model_validate(values)


def test_product_review_label_rejects_a_core_ingredient_group() -> None:
    values = valid_label_values()
    values["group"] = IngredientGroup.OMEGA3

    with pytest.raises(ValidationError, match="comparison ingredient group"):
        ProductReviewLabel.model_validate(values)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_product_review.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'claimledger.product_review'`. A syntax or fixture error is not the required RED; correct the test until the missing production module is the failure.

- [ ] **Step 3: Implement the minimal immutable label contract**

Create `src/claimledger/product_review.py` with these public definitions and validators:

```python
from datetime import datetime
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from claimledger.domain import IngredientGroup, NonBlankText
from claimledger.extension_selection import COMPARISON_GROUPS

_SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class MappingVerdict(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    UNCERTAIN = "uncertain"


class MappingReasonCode(StrEnum):
    NONE = "none"
    WRONG_GROUP = "wrong_group"
    ALIAS_COLLISION = "alias_collision"
    COMBINATION_PRODUCT = "combination_product"
    NEGATIVE_OR_EXCLUSION_CONTEXT = "negative_or_exclusion_context"
    NEEDS_EXPERT = "needs_expert"
    OTHER = "other"


class FunctionTextStatus(StrEnum):
    USABLE = "usable"
    INCOMPLETE = "incomplete"
    UNCERTAIN = "uncertain"


class FunctionReasonCode(StrEnum):
    NONE = "none"
    MISSING_TEXT = "missing_text"
    TRUNCATED_OR_MALFORMED = "truncated_or_malformed"
    TOO_VAGUE_FOR_RULE = "too_vague_for_rule"
    NEEDS_EXPERT = "needs_expert"
    OTHER = "other"


def _reject_formula_prefix(value: str, field_name: str) -> None:
    if value.startswith(_SPREADSHEET_FORMULA_PREFIXES):
        raise ValueError(f"{field_name} starts with a spreadsheet formula prefix")


class ProductReviewLabel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    group: IngredientGroup
    report_no: NonBlankText
    mapping_verdict: MappingVerdict
    mapping_reason_code: MappingReasonCode
    function_text_status: FunctionTextStatus
    function_reason_code: FunctionReasonCode
    review_note: str = ""
    reviewer: NonBlankText
    reviewed_at_iso8601: AwareDatetime

    @model_validator(mode="after")
    def _validate_human_contract(self) -> "ProductReviewLabel":
        if self.group not in COMPARISON_GROUPS:
            raise ValueError("product review requires a comparison ingredient group")
        if self.mapping_verdict is MappingVerdict.CORRECT:
            if self.mapping_reason_code is not MappingReasonCode.NONE:
                raise ValueError("correct mapping requires reason none")
        elif self.mapping_reason_code is MappingReasonCode.NONE:
            raise ValueError("non-correct mapping requires a reason")
        if self.function_text_status is FunctionTextStatus.USABLE:
            if self.function_reason_code is not FunctionReasonCode.NONE:
                raise ValueError("usable function text requires reason none")
        elif self.function_reason_code is FunctionReasonCode.NONE:
            raise ValueError("non-usable function text requires a reason")
        note_required = self.mapping_reason_code in {
            MappingReasonCode.NEEDS_EXPERT,
            MappingReasonCode.OTHER,
        } or self.function_reason_code in {
            FunctionReasonCode.NEEDS_EXPERT,
            FunctionReasonCode.OTHER,
        }
        if note_required and not self.review_note.strip():
            raise ValueError("needs_expert and other reasons require a review note")
        _reject_formula_prefix(self.reviewer, "reviewer")
        _reject_formula_prefix(self.review_note, "review_note")
        return self
```

Do not add pack reading, aggregate scores, advertisement fields, or recommendation calls in this task.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_product_review.py -q
.venv\Scripts\ruff.exe check src\claimledger\product_review.py tests\test_product_review.py
git diff --check
```

Expected: all Task 1 tests pass, Ruff prints `All checks passed!`, and `git diff --check` exits `0`.

- [ ] **Step 5: Commit the label contract**

Run a key-pattern scan that reports counts without printing matching values, then:

```powershell
git add src\claimledger\product_review.py tests\test_product_review.py
git diff --cached --check
git commit -m "feat: define C003 product review labels"
```

Expected: exactly the two Task 1 files are committed.

---

### Task 2: Generate the Deterministic v2 Review Pack

**Files:**
- Modify: `src/claimledger/product_review.py`
- Modify: `scripts/build_extension_review.py:19-205`
- Modify: `tests/test_extension_selection.py:406-532`
- Create: `tests/fixtures/product_review_labels.csv`

**Interfaces:**
- Consumes: existing `ReviewSample`, `build_samples(...)`, input JSONL path, seed `20260823`.
- Produces: `ReviewGroupCounts`, `ProductReviewManifest`, `sha256_file(path)`, `build_product_review_manifest(...)` and exactly four generated files.
- `write_review_pack(output_dir, samples, seed, *, source_export_path)` refuses an existing destination and removes its newly-created destination on a write failure.

- [ ] **Step 1: Replace the v1 generator expectations with failing v2 tests**

In `tests/test_extension_selection.py`, change the existing CLI pack test to require:

```python
assert {path.name for path in first_output.iterdir()} == {
    "README.md",
    "manifest.json",
    "product_review_labels.csv",
    "samples.csv",
}
assert all(
    (first_output / name).read_bytes() == (second_output / name).read_bytes()
    for name in (
        "README.md",
        "manifest.json",
        "product_review_labels.csv",
        "samples.csv",
    )
)
manifest = json.loads((first_output / "manifest.json").read_text(encoding="utf-8"))
assert manifest == {
    "contract_version": "c003-product-review-v2",
    "group_counts": {
        "coenzyme_q10": 20,
        "magnesium": 20,
        "milk_thistle": 20,
        "red_ginseng": 20,
        "vitamin_d": 20,
    },
    "mapping_rule_versions": ["ingredient-map-v1"],
    "sample_count": 100,
    "samples_sha256": hashlib.sha256(
        (first_output / "samples.csv").read_bytes()
    ).hexdigest().upper(),
    "seed": 20260823,
    "source_export_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest().upper(),
}
```

Add imports for `hashlib`, and assert the new label header exactly:

```python
with (first_output / "product_review_labels.csv").open(
    encoding="utf-8", newline=""
) as handle:
    assert next(csv.reader(handle)) == [
        "group",
        "report_no",
        "mapping_verdict",
        "mapping_reason_code",
        "function_text_status",
        "function_reason_code",
        "review_note",
        "reviewer",
        "reviewed_at_iso8601",
    ]
```

Update the formula-neutralization test to inspect `product_review_labels.csv`, and add:

```python
def run_cli(
    input_path: Path,
    output_dir: Path,
    *,
    seed: int = 20260823,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/build_extension_review.py",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--seed",
            str(seed),
        ],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_refuses_to_overwrite_an_existing_review_pack(tmp_path: Path) -> None:
    input_path = tmp_path / "products.jsonl"
    output_dir = tmp_path / "output"
    write_jsonl(input_path, jsonl_records())
    output_dir.mkdir()
    (output_dir / "keep.txt").write_text("preserve", encoding="utf-8")

    result = run_cli(input_path, output_dir)

    assert result.returncode != 0
    assert "output directory already exists" in result.stderr
    assert (output_dir / "keep.txt").read_text(encoding="utf-8") == "preserve"


def test_cli_rejects_noncanonical_v2_seed(tmp_path: Path) -> None:
    input_path = tmp_path / "products.jsonl"
    output_dir = tmp_path / "output"
    write_jsonl(input_path, jsonl_records())

    result = run_cli(input_path, output_dir, seed=1)

    assert result.returncode != 0
    assert "v2 seed must be 20260823" in result.stderr
    assert not output_dir.exists()
```

Create `tests/fixtures/product_review_labels.csv` with only this header and newline:

```csv
group,report_no,mapping_verdict,mapping_reason_code,function_text_status,function_reason_code,review_note,reviewer,reviewed_at_iso8601
```

Keep the old `tests/fixtures/extension_review_labels.csv` unchanged as v1 contract evidence.

- [ ] **Step 2: Run the generator tests and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_extension_selection.py -q
```

Expected: the existing generator still writes `review_labels.csv` and lacks `manifest.json`, so the exact-file assertion fails. A failure caused only by a missing `hashlib` import is not the required RED.

- [ ] **Step 3: Add immutable manifest models and hashing**

Extend `src/claimledger/product_review.py` with:

```python
import hashlib
from pathlib import Path
from typing import Literal

from pydantic import Field


class ReviewGroupCounts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    milk_thistle: Literal[20] = 20
    vitamin_d: Literal[20] = 20
    red_ginseng: Literal[20] = 20
    coenzyme_q10: Literal[20] = 20
    magnesium: Literal[20] = 20


class ProductReviewManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_version: Literal["c003-product-review-v2"] = "c003-product-review-v2"
    seed: Literal[20260823] = 20260823
    sample_count: Literal[100] = 100
    group_counts: ReviewGroupCounts
    samples_sha256: str = Field(pattern=r"^[0-9A-F]{64}$")
    source_export_sha256: str = Field(pattern=r"^[0-9A-F]{64}$")
    mapping_rule_versions: tuple[NonBlankText, ...]

    @model_validator(mode="after")
    def _require_sorted_unique_rule_versions(self) -> "ProductReviewManifest":
        if not self.mapping_rule_versions:
            raise ValueError("mapping rule versions must not be empty")
        if self.mapping_rule_versions != tuple(sorted(set(self.mapping_rule_versions))):
            raise ValueError("mapping rule versions must be sorted and unique")
        return self


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()
```

Add `build_product_review_manifest(samples_path, source_export_path, samples, seed)` with these validations before constructing `ProductReviewManifest`:

- `seed == 20260823`;
- exactly 100 samples;
- each comparison group occurs exactly 20 times;
- rule versions are sorted and unique;
- hashes are calculated from the actual files after `samples.csv` is written.

- [ ] **Step 4: Convert the builder to v2 without changing sample serialization**

In `scripts/build_extension_review.py`:

- replace `REVIEW_LABEL_FIELDS` with `PRODUCT_REVIEW_LABEL_FIELDS` using the exact nine-column order;
- keep `SAMPLE_FIELDS`, `_sample_row`, `_spreadsheet_safe`, `load_products`, and `build_samples` behavior unchanged;
- change `write_review_pack` to accept `source_export_path` as a keyword-only argument;
- refuse any pre-existing `output_dir` before creating files;
- write `samples.csv` first, then `product_review_labels.csv`, `manifest.json`, and `README.md`;
- remove a newly-created output directory with `shutil.rmtree(output_dir)` if any write raises;
- serialize manifest with `ensure_ascii=False`, `indent=2`, `sort_keys=True`, and a trailing newline;
- state `advertising evidence: NOT_MEASURED`, `recommendation: BLOCKED`, `finalized: false` in README;
- call `write_review_pack(..., source_export_path=args.input)` from `main()`.

The blank row body must be:

```python
{
    "group": sample.group.value,
    "report_no": _spreadsheet_safe(sample.report_no),
    "mapping_verdict": "",
    "mapping_reason_code": "",
    "function_text_status": "",
    "function_reason_code": "",
    "review_note": "",
    "reviewer": "",
    "reviewed_at_iso8601": "",
}
```

Do not add ad text, URLs, numeric roadmap scores, or recommendation output.

- [ ] **Step 5: Run generator tests and verify GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_extension_selection.py -q
.venv\Scripts\python.exe -m pytest tests\test_audit_c003.py tests\test_extension_selection.py -q
.venv\Scripts\ruff.exe check src\claimledger\product_review.py scripts\build_extension_review.py tests\test_product_review.py tests\test_extension_selection.py
git diff --check
```

Expected: all focused tests pass. The exporter-to-loader-to-sampler integration still passes, and the builder creates exactly four deterministic v2 files.

- [ ] **Step 6: Commit the v2 generator**

Run the staged secret scan and then:

```powershell
git add src\claimledger\product_review.py scripts\build_extension_review.py tests\test_extension_selection.py tests\fixtures\product_review_labels.csv
git diff --cached --check
git commit -m "feat: generate C003 review packs v2"
```

Expected: the old fixture and local v1 pack remain untouched.

---

### Task 3: Validate Pack Identity and Pending State

**Files:**
- Modify: `src/claimledger/product_review.py`
- Modify: `tests/test_product_review.py`

**Interfaces:**
- Consumes: `pack_dir`, `source_export_path`, timezone-aware `validated_at`.
- Produces: `ReviewGateStatus`, `ReviewIssue`, frozen metric/result DTOs, and `validate_product_review_pack(...)`.
- Task 3 validates files, hashes, headers, exact keys and blank-template progress. It freezes the final summary schema now, while completed-label calculation remains Task 4.

- [ ] **Step 1: Add failing pack-integrity and PENDING tests**

Add test helpers that create 100 synthetic sample and blank label rows using the exact v2 headers. Use `ProductReviewManifest` to write a valid manifest. Then add:

```python
from claimledger.product_review import (
    ProductReviewManifest,
    ReviewGateStatus,
    ReviewGroupCounts,
    ReviewIssue,
    ReviewValidationResult,
    sha256_file,
    validate_product_review_pack,
)


def test_blank_exact_v2_template_is_pending_zero_of_one_hundred(tmp_path: Path) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)

    result = validate_product_review_pack(
        pack_dir,
        source_export,
        validated_at=NOW,
    )

    assert result.status is ReviewGateStatus.PENDING
    assert result.expected_label_count == 100
    assert result.valid_label_count == 0
    assert result.pending_label_count == 100
    assert result.issues == ()
    assert result.summary is None
    assert result.advertising_evidence_status == "NOT_MEASURED"
    assert result.extension_recommendation_status == "BLOCKED"
    assert result.finalized is False


@pytest.mark.parametrize(
    "mutation",
    [
        "extra_file",
        "sample_hash",
        "source_hash",
        "duplicate_label_key",
        "missing_label_key",
        "unexpected_label_key",
        "wrong_header",
        "wrong_group_count",
    ],
)
def test_pack_identity_mutations_are_invalid(tmp_path: Path, mutation: str) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)
    mutate_pack(pack_dir, source_export, mutation)

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.INVALID
    assert result.valid_label_count is None
    assert result.pending_label_count is None
    assert result.summary is None
    assert result.issues
    assert result.extension_recommendation_status == "BLOCKED"
    assert result.finalized is False


def test_invalid_status_cannot_claim_zero_review_progress() -> None:
    with pytest.raises(ValidationError, match="INVALID requires"):
        ReviewValidationResult(
            status=ReviewGateStatus.INVALID,
            valid_label_count=0,
            pending_label_count=0,
            issues=(ReviewIssue(code="bad_pack", message="pack is invalid"),),
        )
```

The helper must write only synthetic values such as `MILK_THISTLE-000`; it must not copy live C003 rows into tracked tests.

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_product_review.py -q
```

Expected: import fails for `ReviewGateStatus` or `validate_product_review_pack` because pack validation does not exist.

- [ ] **Step 3: Implement exact schemas and sanitized issues**

Add these models:

```python
from typing import Literal

from claimledger.domain import MappingStatus


class ReviewGateStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PENDING = "PENDING"
    INVALID = "INVALID"


class ProductReviewSample(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

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


class ReviewIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: NonBlankText
    message: NonBlankText
    line_number: int | None = None
    group: str | None = None
    report_no: str | None = None


class WilsonInterval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lower: float = Field(ge=0.0, le=1.0)
    upper: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _require_ordered_bounds(self) -> "WilsonInterval":
        if self.lower > self.upper:
            raise ValueError("Wilson lower bound must not exceed upper bound")
        return self


class ReviewMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sample_count: int = Field(ge=1)
    mapping_correct_count: int = Field(ge=0)
    mapping_incorrect_count: int = Field(ge=0)
    mapping_uncertain_count: int = Field(ge=0)
    mapping_precision_decidable: float | None = Field(ge=0.0, le=1.0)
    mapping_precision_wilson_95: WilsonInterval | None
    mapping_uncertainty_rate: float = Field(ge=0.0, le=1.0)
    function_usable_rate: float = Field(ge=0.0, le=1.0)
    function_incomplete_rate: float = Field(ge=0.0, le=1.0)
    function_uncertainty_rate: float = Field(ge=0.0, le=1.0)


class GroupReviewMetrics(ReviewMetrics):
    group: IngredientGroup


class ReviewerCount(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reviewer: NonBlankText
    row_count: int = Field(ge=1)


class ProductReviewSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    overall: ReviewMetrics
    groups: tuple[GroupReviewMetrics, ...]
    reviewer_counts: tuple[ReviewerCount, ...]
    review_started_at: AwareDatetime
    review_completed_at: AwareDatetime


class ReviewValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ReviewGateStatus
    expected_label_count: Literal[100] = 100
    valid_label_count: int | None = Field(ge=0, le=100)
    pending_label_count: int | None = Field(ge=0, le=100)
    issues: tuple[ReviewIssue, ...]
    summary: ProductReviewSummary | None = None
    advertising_evidence_status: Literal["NOT_MEASURED"] = "NOT_MEASURED"
    extension_recommendation_status: Literal["BLOCKED"] = "BLOCKED"
    finalized: Literal[False] = False

    @model_validator(mode="after")
    def _require_status_consistency(self) -> "ReviewValidationResult":
        if self.status is ReviewGateStatus.COMPLETE:
            if (
                self.valid_label_count != 100
                or self.pending_label_count != 0
                or self.summary is None
                or self.issues
            ):
                raise ValueError("COMPLETE requires 100 valid labels and a clean summary")
        elif self.status is ReviewGateStatus.PENDING:
            if (
                self.valid_label_count is None
                or self.pending_label_count is None
                or self.valid_label_count + self.pending_label_count != 100
                or self.pending_label_count == 0
                or self.summary is not None
                or self.issues
            ):
                raise ValueError("PENDING requires a clean incomplete 100-row pack")
        elif (
            self.valid_label_count is not None
            or self.pending_label_count is not None
            or self.summary is not None
            or not self.issues
        ):
            raise ValueError("INVALID requires issues and unreported progress counts")
        return self
```

These metric DTOs are the final public shape even though Task 3 only returns `summary=None`. Do not use `model_construct` at validation boundaries.

- [ ] **Step 4: Implement pack integrity validation**

Implement the public signature `validate_product_review_pack(pack_dir: Path, source_export_path: Path, *, validated_at: AwareDatetime) -> ReviewValidationResult`.

The function must:

1. require exactly `README.md`, `manifest.json`, `samples.csv`, and `product_review_labels.csv`;
2. reject a missing or malformed export, manifest or CSV as `INVALID` rather than raise;
3. reject high-confidence secret patterns without including the matched value in `ReviewIssue`;
4. validate manifest via `ProductReviewManifest.model_validate_json`;
5. compare current sample and export hashes to manifest;
6. require exact sample and label headers;
7. parse each sample with `ProductReviewSample.model_validate`;
8. require five groups × 20 and 100 globally unique `group + report_no` keys;
9. require the label key set to equal the sample key set exactly;
10. treat a row with every human field blank as pending;
11. treat a partially filled row as `INVALID` with line number and key rather than reporting speculative progress;
12. sort issues deterministically by line number, code, group and report number;
13. return `INVALID` before `PENDING` when any integrity issue exists.

Do not print product names, functions, raw materials, notes, secret-like values or full CSV rows in issues.

- [ ] **Step 5: Run integrity tests and verify GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_product_review.py -q
.venv\Scripts\python.exe -m pytest tests\test_extension_selection.py tests\test_product_review.py -q
.venv\Scripts\ruff.exe check src\claimledger\product_review.py tests\test_product_review.py
git diff --check
```

Expected: blank template is exactly `PENDING 0/100`; all structural mutations are `INVALID`; no summary is present.

- [ ] **Step 6: Commit pack identity validation**

```powershell
git add src\claimledger\product_review.py tests\test_product_review.py
git diff --cached --check
git commit -m "feat: validate C003 review pack identity"
```

---

### Task 4: Validate Completed Labels and Compute Non-Recommendation Metrics

**Files:**
- Modify: `src/claimledger/product_review.py`
- Modify: `tests/test_product_review.py`

**Interfaces:**
- Consumes: structurally valid pack, 100 `ProductReviewLabel` rows, and the frozen metric DTOs from Task 3.
- Produces: `wilson_interval(...)` and deterministic COMPLETE metrics in `ProductReviewSummary`.
- No interface returns `ExtensionCandidateStats` or calls `recommend_extension_candidates`.

- [ ] **Step 1: Add failing COMPLETE, metric, uncertainty and invalid-label tests**

Add a helper that fills all 100 rows with consistent synthetic labels. Then add:

```python
def test_complete_labels_produce_metrics_but_no_recommendation(tmp_path: Path) -> None:
    pack_dir, source_export = write_completed_pack(tmp_path)

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.COMPLETE
    assert result.valid_label_count == 100
    assert result.pending_label_count == 0
    assert result.summary is not None
    assert result.summary.overall.sample_count == 100
    assert len(result.summary.groups) == 5
    assert {group.sample_count for group in result.summary.groups} == {20}
    assert result.advertising_evidence_status == "NOT_MEASURED"
    assert result.extension_recommendation_status == "BLOCKED"
    assert result.finalized is False


def test_wilson_interval_and_not_measured_denominator_are_explicit() -> None:
    assert wilson_interval(0, 0) is None
    perfect = wilson_interval(20, 20)
    assert perfect is not None
    assert perfect.lower == pytest.approx(0.838874841947, abs=1e-12)
    assert perfect.upper == pytest.approx(1.0, abs=1e-12)

    half = wilson_interval(10, 20)
    assert half is not None
    assert half.lower == pytest.approx(0.299298008198, abs=1e-12)
    assert half.upper == pytest.approx(0.700701991802, abs=1e-12)


@pytest.mark.parametrize(("successes", "total"), [(-1, 20), (21, 20), (1, -1)])
def test_wilson_interval_rejects_impossible_counts(
    successes: int, total: int
) -> None:
    with pytest.raises(ValueError, match="0 <= successes <= total"):
        wilson_interval(successes, total)


def test_all_uncertain_mappings_do_not_become_zero_precision(tmp_path: Path) -> None:
    pack_dir, source_export = write_completed_pack(
        tmp_path,
        mapping_verdict="uncertain",
        mapping_reason_code="needs_expert",
        review_note="전문가 확인 필요",
    )

    result = validate_product_review_pack(pack_dir, source_export, validated_at=NOW)

    assert result.status is ReviewGateStatus.COMPLETE
    assert result.summary is not None
    assert result.summary.overall.mapping_precision_decidable is None
    assert result.summary.overall.mapping_precision_wilson_95 is None
    assert result.summary.overall.mapping_uncertainty_rate == 1.0
```

Add a parameterized test covering invalid enum, reason contradiction, required-note omission, formula-prefixed reviewer/note, blank reviewer, naive timestamp, and `reviewed_at_iso8601 > validated_at + 24 hours`. Every case must return `INVALID`, not raise and not produce a summary.

- [ ] **Step 2: Run the completion tests and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_product_review.py -q
```

Expected: COMPLETE rows have no implemented summary or `wilson_interval` import fails.

- [ ] **Step 3: Implement Wilson against the frozen metric DTOs**

Add:

```python
import math
from collections import Counter


def wilson_interval(
    successes: int,
    total: int,
    *,
    z: float = 1.959963984540054,
) -> WilsonInterval | None:
    if successes < 0 or total < 0 or successes > total:
        raise ValueError("Wilson inputs require 0 <= successes <= total")
    if total == 0:
        return None
    proportion = successes / total
    z_squared = z * z
    denominator = 1 + z_squared / total
    center = (proportion + z_squared / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total
            + z_squared / (4 * total * total)
        )
        / denominator
    )
    return WilsonInterval(
        lower=max(0.0, center - margin),
        upper=min(1.0, center + margin),
    )
```

- [ ] **Step 4: Parse completed labels and calculate deterministic summaries**

When no structural issue exists:

- keep wholly blank rows as `PENDING`;
- pass fully filled rows through `ProductReviewLabel.model_validate`;
- reject timestamps later than `validated_at + timedelta(hours=24)`;
- count `correct`, `incorrect`, and `uncertain` separately;
- calculate `mapping_precision_decidable` only from `correct + incorrect`;
- include 95% Wilson interval only when that denominator is nonzero;
- calculate function rates against all rows;
- sort group metrics in `COMPARISON_GROUPS` order;
- sort reviewer counts by reviewer identifier;
- use min and max reviewed timestamps for the review window;
- produce `COMPLETE` only when all 100 rows validate;
- preserve the three blocked recommendation fields in `ReviewValidationResult`.

Revalidate models normally; do not use mutable dicts as trusted scored output and do not call legacy extension scoring.
For any `INVALID` result, set both progress counts to `None`; never turn an unreadable or contradictory pack into `0 / 100`.

- [ ] **Step 5: Run completed-label tests and verify GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_product_review.py -q
.venv\Scripts\python.exe -m pytest tests\test_extension_selection.py tests\test_product_review.py -q
.venv\Scripts\ruff.exe check src\claimledger\product_review.py tests\test_product_review.py
git diff --check
```

Expected: COMPLETE metrics, uncertainty handling, Wilson values and all invalid-label cases pass; recommendation remains blocked.

- [ ] **Step 6: Commit completed review metrics**

```powershell
git add src\claimledger\product_review.py tests\test_product_review.py
git diff --cached --check
git commit -m "feat: summarize C003 human reviews"
```

---

### Task 5: Add the Operator Validation CLI

**Files:**
- Create: `scripts/validate_product_review.py`
- Modify: `tests/test_product_review.py`

**Interfaces:**
- Consumes: `--pack-dir`, `--source-export`, optional `--summary-output`.
- Produces: sanitized status output and process exit `0`, `2`, or `3`.
- Writes a JSON summary atomically only for `COMPLETE`; the summary contains counts, rates, intervals, reviewers and blocked flags, not product rows.

- [ ] **Step 1: Add failing CLI exit-code and output tests**

Add:

```python
from scripts.validate_product_review import main as validate_review_main


def test_cli_returns_two_for_pending_without_writing_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)
    output = tmp_path / "summary.json"

    exit_code = validate_review_main(
        [
            "--pack-dir",
            str(pack_dir),
            "--source-export",
            str(source_export),
            "--summary-output",
            str(output),
        ],
        validated_at=NOW,
    )

    assert exit_code == 2
    assert '"status": "PENDING"' in capsys.readouterr().out
    assert not output.exists()


def test_cli_returns_three_for_invalid_without_writing_summary(
    tmp_path: Path,
) -> None:
    pack_dir, source_export = write_valid_blank_pack(tmp_path)
    (pack_dir / "unexpected.txt").write_text("unexpected", encoding="utf-8")
    output = tmp_path / "summary.json"

    exit_code = validate_review_main(
        ["--pack-dir", str(pack_dir), "--source-export", str(source_export),
         "--summary-output", str(output)],
        validated_at=NOW,
    )

    assert exit_code == 3
    assert not output.exists()


def test_cli_returns_zero_and_atomically_writes_complete_summary(tmp_path: Path) -> None:
    pack_dir, source_export = write_completed_pack(tmp_path)
    output = tmp_path / "summary.json"

    exit_code = validate_review_main(
        ["--pack-dir", str(pack_dir), "--source-export", str(source_export),
         "--summary-output", str(output)],
        validated_at=NOW,
    )

    assert exit_code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "COMPLETE"
    assert saved["advertising_evidence_status"] == "NOT_MEASURED"
    assert saved["extension_recommendation_status"] == "BLOCKED"
    assert saved["finalized"] is False
    assert "name" not in output.read_text(encoding="utf-8")
    assert "raw_materials" not in output.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the CLI tests and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_product_review.py -q
```

Expected: import fails because `scripts.validate_product_review` does not exist.

- [ ] **Step 3: Implement the minimal CLI**

Create `scripts/validate_product_review.py` with:

```python
import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import AwareDatetime

from claimledger.product_review import ReviewGateStatus, validate_product_review_pack

EXIT_CODES = {
    ReviewGateStatus.COMPLETE: 0,
    ReviewGateStatus.PENDING: 2,
    ReviewGateStatus.INVALID: 3,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a C003 product review pack v2")
    parser.add_argument("--pack-dir", type=Path, required=True)
    parser.add_argument("--source-export", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path)
    return parser.parse_args(argv)


def _write_complete_summary(path: Path, serialized: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(serialized, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(
    argv: list[str] | None = None,
    *,
    validated_at: AwareDatetime | None = None,
) -> int:
    args = parse_args(argv)
    result = validate_product_review_pack(
        args.pack_dir,
        args.source_export,
        validated_at=validated_at or datetime.now(UTC),
    )
    serialized = json.dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    print(serialized, end="")
    if result.status is ReviewGateStatus.COMPLETE and args.summary_output is not None:
        _write_complete_summary(args.summary_output, serialized)
    return EXIT_CODES[result.status]


if __name__ == "__main__":
    raise SystemExit(main())
```

The result serializer must not include sample rows or raw human notes. If the current result model includes `ReviewIssue.message`, keep messages categorical and sanitized.

- [ ] **Step 4: Run CLI and related tests and verify GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_product_review.py -q
.venv\Scripts\python.exe -m pytest tests\test_audit_c003.py tests\test_extension_selection.py tests\test_product_review.py -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
```

Expected: exit-code tests pass and no PENDING/INVALID summary file is created.

- [ ] **Step 5: Commit the operator CLI**

```powershell
git add scripts\validate_product_review.py tests\test_product_review.py
git diff --cached --check
git commit -m "feat: add C003 review validation CLI"
```

---

### Task 6: Build and Verify the Live v2 Pack Without Human Labels

**Files:**
- Generated, ignored: `build/extension-review-v2/README.md`
- Generated, ignored: `build/extension-review-v2/manifest.json`
- Generated, ignored: `build/extension-review-v2/samples.csv`
- Generated, ignored: `build/extension-review-v2/product_review_labels.csv`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/CODEX_HANDOFF.md`
- Modify: `docs/evidence/PHASE_1_EXTENSION_REVIEW.md`

**Interfaces:**
- Consumes: verified local `data/c003-products.jsonl` and existing v1 `samples.csv`.
- Produces: actual v2 pack, hash comparison evidence, `PENDING 0/100`, updated tracked documentation.
- No live API call is needed because the verified export already exists.

- [ ] **Step 1: Run a clean preflight**

Run:

```powershell
git status --short --branch
Test-Path -LiteralPath 'data\c003-products.jsonl'
Test-Path -LiteralPath 'build\extension-review\samples.csv'
Test-Path -LiteralPath 'build\extension-review-v2'
git check-ignore -v 'data/c003-products.jsonl' 'build/extension-review-v2/samples.csv'
.venv\Scripts\python.exe -m pytest tests\test_audit_c003.py tests\test_extension_selection.py tests\test_product_review.py -q
```

Expected: worktree is clean; export and v1 samples exist; v2 directory is absent; both generated paths are ignored; focused tests pass. If v2 already exists, inspect and report it instead of deleting it.

- [ ] **Step 2: Generate the v2 pack from the verified export**

Run:

```powershell
.venv\Scripts\python.exe scripts\build_extension_review.py --input data\c003-products.jsonl --output-dir build\extension-review-v2 --seed 20260823
```

Expected: exit `0` and exactly four files. The command must not require or print an API key.

- [ ] **Step 3: Prove sample preservation and manifest identity**

Run:

```powershell
$v1Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath 'build\extension-review\samples.csv').Hash
$v2Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath 'build\extension-review-v2\samples.csv').Hash
if ($v1Hash -ne $v2Hash) { throw 'v2 samples differ from preserved v1 samples' }
Write-Output "samples_sha256=$v2Hash"
Get-ChildItem -LiteralPath 'build\extension-review-v2' -File | Sort-Object Name | Select-Object Name,Length
```

Expected: both hashes equal the currently recorded
`BCF1702FD7C1D85B7B676FA66F752FC04853FAC3AB9C9A2DB48D4353534B774C`; files are exactly README, manifest, product labels and samples. If the hash differs, stop before editing tracked docs.

Parse `manifest.json` without printing product rows and confirm:

- contract version `c003-product-review-v2`;
- export hash `CF0D58B478408448F1D9FC0C2A5EB22E3E08055675072C8B863CD6E112703B7E`;
- sample count 100;
- each group 20;
- mapping rule version list `ingredient-map-v1`.

- [ ] **Step 4: Run the real validator and require PENDING exit 2**

Run:

```powershell
.venv\Scripts\python.exe scripts\validate_product_review.py --pack-dir build\extension-review-v2 --source-export data\c003-products.jsonl
$reviewExit = $LASTEXITCODE
if ($reviewExit -ne 2) { throw "expected PENDING exit 2, got $reviewExit" }
```

Expected output contains `"status": "PENDING"`, `"valid_label_count": 0`, `"pending_label_count": 100`, `"advertising_evidence_status": "NOT_MEASURED"`, `"extension_recommendation_status": "BLOCKED"`, and `"finalized": false`. No summary file is created.

- [ ] **Step 5: Validate security and Git-ignore boundaries**

Check only counts for key/token patterns; do not print matched values. Confirm:

- actual local API key value is absent from all four files;
- URLs, C003 envelope fields and prohibited metadata are absent;
- `git status --short` does not show either review-pack;
- `git ls-files -- data build` remains empty;
- v1 files still exist and their hashes are unchanged.

- [ ] **Step 6: Update tracked operator documentation with observed facts**

Apply these exact semantic changes:

- `AGENTS.md`: replace the stale Phase 0 “현재 첫 작업” with v2 product review labels and validation; keep Phase 2 blocked.
- `README.md`: state that v1 numeric scores are superseded, v2 pack is generated locally, actual v2 status is `PENDING 0/100`, ad evidence `NOT_MEASURED`, recommendation `BLOCKED`; add build and validate commands.
- `docs/CODEX_HANDOFF.md`: record implementation commit range, exact tests and actual v2 hashes; point the next operator to `product_review_labels.csv`.
- `docs/evidence/PHASE_1_EXTENSION_REVIEW.md`: preserve v1 evidence as historical, add a dated v2 section with four file hashes, manifest values, sample identity equality, validation exit `2`, and the no-recommendation boundary.

Do not claim human review, official advertising corpus, extension recommendation, Phase 2, merge or push complete.

- [ ] **Step 7: Run project verification before the docs commit**

Run:

```powershell
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\python.exe -m pytest tests\test_identity.py tests\test_ingredients.py tests\test_official.py tests\test_product_evidence.py tests\test_safety.py tests\test_evaluation_dataset.py tests\test_product_review.py -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
git status --short --branch
```

Expected: all tests pass, coverage does not regress below 96%, Ruff and diff checks pass, and only the four intended tracked docs are modified. Report exact observed counts rather than copying the pre-change `204` and `106` values.

- [ ] **Step 8: Commit verified v2 readiness documentation**

After staged secret scanning:

```powershell
git add AGENTS.md README.md docs\CODEX_HANDOFF.md docs\evidence\PHASE_1_EXTENSION_REVIEW.md
git diff --cached --check
git commit -m "docs: record C003 review v2 readiness"
```

---

### Task 7: Synchronize the Obsidian Wiki and Perform Final QA

**Files:**
- Modify: `%USERPROFILE%\Desktop\AI-Agent-Wiki\AI-Sessions\wiki\projects\근거있어.md`
- Modify: `%USERPROFILE%\Desktop\AI-Agent-Wiki\AI-Sessions\conversations\2026-08-22-근거있어-코덱스-핸드오프.md`
- Modify: `%USERPROFILE%\Desktop\AI-Agent-Wiki\index.md`
- Modify: `%USERPROFILE%\Desktop\AI-Agent-Wiki\log.md`

**Interfaces:**
- Consumes: final project commits and freshly observed test/hash/PENDING evidence.
- Produces: a separate clean wiki commit and final evidence report.

- [ ] **Step 1: Re-read wiki rules and current notes before editing**

Run read-only checks from `%USERPROFILE%\Desktop\AI-Agent-Wiki`:

```powershell
Get-Content -LiteralPath 'AGENTS.md' -Raw
Get-Content -LiteralPath 'index.md' -Raw
Get-Content -LiteralPath 'log.md' -Tail 20
Get-Content -LiteralPath 'AI-Sessions\wiki\projects\근거있어.md' -Raw
Get-Content -LiteralPath 'AI-Sessions\conversations\2026-08-22-근거있어-코덱스-핸드오프.md' -Raw
git status --short --branch
```

Expected: wiki worktree is clean. If unrelated user changes exist, preserve them and stop before overlapping edits.

- [ ] **Step 2: Update the four wiki files with the v2 boundary**

Record only verified facts:

- v1 numeric score contract was rejected because C003 has no advertising content and no 100-row-to-5-group aggregation rule;
- approved design commit `bdf95af` and actual implementation commit range;
- v2 exact sample preservation and actual hashes;
- v2 human labels remain `0/100`, `PENDING`;
- ad evidence is `NOT_MEASURED`, recommendation `BLOCKED`, final `false`;
- next action is human mapping/function review, not advertisement scoring or Phase 2;
- official ad corpus remains a separate design after v2 review tooling.

Update the existing index description rather than adding a duplicate 근거있어 link. Append one dated `save` line to `log.md`.

- [ ] **Step 3: Verify and commit wiki changes separately**

Run:

```powershell
git diff --check
git diff --name-status
git status --short --branch
```

Confirm exactly the four intended files changed, scan staged text for secret values without printing matches, and then:

```powershell
git add -- 'AI-Sessions/conversations/2026-08-22-근거있어-코덱스-핸드오프.md' 'AI-Sessions/wiki/projects/근거있어.md' 'index.md' 'log.md'
git diff --cached --check
git commit -m "save: record ClaimLedger review contract v2"
```

Use per-command `-c safe.directory=%USERPROFILE%/Desktop/AI-Agent-Wiki` if Windows ownership checks require it; do not modify global Git configuration.

- [ ] **Step 4: Run final project and repository proof**

After every commit, freshly run:

```powershell
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
git status --porcelain=v1
git log -8 --oneline
```

Also verify:

- live v2 validator still exits `2` with `PENDING 0/100`;
- v1 and v2 sample hashes remain identical;
- generated artifacts remain ignored and untracked;
- project branch and wiki worktree are clean;
- project `main` remains `cd7095b`;
- no merge, remote creation, push or worktree deletion occurred.

- [ ] **Step 5: Report the proven completion level**

Report:

- created/modified tracked files and both commit lists;
- exact fresh test count, coverage, Ruff and diff results;
- actual v2 manifest and four file hashes;
- actual `PENDING 0/100` result and CLI exit `2`;
- explicit statement that this completes review-tool readiness only;
- next manual action: fill `product_review_labels.csv` using `samples.csv`;
- explicit blocks: no ad corpus, no recommendation, no final ingredient, no Phase 2, no merge/push.

Do not invoke `finishing-a-development-branch` because the broader project and human review gate are not complete. Preserve the worktree for the next review session.
