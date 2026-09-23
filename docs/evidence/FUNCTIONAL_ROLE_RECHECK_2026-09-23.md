# 기능성 역할 규칙 최신성 복구 — 2026-09-23

## 결론

실제 식약처 원본 재다운로드와 개정 목록 대조 후, 최신성 확인 시각만 다른 별도 규칙과 검토팩을 만들었다.
새 pack의 실제 검증 결과는 **PENDING / 유효 6 / 대기 269 / 이슈 0 / exit 2 / summary null**이다.
유효 6은 과거 승인 AI 5 + 상속 제외 1이며 신규 사람 검토 6건이 아니다.
별도 269개 AI 초안을 사람용 라벨에 이관하지 않았다.

## 재현한 차단과 공식 재확인 범위

9월 14일 규칙의 내부 7일 최신성 기준이 지나 기존 pack은 `INVALID`/exit 3,
`RULES_INVALID` 및 `LABEL_VALIDATION_UNAVAILABLE`을 반환했다. 유효·대기 수는 null이었다.
라벨 훼손으로 단정하지 않고 보존했다.

- [건강기능식품 기준·규격 제2026-43호 고시전문](https://www.mfds.go.kr/brd/m_211/view.do?seq=14973)의
  공식 ZIP을 9월 23일 다시 받았다. 3,524,589바이트, 기존 내용 해시와 일치한다.
- [제·개정고시 목록](https://www.mfds.go.kr/brd/m_207/list.do)의 1~3페이지를 직접 내려받고,
  최신 제2026-67호부터 제2026-43호 게시물까지 제목과 식별자를 대조했다.
  확인한 범위에서 이 기준·규격의 후속 개정은 발견하지 못했다.
- [제2026-66호 표시기준 개정](https://www.mfds.go.kr/brd/m_207/view.do?seq=15195)은 별도 기준이다.
  공식 게시 설명은 건강기능식품·GMP 도안 변경에 관한 내용이다. 이를 기능성 원료형·기능 문구
  변경으로 혼동하지 않았다. 향후 표시·OCR 검증에는 별도 적용 검토가 필요하며 이번에 구현하지 않았다.
- 실제 재확인 시각: `2026-09-23T15:02:04.1815514+09:00`.
  이 시각부터 내부 7일 기준을 적용한다. 법령 만료일이나 사용자 검토 마감일이 아니다.
- 위 결론은 확인한 공식 게시 범위의 재확인이다. 모든 관계 법령의 무변경·제품 안전·효능·광고 적법성을
  보증하지 않는다. C003 제품 원문은 2026-08-27 스냅샷이며 재수집하지 않았다.

## 로컬 증거

감사 원본은 `build/functional-role-source-recheck-2026-09-23/`에 보존한다.
샌드박스 네트워크 소켓 거부 후 공개 원본 다운로드 권한으로 재시도했다. API 키·개인정보를 전송하지 않았다.

| 증거 | SHA-256 |
|---|---|
| mfds-2026-43.zip | `3D25C54F8248204C75E02F889C1EE4ADC3BC3FA2188ED91DA06DA33402AFEBFB` |
| mfds-fulltext.html | `1B9F2B1C10AD1F77247F4AC6E3F136A4F38EFAF5EB934CC8C6E01328D5F0345F` |
| mfds-amendments-1.html | `10A8CAAA62972C242D9F7D115748A453261C6BD2CB8DDD34D063603871980BBE` |
| mfds-amendments-2.html | `0B319EE130683543F1B63255CE911561D476C2E0E366E54FCA207E58F34A57C9` |
| mfds-amendments-3.html | `0851B5287DC01A9D1547DB29B0B03AE350C939C5695F2F0248DA15260F0CD7E0` |
| mfds-label-notice-2026-66.html | `1AF7E5E5D4D8B2E2BC62E3BB6D7DF00B26AB06831FF4624E035B9A84DAD7D067` |

## 별도 규칙·검토팩과 이관 검증

- 규칙: `data/reference/functional-role-rules-v1-reverified-2026-09-23.json`.
- 운영 pack: `build/functional-role-review-v1-reverified-2026-09-23/`.
- 기존 모든 규칙/pack은 그대로 보존했다. 새 규칙의 다섯 `verified_current_at`을
  원래 값으로 되돌려 비교했을 때 나머지 JSON 내용은 동일했다.
  CHOI·DOHA의 사람 규칙 검토 시각·규칙 의미·버전은 바꾸지 않았다.
- 기존 생성기로 새 경로에만 생성(exit 0)한 후 samples 전체 SHA-256 동일성을 확인했다.
  그 후 이전 labels를 바이트 동일하게 이관했다. AI 초안 269건을 새로 채우지 않았다.
- 새 pack은 README, manifest, samples, labels의 네 파일만 포함한다.

| 새 파일 | SHA-256 |
|---|---|
| rules | `CC7752DBAFF491A60CBBC490FF3AA4AF322E8A9E47BB4690CEFD3A63EA78CD2F` |
| manifest | `6BFBFD0AA29FC691C50B10158091085701675C175B35BBCF319AA458433A0FC4` |
| samples — 이전과 동일 | `2A5A2554C5B0A5C0FB289E902CC210274A3B99294E8C3779A9CB309B233EDF25` |
| labels — 이전과 동일 | `1DF8FB5A37DF9C4F2370B9E8F691118C625601F8FDFB89A0DBAAEB4E53EFD2CB` |

현재 운영 명령:

```powershell
.venv\Scripts\python.exe scripts\validate_functional_role_review.py --pack-dir build\functional-role-review-v1-reverified-2026-09-23 --source-export data\c003-products.jsonl --product-review-pack build\extension-review-v2 --rules data\reference\functional-role-rules-v1-reverified-2026-09-23.json
$roleValidatorExit = $LASTEXITCODE
$roleValidatorExit
```

실제 결과: expected 275, valid 6, pending 269, issues [], PENDING, summary null,
광고 B NOT_MEASURED, 추천 C BLOCKED, finalized false. 역할 적격성이나 사람 정확도는 미측정이다.
1번·5번의 기존 코드/AI 차이는 해결되지 않았다.

AI 초안 수정·구조 검사·전체 테스트·잔여 작업은 [AI 중간 인계](FUNCTIONAL_ROLE_AI_REVIEW_2026-09-23.md)를 본다.
이번 복구는 날짜만 조작한 통과가 아니며, 새로운 사람 검토나 서비스 출시 승인도 아니다.
