# Codex 인수인계 — 근거있어

- 기준일: `2026-09-29 Asia/Seoul`
- 작업 브랜치: `phase-0-c003-data-gate`
- 상태: **귀속 개선 1·2단계 완료; 3단계 고시형 대응표 완료·`I-0040` 활용신청 대기; 핵심 MVP Task 1~6 완료; A COMPLETE(AI 대리 라벨); B·C 보류**
- 정확도 원칙: 신원·공식 출처·필수 근거가 부족하거나 충돌하면 추정하지 않고
  `ambiguous` 또는 `unverifiable`로 중단한다.

## 이번 인계 — 2026-10-01 v2.9 보류 원인 반영 (Claude Code)

- [형식 확장 기록의 v2.9 절](evidence/HOLD_FORMATS_2026-10-01.md). 점 기호 글머리, `노화로 인하여`, 헤더 끝 `숫자%`, 본문 없는 `정제1`류 구분 줄 허용.
- 원료명 사전 재생성(364→356, 추가 0, 대시 조각·`…20%` 삭제). 제외 목록에서 더 이상 나오지 않는 조각 4개를 지우고 개정 기록을 남김.
- C003 v2.8→v2.9: 루테인 +30쌍, 오메가3 +27쌍, 프로바이오틱스 +21쌍, 잃은 쌍 0. 1044 passed·97.78%.
- **사용자 결정 대기:** U+2024를 가운뎃점으로 읽으면 오메가3 +43·프로바이오틱스 +154개 제품(추정)이지만,
  9/28 강화 테스트가 이를 애매한 문장 구분으로 보류하도록 정해 두었다. 구현했다가 되돌렸다.

## 이전 인계 — 2026-10-01 평가세트 v2 (Claude Code)

- [평가세트 v2](evidence/ATTRIBUTION_EVAL_V2_2026-10-01.md). v1 제품 제외, 시드 20261002, 새 층 `attributed_new_format`(v2.7~v2.8 형식).
  manifest는 라벨 전에 커밋(`1f79d3e`).
- 맹검 AI 라벨러 두 개(Sonnet·Opus)가 검토지만 읽고 라벨, 100/100 일치. 개발 세션은 라벨을 붙이지 않음.
- 귀속 70쌍 잘못 귀속 0(상한 5.2%), 새 형식 25쌍 0(상한 13.3%). v1 맹검 라벨과 합치면 귀속 130쌍 0(상한 2.9%, 참고값).
- 남은 보류 원인: `노화로 인하여` 문구 변형, 개별인정 균주 헤더(I-0040 필요), `정제1`류 제형 헤더, 헤더 오타·함량 표기, U+2024·`ᆞ` 나열.

## 이전 인계 — 2026-10-01 보류 원인별 형식 확장 v2.7 → 재검토 반영 v2.8 (Claude Code)

- [형식 확장 기록](evidence/HOLD_FORMATS_2026-10-01.md). 현재 파서 `official-function-v2.8`, 판정 규칙(claim-verdict-v1.2)과 사전은 불변.
- 독립 AI 재검토: P1 0, P2 1, P3 3. v2.8에서 영문 번역은 사전 속 "대상 공식 문장 + 영문" 쌍의 영문 조각(4개)일 때만 떼고,
  `[A] : B : 문장`(같은 줄 두 번째 헤더)은 보류한다. C003 수치 v2.7과 동일. 1013 passed·97.82%.
- 허용: 괄호 안 `-`·`:`로 헤더를 자르지 않음(AE-016 버그), `[원료] :` 콜론, `(1) 기능성 내용 :` 라벨,
  사전 게이트를 통과한 `(영문)` 번역, "도움을 줄 수 있음" 뒤 `(생리활성기능 2등급)`, 헤더 `(or` → `(또는`.
- C003 귀속 제품 루테인 1,132→1,226, 오메가3 1,870→1,945, 프로바이오틱스 2,734→2,788. 새 귀속 221개는 모두 6개 형식 중 하나,
  잃은 것은 1개 제품(버그 조각이 사전에 있던 경우, 이제 보류).
- 평가세트: 표류 5건이 보류→귀속, 모두 두 라벨 `yes`. 다만 이번 형식을 고른 사례라 독립 검증이 아니다.
- 다음: (선택) v2.7 기준 새 평가 표본, U+2024 나열(압축 규칙+사전 재생성), `I-0040` 후 나열형 귀속 규칙.

## 이전 인계 — 2026-09-30 4단계 평가세트 v1 (Claude Code)

- [평가 결과](evidence/ATTRIBUTION_EVAL_2026-09-30.md). C003 22,509쌍에서 6개 층 100쌍(시드 20261001), 파서 결과를 가린 검토지로 AI 라벨.
- 귀속 60쌍 잘못 귀속 0(상한 6.0%). 보류 30쌍 중 29쌍 귀속 가능 → 헤더 없는 나열 15/15, 대상 헤더 아래 14/15.
- 보류 원인: 영문 번역 줄, 등급 표기, U+2024 나열, 잡표기, 사전 밖 헤더, 인정번호 안 대시 분할 버그(AE-016).
- 교차 라벨: 라벨·층·파서 코드를 가린 Sonnet 서브에이전트가 검토지만 읽고 다시 라벨링했다(`labels-independent.csv`).
  99/100 일치, kappa 0.918, 불일치는 AE-066(1차 unclear, 교차 yes) 하나다. 교차 라벨 채점도 잘못 귀속 0/60이다.
  둘 다 AI이고 같은 판정 기준을 받았으므로 사람 정확도로 표현하지 않는다.
- 다음: (선택) 사람 스팟체크, 보류 원인별 형식 확장(테스트 먼저), `I-0040` 후 나열형 귀속 규칙.

## 이전 인계 — 2026-09-30 3단계 대응표 진행 중 (Claude Code)

- [대응표 기록](evidence/CARRIER_TABLE_2026-09-30.md). 고시형 93개 항목의 공식 기능성 문구와 효과를 참조 파일로 만들었다.
- 개별인정형 `I-0040` 수집기는 준비됐지만 현재 키가 `I-0040`에 활용신청돼 있지 않다(`INFO-110`). 사용자 신청 후
  `.venv\Scripts\python.exe scripts\fetch_i0040.py --env-file <프로젝트 루트>\.env --output build\i0040\i0040-approvals.jsonl`.
- 측정: 나열형 귀속 후보 상한 루테인 336·오메가3 310·프로바이오틱스 366. 단순 P2 대조는 프로바이오틱스 594개 보류라 부적합.
- P2: 사용자가 좁은 규칙을 골랐다. 귀속 문장이 다른 고시형 원료의 공식 문장과 글자 그대로 같고 그 원료가 원재료에 있으면서
  자기 헤더가 없으면 보류(`OFFICIAL_STATEMENT_OF_OTHER_INGREDIENT`, claim-verdict-v1.2). 실제 C003 보류 0개, 960 passed·97.26%.
- 다음: `I-0040` 수집(사용자 활용신청 후) → 나열형 귀속 규칙(테스트 먼저).

## 이전 인계 — 2026-09-29 2단계 공식 문장 사전 게이트 (Claude Code)

- [2단계 결과](evidence/CLAUSE_GATE_2026-09-29.md). 재검토 P1-A(본문 속 주석) 재현 15개를 RED로 고정한 뒤 해결했다.
- 필드의 모든 본문 절은 공식 문장 사전(852개), 대상 문장 문법 완전 일치, 또는 공식 술어로 끝나는 사전 절의 연쇄여야 한다.
- 대상 문장 형식 확장: `(가)` 번호, 쉼표·`/` 연결 완결 문장, `•`·`ᆞ` 구분자, `(국문)`. 마침표 효과 나열은 여전히 불허.
- v2.4→v2.5 판정 가능 제품: 루테인 1,140→1,131, 오메가3 1,666→1,869, 프로바이오틱스 2,585→2,721. 개발 사례 불변.
- GPT 회귀 1개의 비현실적 루테인 공식 문구 입력을 실제 공식 문구로 바꿨다(기대값 불변).
- 2단계 독립 AI 재검토: P1 0건. P3(이어 붙인 문장 판정 계산량, `‧` 미인식)는 실패 테스트 후 고쳐 official-function-v2.6,
  절 사전 845개로 재생성. P2(헤더 아래 쉼표·슬래시로 이은 다른 원료 문장도 헤더 원료로 귀속)는 3단계에서 닫는다.
- 다음: 3단계 기능성-원료 대응표(P2 포함) → 4단계 실제 제품 평가세트.

## 이전 인계 — 2026-09-29 1단계 헤더 인식기 (Claude Code)

- 사용자가 전체 필드 게이트의 판정 범위 손실을 우려해, 손실 원인 측정 후 제안한 4단계 계획을 골랐다.
  [계획](superpowers/plans/2026-09-29-attribution-coverage.md) · [1단계 결과](evidence/HEADER_RECOGNITION_2026-09-29.md).
- 남은 P1(본문 있는 `[검토 중]`·`검토 중:` 주석)은 원료명 사전 게이트로 해결했다. 사전 밖 헤더가 있으면 필드 전체 보류.
- 목록 기호 정규식의 `^` 때문에 둘째 줄부터 기호가 헤더에 남던 버그를 고쳤고, 인정번호 등 허용된 괄호 표기만 떼어
  공식 이름 변형을 인식한다. 판정 가능 제품은 루테인 999→1,140, 오메가3 1,538→1,666, 프로바이오틱스 2,305→2,585.
- 개발 사례는 일치 28/30·오인 승인 0/19로 불변.
- 독립 AI 재검토: P1-B(한 글자 괄호가 목록 기호로 지워짐)·P3(원문자 번호) 수정 → official-function-v2.4.
  **P1-A(본문 속 주석 미검사)는 미해결**이며 실제 C003에서는 관찰되지 않았다. 재현 사례는 1단계 결과 문서에 있다.
- 다음: 2단계에서 공식 문장 사전 게이트(V2)로 P1-A 해결 + 공식 문장 형식 확장 → 3단계 기능성-원료 대응표 → 4단계 평가세트.

## 이전 인계 — 2026-09-28~29 오인 승인 방지 강화 (GPT)

**(9/29 1단계로 P1 해결. 아래는 당시 기록.) 미완료 / 사용자 설계 선택 대기.** 마지막 리뷰에서 본문이 있는 `[검토 중]` 또는
`검토 중:` 주석이 앞선 긍정 판정을 되살리는 P1이 남았다. 총7건 중6건의 경로를 수정했으며1건 미해결.
같은 예외를 계속 추가하지 말고, 전체 필드 허용 문형 게이트(권장) 또는 구조화 근거 우선 설계 중
사용자 답을 먼저 확인한다. 옵션1은 정상 복합 제품도 크게 보류한다(수치는 증거 문서).
아직 어느 선택도 적용하지 않았다. 자동 승인 신뢰성·병합·출시 완료로 표현하지 않는다.

- 사용자 승인 범위: 위험 입력 점검 → 실패 재현 → 최소 수정 → 개발 검증 기록. 사람 검토 재개는 아니다.
- [현재 검증·한계](evidence/FALSE_CLEARANCE_HARDENING_2026-09-28.md)와
  [실행 계획](superpowers/plans/2026-09-28-false-clearance-hardening.md)을 먼저 읽는다.
- 신규 회귀125개, 기존 핵심 검사와 함께228개 통과. 1차 중간92개를 이전 코드에 대조하면75실패/17통과였다.
  이 수치는 독립 버그 수나 실서비스 오류율이 아니다. 독립 AI 코드 리뷰의 P1 6종을 실패 재현 후 수정했다.
- 최종 전체 pytest/coverage·Ruff·diff·secret-pattern·독립 재검토 상태는 증거 문서를 따른다.
  현재837passed/294.44s·97.72%·Ruff 통과. 별도 직접 재현에서 미해결 P1을 확인했으므로 완료가 아니다.
  TestClient의 기존 사용 중단 예정 경고1개는 남겼다. 추가 패키지는 설치하지 않았다.
- 긍정 판정에 문장 전체·원료 주체 검사를 추가했다. 해석하지 못한 추가 효과/대상/수치/부정/질문은 보류한다.
  공식 원료명 부분 일치, 혼합 헤더의 잘못된 계승, 부정·제외 문구도 긍정 근거로 사용하지 않는다.
- 규칙 버전: claim-extract-v1.2 / official-function-v2.2 / claim-verdict-v1.1.
- 공식 문구는 블록 전체 문맥과 긍정 술어를 확인한다. 미지원 빈 헤더/부정 문맥은 필드 귀속을 보류한다.
  마침표는 효과 목록 구분자가 아니며, 광고 줄바꿈으로 주체/조건을 떨어뜨리지 않는다.
- 기존 개발 평가31건의 일치는29/30→28/30, 오인 승인0/19, 재현율10/11→9/11, 커버리지20/30→19/30.
  PB-06 외 PB-07도 같은 절의 오기 '월활'로 전체 보류한다. 라벨은 바꾸지 않았다.
  원료군별 감소와 측정 분모는 증거 문서를 따른다. 라벨·원본·답변지 변경 없음, 사람 정확도 미측정 유지.
- 첫 독립 코드 리뷰는 사용량 제한 후 재개되어 P1 6종을 발견했다. 후속 수정의 재검토 결과는 정본에 기록한다.
  다음은 미해결 P1 설계 선택과 수정·재검토이고, 그 뒤 보류 유형 점검과 독립 평가 설계이며,
  통과율 때문에 인식 범위를 임의 확대하지 않는다. LLM/OCR·확장 원료·push·병합·배포는 이번 범위가 아니다.

## 이전 인계 — 2026-09-27 개발 평가와 웹 화면 (Task 5·6)

- 기록: [핵심 MVP 개발 평가·화면](evidence/CORE_MVP_DEV_EVAL_2026-09-27.md).
- 개발 사례 31건(`data/dev-cases/core-mvp-dev-v1.json`): 오인 승인 0건(분모 19), 판정 일치 29/30,
  `확인됨` 재현율 10/11, 커버리지 20/30. 광고는 가상 문장, 기대 판정은 AI 개발자 라벨이다.
  개발 중 조정에 쓴 표본이라 발표 성능 수치로 쓰지 않는다.
- 불일치 1건(PB-06)은 공식 원문 오기 '월활' 때문에 `검증 불가`가 된 재현율 손실이다. 오기 사전은 넣지 않았다.
- 사용자 확인 후 FastAPI 0.141.1·uvicorn 0.54.0을 설치했다. `src/claimledger/api.py`, `src/claimledger/web/index.html`,
  `scripts/serve_api.py`. 분석은 메모리 저장뿐이고, 제품 미확정 판정 요청은 409로 거부한다.
- 실제 C003 45,907건 적재 후 브라우저에서 확인됨·근거 불일치·검증 불가가 기대대로 나왔다.
- 다음 후보: 사람 라벨 동결 평가세트, LLM 주장 추출·논문 근거·OCR 범위 재결정. push·병합은 하지 않았다.

## 같은 날 앞선 단계 — 핵심 MVP 수직 슬라이스 1차

- 계획: [핵심 MVP 수직 슬라이스](superpowers/plans/2026-09-27-core-mvp-vertical-slice.md). Task 1~4 완료 시점의 기록이다.
- 출발점 실측: 핵심 3종 제품 9,225개 중 기존 Phase 1 `READY`는 7개였다. v1 파서가 정확한 6문구만 인식했기 때문이다.
- 새 모듈:
  - `official_v2.py`: 원료명 표시 블록과 공식 효과를 원문 범위와 함께 추출한다.
  - `claims_v1.py`: 광고 문장별 효과·표현 강도를 분류한다.
  - `verdict_v1.py`: fail-closed 판정.
  - `receipt.py`: 영수증 JSON·Markdown.
  - `scripts/make_receipt.py`: CLI.
- 대상 원료명 아래 공식 효과를 찾는 비율은 루테인 68.9%, 오메가3 75.6%, 프로바이오틱스 60.1%다.
  원료명 없는 나열은 같은 문구를 다른 원료도 쓰므로 `검증 불가`로 둔다.
- 이 슬라이스는 `insufficient`·`contradicted`를 만들지 않는다(과학 근거 층 없음). LLM·OCR·URL·웹 화면은 아직 없다.

## 2026-09-27 A 종료와 방향 전환

- 먼저 [A 종료 기록](evidence/FUNCTIONAL_ROLE_GATE_AI_PROXY_2026-09-27.md)을 읽는다.
- 사용자가 "사람 검토는 넘어가고 다음 단계로 넘어가줘"라고 한 뒤, 선택 질문에서 "AI 대리 라벨로 닫기"와 "핵심 MVP 먼저"를 골랐다.
- 운영 pack 라벨 269행에 AI 재검토 결과를 대리 라벨로 반영했다. 기존 6행은 그대로다. 검증기 `COMPLETE`, 유효 275, 이슈 0, exit 0.
- 요약 `docs/evidence/functional-role-summary-v1-ai-proxy.json`은 원문·검토자 없이 생성했다.
  비타민D·코엔자임Q10·마그네슘은 `ROLE_ELIGIBLE`, 밀크씨슬·홍삼은 `ROLE_INSUFFICIENT`(미해결 긍정·과신 판정)이다.
- 사람 기준 정확도는 미측정이다. B `NOT_MEASURED`, C `BLOCKED`, 확장 원료 미선정. 다음은 핵심 원료 3종 MVP 수직 슬라이스다.

## 같은 날 앞선 단계 — AI 재검토 완료

- [9월 27일 재검토 완료 기록](evidence/FUNCTIONAL_ROLE_AI_REVIEW_2026-09-27.md).
- 네 그룹 214행은 Claude Code(`claude-opus-5-5`, 기록 식별자 `CLAUDE-OPUS-5.5-AI`)가 원문을 먼저 읽고 기존 AI 행과 대조해 전 행 재검토했다.
  마그네슘 55행도 같은 방식으로 교차 확인했다. 269행 모두 내용 수정 0이며 `reviews/` 해시는 9/23과 같다.
- 블라인드 실험·사람 검토가 아니다. 홍삼 22·28번은 1차 판단과 달랐지만 그룹의 보수적 기준에 맞아 유지했다.
- 완료 여부는 `audit/revision-completion-2026-09-27.json`이 판단한다. `audit/validate-2026-09-27.py`는 리뷰 해시가 그 기록과 같을 때만 완료로 인정한다.
  실제 결과는 `PASS_STRUCTURE_ONLY`, 완료 확인 5그룹, 경고 0이다.
  PowerShell 7이 없어 9/23 ps1 대신 같은 검사를 Python으로 옮겼다.
- 운영 validator는 그대로 `PENDING`/유효6/대기269/이슈0/exit2다. 9/23 규칙의 7일 경계는 `2026-09-30T15:02:04+09:00`이다.
- 다음은 사람만 할 수 있는 독립 검토(pilot-002)다. AI가 답변지를 채우지 않는다. 1번·5번 보충 근거는 9/27 웹 검색에서 찾지 못해 보류를 유지한다.

## 2026-09-23 인계 (이력)

AI 초안 269행의 구조·원문 대조는 통과했습니다. 마그네슘 55행의 재검토 기록은 있지만,
나머지 네 그룹 214행의 의미 재검토 완료·완료 시각 및 후속 표본 감사는 사용량 제한으로 미완료입니다.
표본 감사 지적 두 행은 원문과 직접 대조해 수정했습니다. AI를 사람 정답으로 취급하지 않습니다.

- 먼저 [AI 중간 인계](evidence/FUNCTIONAL_ROLE_AI_REVIEW_2026-09-23.md)와 [복구 기록](evidence/FUNCTIONAL_ROLE_RECHECK_2026-09-23.md)을 읽습니다.
- 사용자 승인은 269건 AI 선행 검토까지 이미 있습니다. 같은 승인을 다시 묻지 않습니다.
- 전수 검사: 269키, 원문1,614필드, 인용490개 일치; 보호13파일·입력5파일 해시 불변.
- 새 공식 원본 ZIP은 동일합니다. 현재 운영 규칙/pack은 `reverified-2026-09-23` 사본입니다.
- 실제 validator PENDING/유효6/대기269/이슈0/exit2/summary null. 유효6은 이전 승인AI5+상속제외1입니다.
- 오늘 전체 609 passed/293.72s, 코드 커버리지97.22%, Ruff 통과. 실제 판정 정확도와는 별도입니다.
- 다음은 네 그룹의 실제 재검토와 완료 시각·후속 표본 감사입니다. 사람용 CSV 자동 채우기 금지.
- 사람 검토 시작용 자료는 `build/functional-role-review-guides/pilot-002.md`와 빈 답변지입니다.
  원료군별 첫 행으로 고른 비무작위 시작 자료이며 성능 평가표본이 아닙니다.
- 기존 첫 배치1·5번 보충 근거, 독립 사람 평가와 광고 근거·추천 차단은 그대로입니다.

## 2026-09-14 이전 인계 — 최신성 복구와 승인 AI 라벨 이관

- 정본 증거: [2026-09-14 복구 기록](evidence/FUNCTIONAL_ROLE_RECHECK_2026-09-14.md).
- 공식 고시 전문·후속 개정 목록을 실제 대조하고 첨부 ZIP의 기존 해시 일치를 확인했다.
  다섯 규칙의 최신성 시각만 `2026-09-14T15:13:50+09:00`으로 재확인했다.
- 새 규칙은 `data/reference/functional-role-rules-v1-reverified-2026-09-14.json`,
  현재 운영 pack은 `build/functional-role-review-v1-reverified-2026-09-14/`다.
  기존 규칙과 pack은 역사적 증거로 보존한다. 새 samples 전체와 이관 labels는 기존과 바이트 동일하다.
- 실제 validator: `PENDING`, 전체 275, 유효 6, 대기 269, 이슈 0, exit 2, summary null.
  유효 6은 사용자 승인 AI 5와 상속 매핑 오류 제외 1이다. 사람 검토 6건이 아니다.
- 사용자 승인에 따라 첫 5개 AI 결과를 `CLAUDE-OPUS-5-AI` 출처 그대로 수용했다.
  사람·전문가 정답 또는 독립 인간 평가로 사용하지 않는다. 남은 269건 AI 자동 라벨링 승인은 아니다.
- 1번·5번의 복합원료 연결은 코드 보류와 AI 추론이 다르다. 신고번호가 연결되는 보충 원문 없이는
  어느 쪽을 확정 정답으로 바꾸지 않는다. 코드·규칙 의미를 완화하지 않았다.
- A 적격성 미측정, B `NOT_MEASURED`, C `BLOCKED`, `finalized=false`다.
  아래 날짜가 표시된 이전 검증·인계는 당시의 이력이다.
- 9월 14일 새 전체 검증: `609 passed in 328.52s`, 코드 커버리지 `97.22%`,
  `--cov-fail-under=97` 통과, Ruff·diff 검사 통과. 코드·테스트 변경은 없다.
  코드 건강 지표이며 사람 기준 판정 정확도는 미측정이다.

## 2026-09-10 이전 인계 — 사용자 검토 시작

- [사용자 작업 핸드오프](USER_REVIEW_HANDOFF.md)에 첫 5건 시작 방법, 세 판정의 기준,
  제품별 응답 양식, 사용자/에이전트 책임, 최신성·Git 경계를 정리했다.
- 첫 5건 원문은 `build/functional-role-review-guides/batch-001.md`, 빈 답변지는
  `build/functional-role-review-guides/batch-001-response.md`다. 둘 다 로컬 ignored 자료다.
  답변지의 제품 키만 채웠으며 사람 판정·인용·검토자·시각은 비워뒀다.
- 2026-09-10T23:34:01+09:00 실제 검증기 결과는 `PENDING`: 전체 275,
  상속 제외 유효 1, 대기 274, 이슈 0, 종료코드 2, summary null이다.
- 규칙·역할 manifest/samples/labels·v2 labels의 SHA-256을 재대조했고 기존 값과 같다.
  사람 검토나 적격성 측정이 추가로 완료된 것은 아니다. 광고 `NOT_MEASURED`,
  추천 `BLOCKED`, `finalized=false`를 유지한다.
- 이번 변경은 검토 운영 문서와 빈 답변지뿐이다. 아래 전체 테스트 수치는 9월 9일 실행 기록이며
  이번 문서 변경에서 전체 609개 테스트를 재실행했다는 뜻이 아니다.
- 현재 원격 저장소는 연결돼 있지 않다. push·병합은 하지 않으며 필요 시 대상과 승인을 확인한다.
- 다음 입력은 실제 제품별 검토 결과다. 원문 질문만 도착하면 설명을 제공하고 판정으로 저장하지 않는다.
  최신성 기한을 넘기면 실제 출처 재확인과 규칙/pack 버전 영향을 먼저 처리한다.

## 이전 코드 검증 결과 — 2026-09-09

2026-09-09에 규칙 자료형 오류의 예외 종료와 CLI 회귀 테스트의 만료 오인 통과를
수정한 뒤 다음 명령을 실행했다.

```cmd
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing --cov-fail-under=97 --cov-report=json:build\coverage-2026-09-09.json --junitxml=build\test-results-2026-09-09.xml -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
git status --short --branch
```

- 전체 테스트: `609 passed` (311.60초), 종료코드 `0`
- 전체 코드 커버리지: `97.22%` (`2,485` statements, `69` missed, 제외 줄 `0`)
- 계획의 `97%` 목표를 명령의 `--cov-fail-under=97`로 통과했다. 실제 판정 정확도와는 별도다.
- 이전 507개에서 회귀 사례 102개를 추가했다. 실제 규칙·원본·검토 라벨은 변경하지 않았다.
- 독립 코드 검토의 P2 1건(만료된 CLI fixture의 오인 통과)을 실패 재현 후 수정했다.
  정상 입력의 `PENDING/exit 2`를 먼저 확인한 뒤 손상 입력의 `INVALID/exit 3`를 확인한다.
  독립 재검토에서 해당 지적 해결과 추가로 발견된 변경 코드 문제 없음이 확인됐다.
- Ruff: `All checks passed!`
- `git diff --check`: exit `0`, 오류 없음
- 2026-09-04 기능성 역할 규칙 집중 검증: `63 passed`; 검토팩 집중 검증: `163 passed`
- 2026-09-07 CLI 날짜 회귀: `3 passed` (최신 규칙 성공, 8일 경과 거부, 잘못된 표본 수 거부)
- 라이브 export, 보존된 v1 pack, 현재 v2 pack: 모두 로컬 ignored 경로에 존재
- 2026-08-28 당시 v2 네 파일의 고신뢰 key/token, URL, C003 envelope, 금지 메타데이터 패턴: 각 `0`
- 2026-08-28 당시 실제 로컬 키 값과 v2 파일의 비노출 대조: 동일 문자열 `0`.
  이번 재검증에서는 키 파일을 읽지 않고 변경 파일의 고신뢰 토큰 패턴을 검사했다.
- 2026-08-29 저장소 루트를 `_persnal V1`에서 `geungeo-isseo`로 이동하고
  `git worktree repair`로 main·feature 양방향 절대경로를 복구했다.
- 최초 이동 후 테스트는 `.venv`의 기존 `__editable__.claimledger-0.1.0.pth`가 이전
  절대경로를 가리켜 수집 오류 14건으로 실패했다. 기존 editable 배포를 제거하고
  `pip install --no-deps --no-build-isolation --editable .`로 재설치한 뒤 이전 경로 0건,
  `claimledger` 새 경로 import, 전체 `280 passed`, Ruff 통과를 새로 확인했다.

다음 핵심 불변식 묶음은 2026-08-30의 역사적 실행 결과다.

```cmd
.venv\Scripts\python.exe -m pytest tests\test_identity.py tests\test_ingredients.py tests\test_official.py tests\test_product_evidence.py tests\test_safety.py tests\test_evaluation_dataset.py tests\test_product_review.py -q
```

당시 결과는 `175 passed`다. 제품 신원 확인, 원료 매핑, 공식 원문 보존,
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
- 다섯 원료의 공식 규칙 등록(`7678890`), 마그네슘 명시 연결 정책(`a45d6b6`)
- 기능성 역할의 결정적 분류·일반/양성 감사 표본·해시 검증·사람 라벨·정확도 통계 CLI

2026-09-09 기존 역할 pack 재검증은 `PENDING`, 유효 `1 / 275`, 대기 `274 / 275`,
이슈 `0`, 종료코드 `2`다. 유효 1행은 v2 홍삼 alias 오류를 상속한 제외 행이다.
원료별 적격성 summary는 `null`이며 아직 추적 summary 파일을 생성하지 않았다.
다섯 규칙의 추출자는 CHOI, 독립 검토자는 DOHA, 재확인 시각은
`2026-09-04T17:28:58+09:00`이다. 공식 출처·샘플 구성·모든 해시는
[역할 검토 증거](evidence/PHASE_1_EXTENSION_REVIEW.md)에 기록한다.

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
  - `product_review_labels.csv`의 2026-08-28 당시 빈 템플릿 해시:
    `DC65DBC164CDB135C8C0B0FF7688CEB6F3766E92B6D47BBC0C55CB9FEA350CC8`
  - `samples.csv`: `BCF1702FD7C1D85B7B676FA66F752FC04853FAC3AB9C9A2DB48D4353534B774C`
- 실제 v2 재검증: 프로세스 종료코드 `0`, `COMPLETE`, 유효 라벨 `100건 전부`
- 대기 라벨: `0 / 100`; 매핑 `99 correct / 1 incorrect / 0 uncertain`, 기능성 원문 `usable 100 / 100`
- 유일한 매핑 오류: `red_ginseng`, 신고번호 `20160012278100`, 사유 `alias_collision`
- 완료 라벨 SHA-256:
  `A00B3C1A038DBFD06484A89A6C1B41AAA63837D3BD87FAC29E2AF5DF0E011CC1`
- `function_text_status=usable`은 공식 기능성 원문이 행 단위 검토에 사용 가능하다는 뜻이며,
  원료가 그 기능을 유발한다는 인과 근거가 아니다.
- 광고 근거 `NOT_MEASURED`, 확장 추천 `BLOCKED`, `finalized=false`
- 선택된 확장 원료: 없음. 기능적 역할 검토 A와 공식 광고 근거 게이트 전에는 추천 또는
  최종 선택을 만들지 않는다.

현재 성공 상태는
[`docs/evidence/C003_LIVE_ATTEMPT.md`](evidence/C003_LIVE_ATTEMPT.md)에 별도로
기록했다. 비교군별 pool·mapping 상태·표본 상태와 파일 해시는
[`docs/evidence/PHASE_1_EXTENSION_REVIEW.md`](evidence/PHASE_1_EXTENSION_REVIEW.md)에
있다.

## 다음 검토 작업

기존 검토팩 검증에는 API 키가 필요하지 않다. 완료된 v2와 현재 역할 pack을 보존한다.

```powershell
.venv\Scripts\python.exe scripts\validate_functional_role_review.py --pack-dir build\functional-role-review-v1-reverified-2026-09-23 --source-export data\c003-products.jsonl --product-review-pack build\extension-review-v2 --rules data\reference\functional-role-rules-v1-reverified-2026-09-23.json
$roleValidatorExit = $LASTEXITCODE
$roleValidatorExit
```

현재 역할 pack은 종료코드 `2`, 완료된 v2는 v2 validator에서 `0`을 반환한다.
라이브 C003 export 자체를 다시 받아야
할 때만 승인된 운영자가 `FOOD_SAFETY_API_KEY`를 로컬 환경에
설정하고 `scripts/audit_c003.py`를 별도로 실행한다. 키 값을 문서·로그·명령 출력에
복사하지 않는다.

A는 2026-09-27 AI 대리 라벨로 `COMPLETE`다(사람 정확도 미측정). 현재 다음 작업은 핵심 원료 3종 MVP 수직 슬라이스다.
운영 명령은 9/23 규칙의 7일 경계(2026-09-30T15:02:04+09:00) 이후 규칙 만료로 INVALID가 되며, 재사용하려면 공식 출처를 재확인한다.
첫 5행 수용 및 269건 AI 선행 검토 승인은 이미 확인됐다. 재제출·재승인을 요구하지 않는다.
원래 첫 배치 1번·5번은 여전히 신고번호에 묶인 보충 근거가 필요하다. AI 출처를 사람 검토로 바꾸지 않는다.
기계 판정이나 AI 추론을 독립 정답으로 복사하지 않는다.
v2의 100개 라벨이 유효해도 광고 근거가 `NOT_MEASURED`인 동안 추천과 최종 선택은
`BLOCKED`다.

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
- 영속화, 감사 이벤트, SSE (FastAPI 로컬 API·단일 웹 화면은 2026-09-27 핵심 3종 슬라이스로 추가)
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
- 역할 pack·공식 ZIP·사람 검토 안내도 `build/` 아래 로컬 ignored 경로에 있다.
- `data/reference/functional-role-rules-v1.json`만 새로 추적하며, 원본 JSONL과
  모든 `build/` 산출물은 추적하지 않는다.
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

> 먼저 `docs/evidence/FUNCTIONAL_ROLE_GATE_AI_PROXY_2026-09-27.md`를 읽는다. A는 사용자 결정으로
> AI 대리 라벨을 써서 COMPLETE(유효275)이며 비타민D·코엔자임Q10·마그네슘 ROLE_ELIGIBLE,
> 밀크씨슬·홍삼 ROLE_INSUFFICIENT다. 사람 정확도는 미측정이고 이를 사람 검증으로 표현하지 않는다.
> 사용자는 확장 원료 선정(B·C)보다 핵심 원료 3종 MVP 수직 슬라이스를 먼저 하기로 했다.
> B NOT_MEASURED, C BLOCKED, finalized=false, 확장 원료 미선정을 유지한다.
