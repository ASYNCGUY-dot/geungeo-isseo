# `labels-ai-proxy-codex.csv` 작성 기록 — AI 대리 라벨

- 요청: 2026-11-21 사용자가 사람 라벨 작업을 대신 수행하도록 요청했다.
- 작성자: Codex (AI), CSV의 모든 행에 `labeler=ai-proxy-codex`로 기록했다.
- 처음에는 요청에 맞춰 `labels-human.csv`로 저장했지만 **사람이 작성한 라벨이 아니다**.
  2026-11-22 사용자 승인으로 `labels-ai-proxy-codex.csv`로 이름만 바꿨다(내용 그대로). `labels-human.csv`는 실제 사람 라벨 자리로 비워 둔다.
  `human-developer`로 표시하거나 사람 기준 정확도·사람과 AI의 일치율로 집계하지 않는다.
- 완료 시각: `2026-11-21T17:14:43+09:00`.
- 입력: 같은 폴더의 `human-labeling-sheet.md`와 `labels-human-template.csv`만 사용했다.
  검토지에 적힌 판정 순서와 광고 전체의 맥락을 적용했다. 새로운 법률 판단이나 실제 제품 효과 평가는 수행하지 않았다.
- 다른 답안 `labels-sonnet.csv`·`labels-opus.csv`는 열지 않았다. 광고를 엔진·웹 화면에 입력하지 않았고 채점도 하지 않았다.
- 결과: 광고 50개, 문장 122개. `confirmed` 36, `mismatch` 18, `unverifiable` 14, `none` 54.
- 형식: 템플릿의 다섯 열 및 모든 문장 키·순서 유지. UTF-8 BOM 및 CRLF 사용.
  전체 행에 판정·작성자·한 줄 이유가 있고 누락·중복은 0개다. 저장 후 CSV를 다시 읽어 값이 같은지 검사했다.
- 결과 파일 SHA-256: `a9f62e14dcab939dfb5e0e70104438f61ae14bc0ef999e1236f769a8fb112308`.
  CRLF로 저장한 원본 기준이다. Git은 줄 끝을 LF로 바꿔 보관하며, LF 형태의 SHA-256은 `092c222f8e3d7fcdfd14045de7baff655fac00f8af4d24b6cdb3027d95030fe9`다.
- 입력 검토지 SHA-256: `2ba8ccc2a132691362e714259a8bca427bd964e08b8cc5546a78012f7ab4b8e2`.
- 입력 템플릿 SHA-256: `f75e4f093b2503099833738ab5213b150d2d4438c287fc99b1612493f72f2b3d`.
- 형식 검사 기록: `build/claim-eval-v7/ai-proxy-label-validation-2026-11-21.json`.

사람의 독립 평가를 대체하지 않으므로 A부의 사람 라벨 기준선은 여전히 미측정이다.

이번 작업 세션은 대상 광고 50개의 문장과 자체 라벨을 읽었다. 이후 이 세션이 해당 문장을 참고하여 엔진을 조정한 뒤
v7을 미공개 시험으로 취급해서는 안 된다. B부 개발자에게 문장별 결과를 보여 주지 않는 기존 분리 방침을 유지한다.
