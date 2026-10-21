# 근거있어 프로젝트 이름 변경 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 소비자 서비스와 프로젝트 표시명을 `근거있어`로 바꾸고, 로컬 Git 저장소
폴더를 `geungeo-isseo`로 옮기되 `근거영수증` 결과물과 `ClaimLedger` 내부 엔진 계약,
linked worktree, Git 이력을 보존한다.

**Architecture:** 브랜드 이름은 사용자용 서비스, 출력 결과물, 내부 엔진, 저장소 슬러그의
네 층으로 분리한다. 콘텐츠 변경은 기존 `phase-0-c003-data-gate` worktree와 기본
`main` checkout에 각각 커밋하고, Obsidian 위키는 자체 저장소에서 별도 커밋한다. 모든
콘텐츠 커밋 뒤 상위 프로젝트 폴더를 같은 볼륨 안에서 이동하고 Git의 worktree
관리파일을 `git worktree repair`로 복구한다.

**Tech Stack:** Markdown, Python 3.12 packaging metadata, Git linked worktrees, PowerShell,
Obsidian Markdown vault

## Global Constraints

- 소비자 서비스·프로젝트 표시명은 정확히 `근거있어`다.
- 질문형 브랜드 문장은 `이 광고, 근거 있어?`다.
- 결과물 이름 `근거영수증`은 유지하며 서비스 전체 이름으로 사용하지 않는다.
- 내부 엔진명 `ClaimLedger`, import 패키지 `claimledger`, `src/claimledger`는 유지한다.
- 로컬 폴더와 향후 원격 저장소 슬러그는 정확히 `geungeo-isseo`다.
- 새 프로젝트 루트는
  `%USERPROFILE%\Desktop\DONGA AI LAB\DONGA KDT 3RD PROJECT\geungeo-isseo`다.
- 원격 저장소가 없으므로 remote 생성, push, PR, feature-to-main merge를 수행하지 않는다.
- 과거 로그 문장은 덮어쓰지 않고 2026-08-28 이름 변경 기록을 새로 추가한다.
- 비밀정보, ignored 라이브 export, 사람 검토 pack의 내용을 읽거나 커밋하지 않는다.
- 폴더 이동 전 old/new 절대경로를 확인하고 새 경로가 존재하면 이동하지 않는다.

---

### Task 1: 활성 개발 worktree의 브랜드·프로젝트 메타데이터 변경

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `pyproject.toml`
- Modify: `src/claimledger/__init__.py`
- Modify: `docs/PROJECT_BRIEF.md`
- Modify: `docs/CODEX_HANDOFF.md`
- Modify: `docs/superpowers/specs/2026-08-23-claimledger-product-mvp-design.md`
- Modify: `docs/superpowers/plans/2026-08-28-c003-human-review-contract-v2.md`

**Interfaces:**
- Consumes: `docs/superpowers/specs/2026-08-28-geungeo-isseo-brand-design.md`
- Produces: 현재 프로젝트 문서의 단일 서비스명 `근거있어`, 새 절대경로, 배포
  프로젝트명 `geungeo-isseo`, 보존된 `claimledger` import 계약

- [ ] **Step 1: 현재 이름과 절대경로의 변경 대상을 다시 나열한다**

Run:

```powershell
rg -n --hidden -g '!.git/**' -g '!.venv/**' -g '!artifacts/**' -g '!*.json' '근거영수증 / ClaimLedger|제품 작업명|_persnal V1|name = "claimledger"' .
```

Expected: README, AGENTS, 현재 브리프·인수인계·v2 계획, `pyproject.toml`만 현재 이름이나
이전 경로를 사용하며, `src/claimledger` import 참조는 변경 대상이 아니다.

- [ ] **Step 2: 현재 사용자용 문서에 브랜드 역할을 명시한다**

Apply these exact rules:

```text
README heading: # 근거있어
README tagline: 건강광고, 말보다 근거부터.
Project brief heading: # 근거있어 프로젝트 브리프
Handoff heading: # Codex 인수인계 — 근거있어
Current product rule: 서비스명 근거있어 / 결과물 근거영수증 / 엔진 ClaimLedger
Current worktree root: ...\geungeo-isseo\.worktrees\phase-0-c003-data-gate
Base checkout root: ...\geungeo-isseo
```

Expected: `근거영수증`은 주장별 결과물 문맥에만 남고 `ClaimLedger`는 기술 엔진
문맥에만 남는다.

- [ ] **Step 3: 배포 프로젝트명과 내부 엔진 docstring을 분리한다**

Change `pyproject.toml` to:

```toml
[project]
name = "geungeo-isseo"
```

Change `src/claimledger/__init__.py` to:

```python
"""ClaimLedger evidence engine for the Geungeo Isseo service."""
```

Expected: 패키지 디렉터리와 imports는 `claimledger` 그대로다.

- [ ] **Step 4: 이름 경계와 경로를 정적 검사한다**

Run:

```powershell
rg -n --hidden -g '!.git/**' -g '!.venv/**' -g '!artifacts/**' -g '!*.json' '_persnal V1|근거영수증 / ClaimLedger|제품 작업명은 \*\*근거영수증' .
rg -n 'name = "geungeo-isseo"|# 근거있어|서비스명.*근거있어|ClaimLedger.*엔진' README.md AGENTS.md pyproject.toml docs src/claimledger/__init__.py
```

Expected: 첫 명령은 현재 경로·현재 제품명으로 쓰인 일치 항목이 없고, 두 번째 명령은
새 이름 경계를 보여준다. 역사 문맥의 `ClaimLedger`와 `근거영수증`은 허용한다.

- [ ] **Step 5: 전체 Python 검증을 실행한다**

Run:

```powershell
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
```

Expected: `280 passed`, Ruff `All checks passed!`, `git diff --check` exit `0`.

- [ ] **Step 6: 활성 개발 브랜치 변경을 커밋한다**

Run:

```powershell
git add README.md AGENTS.md pyproject.toml src/claimledger/__init__.py docs
git commit -m "docs: rebrand service as geungeo isseo"
```

Expected: `phase-0-c003-data-gate`에 이름 변경 커밋이 생기고 working tree가 깨끗하다.

---

### Task 2: 기본 main checkout의 현재 프로젝트 문서 동기화

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/PROJECT_BRIEF.md`
- Modify: `docs/CODEX_HANDOFF.md`

**Interfaces:**
- Consumes: Task 1의 브랜드 문구와 새 절대경로
- Produces: feature-to-main merge 없이도 기본 checkout을 열었을 때 보이는 새 프로젝트명

- [ ] **Step 1: main checkout이 깨끗하고 `main`인지 확인한다**

Run:

```powershell
git status --short --branch
git branch --show-current
```

Expected: `## main`, branch `main`, 변경 없음.

- [ ] **Step 2: main의 현재 문서만 같은 이름 체계로 갱신한다**

Apply these exact rules:

```text
Project/service: 근거있어
Signature output: 근거영수증
Internal engine: ClaimLedger
Repository path: %USERPROFILE%\Desktop\DONGA AI LAB\DONGA KDT 3RD PROJECT\geungeo-isseo
```

Expected: main에 존재하지 않는 Phase 1 코드나 측정 결과는 추가하지 않는다.

- [ ] **Step 3: 문서 정적 검사를 실행하고 커밋한다**

Run:

```powershell
rg -n '_persnal V1|근거영수증 / ClaimLedger|제품 작업명은 \*\*근거영수증' README.md AGENTS.md docs
git diff --check
git add README.md AGENTS.md docs/PROJECT_BRIEF.md docs/CODEX_HANDOFF.md
git commit -m "docs: rebrand project as geungeo isseo"
```

Expected: `rg`는 현재 이름·경로 불일치가 없어서 exit `1`, `git diff --check`는 exit `0`,
main에 문서 전용 커밋이 생긴다.

---

### Task 3: Obsidian 위키 정본과 링크 이름 변경

**Files:**
- Rename: `AI-Sessions/wiki/projects/근거영수증-claimledger.md` →
  `AI-Sessions/wiki/projects/근거있어.md`
- Rename: `AI-Sessions/conversations/2026-08-22-근거영수증-코덱스-핸드오프.md` →
  `AI-Sessions/conversations/2026-08-22-근거있어-코덱스-핸드오프.md`
- Modify: `AI-Sessions/wiki/projects/근거있어.md`
- Modify: `AI-Sessions/conversations/2026-08-22-근거있어-코덱스-핸드오프.md`
- Modify: `AI-Sessions/conversations/2026-08-22-3차-프로젝트-핸드오프.md`
- Modify: `AI-Sessions/wiki/decisions/3차-프로젝트-주제-검토-2026-08-22.md`
- Modify: `AI-Sessions/wiki/learning/3차-프로젝트-계획.md`
- Modify: `AI-Sessions/wiki/learning/동아ai랩-3기.md`
- Modify: `AI-Sessions/wiki/projects/조항대조-clauseledger.md`
- Modify: `index.md`
- Modify: `.obsidian/workspace.json`
- Modify: `log.md`

**Interfaces:**
- Consumes: 새 프로젝트명, 새 저장소 경로, Task 1의 현재 상태
- Produces: Obsidian에서 열리는 `근거있어` 정본과 인수인계, 기존 문서에서 새 파일로
  연결되는 유효한 wikilink

- [ ] **Step 1: 두 원본 파일이 tracked이고 두 목적지가 비어 있는지 확인한다**

Run:

```powershell
git ls-files -- 'AI-Sessions/wiki/projects/근거영수증-claimledger.md' 'AI-Sessions/conversations/2026-08-22-근거영수증-코덱스-핸드오프.md'
Test-Path -LiteralPath 'AI-Sessions/wiki/projects/근거있어.md'
Test-Path -LiteralPath 'AI-Sessions/conversations/2026-08-22-근거있어-코덱스-핸드오프.md'
```

Expected: tracked 원본 두 개가 출력되고 목적지 두 개는 모두 `False`.

- [ ] **Step 2: Git이 추적하도록 두 파일을 이름 변경한다**

Run:

```powershell
git mv -- 'AI-Sessions/wiki/projects/근거영수증-claimledger.md' 'AI-Sessions/wiki/projects/근거있어.md'
git mv -- 'AI-Sessions/conversations/2026-08-22-근거영수증-코덱스-핸드오프.md' 'AI-Sessions/conversations/2026-08-22-근거있어-코덱스-핸드오프.md'
```

Expected: `git status --short`가 두 rename을 표시한다.

- [ ] **Step 3: 현재 위키 표기·경로·링크를 새 이름으로 갱신한다**

Apply these exact rules:

```text
Current project heading: # 근거있어
Current product name: 근거있어
Signature output: 근거영수증
Engine: ClaimLedger
Project link: [[.../projects/근거있어|근거있어]]
Handoff link: [[.../2026-08-22-근거있어-코덱스-핸드오프|근거있어 코덱스 인수인계]]
Repository root: ...\geungeo-isseo
```

Append exactly one new `2026-08-28 | save |` line to `log.md` describing the rename. Do not
rewrite older log entries because they record the name and path used at those times.

- [ ] **Step 4: Obsidian 링크와 현재 경로를 검사한다**

Run:

```powershell
rg -n '근거영수증-claimledger|2026-08-22-근거영수증-코덱스-핸드오프|_persnal V1' index.md .obsidian AI-Sessions
Test-Path -LiteralPath 'AI-Sessions/wiki/projects/근거있어.md'
Test-Path -LiteralPath 'AI-Sessions/conversations/2026-08-22-근거있어-코덱스-핸드오프.md'
git diff --check
```

Expected: 첫 명령은 역사적 일반 텍스트를 제외한 현재 링크·경로에서 일치가 없고, 두
파일 존재 검사는 `True`, `git diff --check`는 exit `0`.

- [ ] **Step 5: 위키 변경을 별도 커밋한다**

Run:

```powershell
git add -- .obsidian/workspace.json AI-Sessions index.md log.md
git commit -m "save: rename project to geungeo isseo"
```

Expected: 위키 `master`에 rename과 링크 갱신 커밋이 생기고 working tree가 깨끗하다.

---

### Task 4: 로컬 저장소 폴더 이동과 linked worktree 복구

**Files:**
- Move directory: `%USERPROFILE%\Desktop\DONGA AI LAB\DONGA KDT 3RD PROJECT\_persnal V1`
  → `%USERPROFILE%\Desktop\DONGA AI LAB\DONGA KDT 3RD PROJECT\geungeo-isseo`
- Repair: `geungeo-isseo/.git/worktrees/phase-0-c003-data-gate/*`
- Repair: `geungeo-isseo/.worktrees/phase-0-c003-data-gate/.git`

**Interfaces:**
- Consumes: clean main, clean feature worktree, clean wiki and 새 경로를 가리키는 문서
- Produces: 새 루트에서 정상 동작하는 main checkout과 같은 HEAD·브랜치를 유지한 linked
  worktree

- [ ] **Step 1: 이동 대상을 절대경로로 검증한다**

Run from the parent directory:

```powershell
$oldProjectPath = '%USERPROFILE%\Desktop\DONGA AI LAB\DONGA KDT 3RD PROJECT\_persnal V1'
$newProjectPath = '%USERPROFILE%\Desktop\DONGA AI LAB\DONGA KDT 3RD PROJECT\geungeo-isseo'
[System.IO.Path]::GetFullPath($oldProjectPath)
[System.IO.Path]::GetFullPath($newProjectPath)
Test-Path -LiteralPath $oldProjectPath
Test-Path -LiteralPath $newProjectPath
```

Expected: 두 resolved 경로가 같은 지정 부모 아래 있고 old `True`, new `False`.

- [ ] **Step 2: 두 checkout과 위키의 clean 상태를 다시 확인한다**

Run:

```powershell
git -C "$oldProjectPath" status --short --branch
git -C "$oldProjectPath\.worktrees\phase-0-c003-data-gate" status --short --branch
git -C '%USERPROFILE%\Desktop\AI-Agent-Wiki' status --short --branch
```

Expected: main과 feature worktree, wiki 모두 변경 없음.

- [ ] **Step 3: 저장소 루트 전체를 같은 부모 안에서 이동한다**

Run:

```powershell
Move-Item -LiteralPath $oldProjectPath -Destination $newProjectPath
```

Expected: old `False`, new `True`. 이동 실패 시 반복 이동하지 말고 실제 경로를 다시
확인한다.

- [ ] **Step 4: linked worktree 관리 경로를 복구한다**

Run:

```powershell
git -C "$newProjectPath" worktree repair
git -C "$newProjectPath" worktree repair "$newProjectPath\.worktrees\phase-0-c003-data-gate"
git -C "$newProjectPath" worktree list --porcelain
```

Expected: main 경로와 linked worktree 경로가 모두 `geungeo-isseo` 아래에 표시되고,
feature branch는 `phase-0-c003-data-gate`를 유지한다.

- [ ] **Step 5: 새 경로에서 전체 검증을 다시 실행한다**

Run from `geungeo-isseo/.worktrees/phase-0-c003-data-gate`:

```powershell
.venv\Scripts\python.exe -m pytest --cov=claimledger --cov-report=term-missing -q
.venv\Scripts\ruff.exe check src tests scripts
git diff --check
git status --short --branch
git -C '..\..' status --short --branch
git -C '..\..' remote -v
```

Expected: `280 passed`, Ruff `All checks passed!`, diff check exit `0`, feature와 main이
깨끗하고 remote 출력은 비어 있다.

- [ ] **Step 6: 경로·브랜드·위키 최종 감사를 실행한다**

Run:

```powershell
Test-Path -LiteralPath '%USERPROFILE%\Desktop\DONGA AI LAB\DONGA KDT 3RD PROJECT\_persnal V1'
Test-Path -LiteralPath '%USERPROFILE%\Desktop\DONGA AI LAB\DONGA KDT 3RD PROJECT\geungeo-isseo'
rg -n '_persnal V1|근거영수증 / ClaimLedger|근거영수증-claimledger|2026-08-22-근거영수증-코덱스-핸드오프' '%USERPROFILE%\Desktop\DONGA AI LAB\DONGA KDT 3RD PROJECT\geungeo-isseo' '%USERPROFILE%\Desktop\AI-Agent-Wiki'
```

Expected: old path `False`, new path `True`. 마지막 `rg` 결과는 이전 이름과 경로를
설명하는 승인된 역사 기록뿐이며 현재 README, handoff, AGENTS, index, workspace 포인터에는
일치가 없다.

## Execution Record — 2026-08-29

- 브랜드 설계: `ecf765c`
- 이름 변경 계획: `ebea0d8`
- feature 문서·메타데이터: `7be7b33`
- main 현재 문서: `3892928`
- 위키 파일명·링크: `9d57f19`
- 실제 루트: `%USERPROFILE%\Desktop\DONGA AI LAB\DONGA KDT 3RD PROJECT\geungeo-isseo`
- 이전 `_persnal V1` 경로: 존재하지 않음
- worktree 복구: main `3892928`, `phase-0-c003-data-gate` `7be7b33`; 두 경로 모두
  `geungeo-isseo` 아래에서 clean
- remote: 구성되지 않음
- Git 객체 검사: `git fsck --full` exit `0`; dangling blob만 보고됐고 손상 객체는 없음
- 첫 post-move 테스트: editable `.pth`의 이전 절대경로 때문에 수집 오류 14건
- 원인 복구: `.venv`의 `claimledger 0.1.0` editable 설치를 제거하고
  `geungeo-isseo 0.1.0`을 `--no-deps --no-build-isolation --editable .`로 재설치
- 복구 검증: site-packages 이전 경로 `0`, `claimledger`는 새 `src/claimledger`에서 import,
  전체 `280 passed`, `1,260` statements / `40` missed (`96.83%`), Ruff 통과
