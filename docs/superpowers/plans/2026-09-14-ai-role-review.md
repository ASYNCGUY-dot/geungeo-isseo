# AI 참고 라벨 269건 분리 검토 실행 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans for the operational steps; use dispatching-parallel-agents for the five independent source-review batches. This is data review, not production feature implementation.

**Goal:** 사용자 승인에 따라 남은 269건에 AI 참고 판정·인용·이유를 작성하고 사람 평가 및 서비스 확정 판정과 분리한다.

**Architecture:** 기존 역할 pack과 서비스 코드는 변경하지 않는다. 기계 판정 열을 제거한 입력을 원료군별 AI 검토자에게 제공하고, 결과는 pack 밖 ignored 디렉터리에 저장한다. 부모 작업은 키·출처·인용·수량·시각·판정 경계를 검사하고 AI 검토 현황만 별도로 보고한다.

**Tech Stack:** 기존 Python/PowerShell read-only 감사, JSON 자료, Codex AI 검토자. 새 패키지·API 키·서비스 코드 없음.

## 2026-09-23 재개 상태

- Task1 완료; AI초안269행 저장·구조/인용 검사 통과. 전체 의미 재검토는 미완료.
- 마그네슘55행 재검토 기록 보존. 네 그룹214행은 사용량 제한으로 완료 미확인; 실제 완료 시각도 확정하지 않는다.
- 11행 표본 감사의 두 지적은 부모 AI가 원문과 직접 대조해 수정했다. 기존 초안 사본과 표적 수정 이력 보존.
- 만료로 INVALID였던 운영 pack은 실제 공식 출처 확인 후 별도9/23규칙·pack으로 복구, PENDING6/269/0.
  기존 보호13파일 불변. 새 규칙은 확인 시각만 다르고, 새 samples/labels는 이전과 바이트 동일하다.
- 문서·위키는 완료분과 미완료분을 구분해 로컬 기록한다. 재검토214행 및 후속 의미 감사는 계속 미완료다.
- 정본: `docs/evidence/FUNCTIONAL_ROLE_AI_REVIEW_2026-09-23.md`, `FUNCTIONAL_ROLE_RECHECK_2026-09-23.md`.

## Global Constraints

- 사용자 승인: 2026-09-14 채팅 “그 방식으로 다음 단계 넘어가줘”.
- 승인 대상: 남은 269건의 AI 검토 선행. 독립 사람·전문가 평가와 분리; 서비스 확정 판정 자동 반영 금지.
- 시작 HEAD: cc39009. 같은 날 이전 검토팩 validator: 유효 AI 5 + 상속 제외 1, 대기 269.
- 보호: 모든 기존 규칙·pack·labels·batch-001 응답 파일. 기존 첫 5건과 두 미해결 이견을 재작성하지 않는다.
- 새 자료: build/functional-role-ai-review-2026-09-14/{inputs,reviews,audit}; 기존 4파일 pack 내부에 파일을 추가하지 않는다.
- 검토 대상: milk_thistle 50, vitamin_d 55, red_ginseng 54, coenzyme_q10 55, magnesium 55.
- 원료 규칙은 functional-role-rules-v1-reverified-2026-09-14.json의 범위에 한정한다. 용량·효능·안전·법률 판단을 하지 않는다.
- 학습된 의학 지식이나 상품명만으로 누락 원문·원료별 인과를 채우지 않는다.
- 원본/라벨/인용 전문은 ignored 로컬 보존. 추적 문서는 승인·해시·집계·제한만 포함한다.
- 새 AI 결과로 기존 human_verdict 열을 채우지 않는다. A 완료·ROLE_ELIGIBLE·사람 정확도·추천 승인으로 승격하지 않는다.
- B NOT_MEASURED, C BLOCKED, finalized=false 유지. push·병합·worktree 삭제 없음.

## Task 1: 입력 동결과 판정 기준

**Files:**
- Create: build/functional-role-ai-review-2026-09-14/inputs/{group}.json
- Create: build/functional-role-ai-review-2026-09-14/REVIEW_RUBRIC.md
- Create: build/functional-role-ai-review-2026-09-14/audit/provenance.json
- Read: 현재 역할 samples/labels와 바인딩 규칙

**Interfaces:** source-only input JSON의 records는 group, report_no, name, company, primary_function, raw_materials, intake_method만 포함한다. 기계 판정·표본 층·이전 AI 답은 입력에서 제외한다. CSV escape는 기존 복원 규약으로 되돌린다.

- [x] 1. Git·보호 파일 해시를 기록하고 실제 현재 대기 키 269개를 추출한다.
- [x] 2. 해당 키의 source-only 원문을 원료군별로 추출, 결과를 apply_patch로 저장한다.
- [x] 3. 입력 키 집합과 6필드 원문을 기존 samples 및 C003 스냅샷과 대조한다.
- [x] 4. 출력 계약과 근거 부족 시 uncertain 원칙을 아래 rubric으로 동결한다.

## Task 2: 다섯 원료군 독립 AI 검토

**Files:**
- Create only: build/functional-role-ai-review-2026-09-14/reviews/{group}.json
- Read only: 배정한 inputs/{group}.json, REVIEW_RUBRIC.md, 현재 규칙 JSON

**Interfaces:** 각 출력은 reviewer_type=ai, reviewer_id, reviewed_at_iso8601, records 배열.
각 record는 group, report_no, ai_verdict, linkage_basis, raw_excerpt, function_excerpt, rationale.
판정 enum: supported_candidate / nonfunctional_candidate / uncertain.
연결 enum: explicit / contextual / missing / ambiguous / nonfunctional_explicit.
인용은 해당 원문에서 복사한 연속 부분문자열 또는 null이다.

- [x] 1. 원료군당 새 AI 검토자를 배정하며 정확한 입출력 경로·문자 일치 기준만 전달한다.
- [ ] 2. 검토자는 행마다 원재료·기능성·제한된 규칙을 읽고 실제 판단·인용·이유를 작성한다.
- [ ] 3. 명시 연결과 문맥 추론을 구분하고 다의적 기능·복합원료·범위 밖 문구는 uncertain으로 남긴다.
- [ ] 4. 검토 후 실제 시각을 조회해 AI 검토 시각으로 기록한다. CHOI/DOHA 이름을 사용하지 않는다.
- [ ] 5. 기존 기계 결과 복사나 정규식 결과를 AI 읽기 검토인 것처럼 기록하지 않는다.

## Task 3: 구조·인용 검증과 보류 항목 정리

**Files:**
- Create: build/functional-role-ai-review-2026-09-14/audit/validation.json
- Create: docs/evidence/FUNCTIONAL_ROLE_AI_REVIEW_2026-09-16.md (중간 이력)
- Create: docs/evidence/FUNCTIONAL_ROLE_AI_REVIEW_2026-09-23.md (현재 인계)

- [ ] 1. 다섯 출력의 실제 파일을 읽어 269개 키 전부·중복 없음·정확한 스키마·AI 식별자·실제 시각을 확인한다.
- [x] 2. 모든 비어 있지 않은 인용이 같은 제품의 지정 필드에 문자 그대로 존재하는지 검사한다.
- [ ] 3. supported_candidate는 두 인용과 명시 또는 문맥 근거를 요구한다. 누락·모순·시각 오류는 해당 검토자에게 되돌린다.
- [x] 4. 결과를 원료군·판정·연결 방식별로 집계한다. 부모의 기계 결과 대조는 검토 종료 후만 수행한다.
- [ ] 5. 전수 구조/인용 검사와 별도 표본 AI 감사 결과를 기록한다. 인용 일치는 추론의 참이나 임상 정확도를 증명하지 않는다.
- [x] 6. 기존 pack의 만료 INVALID를 확인하고 실제 출처 재확인 후 별도9/23 pack에서 PENDING/유효6/대기269/이슈0/summary null을 확인했다.

운영 명령:

```powershell
.venv\Scripts\python.exe scripts\validate_functional_role_review.py --pack-dir build\functional-role-review-v1-reverified-2026-09-23 --source-export data\c003-products.jsonl --product-review-pack build\extension-review-v2 --rules data\reference\functional-role-rules-v1-reverified-2026-09-23.json
```

## Task 4: 문서·위키·로컬 Git 기록

**Files:** README.md, AGENTS.md 현재 상태, docs/CODEX_HANDOFF.md, docs/USER_REVIEW_HANDOFF.md,
docs/evidence/PHASE_1_EXTENSION_REVIEW.md, AI-Agent-Wiki 프로젝트/인계/index/log.

- [x] 1. AI 초안269행 저장·재검토214행 미완료와 사람 검토·적격성 미측정을 별도 수치로 표시했다.
- [x] 2. 새 결과 파일 해시·검토자 유형·잔여 불확실·사람 검토 시작용5건을 기록했다.
- [x] 3. 9/23 전체609 tests·97.22%, Ruff·diff·고신뢰 비밀정보 패턴·53개 로컬 링크·보호13해시를 검사했다.
- [ ] 4. 전체 재검토 완료 후 최종 프로젝트·위키 기록을 마무리한다. 9/23 미완료 체크포인트는 별도 로컬 커밋하고 원문/라벨 원격 업로드는 하지 않는다.
