---
name: obsidian-init
description: "Initialize or refresh the user's Obsidian vault schema: scan the vault and write AGENTS.md (with CLAUDE.md linked to it), index.md, and the operation log. Use right after installation, when the user asks to initialize/set up/rescan the vault, or when another obsidian-* skill reports that AGENTS.md is missing. Korean triggers: 볼트 초기화, 옵시디언 초기화, 볼트 설정, 인덱스 다시 만들어."
---

# obsidian-init

볼트를 스캔해서 스키마(`AGENTS.md`), 내용 카탈로그(`index.md`), 작업 로그(`log.md` + `Logs/`)를 만들거나 갱신합니다. Karpathy LLM Wiki의 **Schema** 계층입니다. Claude Code는 `CLAUDE.md`, Codex는 `AGENTS.md`를 읽으므로 `AGENTS.md`를 정본으로 두고 `CLAUDE.md`를 그 파일에 연결합니다.

## 0. 시작 절차

1. 설정을 읽습니다:
   ```bash
   python3 "{{OSB_ROOT}}/scripts/osb_env.py"
   ```
   종료 코드가 0이 아니면 오류를 전하고 멈춥니다. 현재 디렉터리를 볼트로 간주하지 않습니다.
2. `<skill_root>/references/agents-md-template.md`, `<skill_root>/references/folder-map.md`, `<skill_root>/references/ai-first-rules.md`를 읽습니다.
3. `<vault_path>/.osb/profile.json`이 있으면 읽습니다. 설치 때 입력한 소유자 이름, 회사, 직책, 언어가 들어 있습니다.

## 1. 볼트 스캔

1. `<vault_path>` 아래 `.md` 파일 목록을 만듭니다(`.obsidian/`, `.git/`, `.trash/` 제외).
2. `folder-map.md`의 기본 폴더 중 없는 것을 만듭니다. 이미 다른 이름으로 같은 역할을 하는 폴더가 있으면(예: `People/`) 새로 만들지 말고 사용자에게 어느 쪽을 쓸지 묻고, 답을 `AGENTS.md`의 폴더 표에 적습니다.
3. 폴더마다 노트 한두 개를 읽어 frontmatter 형식과 이름 규칙을 파악합니다. 노트가 많으면 호스트가 지원할 때 하위 에이전트로 나눠 읽어도 됩니다.
4. 이미 쓰고 있는 프로젝트(`type: project`)와 최근 30일에 바뀐 노트를 파악해 "지금 중요한 것"의 재료로 씁니다.

## 2. AGENTS.md 작성

1. 템플릿의 `{{...}}`을 실제 값으로 채웁니다. 소유자/회사/직책/언어는 `profile.json`에서, 볼트 경로는 설정에서, 날짜는 오늘. 모르는 값은 `TBD`.
2. `language`가 `ko`면 템플릿 그대로 한국어로, `en`이면 제목과 본문을 영어로 옮겨 씁니다.
3. `<vault_path>/AGENTS.md`가 이미 있으면 새로 쓴 내용과의 차이를 보여 주고 승인받은 뒤에만 덮어씁니다. 사용자가 직접 추가한 섹션은 남깁니다. 비대화형 실행처럼 물을 수 없으면 덮어쓰지 않고 차이만 보고합니다.
4. `CLAUDE.md` 연결:
   - `<vault_path>/CLAUDE.md`가 없으면 심볼릭 링크를 만듭니다: `ln -s AGENTS.md "<vault_path>/CLAUDE.md"`.
   - 이미 있고 `AGENTS.md`를 가리키는 링크면 그대로 둡니다.
   - 일반 파일로 있으면 내용을 보여 주고, `AGENTS.md`로 합칠지 묻습니다. 합친 뒤 링크로 바꿉니다.
   - 링크를 만들 수 없는 환경이면 `CLAUDE.md`에 `@AGENTS.md` 한 줄만 씁니다.
5. 예전 버전의 `_CLAUDE.md`가 있으면 그 내용을 `AGENTS.md`에 반영할지 묻고, 반영 후 `_CLAUDE.md`는 지우지 말고 `type: redirect`로 바꿉니다.

## 3. index.md 작성

- 볼트 루트에 `index.md`를 새로 생성합니다(항상 현재 상태로 다시 만듭니다).
- 폴더별 섹션(`## 엔티티`, `## 개념`, `## 소스`, `## 프로젝트`, `## 결정`, `## 종합`, `## 세션`, `## 리뷰`, 그 외 폴더), 각 줄은 `- [[노트 제목]] - 한 줄 설명`.
- 설명은 frontmatter의 `description`/`summary`, 없으면 `## For future agent` 첫 문장, 없으면 첫 단락에서 가져옵니다. `raw/`는 개수만 적고 나열하지 않습니다.
- 에이전트는 질문에 답할 때 이 파일을 먼저 읽습니다. 수백 페이지 규모까지는 검색 엔진 없이 이것으로 충분합니다.

## 4. 작업 로그

- `log.md`가 없으면 안내 파일로 만듭니다: 로그는 `Logs/YYYY-MM-DD.md`에 하루 한 파일로 쌓이고, 각 줄 형식은 `**HH:MM** - <작업> | <요약>`이며, `grep -h "^\*\*" Logs/*.md | tail -20`으로 최근 기록을 볼 수 있다는 내용.
- 예전 형식으로 `log.md` 안에 `## [YYYY-MM-DD]` 기록이 쌓여 있으면 지우지 말고 그대로 둡니다.
- 오늘 `Logs/YYYY-MM-DD.md`에 `**HH:MM** - init | AGENTS.md, index.md 생성 (노트 N개)`을 추가합니다.

## 5. 검증과 보고

1. `CLAUDE.md`가 `AGENTS.md`를 가리키는지 확인합니다: `ls -l "<vault_path>/CLAUDE.md"`.
2. 모든 쓰기를 마친 뒤 마지막으로, 이번에 만들거나 고친 노트를 검증합니다(`AGENTS.md`, `index.md`, `log.md`, `Logs/`는 검사 대상에서 자동 제외됩니다):
   ```bash
   "<python>" "<skill_root>/scripts/check_notes.py" --path "<vault_path>" <쓴 파일들>
   ```
   실패가 있으면 고치고 다시 검증합니다.
3. 만든 파일과 폴더, 노트 수, 사용자에게 물어서 정한 것을 보고합니다.
4. 다음 사용법을 안내합니다: 어느 프로젝트에서든 "이거 볼트에 저장해"(obsidian-save), "볼트에서 찾아줘"(obsidian-find), "볼트 점검해"(obsidian-health), "이번 주 리뷰"(obsidian-review).

<!-- author-credit -->

---

Based on [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain) by Eugeniu Ghelbur. MIT license.
