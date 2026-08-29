# 근거있어

**건강광고, 말보다 근거부터.**

근거있어는 건강기능식품 광고가 한 주장을 **공식 제품 정보와 선별된 과학적 근거에
대조하여, 확인된 범위와 확인할 수 없는 범위를 주장별 근거영수증으로 보여주는 정확도
우선 검수 서비스**입니다. 결정적 검증 로직과 파이썬 패키지는 내부 엔진명
`ClaimLedger`와 `claimledger`를 유지합니다.

## 현재 상태

- 2026-08-22: 3차 프로젝트 주제와 제품 원칙 확정
- 2026-08-24: Phase 1의 결정적 제품 검색·원료 매핑·공식 문구·안전 신호·제품 근거
  준비 게이트·claim-bound support 경계·평가 계약·6필드 확장 원료 review-pack 기반을
  구현했습니다.
- 2026-08-27: 로컬 운영자 키로 C003 라이브 export를 세 번 시도했지만, 식약처가
  모두 `ERROR-503`을 반환하여 fail closed로 중단했습니다. 과거 성공 측정과 최신 실패
  시도를 별도 보고서로 보존하는 회귀 수정은 `7271074`에 기록했습니다.
- 2026-08-27 21:42 KST: C003 재시도에서 `INFO-000`을 받아 `45,907 / 45,907`건을
  redacted 6필드 JSONL로 생성했습니다. 신고번호 중복은 `0`이며, seed `20260823`으로
  다섯 비교군 각 `20`건·총 `100`건의 review-pack도 생성·검증했습니다.
- 2026-08-28: 기존 v1의 광고 위험·기능 다양성·구현 가능성 1~5점 계약을 역사적
  산출물로 보존하고 사용 중단했습니다. v2는 제품 매핑과 공식 기능성 원문의 사람 검토,
  pack 무결성 검증, Wilson 구간이 포함된 비추천 통계, 상태별 CLI 종료코드만 제공합니다.
- 2026-08-28: 소비자 서비스·프로젝트명을 **근거있어**로 확정했습니다. 대표 결과물은
  **근거영수증**, 내부 검증엔진은 **ClaimLedger**, 저장소 슬러그는 `geungeo-isseo`입니다.
- 최신 오프라인 검증은 `280 passed`, 전체 커버리지 `96.83%`이며 Ruff와
  `git diff --check`도 통과했습니다.
- 라이브 export, 보존된 v1 pack, 현재 v2 pack은 로컬 ignored 경로에 존재합니다.
  2026-08-30에 재검증한 v2 제품 매핑·공식 기능성 원문 사람 검토는 `COMPLETE`: 유효 라벨
  `100건 전부`다. 대기 라벨은 `0 / 100`, 매핑은 `99 correct / 1 incorrect / 0 uncertain`, 기능성 원문은
  `usable 100 / 100`입니다. 단, `usable`은 해당 제품 행의 공식 기능성 원문을 검토에 사용할
  수 있다는 뜻일 뿐 원료가 그 기능을 유발한다는 인과 근거가 아닙니다. 유일한 매핑 오류는
  `red_ginseng`의 alias collision입니다. 라벨 SHA-256은
  `A00B3C1A038DBFD06484A89A6C1B41AAA63837D3BD87FAC29E2AF5DF0E011CC1`입니다.
  기능적 역할 검토 A는 아직 구축하지 않았고, 광고 근거 `NOT_MEASURED`, 추천 `BLOCKED`,
  `finalized=false`는 유지됩니다. 확장 원료 추천·최종 선택은 만들지 않았습니다.
- OCR, URL crawler, LLM, RAG, 전체 판정 규칙, FastAPI, React, 인증은 아직 구현하지
  않았습니다. 따라서 현재 코드는 완성된 애플리케이션이나 배포 서비스가 아닙니다.
- 복습 코드는 별도 저장소 `C:\WORK\WORK\donga-review`에 유지합니다.

## 코덱스에서 이어가기

1. 병합 전에는 코덱스에서
   `C:\Users\Donga\Desktop\DONGA AI LAB\DONGA KDT 3RD PROJECT\geungeo-isseo\.worktrees\phase-0-c003-data-gate`
   worktree를 엽니다.
2. [AGENTS.md](AGENTS.md)를 먼저 읽습니다.
3. [코덱스 핸드오프](docs/CODEX_HANDOFF.md)에서 구현 범위, 검증 결과, 미구현 경계를
   확인합니다.
4. [Phase 1 확장 원료 검토 상태](docs/evidence/PHASE_1_EXTENSION_REVIEW.md)에 기록된
   운영 명령과 사람 검토 절차를 따릅니다.

현재 다음 작업은 화면 제작이나 Phase 2 구현이 아니라 **기능적 역할 검토 A를 구축하는
것**입니다. v2의 다섯 비교군 100건 사람 라벨은 이미 유효성 검증을 마쳤으며, 입력·기록은
`build/extension-review-v2/product_review_labels.csv`에 보존됩니다. 기존
`build/extension-review/review_labels.csv`의 숫자 점수는 더 이상 사용하지 않습니다.

검증된 로컬 export에서 v2 pack을 재생성하고 상태를 확인하는 명령은 다음과 같습니다.

```cmd
.venv\Scripts\python.exe scripts\build_extension_review.py --input data\c003-products.jsonl --output-dir build\extension-review-v2 --seed 20260823
.venv\Scripts\python.exe scripts\validate_product_review.py --pack-dir build\extension-review-v2 --source-export data\c003-products.jsonl
```

2026-08-28 당시 빈 템플릿에서 두 번째 명령의 출력 상태는 `PENDING 0 / 100`이고
종료코드는 `2`였다. 현재 완료된 v2 검증은 종료코드 `0`, `COMPLETE`, 유효 라벨 `100건 전부`다.
대기 라벨은 `0 / 100`이다. 기능적 역할 검토 A와 공식 광고 근거가 별도로 끝나기 전에는 추천이
계속 차단됩니다.

오프라인 검증 명령은 다음과 같습니다.

```cmd
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
```

## 목표 MVP 경계 (현재 미구현 기능 포함)

아래는 최종 MVP의 목표이며 현재 지원 기능 목록이 아닙니다. 실제 구현 상태는 위의
`현재 상태`와 [코덱스 핸드오프](docs/CODEX_HANDOFF.md)를 기준으로 판단합니다.

MVP가 하는 일:

- 사용자가 광고 이미지 또는 텍스트를 입력한다.
- AI가 광고 문구에서 검증 가능한 주장을 원자 단위로 추출한다.
- 사용자가 제품 후보를 직접 선택하여 제품 신원을 확정한다.
- 공식 제품 정보, 공식 기능성 문구, 선별된 과학적 근거를 대조한다.
- 규칙 엔진이 `확인됨`, `근거 불일치`, `근거 부족`, `검증 불가`, `직접 반박됨` 중 하나를 출력한다.
- 모든 결과에 출처, 기준일, 적용 규칙, 불확실성을 함께 표시한다.

MVP가 하지 않는 일:

- 개인에게 효과가 있다고 보장
- 개인별 복용 안전성·의약품 상호작용 판정
- 질병 진단·치료·예방 조언
- 제품 실물의 함량·순도·오염 여부 판정
- 민간 서비스가 공식 광고 심의나 법적 판단을 대체한다고 주장

## 문서 지도

- [프로젝트 브리프](docs/PROJECT_BRIEF.md): 문제, 범위, 품질 기준, 일정, 장기 사업 로드맵
- [정확도 우선 경계 결정](docs/decisions/0001-accuracy-first-boundary.md): 왜 이 범위로 시작하는지
- [코덱스 핸드오프](docs/CODEX_HANDOFF.md): 다음 세션이 바로 시작할 수 있는 현재 상태
- [Phase 0 구현 계획](docs/superpowers/plans/2026-08-22-phase-0-data-confidence-gate.md): 첫 구현 체크리스트
- [Phase 1 구현 계획](docs/superpowers/plans/2026-08-23-phase-1-product-evidence-foundation.md):
  제품 근거 기반 구현·검증 체크리스트
- [C003 사람 검토 v2 설계](docs/superpowers/specs/2026-08-28-c003-human-review-contract-v2-design.md):
  사람 라벨, 무결성, 통계, 비추천 경계의 정본
- [C003 사람 검토 v2 실행 계획](docs/superpowers/plans/2026-08-28-c003-human-review-contract-v2.md):
  v2 구현·생성·검증 체크리스트
- [근거있어 브랜드·명명 설계](docs/superpowers/specs/2026-08-28-geungeo-isseo-brand-design.md):
  서비스·결과물·엔진·저장소 이름의 역할 경계
- [근거있어 프로젝트 이름 변경 계획](docs/superpowers/plans/2026-08-28-geungeo-isseo-project-rename.md):
  저장소·위키·linked worktree 이동과 검증 절차
- [Phase 1 확장 원료 검토 상태](docs/evidence/PHASE_1_EXTENSION_REVIEW.md): 라이브 측정과
  사람 검토의 현재 상태
- [최신 C003 라이브 시도](docs/evidence/C003_LIVE_ATTEMPT.md): 최신 성공 측정을 덮어쓰지
  않고 보존한 라이브 성공·차단 상태

## 지식 기록소

프로젝트의 정본 기록은 별도 Obsidian vault에 함께 보존합니다.

- `C:\Users\Donga\Desktop\AI-Agent-Wiki`
- 개인 메모 vault인 `JISOO.DOC`과 혼동하지 않습니다.
- 프로젝트 코드와 현재 검증 결과가 위키의 과거 기록보다 우선합니다.

## 보안

- API 키와 개인정보는 저장소에 커밋하지 않습니다.
- 상위 폴더 `C:\WORK\WORK\.env`의 값을 복사하거나 문서에 기록하지 않습니다.
- 필요한 키는 이 저장소의 `.env.example` 형식만 정의하고 실제 값은 사용자가 로컬 환경에 설정합니다.
