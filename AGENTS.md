# AGENTS.md

이 파일은 Codex가 `근거있어` 프로젝트에서 작업할 때 지켜야 하는 프로젝트 규칙입니다.
`근거영수증`은 주장별 결과물, `ClaimLedger`는 내부 검증엔진 이름입니다.

## 작업 시작 순서

1. `README.md`를 읽습니다.
2. `docs/CODEX_HANDOFF.md`에서 현재 상태와 이번 세션의 첫 작업을 확인합니다.
3. `docs/PROJECT_BRIEF.md`에서 승인된 범위와 금지 범위를 확인합니다.
4. 현재 작업에 해당하는 `docs/superpowers/plans/` 계획을 읽습니다.
5. `git status --short --branch`와 최근 커밋을 확인한 뒤 작업합니다.

## 현재 정본과 참고자료 우선순위

1. 이번 세션에서 사용자가 한 요청
2. 이 저장소의 현재 코드·테스트·실행 결과
3. 공식 데이터 원문과 현재 법령·공식 문서
4. `C:\Users\Donga\Desktop\AI-Agent-Wiki`의 프로젝트 기록
5. 과거 대화 요약

위키 기록은 맥락 복원용이며 현재 실행 결과를 덮어쓰는 진실로 취급하지 않습니다.

## 정확도 비협상 원칙

- 절대적인 정확도를 약속하지 않습니다. 대신 오류가 확정 판정으로 노출되지 않게 설계합니다.
- 제품 신원이 확정되지 않으면 제품 수준 판정을 하지 않습니다.
- 제품명 자동 추정만으로 제품을 확정하지 않습니다. 후보를 보여주고 사용자가 선택하게 합니다.
- LLM은 주장 추출·정규화·검색 보조에만 사용합니다. 최종 상태는 명시적 규칙과 검증된 데이터로 결정합니다.
- 근거가 부족하거나 데이터가 충돌하면 `검증 불가` 또는 `근거 부족`으로 중단합니다.
- LLM·API·파서 실패를 정상 또는 안전 판정으로 변환하지 않습니다.
- 결과마다 출처 URL 또는 공식 식별자, 조회 시각, 적용 규칙 버전을 보존합니다.
- 평가의 최우선 지표는 `False Clearance Rate`입니다. 근거 없는 주장을 `확인됨`으로 통과시키는 오류를 가장 치명적으로 취급합니다.
- 자동화 범위가 줄더라도 오인 승인을 허용하지 않습니다.

## 공개 판정 상태

코드 내부 값과 사용자 화면 문구는 다음처럼 고정합니다.

| 코드 값 | 화면 문구 | 의미 |
|---|---|---|
| `confirmed` | 확인됨 | 현재 제품·주장·근거가 명시적 규칙으로 일치 |
| `mismatch` | 근거 불일치 | 광고 표현과 공식 인정 범위·조건이 일치하지 않음 |
| `insufficient` | 근거 부족 | 관련 자료는 있으나 주장을 확인할 수준이 아님 |
| `unverifiable` | 검증 불가 | 제품 신원·필수 데이터·판정 규칙이 부족함 |
| `contradicted` | 직접 반박됨 | 신뢰 가능한 근거가 광고 주장을 직접 반박함 |

`거짓`, `안전`, `효과 있음` 같은 단정어는 승인된 규칙 없이 새로 만들지 않습니다.

## MVP 의료·법률 경계

- 개인 맞춤 효능, 복용 안전, 의약품 상호작용, 진단·치료 기능을 구현하지 않습니다.
- 약사·영양사 페르소나를 프롬프트에 넣어 전문가 검토를 대체하지 않습니다.
- 광고 사전점검 결과를 공식 심의 통과 또는 법적 확정으로 표현하지 않습니다.
- 실제 출시 확장은 약사, 영양사, 표시광고 전문가, 의사, 시험·검사기관 중 기능별 책임 주체를 붙인 뒤 별도 계획으로 진행합니다.

## 개발 방식

- 기능 또는 버그 수정은 먼저 실패하는 테스트를 작성한 뒤 최소 구현으로 통과시킵니다.
- 작은 단위로 커밋하고 커밋 전 전체 관련 테스트를 새로 실행합니다.
- 네트워크 테스트와 단위 테스트를 분리합니다. 기본 테스트는 외부 API나 유료 LLM 없이 재현 가능해야 합니다.
- 외부 응답은 원본 전체를 커밋하지 말고 비밀정보·개인정보를 제거한 최소 fixture만 저장합니다.
- 라이브 데이터 결과에는 조회 날짜와 소스 식별자를 기록합니다.
- 근거 없는 샘플 수치나 성능 수치를 README·발표자료에 넣지 않습니다.
- 새 의존성을 추가할 때는 이 프로젝트의 정확도, 재현성, 운영성 중 무엇을 개선하는지 문서에 남깁니다.

## Git과 비밀정보

- `.env`, API 키, 비밀번호, 토큰, 사용자 건강정보를 커밋하지 않습니다.
- 상위 폴더 `C:\WORK\WORK\.env`를 읽어 문서화하거나 이 저장소로 복사하지 않습니다.
- 실제 키가 필요한 라이브 검증은 사용자가 이 프로젝트의 로컬 환경에 설정한 뒤 실행합니다.
- 커밋 전 `git diff --check`, 비밀정보 패턴 검사, 관련 테스트를 실행합니다.
- 원격 저장소 생성·push는 사용자가 명시적으로 요청하거나 원격 위치를 확인한 뒤 수행합니다.

## 위키 저장

의미 있는 결정, 검증 결과, 실패와 복구 방법은 다음 정본에 반영합니다.

- Vault: `C:\Users\Donga\Desktop\AI-Agent-Wiki`
- Project page: `AI-Sessions/wiki/projects/근거있어.md`
- Continuity handoff: `AI-Sessions/conversations/2026-08-22-근거있어-코덱스-핸드오프.md`

`JISOO.DOC`은 개인 참고 vault이므로 사용자가 별도로 요청하지 않으면 수정하지 않습니다. 위키 수정 시 기존 파일을 먼저 읽고, `index.md`와 `log.md`를 함께 갱신하며, 위키 자체 Git에 별도 커밋합니다.

## 현재 첫 작업

현재 작업 계획은 `docs/superpowers/plans/2026-09-27-core-mvp-vertical-slice.md`입니다. Task 1~6(공식 기능성 파서 v2,
광고 주장 추출 v1, 주장별 판정 v1, 근거영수증·CLI, 개발 사례 평가, FastAPI·웹 화면)은 2026-09-27 완료했습니다.
개발 평가 기록은 `docs/evidence/CORE_MVP_DEV_EVAL_2026-09-27.md`이며, 개발 사례 수치(AI 개발자 라벨)를 서비스 정확도로 쓰지 않습니다.
판정은 결정론적 규칙만 내리고, `확인됨`은 대상 원료명에 붙은 공식 문구와 공식 강도('도움을 줄 수 있음') 이내일 때만 허용합니다.
FastAPI·uvicorn 외의 새 패키지 설치는 사용자 확인 후 진행합니다. 다음 작업 범위(동결 평가세트, LLM·논문·OCR)는 사용자와 다시 정합니다.

2026-09-27 A 게이트 정본은 `docs/evidence/FUNCTIONAL_ROLE_GATE_AI_PROXY_2026-09-27.md`입니다.
사용자 결정("사람 검토는 넘어가고 다음 단계로")에 따라 A를 AI 대리 라벨로 `COMPLETE` 처리했습니다.
비타민D·코엔자임Q10·마그네슘 `ROLE_ELIGIBLE`, 밀크씨슬·홍삼 `ROLE_INSUFFICIENT`, 사람 정확도 미측정입니다.
사용자가 "핵심 MVP 먼저"를 골랐으므로 B·C(확장 원료 선정)는 미루고 핵심 원료 3종 MVP 수직 슬라이스를 진행합니다.
확장 원료를 선정하거나 A 결과를 사람 검증으로 표현하지 않습니다.
2026-09-28 사용자 지시로 pilot-002 답변지(ignored `build/`)를 AI가 채웠습니다. AI 대리 라벨을 옮긴 것이며 사람 독립 검토가 아닙니다.
아래는 같은 날 앞선 AI 재검토 단계의 기록입니다.

AI 재검토 기록은 `docs/evidence/FUNCTIONAL_ROLE_AI_REVIEW_2026-09-27.md`입니다.
최신성 복구는 `docs/evidence/FUNCTIONAL_ROLE_RECHECK_2026-09-23.md`를 따릅니다.
AI 초안 269행의 전체 재검토가 끝났습니다(네 그룹 214행은 9/27 Claude 재검토, 마그네슘 55행은 9/20 재검토 + 9/27 교차 확인).
수정 행은 0이며, 완료 여부는 `build/functional-role-ai-review-2026-09-14/audit/revision-completion-2026-09-27.json`의 해시 결합으로 판단합니다.
AI를 사람 정답으로 취급하지 않습니다. pilot-002 사람 검토는 사용자 결정으로 생략했으며 AI가 대신 채우지 않았습니다.
9/23 규칙의 내부 7일 경계(`2026-09-30T15:02:04+09:00`) 이후 라벨을 반영하려면 실제 공식 출처 재확인이 먼저입니다.
현재 운영 규칙/pack은 `reverified-2026-09-23` 사본이며, 실제 검증은 PENDING/유효6/대기269/이슈0/exit2입니다.
유효6은 기존 승인 AI5 + 상속 제외1이며 사람 검토 수가 아닙니다. 새 AI 초안은 human_verdict에 자동 이관하지 않습니다.
기존 1번·5번 보충 근거, A 적격성 미측정, B NOT_MEASURED, C BLOCKED, finalized=false를 유지합니다.

현재 운영 명령:

```powershell
.venv\Scripts\python.exe scripts\validate_functional_role_review.py --pack-dir build\functional-role-review-v1-reverified-2026-09-23 --source-export data\c003-products.jsonl --product-review-pack build\extension-review-v2 --rules data\reference\functional-role-rules-v1-reverified-2026-09-23.json
$LASTEXITCODE
```

## 2026-09-14 및 이전 작업 이력 (현재 상태 아님)

2026-09-14 최신 상태는 `docs/evidence/FUNCTIONAL_ROLE_RECHECK_2026-09-14.md`를 우선합니다.
공식 원본 재확인 후 별도 규칙 `functional-role-rules-v1-reverified-2026-09-14.json`과
별도 pack `build/functional-role-review-v1-reverified-2026-09-14/`으로 복구했습니다.
실제 검증은 `PENDING`, 유효 6(사용자 승인 AI 5 + 상속 제외 1), 대기 269, 이슈 0, exit 2입니다.
첫 5건은 AI 출처 그대로 수용하며 사람·전문가 정답으로 표현하지 않습니다.
남은 행 자동 AI 라벨링으로 승인 범위를 확대하지 않습니다. 1번·5번의 코드/AI 차이는 추가 근거 대기입니다.
기존 규칙·pack·응답 파일은 보존본이며 아래 9월 10일 절차·수량은 당시 이력입니다.

기능적 역할 검토 A의 기존 275행 pack을 보존하고 남은 274행을 사람 검토합니다.
코드·규칙 등록·pack 생성은 완료했고, 제품별 역할 적격성은 아직 미측정입니다.
v2는 유효 라벨 `100건 전부`다.
대기 라벨은 `0 / 100`이며, 매핑은 `99 correct / 1 incorrect / 0 uncertain`,
기능성 원문 `usable 100 / 100`으로 `COMPLETE`다. 유일한 오류는 `red_ginseng`의
`alias_collision`이며, 라벨 SHA-256은
`A00B3C1A038DBFD06484A89A6C1B41AAA63837D3BD87FAC29E2AF5DF0E011CC1`이다.
`function_text_status=usable`은 행의 공식 기능성 원문을 검토에 사용할 수 있다는 상태일
뿐 원료가 그 기능을 유발함을 증명하지 않는다.

규칙은 `data/reference/functional-role-rules-v1.json`에 추적합니다. CHOI(추출)·DOHA(독립
검토)의 원료 규칙 재확인 시각은 `2026-09-04T17:28:58+09:00`입니다.
이 확인을 새 제품별 사람 라벨에 일괄 전용하지 않습니다.
첫 5개 제품의 검토 안내는 `build/functional-role-review-guides/batch-001.md`에 있습니다.
사용자 안내 정본은 `docs/USER_REVIEW_HANDOFF.md`, 첫 배치의 빈 답변지는
`build/functional-role-review-guides/batch-001-response.md`입니다. 답변지의 저장만으로
라벨 완료를 선언하지 않고 실제 확인된 제품별 답변만 계약에 맞게 반영합니다.

다음 명령으로 기존 pack을 검증합니다. 완료된 v2나 역할 pack에 생성기를 다시 실행하지 않습니다.

```powershell
.venv\Scripts\python.exe scripts\validate_functional_role_review.py --pack-dir build\functional-role-review-v1 --source-export data\c003-products.jsonl --product-review-pack build\extension-review-v2 --rules data\reference\functional-role-rules-v1.json
$roleValidatorExit = $LASTEXITCODE
$roleValidatorExit
```

2026-09-10 23:34 KST 역할 validator는 `PENDING`, 유효 `1`, 대기 `274`, 이슈 `0`, 종료코드 `2`입니다.
유효 1행은 상속된 매핑 오류 제외 행입니다. 사람 검토자가 확인한 행만 라벨에 기록합니다.
공식 최신성 확인 시각 `2026-09-04T17:31:53+09:00`에서 7일이 지나면 규칙 재확인이
필요하며, 현재 manifest에 묶인 규칙 해시를 날짜 수정만으로 무효화하지 않습니다.
현재 v2 상태는 `COMPLETE`이며 광고 근거는
`NOT_MEASURED`, 확장 원료 추천은 `BLOCKED`, `finalized=false`다. 기능적 역할 및 공식
광고 근거 게이트가 별도로 끝나기 전에는 확장 원료를 선택하거나 Phase 2, 프론트엔드,
개인화 기능을 시작하지 않습니다.
