# 실제 제품 귀속 평가세트 v2 (v2.8 독립 표본) — 2026-10-01

**결론: v1과 겹치지 않는 새 표본 100쌍에서, 파서(`official-function-v2.8`)가 귀속한 70쌍 중 잘못 귀속은 0개였다
(Wilson 95% 상한 5.2%). v2.7~v2.8에서 새로 허용한 형식으로 귀속된 25쌍도 0개였다(상한 13.3%).
라벨은 규칙을 만들지 않은 맹검 AI 라벨러 두 개(Sonnet, Opus)가 따로 붙였고 100쌍 모두 일치했다. 사람 검토가 아니다.**
v1 기록은 [평가세트 v1](ATTRIBUTION_EVAL_2026-09-30.md), 형식 확장은 [형식 확장 v2.7→v2.8](HOLD_FORMATS_2026-10-01.md)이다.

## 왜 새 표본인가

- v1에서 보류됐던 AE-016·017·027·067·092는 v2.7 형식을 고르는 데 쓴 사례라, 새 형식의 정확도를 독립적으로 보여주지 못했다.
- v2는 v1의 100개 제품을 빼고 다른 시드로 뽑았고, 새 형식으로 귀속된 쌍을 따로 층으로 나눠 많이 뽑았다.

## 표본

- 틀: C003 스냅샷(조회 `2026-08-27T12:42:29.050550+00:00`, SHA-256 `CF0D58B4…03B7E`)에서 v1 제품 100개를 뺀 후보 22,329쌍.
- 새 층 `attributed_new_format`: v2.7~v2.8에서 처음 허용한 형식(영문 번역, `기능성 내용` 라벨, 2등급 표기, `[원료] :`,
  헤더 `(or`, 이름 줄 괄호 안 구분자)으로 귀속된 쌍. 형식 표시로 판별하며, C003 전체에서 v2.6 대비 새로 귀속된 509쌍을
  모두 잡고 v2.6도 귀속하던 3쌍을 함께 잡는다(읽기 전용 비교로 확인).

| 층 | 틀 | 표본 |
|---|---:|---:|
| attributed_canonical | 13,356 | 15 |
| attributed_variant_header | 185 | 15 |
| attributed_extended_format | 1,121 | 15 |
| attributed_new_format | 502 | 25 |
| held_under_target_header | 1,217 | 10 |
| held_headerless | 5,546 | 10 |
| held_other | 402 | 10 |

- 시드 `20261002`, 항목 번호 `AE2-001`~`AE2-100`, 제품당 한 쌍, v1과 겹치는 제품 0개.
- **표본 목록(manifest)은 라벨이 생기기 전에 커밋해 고정했다**(`1f79d3e`). 제품 원문이 담긴 검토지는 ignored
  `build/eval/attribution-eval-v2/review.md`에만 있다.

## 라벨

- 라벨러: Claude Code 서브에이전트 두 개, 모델 Sonnet(`independent-sonnet-ai`)과 Opus(`independent-opus-ai`). 규칙을 만든
  개발 세션(이 문서 작성자)은 라벨을 붙이지 않았다. **두 라벨 모두 AI 라벨이며 사람·전문가 검토가 아니다.**
- 맹검: 두 에이전트 모두 검토지만 읽게 했고, 층·파서 결과·서로의 라벨은 보지 못하게 했다. 대화 기록에서 도구 호출을 확인했다.
  둘 다 검토지 전체를 나눠 읽었고(Sonnet 4번, Opus 5번), 그 밖에는 자기 출력 CSV를 쓰고 검증한 것뿐이다.
- 판정 질문, 정의, 고시형 배경지식은 v1 교차 라벨과 같은 지시문을 썼다. 따라서 두 라벨의 일치는 같은 기준을 일관되게
  적용한다는 뜻이지 기준 자체가 맞다는 증거는 아니다.
- 결과: 두 라벨러 모두 `yes` 91, `no` 9, `unclear` 0이며 **100쌍 모두 일치**(Cohen's kappa 1.0, 우연 일치 0.836).
- `no` 9쌍(AE2-017·026·043·044·056·062·075·092·096)은 모두 보류 층이다. 대상 원료가 원재료에만 있고 공식 문구가 없거나,
  효과 문구가 은행잎·홍삼·차전자피·자일로올리고당 같은 다른 원료의 것이었다.

## 결과 (`scripts/score_attribution_eval.py`, 두 라벨 파일 모두 같은 결과)

| 층 | n | 잘못 귀속 | 놓친 귀속 | Wilson 95% |
|---|---:|---:|---:|---|
| 표준 헤더 귀속 | 15 | 0 | — | 0~20.4% |
| 헤더 변형 귀속 | 15 | 0 | — | 0~20.4% |
| 확장 형식 귀속 | 15 | 0 | — | 0~20.4% |
| **새 형식 귀속(v2.7~v2.8)** | **25** | **0** | — | **0~13.3%** |
| **귀속 전체** | **70** | **0** | — | **0~5.2%** |
| 대상 헤더 아래 보류 | 10 | — | 9 | 59.6~98.2% |
| 헤더 없는 나열 보류 | 10 | — | 10 | 72.2~100% |
| 기타 보류 | 10 | — | 2 | 5.7~51.0% |

- 층 표류 0, 라벨 없는 항목 0, 채점 종료코드 0(`--require-zero-false-attribution`).
- v1과 합치면: v1의 귀속 60쌍은 v2.8에서도 모두 귀속이고, 맹검 교차 라벨(v1 Sonnet)과 v2 두 라벨 모두 잘못 귀속 0이다.
  **AI 맹검 라벨 기준 귀속 130쌍 중 잘못 귀속 0(Wilson 상한 2.9%).** 단, 두 평가세트는 층 정의와 라벨러 구성이 다르므로
  합친 수치는 참고값으로만 쓴다.
- 보류 쪽은 v1과 같은 경향이다. 대상 헤더 아래 보류와 헤더 없는 나열은 대부분 원문상 귀속 가능한 과잉 보류였고,
  기타 보류는 대부분 올바른 보류였다.

## 보류 원인 (보류 층 30쌍, 다음 개선 후보)

- 대상 헤더 아래 보류 중 귀속 가능 9쌍의 원인:
  - 문구 변형 `노화로 인하여`(표준 `인해`, AE2-006)
  - 사전에 없는 개별인정 균주 헤더(`UREX 프로바이오틱스`, `…TWK10 프로바이오틱스`, AE2-011·032·074). `I-0040`을 받으면 확인 가능.
  - 제형 단위 헤더 `정제1`·`캡슐4`(AE2-047)
  - 헤더 오타 `루테인지아잔틴복합추춤물`(AE2-069)
  - `․` 나열(AE2-059), 문장 사이 `ᆞ`(AE2-076)
  - 함량 표기가 붙은 헤더 `루테인지아잔틴복합추출물20%`(AE2-052). 원료명 사전에는 있어 미해결 헤더는 아니지만
    대상 이름 완전 일치가 아니라 대상으로 읽히지 않는다.
- AE2-075는 대상 헤더 아래 보류였고 두 라벨러 모두 `no`였다. 기억력 문구가 은행잎 추출물 쪽에만 있다. 올바른 보류다.
- 헤더 없는 나열 10쌍은 모두 귀속 가능(나열형 귀속 규칙, `I-0040` 이후).

## 한계

- 라벨은 AI 두 벌이며 같은 지시문을 받았다. 사람 기준 정확도가 필요하면 사람 스팟체크가 따로 필요하다.
- 층별 표본이 15~25쌍이라 층별 상한은 13~20%로 넓다. 발표에서는 "귀속 70쌍 중 잘못 귀속 0(상한 5.2%)"처럼
  표본 크기와 구간을 함께 말한다.
- 광고 문장 해석 오류와 제품 신원 오류는 이 평가 범위 밖이다.

## 실행

```powershell
.venv\Scripts\python.exe scripts\build_attribution_eval.py --source-export data\c003-products.jsonl --source-retrieved-at 2026-08-27T12:42:29.050550+00:00 --seed 20261002 --eval-id attribution-eval-v2 --item-prefix AE2 --exclude-manifest data\eval\attribution-eval-v1\manifest.json --quota attributed_canonical=15 --quota attributed_variant_header=15 --quota attributed_extended_format=15 --quota attributed_new_format=25 --quota held_under_target_header=10 --quota held_headerless=10 --quota held_other=10 --manifest data\eval\attribution-eval-v2\manifest.json --review-sheet build\eval\attribution-eval-v2\review.md --labels-template build\eval\attribution-eval-v2\labels-template.csv
.venv\Scripts\python.exe scripts\score_attribution_eval.py --manifest data\eval\attribution-eval-v2\manifest.json --labels data\eval\attribution-eval-v2\labels-opus.csv --source-export data\c003-products.jsonl --source-retrieved-at 2026-08-27T12:42:29.050550+00:00 --output data\eval\attribution-eval-v2\score-opus.json --require-zero-false-attribution
```

- 같은 명령에 `labels-sonnet.csv`, `score-sonnet.json`을 넣으면 Sonnet 라벨 채점이다. 출력은 둘 다
  `attributed n=70 false_attribution=0 unlabeled=0 drift=0`, 종료코드 0.
- 새 층 판별과 제외·항목 접두어 옵션은 `tests/test_attribution_eval.py`에 테스트를 먼저 썼다(RED 7 → GREEN).
- 전체 pytest **1023 passed, 1 warning in 257.61s**, 종료코드 0, 커버리지 3,425문장 중 미실행 76개 **97.78%**. Ruff 통과.
