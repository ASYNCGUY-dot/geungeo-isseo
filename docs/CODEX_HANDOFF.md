# Codex 인수인계 — 근거있어

- 기준일: `2026-08-29 Asia/Seoul`
- 작업 브랜치: `phase-0-c003-data-gate`
- 상태: **C003 사람 검토 v2 pack·검증 CLI 준비 완료, 사람 라벨 100건 검토 대기**
- 정확도 원칙: 신원·공식 출처·필수 근거가 부족하거나 충돌하면 추정하지 않고
  `ambiguous` 또는 `unverifiable`로 중단한다.

## 현재 검증 결과

현재 worktree 내용에 대해 다음 명령을 새로 실행했다.

```cmd
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
git status --short --branch
```

- 전체 테스트: `280 passed`
- 전체 커버리지: `96.83%` (`1,260` statements, `40` missed)
- Ruff: `All checks passed!`
- `git diff --check`: exit `0`, 오류 없음
- 핵심 불변식 묶음: `175 passed`
- 라이브 export, 보존된 v1 pack, 현재 v2 pack: 모두 로컬 ignored 경로에 존재
- v2 네 파일의 고신뢰 key/token, URL, C003 envelope, 금지 메타데이터 패턴: 각 `0`
- 메인 checkout의 로컬 `.env`에서 실제 키 값 `1`개를 값 비노출 방식으로 대조한 결과,
  v2 네 파일 내 동일 문자열: `0`
- 2026-08-29 저장소 루트를 `_persnal V1`에서 `geungeo-isseo`로 이동하고
  `git worktree repair`로 main·feature 양방향 절대경로를 복구했다.
- 최초 이동 후 테스트는 `.venv`의 기존 `__editable__.claimledger-0.1.0.pth`가 이전
  절대경로를 가리켜 수집 오류 14건으로 실패했다. 기존 editable 배포를 제거하고
  `pip install --no-deps --no-build-isolation --editable .`로 재설치한 뒤 이전 경로 0건,
  `claimledger` 새 경로 import, 전체 `280 passed`, Ruff 통과를 새로 확인했다.

핵심 불변식 묶음도 별도로 실행했다.

```cmd
.venv\Scripts\python.exe -m pytest tests\test_identity.py tests\test_ingredients.py tests\test_official.py tests\test_product_evidence.py tests\test_safety.py tests\test_evaluation_dataset.py tests\test_product_review.py -q
```

결과는 `175 passed`다. 제품 신원 확인, 원료 매핑, 공식 원문 보존,
안전 승인 금지, 제품 근거 준비 상태, 평가 데이터 계약, v2 사람 라벨·pack 무결성·완료
통계·CLI 경계를 포함한다.

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
- `confirmed` 양성 경로에서 버전이 지정된 claim fingerprint, 확인 제품 신고번호,
  literal matched evidence, source id/URL, 조회 시각을 묶는 불변 support record 경계
- 다섯 비교 원료군의 결정적 표본 추출과 기존 v1 숫자 점수 pack. v1의 광고 위험·기능
  다양성·구현 가능성 1~5점 및 recommendation-only 계약은 역사적 산출물로만 보존하며
  현재 검토에는 사용하지 않음
- v2 원료군 매핑·공식 기능성 원문 사람 라벨 계약, manifest·해시·원본·키 집합 무결성
  검증, `PENDING/INVALID/COMPLETE` 상태, 결정 가능 정밀도와 95% Wilson 구간,
  그룹·검토자·검토기간 비추천 통계
- v2 운영자 CLI의 `COMPLETE=0`, `PENDING=2`, `INVALID=3` 종료코드와 완료 상태에서만
  원자적으로 저장하는 비식별 summary
- C003 제품 6개 필드만 내보내는 redacted JSONL export, 동일 6필드 불변 review DTO,
  exporter-to-loader-to-sampler 오프라인 review-pack 생성기
- 라이브 JSONL, export staging, review-pack 산출물의 Git ignore 경계

원래 Task 1~8 구현 범위는 `37a8234^..b1f625a`의 `20`개이며, 초기 검증 인수인계
커밋은 `48cd278`이다. 본 문서를 포함한 final-fix는 단일 커밋 subject
`fix: close Phase 1 integration gaps`로 구성하며, 정확한 SHA와 최종 범위는 커밋 후
`git log`로 확인한다. Coverage 정의를 실제 출력 중 `UNVERIFIABLE`이 아닌 비율로
바로잡은 계획 수정은 별도 커밋 `1da369e`다.

사람 검토 v2 설계·계획은 `bdf95af`, `f0bb219`이며, 구현 범위는
`15c40b4^..3512e8d`의 5개 커밋이다. 순서대로 라벨 계약, v2 pack 생성, pack 신원
검증, 완료 통계, 운영자 CLI를 추가했다. 이 문서 커밋은 해당 범위 뒤에 별도로 기록한다.

## 라이브 측정과 사람 검토 상태

- 조회 시각: `2026-08-27T12:42:29.050550+00:00` (`21:42:29 KST`)
- 라이브 C003 export: `PASS`, API `INFO-000`, `45,907 / 45,907`
- 신고번호: 고유 `45,907`, 중복 `0`
- export 스키마: 모든 행이 승인된 정확히 6필드
- 결측: 제품명 `0`, 업체명 `0`, 기능성 `100`, 원재료 `1`, 섭취방법 `409`
- export 보안 검사: 실제 키 값·URL·응답 envelope·금지 메타데이터 검출 `0`
- export SHA-256: `CF0D58B478408448F1D9FC0C2A5EB22E3E08055675072C8B863CD6E112703B7E`
- v1 review-pack: 역사적 산출물로 로컬 보존, 다섯 비교군 각 `20`, 총 `100`
- v2 review-pack: `GENERATED_AND_VERIFIED`, 다섯 비교군 각 `20`, 총 `100`, 계약
  `c003-product-review-v2`, seed `20260823`, 규칙 `ingredient-map-v1`
- 표본 신고번호: 그룹별 고유 `20`, 전체 고유 `100`
- 표본 6필드 완전성: `100 / 100`
- 계획 표본: 다섯 비교군별 `20`, 총 `100`, seed `20260823`
- v1/v2 `samples.csv` 바이트 동일성: 확인됨, SHA-256
  `BCF1702FD7C1D85B7B676FA66F752FC04853FAC3AB9C9A2DB48D4353534B774C`
- v2 파일 SHA-256:
  - `README.md`: `4F5F610A64A7E90DDED10E3C468D9E330CE2D18092315A0DB0BABBEAB5BC4238`
  - `manifest.json`: `0E3086DF9F2A8895D7845E8B24D00DBE18A43CEEE9C6DC92CBE9095FD873D442`
  - `product_review_labels.csv`: `DC65DBC164CDB135C8C0B0FF7688CEB6F3766E92B6D47BBC0C55CB9FEA350CC8`
  - `samples.csv`: `BCF1702FD7C1D85B7B676FA66F752FC04853FAC3AB9C9A2DB48D4353534B774C`
- 실제 v2 검증: 프로세스 종료코드 `2`, `PENDING`, 유효 `0 / 100`, 대기 `100 / 100`
- 광고 근거 `NOT_MEASURED`, 확장 추천 `BLOCKED`, `finalized=false`
- 선택된 확장 원료: 없음. 공식 광고 근거와 100개 유효 사람 라벨 전에는 추천 또는
  최종 선택을 만들지 않는다.

현재 성공 상태는
[`docs/evidence/C003_LIVE_ATTEMPT.md`](evidence/C003_LIVE_ATTEMPT.md)에 별도로
기록했다. 비교군별 pool·mapping 상태·표본 상태와 파일 해시는
[`docs/evidence/PHASE_1_EXTENSION_REVIEW.md`](evidence/PHASE_1_EXTENSION_REVIEW.md)에
있다.

## 다음 검토 작업

기존 검증 export에서 v2 pack만 재생성하고 검증할 때는 API 키가 필요하지 않다.

```cmd
.venv\Scripts\python.exe scripts\build_extension_review.py --input data\c003-products.jsonl --output-dir build\extension-review-v2 --seed 20260823
.venv\Scripts\python.exe scripts\validate_product_review.py --pack-dir build\extension-review-v2 --source-export data\c003-products.jsonl
```

현재 빈 v2 템플릿은 두 번째 명령에서 종료코드 `2`를 반환한다. 라이브 C003 export
자체를 다시 받아야 할 때만 승인된 운영자가 `FOOD_SAFETY_API_KEY`를 로컬 환경에
설정하고 `scripts/audit_c003.py`를 별도로 실행한다. 키 값을 문서·로그·명령 출력에
복사하지 않는다.

현재 다음 작업은 `build/extension-review-v2/samples.csv`를 근거로
`build/extension-review-v2/product_review_labels.csv`의 매핑 판정·이유, 기능성 원문
상태·이유, 필요한 note, 검토자, timezone-aware 검토 시각을 100건 모두 사람이 입력한
뒤 validator를 다시 실행하는 것이다. 기존 v1 숫자 점수 파일은 채우지 않는다. 100개
라벨이 유효해도 공식 광고 근거가 `NOT_MEASURED`인 동안 추천과 최종 선택은 `BLOCKED`다.

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
- 공식 광고 사례 코퍼스와 광고 근거 측정 게이트
- FastAPI, 영속화, 감사 이벤트, SSE
- React 사용자 확인 흐름과 접근성·이해도 검증
- 인증·권한 관리
- 사용자 승인 후 별도로 수행할 `main` 병합·원격 연결·배포 운영 단계

## 남아 있는 비차단 개선사항

- `search_products(..., limit=...)`의 음수 값 명시적 거부. 현재 Python 음수 slicing
  동작이 남아 있으며 Phase 1 검증에서 해결된 것으로 주장하지 않는다.
- schema-valid free-text 필드와 추가 자격 증명 형식을 대상으로 한 고신뢰 secret-format
  테스트 확장. 현재 tracked/staged 스캔 통과와 별개의 방어 심화 항목이다.

## Git·보안 경계 확인

- 라이브 경로 `data/c003-products.jsonl`은 `.gitignore`의 정확한 경로 규칙으로 보호된다.
- `build/c003-export/`, `build/extension-review/`, `build/extension-review-v2/`는
  `build/` 규칙으로 보호된다.
- 현재 생성 경로는 로컬에 존재하지만 `git status`에서 제외되며,
  `git ls-files -- data build` 및 `git ls-files '*.jsonl'` 결과는 비어 있다.
- tracked/staged 내용의 key-like assignment와 고신뢰 토큰 형식을 검사하고, fixture 및
  evidence 문서의 건강 상세정보·후기·Q&A 구조 필드를 별도로 검사한다. 허용된 빈 환경
  선언, 코드 변수, 합성 `test-key`, 문서 예시만 수동 확인 대상으로 남긴다.
- 검증 시작과 문서 작성 시 `main`은
  `cd7095b1ab19781dcacaeb09ccc86402782509d1`에 있었고 작업 브랜치의 merge-base와
  같았다. 작업은 별도 worktree에서만 수행했다.
- 검증 시 `git remote -v` 결과, 브랜치 upstream, `refs/remotes`가 모두 비어 있었다.
  따라서 그 검증 시점의 checkout에는 구성된 remote·upstream·remote-tracking push
  목적지가 없었다. 이 현재 상태를 전체 Git 작업 이력에 대한 증명으로 확대하지 않는다.

## 확정된 제품 원칙

- 소비자 서비스·프로젝트명은 **근거있어**다.
- 주장별 대표 결과물은 **근거영수증**, 내부 검증엔진과 파이썬 패키지는
  **ClaimLedger**와 `claimledger`다.
- 로컬 폴더와 향후 원격 저장소 슬러그는 `geungeo-isseo`다.
- MVP는 건강기능식품 광고 주장과 공식·과학적 근거의 일치 여부만 다룬다.
- 개인 맞춤 효능·안전·상호작용·진단 기능은 범위에서 제외한다.
- LLM은 이후 단계에서 주장을 추출하지만 최종 판정은 결정적 규칙이 수행한다.
- 제품 자동확정은 하지 않고 후보를 보여준 뒤 사용자가 신고번호를 확정한다.
- 가장 중요한 품질 지표는 오인 승인률이며, 불확실성은 유효한 결과다.

## 관련 경로

- 현재 worktree: `C:\Users\Donga\Desktop\DONGA AI LAB\DONGA KDT 3RD PROJECT\geungeo-isseo\.worktrees\phase-0-c003-data-gate`
- 기본 프로젝트 worktree: `C:\Users\Donga\Desktop\DONGA AI LAB\DONGA KDT 3RD PROJECT\geungeo-isseo`
- 복습 저장소: `C:\WORK\WORK\donga-review`
- AI Agent Wiki: `C:\Users\Donga\Desktop\AI-Agent-Wiki`

## 다음 코덱스에 전달할 한 문장

> 근거있어의 ClaimLedger 엔진과 v2 사람 검토 계약은 280개 테스트, 96.83% 커버리지,
> 핵심 불변식 175개로 검증됐다. 2026-08-27 라이브 C003 `45,907 / 45,907`건과
> 2026-08-28 v2 5×20 pack도 검증됐지만 사람 라벨은 `PENDING 0 / 100`, 광고 근거는
> `NOT_MEASURED`, 추천은 `BLOCKED`다. 100건 검토와 별도 광고 근거 게이트 전에는
> 확장 원료를 선택하거나 Phase 2를 시작하지 말라.
