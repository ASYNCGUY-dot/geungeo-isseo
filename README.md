# 근거있어

**건강광고, 말보다 근거부터.**

근거있어는 건강기능식품 광고가 한 주장을 **공식 제품 정보와 선별된 과학적 근거에
대조하여, 확인된 범위와 확인할 수 없는 범위를 주장별 근거영수증으로 보여주는 정확도
우선 검수 서비스**입니다. 결정적 검증 로직과 파이썬 패키지는 내부 엔진명
`ClaimLedger`와 `claimledger`를 유지합니다.

## 현재 상태

- 2026-09-27 (A 종료): 사용자 결정으로 사람 검토 대신 AI 대리 라벨을 반영해 기능성 역할 게이트 A를
  `COMPLETE`로 닫았습니다. 비타민D·코엔자임Q10·마그네슘 `ROLE_ELIGIBLE`, 밀크씨슬·홍삼 `ROLE_INSUFFICIENT`이며
  사람 기준 정확도는 미측정입니다. 확장 원료 선정(B·C)은 미루고 핵심 원료 3종 MVP를 먼저 만듭니다.
  [A 종료 기록](docs/evidence/FUNCTIONAL_ROLE_GATE_AI_PROXY_2026-09-27.md)을 우선합니다.
- 2026-09-27: AI 초안의 남은 네 그룹 214행 의미 재검토를 마쳤습니다. 마그네슘 55행도 다른 모델(Claude)로
  교차 확인해 269행 전체의 재검토 기록을 갖췄습니다. 수정 행은 0입니다. 블라인드 실험이나 사람 검토가 아니며,
  사람용 라벨은 바뀌지 않았습니다(운영 검증 `PENDING / 유효6 / 대기269 / 이슈0 / exit2`).
  [9월 27일 완료 기록](docs/evidence/FUNCTIONAL_ROLE_AI_REVIEW_2026-09-27.md)을 우선합니다.
- 2026-09-23: AI 초안 269행의 키·1,614개 원문 필드·490개 인용을 전수 검사했습니다.
  감사 지적 2건을 수정했지만 네 그룹 214행의 의미 재검토는 미완료입니다.
  실제 공식 출처 재확인 후 별도 9/23 규칙·pack 복구: `PENDING / 유효6 / 대기269 / 이슈0 / exit2`.
  오늘 전체 `609 passed`(293.72초), 코드 커버리지 97.22%, Ruff 통과입니다. 판정 정확도가 아닙니다.
  [현재 AI 중간 인계](docs/evidence/FUNCTIONAL_ROLE_AI_REVIEW_2026-09-23.md) ·
  [최신성 복구](docs/evidence/FUNCTIONAL_ROLE_RECHECK_2026-09-23.md)를 우선합니다.

- 2026-09-14: 공식 고시 ZIP 재다운로드·후속 개정 목록 대조 후 기존 원본과 같은 해시를
  확인했습니다. 최신성 시각만 갱신한 별도 규칙·pack으로 승인된 AI 라벨 5건을 보존 이관했습니다.
  실제 검증은 `PENDING`, 유효 6(승인 AI 5 + 상속 제외 1), 대기 269, 이슈 0, exit 2입니다.
  AI 라벨은 사람·전문가 정답이 아닙니다. 1번·5번은 코드와 AI의 판단 차이를 보존합니다.
  [복구 근거와 다음 작업](docs/evidence/FUNCTIONAL_ROLE_RECHECK_2026-09-14.md)을 먼저 확인하세요.
  같은 날 전체 테스트 `609 passed`(328.52초), 코드 커버리지 `97.22%`, Ruff도 새로 통과했습니다.
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
- 2026-09-09 입력 오류 방어 보완 후 최종 오프라인 검증은 `609 passed`, 코드 커버리지
  `97.22%`입니다. 계획의 `97%` 목표를 통과했습니다. 이 수치는 서비스 판정 정확도가 아닙니다.
  잘못된 규칙 자료형의 예외 종료를 `INVALID`로 처리하고, 파일·CSV·출처·검토 이력·저장 실패
  회귀 테스트를 보강했습니다. 독립 코드 검토에서 지적된 CLI 테스트의 만료 오인 통과도 수정했습니다.
- 라이브 export, 보존된 v1 pack, 현재 v2 pack은 로컬 ignored 경로에 존재합니다.
  2026-08-30에 재검증한 v2 제품 매핑·공식 기능성 원문 사람 검토는 `COMPLETE`: 유효 라벨
  `100건 전부`다. 대기 라벨은 `0 / 100`, 매핑은 `99 correct / 1 incorrect / 0 uncertain`, 기능성 원문은
  `usable 100 / 100`입니다. 단, `usable`은 해당 제품 행의 공식 기능성 원문을 검토에 사용할
  수 있다는 뜻일 뿐 원료가 그 기능을 유발한다는 인과 근거가 아닙니다. 유일한 매핑 오류는
  `red_ginseng`의 alias collision입니다. 라벨 SHA-256은
  `A00B3C1A038DBFD06484A89A6C1B41AAA63837D3BD87FAC29E2AF5DF0E011CC1`입니다.
  기능적 역할 검토 A의 코드·규칙·275행 검토팩을 구축했고, 광고 근거 `NOT_MEASURED`, 추천 `BLOCKED`,
  `finalized=false`는 유지됩니다. 확장 원료 추천·최종 선택은 만들지 않았습니다.
- 2026-09-04: CHOI(추출)·DOHA(독립 검토)의 재확인을
  `2026-09-04T17:28:58+09:00`으로 기록하고, 공식 고시 제2026-43호에 근거한 다섯
  원료 규칙을 `7678890`으로 커밋했습니다. 마그네슘은 명시적인 기능성 연결을 요구합니다.
- 2026-09-09: 기존 검토팩 재검증은 `PENDING`, 유효 `1 / 275`, 대기 `274 / 275`,
  이슈 `0`, CLI 종료코드 `2`입니다. 유효 1행은 v2 매핑 오류의 상속 제외 행이며
  신규 제품별 사람 검토를 완료했다는 뜻은 아닙니다. 원료별 적격성·판정 정확도는 아직 미측정입니다.
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

기능성 역할 게이트 A는 2026-09-27 사용자 결정으로 AI 대리 라벨을 써서 `COMPLETE`가 됐습니다(사람 정확도 미측정).
현재 다음 작업은 **핵심 원료 3종의 MVP 수직 슬라이스**입니다. 광고 근거 B는 `NOT_MEASURED`, 확장 추천 C는 `BLOCKED`이며
확장 원료는 선정하지 않았습니다. [A 종료 기록](docs/evidence/FUNCTIONAL_ROLE_GATE_AI_PROXY_2026-09-27.md)을 우선하세요.
첫 5건 재제출은 불필요하며, 새 사람 검토 시작용 자료는 `build/functional-role-review-guides/pilot-002.md`입니다.
현재 운영 pack은 `build/functional-role-review-v1-reverified-2026-09-23/`입니다.
기존 1번·5번의 제품 식별자 결합 근거 보강과 CHOI·DOHA의 규칙 검토는 각각 별도 작업입니다.

2026-09-10 23:34 KST 재검증도 `PENDING`, 유효 `1`, 대기 `274`, 이슈 `0`, 종료코드 `2`입니다.
이번에는 사용자 핸드오프·빈 답변지만 추가했으며 실제 사람 라벨·규칙·표본은 변경하지 않았습니다.

현재 검토팩의 상태를 확인하는 명령은 다음과 같습니다.

```powershell
.venv\Scripts\python.exe scripts\validate_functional_role_review.py --pack-dir build\functional-role-review-v1-reverified-2026-09-23 --source-export data\c003-products.jsonl --product-review-pack build\extension-review-v2 --rules data\reference\functional-role-rules-v1-reverified-2026-09-23.json
$roleValidatorExit = $LASTEXITCODE
$roleValidatorExit
```

종료코드는 `COMPLETE=0 / PENDING=2 / INVALID=3`입니다. 원료 규칙의 공식 최신성 확인일은
`2026-09-23T15:02:04.1815514+09:00`이며, 이 시각에서 7일이 지나면 재확인이 필요합니다.
해시가 묶인 입력의 날짜만 임의로 바꾸지 않습니다. 전체 해시와 검토 기준은
[확장 원료 검토 상태](docs/evidence/PHASE_1_EXTENSION_REVIEW.md)에 기록했습니다.

오프라인 검증 명령은 다음과 같습니다.

```cmd
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing --cov-fail-under=97 -q
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
