# 보안 점검과 재현 실행 — 2026-10-07

일정표의 "전체 재현 실행, 보안 점검" 항목의 결과 기록이다. 사용자 요청은 "작업 이어서 해줘"였고,
직전 기록의 추천(현재 엔진으로 MVP 고정 후 Docker·보안 점검)을 따랐다.

## 한 줄 결론

- **재현 실행**: 한 명령(`scripts/reproduce.py`)으로 스냅샷 해시 검증, 단위 테스트 1211개, 평가 게이트 8개가
  로컬에서 모두 통과했다(종료코드 0).
- **보안 점검**: 커밋 이력 130개에서 비밀정보는 나오지 않았다. API에서 실제로 확인된 문제 4건은 고쳤다.
- **Docker**: Dockerfile과 compose 파일은 작성했고 문법 검증까지 통과했다. 그러나 이 PC의 Docker Desktop이 시작되지 않아
  **이미지 빌드와 컨테이너 실행은 검증하지 못했다.** 아래 "Docker 상태"에 경위를 적었다.

## 재현 실행

```powershell
.venv\Scripts\python.exe scripts\reproduce.py
$LASTEXITCODE
```

`scripts/reproduce.py`는 다음 순서로 실행한다. 종료코드는 모든 게이트 통과 0, 게이트 실패 1, 입력 오류 3이다.

1. C003 스냅샷의 SHA-256을 평가세트 manifest의 값(`CF0D58B4…3B7E`)과 비교한다. 다르거나 없으면 아무 단계도 실행하지 않고 멈춘다.
   스냅샷은 git에 넣지 않는 원본 데이터라서, 같은 파일인지 해시로 확인한다.
2. 단위 테스트 전체(`pytest`).
3. 귀속 평가세트 v1~v3의 라벨 6벌을 `--require-zero-false-attribution`으로 채점한다.
4. 독립 평가세트 `claim-eval-v2`와 개발용 `claim-eval-v1`을 `--require-zero-false-clearance`로 채점한다.
5. 개발 사례(`core-mvp-dev-v1`)는 게이트 없이 채점만 한다. 라벨 5건이 헤더 없는 나열 귀속 이전의 정책을 적은 것이기 때문이다
   ([개발 평가 기록](CORE_MVP_DEV_EVAL_2026-09-27.md)의 10/2 재실행 절).

2026-10-07 로컬 실행 결과: 단위 테스트 1211 passed, 게이트 8개 모두 종료코드 0, 요약은 `build/reproduce/reproduce-summary.json`(추적 안 함).
패키지 버전은 `constraints.txt`에 로컬 환경(Python 3.12.14) 그대로 고정했다. 새 의존성은 추가하지 않았다.

## Docker 상태 — 작성했지만 빌드·실행은 미검증

- **작성한 파일.**
  - `Dockerfile`: `python:3.12.14-slim` 기반이다. `constraints.txt`로 같은 버전을 설치하고 일반 사용자(uid 10001)로 실행한다.
  - `.dockerignore`: `.git`, `.venv`, `.env*`, `build`, 그리고 C003 스냅샷을 이미지에서 뺀다.
  - `docker-compose.yml`: 서비스 두 개다.
    - `verify`: 네트워크 없이(`network_mode: none`) `scripts/reproduce.py`를 실행한다. 스냅샷은 읽기 전용으로 연결한다.
    - `web`: 웹 화면을 호스트의 `127.0.0.1:8000`에만 공개한다. 읽기 전용 파일시스템, 권한 제거(`cap_drop: ALL`)를 적용했다.
- **검증된 것.** `docker compose config --quiet`가 종료코드 0이다(엔진 없이 가능한 문법 검증).
- **검증되지 않은 것.** 이미지 빌드, 컨테이너 안 테스트 통과, `python:3.12.14-slim` 태그의 존재, 리눅스에서의 테스트 동작.
  Windows에서만 통과를 확인했으므로 경로·줄바꿈 차이로 리눅스에서 실패하는 테스트가 있을 수 있다.
- **이 PC의 Docker Desktop 문제(2026-10-07 16:30~16:42 KST).**
  - Docker CLI 29.7.2와 Docker Desktop 4.87.0이 설치돼 있으나 엔진이 꺼져 있었다.
  - 개발 세션이 Docker Desktop을 두 번 시작했다(16:30:50 실행 파일, 16:36:41 `docker desktop start`). 두 번 모두 백엔드가 같은 오류로 멈췄다.
    `%LOCALAPPDATA%\Docker\run\sailor-ingest.sock`(9/17에 남은 소켓 파일)을 지우지 못한다는 오류다("The file cannot be accessed by the system").
  - 오류 창의 선택지는 "Quit"와 "Reset to factory defaults"였다. 백엔드 로그에 남은 선택 기록은 다음과 같다.
    - 첫 번째 창: 뜬 지 7초 뒤인 16:31:00에 "Quit".
    - 두 번째 창: 뜬 지 정확히 120초 뒤인 16:38:44에 "Reset to factory defaults". 초기화가 실행돼 같은 초에 완료됐다.
    - 개발 세션은 화면을 조작하지 않았다. 누가 또는 무엇이 선택했는지는 로그만으로 확정할 수 없다.
  - 로그상 초기화가 지운 것: Docker Desktop 확장 기능, `~/.docker`의 buildx·cli-plugins·modules·토큰 시드, 쿠버네티스 인증서, 빌드 기록.
    설정 파일(`settings-store.json`)은 16:38:44에 다시 쓰였다. 이미지·컨테이너가 들어 있는 `docker_data.vhdx`(3.54GB)는 삭제 기록이 없고 파일도 9/17 날짜 그대로 남아 있다.
  - 초기화 뒤에도 소켓 파일은 그대로라 Docker는 여전히 시작되지 않는다. 개발 세션은 이후 Docker 설치 상태를 더 건드리지 않았다.
- **2026-10-22 후기 — 재부팅 뒤에도 같은 상태.** 개발 세션은 Docker를 시작하지 않고 파일 상태만 읽었다.
  - `%LOCALAPPDATA%\Docker\run`에 9/17 09:57에 만들어진 소켓 파일 네 개(`dockerEthernetVfkit`, `dockerInference`, `sailor-ingest.sock`,
    `userAnalyticsOtlpHttp.sock`)가 10/22 09:09 재부팅 뒤에도 남아 있다. 모두 재분석 지점(ReparsePoint)이고 `fsutil reparsepoint query`도
    `Error 1920`("The file cannot be accessed by the system")으로 실패한다. Docker Desktop은 4.87.0 그대로다.
  - Docker 포럼에 같은 증상(Docker Desktop 4.88.1, 2026-08-27, `sailor-ingest.sock`·`dockerInference`)이 보고돼 있다. 재시작, AI 기능 끄기,
    WSL 종료, 업데이트, 폴더 이름 변경으로 풀리지 않았고 확인된 해결책은 없다.
  - Claude Code 이슈 anthropics/claude-code#76383(2026-07-10, 'not planned'로 닫힘)은 Claude Code 프로세스 아래에서 만든 AF_UNIX 소켓 파일이
    이렇게 지워지지 않고 재부팅 뒤에도 남는다고 보고한다. 9/17에 Docker를 어떤 경로로 시작했는지는 확인하지 못해 원인으로 단정하지 않는다.
  - 사용자가 해 볼 순서(이 PC의 Docker 상태를 바꿀 수 있으므로 사용자가 직접 한다).
    1. Claude Code 밖에서, 시작 메뉴로 Docker Desktop을 연다. 오류 창이 뜨면 바로 "Quit"을 누른다. "Reset to factory defaults"는 누르지 않는다
       (10/7에는 창이 뜬 지 120초 뒤 초기화가 선택됐다).
    2. 그래도 같은 오류면 Docker 지원이나 GitHub 이슈에 진단 정보를 남긴다. 파일 삭제나 디스크 검사는 확인된 해결책이 아니다.
  - WSL Ubuntu에서 리눅스 테스트를 대신 돌리는 방법도 지금은 막혀 있다. Ubuntu 26.04에는 Python 3.14.4만 있고 pip·`ensurepip`가 없다.
- **Docker가 복구되면 실행할 명령.**

  ```powershell
  docker compose build
  docker compose run --rm verify
  $LASTEXITCODE
  docker compose up web
  ```

## 보안 점검

| 항목 | 방법 | 결과 |
|---|---|---|
| 커밋 이력의 비밀정보 | 전체 ref 130개 커밋의 추가 줄을 키·토큰·개인키·API 경로 패턴으로 검색 | 실제 값 없음. 걸린 줄은 테스트의 가짜 표식(`SHOULD_NOT_ECHO_12345`, `live-secret-value-123456`) |
| `.env` 커밋 여부 | `git log --all --diff-filter=A -- .env*` | 값이 빈 `.env.example`만 커밋됨 |
| API 키 사용 | `audit_c003.py`, `fetch_i0040.py` 확인 | 환경변수 또는 `--env-file`에서 읽고 출력하지 않음 |
| 화면 삽입(XSS) | `web/index.html`의 DOM 삽입 방식 검색 | `innerHTML` 없음. 모두 `textContent`, 외부 스크립트 없음 |
| 입력 검증 | `api.py` 요청 모델 확인, 경계값 요청 | 광고문 5,000자·검색어 100자·형식 패턴 제한 있음. 기호만 넣은 검색도 500 없이 빈 결과 |
| 다른 출처의 JSON 요청 | `text/plain` 본문으로 POST | 422로 거부(FastAPI가 JSON 타입만 파싱) |
| 오류 노출 | 오류 처리기 확인 | 정해진 오류 본문만 반환, 스택 추적 없음 |
| 기본 바인딩 | `serve_api.py` | 기본 `127.0.0.1` |

### 고친 문제 4건 (`tests/test_api_hardening.py`)

1. **분석 저장소가 무제한으로 커졌다.** 분석을 만들 때마다 메모리에 쌓여, 반복 요청으로 메모리를 소진시킬 수 있었다.
   최대 1,000건(`MAX_ANALYSES`)을 넘으면 가장 오래된 분석부터 버린다.
2. **요청 본문 크기 상한이 없었다.** 64KiB(`MAX_BODY_BYTES`)를 넘는 본문은 파싱 전에 413으로, 길이를 알 수 없는 본문은 411로 거부한다.
   확정 요청의 `claim_ids`(최대 2,000개, 각 32자)와 `report_no`(64자)에도 상한을 두었다.
3. **Host 검사가 없었다.** 인증이 없는 API라서 DNS 리바인딩으로 다른 사이트가 로컬 API를 호출할 여지가 있었다.
   `serve_api.py`는 이제 `127.0.0.1`·`localhost` Host만 받고, 그 밖의 이름은 `--allowed-host`로 명시해야 한다.
4. **브라우저 보안 헤더가 없었다.** 모든 응답에 `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`를 붙인다.
   화면(`/`)에는 Content-Security-Policy를 붙였다. 페이지가 인라인 스크립트 한 파일이라 `script-src 'unsafe-inline'`은 남아 있다.

브라우저 확인(2026-10-07, 실제 C003 45,907건 적재): 새 헤더 아래에서 주장 찾기 → 제품 확정(`200400150831010`) → 영수증 흐름이
끝까지 동작했고 콘솔 오류는 없었다. 창이 화면에 그려지지 않아 버튼은 스크립트로 눌렀고 스크린샷은 남기지 못했다.
세 문장의 판정은 "황반색소밀도를 유지하는 데 도움" `확인됨`, "노안 걱정을 줄여 줍니다" `근거 불일치`, "하루 한 번 루테인은…" `검증 불가`였다.

### 하지 않은 것과 남은 위험

- **의존성 취약점 점검을 하지 않았다.** `pip-audit` 같은 도구가 설치돼 있지 않고, 새 패키지 설치는 사용자 확인이 필요하다.
- **인증·접근 제어가 없다.** 로컬 단일 사용자용이다. 다른 사람이 접속하는 서버로 올리려면 인증, 요청 빈도 제한, HTTPS가 먼저 필요하다.
- 제품 검색은 요청마다 45,907건을 훑는다. 로컬에서는 문제없지만 공개 서버라면 부하 공격 지점이 된다.
- `/docs`(API 문서 화면)는 CDN 스크립트를 쓰므로 CSP를 적용하지 않았다.
- 이 점검은 개발 세션의 자체 점검이며, 독립적인 보안 감사가 아니다.
