# Codex 인수인계 — 근거영수증 / ClaimLedger

- 기준일: `2026-08-24 Asia/Seoul`
- 작업 브랜치: `phase-0-c003-data-gate`
- 상태: **Phase 1 오프라인 제품 근거 기반 구현·검증 완료, 라이브 확장 원료 검토 대기**
- 정확도 원칙: 신원·공식 출처·필수 근거가 부족하거나 충돌하면 추정하지 않고
  `ambiguous` 또는 `unverifiable`로 중단한다.

## 현재 검증 결과

깨끗한 작업 트리에서 다음 명령을 새로 실행했다.

```cmd
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
git status --short --branch
```

- 전체 테스트: `182 passed`
- 전체 커버리지: `96%` (`802` statements, `34` missed)
- Ruff: `All checks passed!`
- `git diff --check`: exit `0`, 오류 없음
- 검증 직후 상태: `## phase-0-c003-data-gate` (변경 없음)

핵심 불변식 묶음도 별도로 실행했다.

```cmd
.venv\Scripts\python.exe -m pytest tests\test_identity.py tests\test_ingredients.py tests\test_official.py tests\test_product_evidence.py tests\test_safety.py tests\test_evaluation_dataset.py -q
```

결과는 `106 passed`다. 제품 신원 확인, 원료 매핑, 공식 원문 보존,
안전 승인 금지, 제품 근거 준비 상태, 평가 데이터 계약을 포함한다.

## Phase 1에서 구현된 범위

- 불변 평가 케이스와 오인 승인률·확인 재현율·Coverage·검증 불가 수의 분리 계산
- 제품명·업체명·신고번호 검색 표현 정규화와 결정적 후보 순위
- 검색 결과와 사용자 제품 확정의 분리: 검색은 `ConfirmedProduct`를 만들지 않음
- 8개 원료군의 좁고 감사 가능한 원문 기반 매핑과 `verified_mapping` / `ambiguous` /
  `unverifiable` 상태
- 공식 기능성·주의 문구의 literal source segment 보존과 제한된 표현 강도 분류
- 공식 출처가 확인된 일반 주의 신호와 `is_safety_clearance == false` 불변식
- 확인 제품, 공식 문구, 원료 매핑, 안전 신호를 동일 제품 스냅샷에 묶는 제품 근거
  준비 게이트
- 다섯 비교 원료군의 결정적 표본 추출, 균등 가중 점수, 사람 검토 입력 검증,
  recommendation-only 결과
- C003 제품 6개 필드만 내보내는 redacted JSONL export와 오프라인 review-pack 생성기
- 라이브 JSONL, export staging, review-pack 산출물의 Git ignore 경계

Phase 1 구현 커밋은 시작 커밋을 포함하는 정확한 범위
`37a8234^..b1f625a`이며 총 `20`개다. Coverage 정의를 실제 출력 중
`UNVERIFIABLE`이 아닌 비율로 바로잡은 계획 수정은 별도 커밋 `1da369e`다.

## 라이브 측정과 사람 검토 상태

- `FOOD_SAFETY_API_KEY`: 현재 프로세스 환경에 없음
- 라이브 C003 export: `NOT RUN`
- 라이브 review-pack 생성: `NOT RUN`
- 현재 export 건수·고유 신고번호 수·필드 완전성: `NOT MEASURED`
- 비교군별 pool/sample 수와 `verified_mapping` / `ambiguous` / `unverifiable`
  건수·비율: `NOT MEASURED`
- 계획 표본: 다섯 비교군별 `20`, 총 `100`, seed `20260823`
- 100건 사람 라벨 검토: `PENDING`
- 선택된 확장 원료: 없음. 검토 전에는 추천 또는 최종 선택을 만들지 않는다.

Phase 0의 `45,720 / 45,720` 수치는
[`docs/evidence/C003_COVERAGE_REPORT.md`](evidence/C003_COVERAGE_REPORT.md)에 기록된
`2026-08-22T15:27:28.041740+00:00`의 별도 과거 측정이다. 이를 현재 Phase 1
export 또는 확장 원료 검토 결과로 재사용하지 않는다.

## 다음 검토 작업

승인된 운영자가 키를 로컬 CMD 환경에만 설정한 뒤 다음을 실행한다. 키 값을 문서,
로그, 명령 출력에 복사하지 않는다.

```cmd
set FOOD_SAFETY_API_KEY=your-local-key
.venv\Scripts\python.exe scripts\audit_c003.py --export-products data\c003-products.jsonl
.venv\Scripts\python.exe scripts\build_extension_review.py --input data\c003-products.jsonl --output-dir build\extension-review --seed 20260823
```

그 다음 다섯 비교군이 각각 고유 신고번호 `20`개를 제공하는지 확인하고, 여섯 export
필드의 완전성 및 매핑 상태 건수·비율을 기록한다. 예상하지 않은 응답 envelope, 키,
URL, 사용자 데이터가 없는지 검사한 뒤 광고 위험·기능 다양성·구현 가능성에 대한 사람
라벨 `100`건을 모두 수집한다. 모든 라벨이 유효할 때만 recommendation-only 결과를
검토하며, 최종 확장 원료 선택은 별도 사용자 결정으로 남긴다.

상세 상태는
[`docs/evidence/PHASE_1_EXTENSION_REVIEW.md`](evidence/PHASE_1_EXTENSION_REVIEW.md)를
갱신한다.

## 아직 구현하지 않은 범위

다음은 Phase 1 완료로 간주하지 않는다.

- 이미지 OCR 및 불변 source span
- 판매자 페이지 URL crawler, 출처 분류, SSRF 방어
- LLM 원자 주장 추출 및 사용자 주장 확인
- 과학 논문 RAG와 근거 적용 가능성 분류
- 전체 광고 주장 verdict 규칙과 동결 100건 정답 평가세트
- FastAPI, 영속화, 감사 이벤트, SSE
- React 사용자 확인 흐름과 접근성·이해도 검증
- 인증·권한 관리
- `main` 병합, 원격 저장소 생성, push, 배포

## 남아 있는 비차단 개선사항

- `search_products(..., limit=...)`의 음수 값 명시적 거부. 현재 Python 음수 slicing
  동작이 남아 있으며 Phase 1 검증에서 해결된 것으로 주장하지 않는다.
- schema-valid free-text 필드와 추가 자격 증명 형식을 대상으로 한 고신뢰 secret-format
  테스트 확장. 현재 tracked/staged 스캔 통과와 별개의 방어 심화 항목이다.

## Git·보안 경계 확인

- 라이브 경로 `data/c003-products.jsonl`은 `.gitignore`의 정확한 경로 규칙으로 보호된다.
- `build/c003-export/`와 `build/extension-review/`은 `build/` 규칙으로 보호된다.
- 검증 시 세 경로는 모두 없었고 `git ls-files -- data build` 및
  `git ls-files '*.jsonl'` 결과는 비어 있었다.
- tracked/staged 내용의 key-like assignment와 고신뢰 토큰 형식을 검사하고, fixture 및
  evidence 문서의 건강 상세정보·후기·Q&A 구조 필드를 별도로 검사한다. 허용된 빈 환경
  선언, 코드 변수, 합성 `test-key`, 문서 예시만 수동 확인 대상으로 남긴다.
- 검증 시작과 문서 작성 시 `main`은
  `cd7095b1ab19781dcacaeb09ccc86402782509d1`에 있었고 작업 브랜치의 merge-base와
  같았다. 작업은 별도 worktree에서만 수행했다.
- `git remote -v` 결과가 비어 있고 브랜치 upstream도 없다. 원격 push는 수행하지 않았다.

## 확정된 제품 원칙

- 제품 작업명은 **근거영수증**, 영문·저장소명은 **ClaimLedger**다.
- MVP는 건강기능식품 광고 주장과 공식·과학적 근거의 일치 여부만 다룬다.
- 개인 맞춤 효능·안전·상호작용·진단 기능은 범위에서 제외한다.
- LLM은 이후 단계에서 주장을 추출하지만 최종 판정은 결정적 규칙이 수행한다.
- 제품 자동확정은 하지 않고 후보를 보여준 뒤 사용자가 신고번호를 확정한다.
- 가장 중요한 품질 지표는 오인 승인률이며, 불확실성은 유효한 결과다.

## 관련 경로

- 현재 worktree: `C:\Users\Donga\Desktop\DONGA AI LAB\DONGA KDT 3RD PROJECT\_persnal V1\.worktrees\phase-0-c003-data-gate`
- 기본 프로젝트 worktree: `C:\Users\Donga\Desktop\DONGA AI LAB\DONGA KDT 3RD PROJECT\_persnal V1`
- 복습 저장소: `C:\WORK\WORK\donga-review`
- AI Agent Wiki: `C:\Users\Donga\Desktop\AI-Agent-Wiki`

## 다음 코덱스에 전달할 한 문장

> Phase 1 오프라인 제품 근거 기반은 182개 테스트와 핵심 불변식 106개로 검증됐지만,
> 라이브 export와 100건 사람 검토는 아직 실행되지 않았다. 승인된 운영자 키로 redacted
> review pack을 만든 뒤 측정값과 라벨을 채우기 전에는 확장 원료를 선택하거나 Phase 2를
> 시작하지 말라.
