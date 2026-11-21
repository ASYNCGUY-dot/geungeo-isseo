# claim-eval-v7 AI 대리 라벨 채점 — 2026-11-21

사용자가 50개 광고의 라벨 작성을 대행시킨 뒤 "채점해봐"라고 요청했다.
`labels-ai-proxy-codex.csv`(처음 이름 `labels-human.csv`, 2026-11-22 이름만 바꿈)의 작성자는 `ai-proxy-codex`다. 사람·전문가 기준 정확도는 여전히 미측정이며
11/18 계획 A부의 사람 기준선이나 B부 승인으로 해석하지 않는다.

## 입력과 실행

- main HEAD: `dd432f9`. 엔진과 기존 채점기는 태그 `public-engine-2026-11-18`과 변경 사항이 없음을 확인했다.
- 엔진: `claim-extract-v1.14` / `claim-verdict-v1.5`.
- 대상: `human-cases.json`에 고정된 광고 50개, 문장 122개.
- 기준 라벨: `data/eval/claim-eval-v7/labels-ai-proxy-codex.csv`(채점 때 이름 `labels-human.csv`); CRLF 원본의 SHA-256은
  `a9f62e14dcab939dfb5e0e70104438f61ae14bc0ef999e1236f769a8fb112308`.
- 원본 C003: 기존 worktree의 보관 스냅샷을 읽었고 manifest의 SHA-256
  `CF0D58B478408448F1D9FC0C2A5EB22E3E08055675072C8B863CD6E112703B7E`와 일치했다.
  조회 시각도 manifest의 `2026-08-27T12:42:29.050550+00:00`을 유지했다. 새 조회 결과가 아니다.
- main의 `src`와 `scripts`를 import 경로로 지정하고 기존 `scripts/score_ad_eval.py`의 `score`를 한 번 호출했다.
  다른 worktree의 Python 실행 환경만 빌렸으며 엔진 코드는 main의 것을 실행했다.
- 실행 보조 파일: `build/claim-eval-v7/score_ai_proxy.py`; 종료코드 0.
- 채점 전 CSV 해시를 확인하고 라벨을 고정했다. 채점 후 라벨을 수정하지 않았다.
- 기존 Sonnet·Opus 라벨은 라벨 작성이 끝난 뒤 이번 비교 계산에서 처음 읽었다.
  요약만 출력했고 문장별 채점 및 불일치는 `build/`에 저장했다.

## 결과

| 지표 | 결과 |
|---|---:|
| 오인 승인: mismatch 또는 unverifiable 라벨 문장 | 0 / 32 |
| 오인 승인: none 라벨 문장 | 0 / 54 |
| 오인 승인 합계 | 0 / 86 |
| confirmed 재현율 | 12 / 36 (33.3%) |
| 문장을 단독으로 입력했을 때 confirmed | 31 / 36 (86.1%) |
| mismatch 재현율 | 11 / 18 (61.1%) |
| 틀린 mismatch: confirmed 또는 none 라벨 문장 | 20 / 90 (22.2%) |
| 엔진과 대리 라벨의 전체 일치 | 66 / 122 (54.1%) |
| 정직한 광고 전체를 라벨대로 판정 | 7 / 23 (30.4%) |

틀린 mismatch 20건은 모두 none 라벨에서 나왔다. 맥락 종류별로 고지 문구 17건, 소개 문장 3건이다.
confirmed 라벨 36개 중 나머지 24개는 모두 unverifiable로 나왔다. 단독 입력은 31개를 확인하므로
광고 전체 맥락의 보류가 재현율을 크게 줄인다. 두 값의 차이 19개를 보류 원인의 확정 분류로 간주하지 않는다.

오인 승인 0/86에 이항 독립 표본을 가정하면 95% 단측 Clopper–Pearson 상한은 약 3.42%다.
이는 설명용 수치다. 문장이 광고 안에 묶여 있고 표본이 층화되었으며 AI 라벨이므로 실제 운영 오류율의
엄밀한 신뢰상한이나 사람 기준 안전성 근거로 쓰지 않는다.

## 기존 AI 라벨과 비교

같은 122문장만 비교했다.

| 비교 | 일치 | Cohen's kappa |
|---|---:|---:|
| Codex 대리 라벨 대 Sonnet | 113 / 122 (92.6%) | 0.8918 |
| Codex 대리 라벨 대 Opus | 120 / 122 (98.4%) | 0.9759 |
| Sonnet 대 Opus | 113 / 122 (92.6%) | 0.8915 |

두 AI가 모두 confirmed로 본 36문장 중 Codex 대리 라벨이 다른 문장은 0개다.
이 수치는 AI끼리의 일치이며 사람과 AI의 일치가 아니다. 다수결이나 유사도가 정답을 증명하지 않는다.

## 저장 결과와 평가 분리

- 요약: `build/claim-eval-v7/score-ai-proxy-summary-2026-11-21.json`.
- 문장별 결과: `build/claim-eval-v7/score-ai-proxy-details-2026-11-21.json`.
- AI 라벨 불일치: `build/claim-eval-v7/ai-proxy-label-disagreements-2026-11-21.json`.
- 채점 입력 사본: `build/claim-eval-v7/cases-ai-proxy-2026-11-21.json`.

이번 세션은 앞서 50개 광고를 라벨했고 입력 형식 확인 중 비대상 `C7-001` 광고의 앞부분도 도구 출력에 노출됐다.
이번 채점 범위는 고정된 50개 광고 그대로이며 나머지 광고를 엔진에 입력하지 않았다.
향후 이 세션에서 노출된 문장을 보고 엔진을 조정한 뒤 v7을 미공개 시험으로 취급하지 않는다.
엔진 수정과 B부 구현은 이번 요청의 범위에 포함하지 않았다.

2026-11-22: 사용자 승인으로 Claude Code가 이 기록과 라벨을 커밋했다. 라벨 파일 이름만 바꿨고 수치는 그대로다.
위 `build/` 파일은 루트 체크아웃의 `build/claim-eval-v7/`에 있다(Git 제외).
