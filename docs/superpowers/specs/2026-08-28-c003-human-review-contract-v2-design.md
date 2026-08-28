# C003 사람 검토 계약 v2 설계

- 작성일: `2026-08-28 Asia/Seoul`
- 상태: 사용자 승인 방향을 구체화한 설계 검토본
- 대상 브랜치: `phase-0-c003-data-gate`
- 선행 증거: C003 `45,907 / 45,907` export와 seed `20260823`의 5개 비교군 × 20건 표본

## 1. 결정

현재 `review_labels.csv`의 제품별 광고 위험·기능 다양성·구현 가능성 1~5점 계약을
확장 원료 선택 근거로 사용하지 않는다. C003 표본에는 광고 원문이 없고, 제품별 100개
점수를 원료군별 5개 통계로 집계하는 규칙도 정의되지 않았기 때문이다.

첫 구현 단위는 기존 100건을 보존한 **C003 제품 매핑·기능성 원문 사용 가능성 사람
검토 게이트**다. 광고 위험은 별도의 공식 광고 사례 코퍼스가 준비될 때까지
`NOT_MEASURED`로 유지한다. 누락된 광고 근거를 `0점`이나 중간 점수로 변환하지 않는다.

## 2. 목표

다음 질문에 재현 가능하게 답하는 검토 계약과 검증기를 만든다.

1. 현재 원료 alias 규칙이 표본 제품을 올바른 비교군에 배정했는가?
2. C003의 공식 기능성 원문을 후속 결정 규칙에 사용할 수 있는가?
3. 사람 검토가 정확히 100건 모두 완료됐으며 표본과 일대일로 대응하는가?
4. 잘못된 매핑과 판단 불가를 성공으로 합치지 않고 별도 비율로 보존하는가?

`COMPLETE`는 입력 계약이 완전하다는 뜻일 뿐 확장 원료가 승인됐다는 뜻이 아니다.

## 3. 범위

### 포함

- 기존 `samples.csv`의 seed, 100개 신고번호, 그룹 배정과 제품 원문 보존
- 제품별 매핑 판정과 기능성 원문 상태를 기록하는 v2 라벨 템플릿
- 템플릿·표본·manifest를 함께 검증하는 오프라인 검증기
- 전체 및 그룹별 매핑 오류·불확실·기능성 원문 사용 가능 비율
- 표본 수가 작은 점을 드러내는 95% Wilson 구간
- `PENDING`, `INVALID`, `COMPLETE` 상태와 비추천 경계
- v1 산출물을 덮어쓰지 않는 별도 v2 pack

### 제외

- 실제 광고 이미지·상세페이지 수집
- 식약처 부당광고 사례집 또는 보도자료 코퍼스 구축
- 광고 위험 점수 또는 위반 발생률 추정
- 약사·영양사·표시광고 전문가 판단 대체
- 확장 원료 추천·최종 선택
- Phase 2, OCR, URL crawler, LLM, RAG, FastAPI, React 구현

공식 광고 사례 코퍼스는 이 설계의 구현과 검증이 끝난 뒤 독립된 설계와 계획으로
다룬다. 해당 코퍼스가 없으면 광고 위험과 고위험·고가치 후보는 계속
`NOT_MEASURED`와 `BLOCKED`다.

## 4. 산출물과 책임

### 4.1 v2 review-pack

새 산출물 경로는 `build/extension-review-v2/`다. 기존
`build/extension-review/`는 삭제하거나 덮어쓰지 않는다.

v2 pack은 정확히 다음 네 파일로 구성한다.

1. `README.md`: 검토 정의, 허용값, 완료와 추천의 차이
2. `manifest.json`: pack과 원본 export의 재현성 정보
3. `samples.csv`: 기존 100건 표본
4. `product_review_labels.csv`: 사람 입력 템플릿

`samples.csv`는 동일 export와 seed를 사용했을 때 기존 파일과 바이트 단위로 같아야
한다. 표본 내용이나 순서를 바꾸지 않고 라벨 계약만 교체한다.

### 4.2 manifest 계약

`manifest.json`은 다음 필드만 갖는다.

| 필드 | 값 또는 규칙 |
|---|---|
| `contract_version` | 고정값 `c003-product-review-v2` |
| `seed` | `20260823` |
| `sample_count` | `100` |
| `group_counts` | 다섯 비교군 각각 `20` |
| `samples_sha256` | 생성된 `samples.csv` SHA-256 |
| `source_export_sha256` | 입력 `data/c003-products.jsonl` SHA-256 |
| `mapping_rule_versions` | 표본에 실제 존재하는 규칙 버전의 정렬된 목록 |

manifest에는 API 키, URL, C003 응답 envelope, 사용자 정보 또는 원본 전체를 넣지
않는다. 검증기는 현재 파일 해시와 manifest를 다시 비교한다.

### 4.3 제품 검토 라벨 계약

`product_review_labels.csv`의 열 순서는 다음과 같이 고정한다.

1. `group`
2. `report_no`
3. `mapping_verdict`
4. `mapping_reason_code`
5. `function_text_status`
6. `function_reason_code`
7. `review_note`
8. `reviewer`
9. `reviewed_at_iso8601`

`group`과 `report_no`는 생성기가 채우며 사람이 변경하지 않는다. 나머지 필드는 처음에
비어 있다.

## 5. 사람 판정 정의

### 5.1 원료 매핑 판정

| 값 | 정의 | 집계 처리 |
|---|---|---|
| `correct` | `raw_materials` 원문이 배정된 원료군을 명시적으로 지지 | 결정 가능 정답 |
| `incorrect` | 원문이 다른 원료를 뜻하거나 alias 규칙의 거짓 양성 | 결정 가능 오류 |
| `uncertain` | 조합제품·모호한 별칭·전문가 확인 필요로 참·거짓 결정 불가 | 정답에 포함하지 않고 불확실로 별도 집계 |

`mapping_reason_code` 허용값은 다음과 같다.

- `none`
- `wrong_group`
- `alias_collision`
- `combination_product`
- `negative_or_exclusion_context`
- `needs_expert`
- `other`

`correct`는 이유가 `none`이어야 한다. `incorrect`와 `uncertain`은 `none`을 사용할 수
없다. `needs_expert` 또는 `other`를 선택하면 `review_note`가 반드시 필요하다.

### 5.2 기능성 원문 상태

| 값 | 정의 | 집계 처리 |
|---|---|---|
| `usable` | 원문이 존재하고, 원문 밖의 의미를 보충하지 않고 후속 규칙 입력으로 사용 가능 | 사용 가능 |
| `incomplete` | 비어 있거나 잘렸거나 형식이 손상되어 규칙 입력으로 사용할 수 없음 | 불완전 |
| `uncertain` | 문장은 있으나 의미 범위 또는 적용 가능성을 전문가 없이 확정할 수 없음 | 판단 불가 |

`function_reason_code` 허용값은 다음과 같다.

- `none`
- `missing_text`
- `truncated_or_malformed`
- `too_vague_for_rule`
- `needs_expert`
- `other`

`usable`은 이유가 `none`이어야 한다. `incomplete`와 `uncertain`은 `none`을 사용할 수
없다. `needs_expert` 또는 `other`를 선택하면 `review_note`가 반드시 필요하다.

### 5.3 검토자와 시각

- `reviewer`는 공백이 아닌 식별자다. 실명 대신 일관된 프로젝트용 식별자를 사용할 수 있다.
- 여러 검토자가 참여할 수 있으며 각 행의 검토자를 그대로 보존한다.
- `reviewed_at_iso8601`은 UTC 오프셋 또는 `Z`를 포함한 timezone-aware ISO 8601이어야 한다.
- 빈 값, 로컬 시각만 있는 naive datetime, 미래로 24시간을 초과한 시각은 유효하지 않다.

## 6. 검증 상태와 실패 처리

검증 결과 상태는 다음 세 개다.

| 상태 | 조건 | CLI 종료 코드 |
|---|---|---:|
| `COMPLETE` | manifest·표본·라벨 구조가 맞고 100행 모두 유효 | `0` |
| `PENDING` | 구조와 키는 맞지만 하나 이상의 사람 입력 필드가 비어 있음 | `2` |
| `INVALID` | 해시 불일치, 행 누락·추가·중복, 잘못된 값, 모순된 이유, 잘못된 시각 | `3` |

검증기는 `group + report_no`를 복합 키로 사용하고 다음을 모두 확인한다.

- 표본과 라벨의 키 집합이 정확히 같음
- 다섯 그룹 각각 20행, 전체 100행
- 중복 키와 예상하지 않은 그룹이 없음
- 라벨 행이 표본 순서와 달라도 결과가 같음
- enum, 이유 코드, note 조건, 검토자와 시각이 유효함
- 사람이 입력한 문자열이 spreadsheet formula prefix로 시작하지 않음
- 현재 `samples.csv` 해시가 manifest와 일치함
- 현재 export 해시가 manifest와 일치함

`PENDING`과 `INVALID`에서는 추천 객체나 성공 summary 파일을 만들지 않는다. CLI는
각 오류를 행 번호와 복합 키로 표시하되 제품 원문 전체나 비밀값을 출력하지 않는다.

## 7. 완료 후 계산할 지표

`COMPLETE`일 때만 전체와 다섯 그룹별로 다음 값을 계산한다.

- `sample_count`
- `mapping_correct_count`
- `mapping_incorrect_count`
- `mapping_uncertain_count`
- `mapping_precision_decidable = correct / (correct + incorrect)`
- `mapping_uncertainty_rate = uncertain / sample_count`
- `function_usable_rate = usable / sample_count`
- `function_incomplete_rate = incomplete / sample_count`
- `function_uncertainty_rate = uncertain / sample_count`
- 검토자별 행 수
- 검토 시작·종료 시각

`correct + incorrect`가 `0`이면 매핑 정밀도는 `0`이 아니라 `NOT_MEASURED`다. 매핑
정밀도에는 `z = 1.959963984540054`를 사용한 95% Wilson 구간을 함께 기록한다. 표본이
그룹별 20건뿐이라는 한계를 숨기지 않기 위해 점추정치만 단독으로 표시하지 않는다.

`incorrect`와 `uncertain`은 합치지 않는다. 오류율을 낮아 보이게 하려고 불확실 행을
분모에서 조용히 제거할 수 없으며, 결정 가능 정밀도의 분모와 전체 표본 수를 함께
표시한다.

## 8. 추천 경계

v2 검토가 `COMPLETE`여도 다음 상태를 고정한다.

- `advertising_evidence_status = NOT_MEASURED`
- `extension_recommendation_status = BLOCKED`
- `finalized = false`

기존 `advertising_risk_score`, `functional_diversity_score`,
`implementation_feasibility_score`를 임의 평균·반올림하여
`ExtensionCandidateStats`로 변환하지 않는다. 기존 recommendation 함수는 회귀 호환을
위해 즉시 삭제하지 않지만 v2 검증 흐름에서는 호출할 수 없다.

## 9. 데이터 흐름

1. 기존 C003 JSONL의 SHA-256을 계산한다.
2. 기존 seed와 매핑 규칙으로 동일한 100건 `samples.csv`를 재생성한다.
3. samples 해시와 최소 재현성 정보로 `manifest.json`을 만든다.
4. 복합 키만 채운 빈 `product_review_labels.csv`를 만든다.
5. 사람이 samples 원문을 보고 라벨 파일만 채운다.
6. 검증기가 manifest, samples, labels, 원본 export를 함께 읽는다.
7. 미완료는 `PENDING`, 모순·변조는 `INVALID`로 중단한다.
8. 정확히 100건이 유효할 때만 비추천 통계 summary를 계산한다.
9. 별도 공식 광고 근거 게이트가 끝나기 전에는 추천 단계로 연결하지 않는다.

모든 단계는 외부 네트워크와 LLM 없이 재현 가능해야 한다.

## 10. 보안과 감사 추적

- live export와 두 review-pack은 계속 Git ignored 경로에 둔다.
- tracked 테스트 fixture는 합성 데이터만 사용한다.
- CSV 작성 시 `=`, `+`, `-`, `@`, tab, carriage return 시작 셀을 계속 중화한다.
- 사람 입력 CSV에서는 같은 formula prefix로 시작하는 reviewer·note 값을 거부한다.
- 검증기는 키·토큰·비밀번호처럼 보이는 입력을 거부한다.
- 실제 API 키 값, URL, 사용자 건강정보, 판매자 페이지 원문을 pack에 추가하지 않는다.
- 기존 v1 pack은 잘못된 계약의 감사 이력으로 로컬에 보존하고 자동 삭제하지 않는다.
- tracked 문서에는 집계값, 해시, 계약 버전과 상태만 기록한다.

## 11. 테스트 전략

구현은 테스트 우선으로 다음 행동을 증명한다.

1. 동일 export와 seed에서 v2 samples가 기존 samples와 바이트 단위로 같다.
2. manifest의 두 SHA-256과 그룹 수가 실제 파일과 일치한다.
3. 빈 템플릿은 `PENDING`, 유효 라벨 수 `0 / 100`을 반환한다.
4. 합성된 유효 100행은 `COMPLETE`이며 그룹별 20행을 유지한다.
5. 누락·추가·중복·변조 키는 `INVALID`다.
6. 잘못된 enum, 이유 코드 모순, 필요한 note 누락은 `INVALID`다.
7. 공백 reviewer, naive datetime, 허용 범위를 벗어난 미래 시각은 `INVALID`다.
8. 모든 행이 `uncertain`이면 매핑 정밀도는 `NOT_MEASURED`다.
9. 계산된 비율과 Wilson 구간이 독립 계산과 일치한다.
10. v2 완료 후에도 광고 근거는 `NOT_MEASURED`, 추천은 `BLOCKED`, final은 `false`다.
11. 비밀정보 패턴과 spreadsheet formula 입력은 기존 보안 경계를 우회하지 못한다.
12. 전체 기존 테스트와 Ruff가 통과한다.

## 12. 완료 기준

다음 조건을 모두 직접 검증해야 이 구현 단위를 완료라고 보고한다.

- 설계에 정의된 v2 pack 네 파일이 로컬 ignored 경로에 생성됨
- 기존 100개 복합 키·그룹 수·표본 바이트가 보존됨
- 빈 실제 v2 라벨 검증 결과가 `PENDING`, `0 / 100`으로 확인됨
- 합성 완료 fixture가 `COMPLETE`로 검증됨
- 변조·불완전·모순 fixture가 각각 정해진 상태와 종료 코드로 거부됨
- 전체 테스트, coverage, Ruff, `git diff --check`, 비밀정보 검사가 통과함
- README, handoff, evidence 문서가 광고 위험 미측정과 추천 차단을 정확히 기록함
- `main` merge, 원격 push, v1 pack 삭제가 수행되지 않음

이 완료 기준은 **검토 도구 준비 완료**를 의미한다. 실제 사람 검토 완료, 광고 사례
코퍼스 완료, 확장 원료 추천 또는 프로젝트 완성을 의미하지 않는다.
