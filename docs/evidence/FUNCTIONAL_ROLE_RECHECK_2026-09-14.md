# 기능성 역할 검토 복구 — 2026-09-14

## 결론과 적용 범위

- 기존 규칙의 7일 최신성 기준 만료를 실제 공식 출처 재확인으로 처리했다.
- 기존 규칙·검토팩은 보존하고, 최신성 확인 시각만 다른 규칙 사본과 별도 검토팩을 만들었다.
- 사용자가 승인한 batch-001 AI 라벨 5건은 검토자와 인용·판정·검토 시각을 바꾸지 않고 이관했다.
- AI와 코드가 다른 1번·5번은 원인을 확인했지만 정답을 확정하지 않았다. 코드의 보류와 AI의 확인 판정을 모두 보존한다.
- 사람·전문가 기준 정확도와 원료별 적격성은 미측정이다. 광고 근거 B는 `NOT_MEASURED`, 추천 C는 `BLOCKED`, `finalized=false`다.
- 이번 작업은 출처 재확인·검토팩 복구·감사 기록이다. 제품 판정 코드, 임계값, 원료형·기능 문구, 테스트 코드는 변경하지 않았다.

## 1. 재현한 실패와 공식 출처 재확인

기존 규칙의 `verified_current_at=2026-09-04T17:31:53+09:00`은 내부 7일 기준을 넘었다.
기존 pack을 현재 시각으로 실행한 실제 검증기는 `INVALID`/exit 3,
`RULES_INVALID`와 `LABEL_VALIDATION_UNAVAILABLE`을 반환했다.
유효·대기 라벨 수와 summary는 null이었다. 입력 라벨의 오류로 단정하지 않았다.

`2026-09-14T15:13:50+09:00`에 다음 공식 게시물과 더 최근 개정고시 목록을 대조했다.

- [건강기능식품의 기준 및 규격 고시 전문 제2026-43호](https://www.mfds.go.kr/brd/m_211/view.do?seq=14973)
- [해당 일부개정고시](https://www.mfds.go.kr/brd/m_207/view.do?seq=15173)
- [제·개정고시 목록 1페이지](https://www.mfds.go.kr/brd/m_207/list.do), 2·3페이지:
  1페이지 최신 게시 제2026-65호부터 3페이지의 제2026-43호까지 제목을 대조했다.
  그 사이 제2026-55호는 일반 식품 기준이며 이 건강기능식품 기준의 개정으로 혼동하지 않았다.
- [공식 ZIP 첨부](https://www.mfds.go.kr/brd/m_211/down.do?brd_id=data0005&seq=14973&data_tp=A&file_seq=1)를
  같은 날 12:59:19 KST에 다시 다운로드했다. 3,524,589바이트이며 기존 ZIP·규칙의 내용 해시와 같다.

확인한 목록에서 이 기준의 후속 개정은 발견하지 못했다. 이는 조사한 공식 출처 범위의
재확인이지 모든 법령·고시 변경이 없다는 포괄 보증이나 제품 효능·안전 확인이 아니다.
C003 제품 데이터를 새로 수집한 것도 아니다. 제품 원문은 2026-08-27 스냅샷 그대로다.

원문 다운로드는 ignored 폴더 `build/functional-role-source-recheck-2026-09-14/`에 보존한다.

| 로컬 증거 | SHA-256 |
|---|---|
| mfds-2026-43.zip | `3D25C54F8248204C75E02F889C1EE4ADC3BC3FA2188ED91DA06DA33402AFEBFB` |
| mfds-fulltext.html | `5C332338D24D189AB7F30B953B5B74D8BBC707A45BB276C669AB33F0E24BD2CF` |
| mfds-amendments-1.html | `30FDF381EC7C3CF3C5A20E891CCF1A418DF0FC35E8753858E2939C88E8C26ABB` |
| mfds-amendments-2.html | `B051455AFCBDE9A2BC88AFEB1FEEFF4EFD2D5710AE2E88EC2B9DB186CA02CC19` |
| mfds-amendments-3.html | `D20B036B316544B528357CBA4F8F697F86C28BF012F24D3B9FD75AF2FA477EB2` |

## 2. 새 규칙 사본과 안전한 이관

- 보존 규칙: `data/reference/functional-role-rules-v1.json`
- 재확인 규칙: `data/reference/functional-role-rules-v1-reverified-2026-09-14.json`
- 보존 pack: `build/functional-role-review-v1/`
- 현재 운영 pack: `build/functional-role-review-v1-reverified-2026-09-14/`

다섯 규칙의 `verified_current_at`만 실제 재확인 시각으로 변경했다.
필드를 원래 값으로 되돌려 JSON 전체를 비교했을 때 다른 의미·검토 이력 변경은 없었다.
CHOI·DOHA의 기존 검토 시각은 9월 4일 그대로다. 오늘 다시 사람 검토했다고 기록하지 않았다.
규칙 버전·계약 버전도 유지한다. 새 파일명 날짜는 재확인 이력을 식별한다.

새 pack 생성 종료코드는 0이며 `generated_at=2026-09-14T06:14:37.583069Z`다.
규칙 파일 해시가 바뀌므로 기존 manifest를 손대지 않고 새 pack을 생성했다.
275행 `samples.csv` 전체 SHA-256이 기존과 같은 것을 확인한 후, 기존 labels를 새 pack에
바이트 동일하게 이관했다. 기존 AI 답변지에는 당시 사용한 옛 규칙 해시가 남아 있으며 이를 고치지 않는다.

| 보호·이관 대상 | SHA-256 |
|---|---|
| 기존 규칙 — 불변 | `E8611F98A41885D65B79AA02ECBDB74A3937F95EB4BE2CCF3C2925D1A0966E7D` |
| 재확인 규칙 | `5484018E6100566783684FF58D0F9739C3D8CBAED3A09B0D64DE84B9FC90B76D` |
| 기존 역할 manifest — 불변 | `FE6186AA2B0454BF24406A80B10198080800989D53BE2BFB794AA1337BEAA538` |
| 새 역할 manifest | `4267A2AF0CC2039B9039AA09053603F4EF7DDC881DCE472648406C49D91548F7` |
| 기존·새 samples — 동일 | `2A5A2554C5B0A5C0FB289E902CC210274A3B99294E8C3779A9CB309B233EDF25` |
| 기존·새 labels — 동일 | `1DF8FB5A37DF9C4F2370B9E8F691118C625601F8FDFB89A0DBAAEB4E53EFD2CB` |
| batch-001-response-choi.md — 불변 | `354BA2EFF537CDD6AEC9FE1E1187B8E671BCA1945E36BD888EAA37753DFD34B7` |
| v2 완료 labels — 불변 | `A00B3C1A038DBFD06484A89A6C1B41AAA63837D3BD87FAC29E2AF5DF0E011CC1` |
| C003 JSONL — 불변 | `CF0D58B478408448F1D9FC0C2A5EB22E3E08055675072C8B863CD6E112703B7E` |

현재 pack 안에는 README, manifest, samples, labels 네 파일만 둔다.
원문·개인별 응답·라벨 전체는 Git에 넣지 않는다.

## 3. 사용자 승인과 AI 라벨의 의미

사용자는 이 작업의 채팅에서 “ㅇㅇ 내가 승인한 내용이 맞아”라고 AI 라벨 반영 승인을
확인했고, 이어 “응 해결하자”라고 요청했다. 이미 존재하는 batch-001의 다섯 AI 결과에
대한 승인으로 기록한다. 남은 행을 새 AI 판정으로 일괄 채울 포괄 승인으로 확대하지 않는다.

- 실제 기록된 검토자: `CLAUDE-OPUS-5-AI`
- 원래 AI 검토 시각: `2026-09-14T11:50:30+09:00`
- 결과: `functional_confirmed` 4, `uncertain` 1.
- 파일명의 `choi`는 사람 검토의 증거가 아니다. CHOI·DOHA로 검토자 이름을 바꾸지 않는다.
- 응답 파일의 모델명·기계 판정 미열람 주장은 해당 파일의 자기보고다. 모델 실행 이력과 독립성을 별도로 입증한 것은 아니다.
- CSV의 `human_verdict`는 기존 열 이름일 뿐 이번 5건의 출처는 AI다.
  검증기의 유효 라벨 수는 계약·인용·무결성 검증 결과이며, 사람 검토 완료 수가 아니다.
- 이 AI 라벨에 대한 일치도를 사람 기준 정확도·전문가 정답률·실사용 정확도로 발표하지 않는다.
- 현재 검증기는 리뷰어 유형을 별도 형식으로 강제하지 않는다. 따라서 향후 혼합 라벨로
  `COMPLETE`가 나오더라도 독립 사람 평가 게이트를 통과했다고 해석할 수 없다.
  AI/사람 출처를 분리하는 평가 계약 없이 AI가 섞인 집계를 인간 기준 적격성 판단에 사용하지 않는다.

[기계가 읽을 수 있는 승인·출처 감사 기록](functional-role-ai-review-provenance-2026-09-14.json)은
위 경계를 기록하는 sidecar다. 기존 validator가 이를 자동으로 검사하는 기능은 추가하지 않았다.

## 4. 1번·5번 불일치의 근본 원인

재확인 규칙으로 동일한 다섯 제품을 직접 분류하고, 매칭된 비교 원료군을 출력했다.

| 번호 | 신고번호 | AI 결과 | 코드 결과·이유 | 원재료에서 잡힌 비교군 |
|---|---|---|---|---|
| 1 | 200400150831113 | 기능성 확인 | 검증 불가 / combination_linkage_ambiguous | 밀크씨슬 + 마그네슘(스테아린산마그네슘) |
| 2 | 200400150831561 | 기능성 확인 | 기능성 확인 / function_and_form_linked | 밀크씨슬 |
| 3 | 20040015107716 | 불확실 | 검증 불가 / form_without_function | 밀크씨슬 + 마그네슘(산화마그네슘) |
| 4 | 20040017021839 | 기능성 확인 | 기능성 확인 / function_and_form_linked | 밀크씨슬 + 홍삼 + 마그네슘(스테아린산마그네슘) |
| 5 | 2004001702936 | 기능성 확인 | 검증 불가 / combination_linkage_ambiguous | 밀크씨슬 + 홍삼 + 마그네슘(스테아린산마그네슘) |

코드는 원재료에서 복수 비교군이 잡히면 대상 원료명과 기능의 명시적 연결을 요구한다.
4번은 기능성 원문에 대상 원료명이 명시되어 통과한다. 1번·5번은 원료명 연결이 없고,
AI는 나머지 기능 문구와 원료의 대응 및 고시형 표기 유무로 귀속을 추론했다.

이는 코드 실행 오류를 입증한 결과가 아니다. `스테아린산마그네슘`을 무조건 비기능성으로
제외하거나, 고시형 표시가 없다는 이유로 다른 기능 가능성을 배제하는 규칙은 만들지 않았다.
확인 불가를 줄일 여지는 있으나 규칙 변경은 별도 근거와 실패 회귀 사례가 필요하다.

외부 보충 조회의 한계:

- 제조사 사이트에 [간에좋은밀크씨슬 C01443](https://hanminutrition.com/c01443/)와
  [동명 C01084](https://hanminutrition.com/c01084/)가 함께 존재한다.
  열람한 내용에서 신고번호 연결을 확인하지 못했다. 같은 이름이라는 이유로 1번에 묶지 않았다.
- 5번의 신고번호가 보인 FMIS 검색 결과는 실제 열린 페이지에서 해당 행을 재확인하지 못했다.
  검색 요약만으로 공식 제품·기능성 증거를 확보했다고 기록하지 않는다.
- 따라서 1번·5번의 최종 중재 상태는 `NEEDS_PRODUCT_BOUND_EVIDENCE`다.
  승인된 AI 라벨과 코드 보류를 각각 보존하며 누구의 결과를 정답으로 덮어쓰지 않는다.

## 5. 검증 결과

재확인 pack의 실제 CLI 실행 결과:

```json
{
  "status": "PENDING",
  "expected_label_count": 275,
  "valid_label_count": 6,
  "pending_label_count": 269,
  "issues": [],
  "summary": null,
  "advertising_evidence_status": "NOT_MEASURED",
  "extension_recommendation_status": "BLOCKED",
  "finalized": false
}
```

종료코드 2다. 최신성 장애는 해소되었지만 A가 완료된 것은 아니다.
유효 6행은 승인 AI 5행과 상속 제외 1행이다. 새 사람 제품 검토를 기록하지 않았다.
대기는 밀크씨슬 50, 비타민D 55, 홍삼 54, 코엔자임Q10 55, 마그네슘 55행이다.
`docs/evidence/functional-role-summary-v1.json`은 생성하지 않았으며 존재하지 않는다.

전체 오프라인 회귀 검증을 2026-09-14 새로 실행했다:

```powershell
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing --cov-fail-under=97 --cov-report=json:build/coverage-2026-09-14.json --junitxml=build/test-results-2026-09-14.xml -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
```

- 테스트: `609 passed in 328.52s`, exit 0.
- 코드 실행 커버리지: `97.22334004024145%`, 2,485문장 중 미실행 69, 97% 목표 통과.
- Ruff: `All checks passed!`; diff 공백 검사 통과.
- 보호 대상 9개 해시 불변, AI 5행의 검토자·시각 보존, 새 pack 파일 수 4개 확인.
- 소스·테스트 코드 변경 없음. 커버리지·검증기 통과는 서비스 판정 정확도나 전문가 검증의 증거가 아니다.
- 별도 읽기 전용 AI 검토에서도 수정이 필요한 무결성·문서 모순은 발견되지 않았다.
  규칙 의미 차이 5곳, 보고서 해시, 표본·라벨 동일성, 출처 기록과 실제 validator 결과를 재확인했다.
  그 검토자는 라이브 조회·다운로드 시각·모델 실행·독립성은 별도 입증하지 않았고,
  전체 테스트는 저장된 JUnit·coverage를 확인했다. 의료·제품 정답 검증이나 병합 승인이 아니다.

## 6. 다음 작업과 사용자에게 필요한 자료

1. 현재 운영 pack·재확인 규칙으로만 후속 검증한다. 보존 pack에 생성기를 다시 실행하지 않는다.
2. 1번·5번을 확정하려면 같은 신고번호의 공식 상세 자료 또는 신고번호와 연결 가능한
   제조사 표시사항이 필요하다. 대상 원료와 기능이 어떻게 연결되는지 확인할 수 있어야 한다.
   제품명만 있는 쇼핑몰 캡처는 충분하지 않다. 오늘 자료라면 8월 27일 스냅샷과의 버전 차이도 기록한다.
3. 사용자가 그 자료를 가지고 있다면 PDF·링크·라벨 사진을 제공한다.
   없으면 두 건의 코드 보류를 유지한 채 다른 검토를 진행할 수 있다.
4. 남은 라벨의 검토 주체를 새로 결정할 때 AI 참고 라벨과 독립 사람/전문가 평가를 구분한다.
   이번 다섯 건 수용만으로 전체 검토 방법·제품 판정 규칙을 자동 변경하지 않는다.
5. 실제 승인·원문이 없으면 빈 행을 채우지 않는다. A 완료나 원료 적격성을 선언하지 않는다.

운영자 명령(사용자가 실행할 필요 없음):

```powershell
.venv\Scripts\python.exe scripts\validate_functional_role_review.py --pack-dir build\functional-role-review-v1-reverified-2026-09-14 --source-export data\c003-products.jsonl --product-review-pack build\extension-review-v2 --rules data\reference\functional-role-rules-v1-reverified-2026-09-14.json
$roleValidatorExit = $LASTEXITCODE
Write-Output "ROLE_VALIDATOR_EXIT=$roleValidatorExit"
```

내부 7일 경계는 재확인 시각에서 `2026-09-21T15:13:50+09:00`에 도달한다.
그 시각을 넘기면 실제 출처를 다시 확인한다. 제출 마감이나 법령 만료일이 아니다.
