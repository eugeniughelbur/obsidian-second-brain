# obsidian-second-brain (Claude Code + Codex)

Obsidian 볼트를 [Karpathy의 LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) 방식으로 운영하는 에이전트 스킬 5개. Claude Code와 Codex에서 똑같이 동작하고, 한 번 설치하면 어느 프로젝트 세션에서든 볼트를 갱신할 수 있습니다.

원본 [eugeniughelbur/obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain)(49개 명령, 8개 플랫폼)을 LLM Wiki의 핵심만 남기도록 줄인 포크입니다. 외부 API(Grok, Gemini, Perplexity 등)는 쓰지 않습니다.

## 아이디어

RAG는 질문할 때마다 원문에서 지식을 다시 찾습니다. LLM Wiki는 에이전트가 소스를 읽을 때마다 위키 페이지를 **갱신**해서, 지식이 한 번 정리되면 계속 최신으로 유지되고 쌓입니다. 사람은 소스를 고르고 질문하며, 요약, 교차참조, 모순 표시 같은 정리 작업은 에이전트가 맡습니다.

| 계층 | 위치 | 누가 쓰나 |
|---|---|---|
| 원본 | `raw/` | 저장할 때 한 번 쓰고 고치지 않음 |
| 위키 | `wiki/` | 에이전트가 유지 |
| 스키마 | `AGENTS.md` (`CLAUDE.md`는 링크) | 사람과 에이전트가 함께 |

`index.md`는 내용 카탈로그(질문에 답할 때 먼저 읽음), `Logs/YYYY-MM-DD.md`는 작업 기록입니다.

## 스킬

| 스킬 | 원안의 연산 | 하는 일 |
|---|---|---|
| `obsidian-init` | Schema | 볼트를 스캔해 `AGENTS.md`, `index.md`, 로그를 만들고 `CLAUDE.md`를 `AGENTS.md`에 연결 |
| `obsidian-save` | Ingest + 답변 저장 | 대화 결과, URL, 파일, 붙여넣은 텍스트, YouTube(자막 추출 후 요약)를 한 번에 여러 개 넣어도 정리. 기존 페이지는 수정안을 보여 주고 승인 후 갱신 |
| `obsidian-find` | Query | `index.md`와 한국어 대응 검색으로 찾고, 근거 노트를 인용해 답변 |
| `obsidian-health` | Lint | 모순, 중복, 깨진 링크, 낡은 주장을 찾아 한 건씩 확인받으며 수정, 병합, 충돌 기록 |
| `obsidian-review` | - | 저장된 노트만으로 일간/주간/월간 리뷰 생성 및 갱신. 배운 점, 놓치고 있는 것, 특히 중요한 것 포함 |

스킬은 사용자가 이름으로 부를 때도, 대화 맥락상 필요할 때도 실행됩니다. Claude Code는 `/obsidian-save`, Codex는 `$obsidian-save`로 직접 부를 수 있고, "이거 볼트에 저장해", "볼트 점검해"처럼 말해도 됩니다.

## 설치

macOS 또는 Linux, `git`, Python 3.10 이상, `jq`가 필요합니다(`jq`가 없으면 설치 중에 brew로 설치할지 묻습니다).

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/iies/obsidian-second-brain/main/scripts/quick-install.sh)
```

설치 스크립트가 묻는 것:
1. 설치할 도구: Claude Code / Codex / 둘 다
2. 볼트 폴더 이름(`~/Documents/` 아래, 기본 `SecondBrain`). 이미 있는 폴더도 됩니다. 기존 파일은 건드리지 않습니다.
3. 이름, 회사명, 직책
4. 노트 작성 언어(`ko` / `en`)

설치 스크립트가 하는 일:
- 툴킷을 `~/.obsidian-second-brain`에 받고 Python 환경(`.venv`)을 만듭니다.
- 스킬 5개를 `~/.claude/skills/`와 `~/.codex/skills/`에 설치합니다(user scope).
- 볼트 폴더 구조, 소유자/회사 노트, `.osb/profile.json`을 만듭니다.
- 볼트를 등록합니다:
  - `~/.config/obsidian-second-brain/.env`: 볼트 경로와 언어
  - Claude Code `~/.claude/settings.json`: `permissions.additionalDirectories`에 볼트 추가, 검증 훅
  - Codex `~/.codex/config.toml`: `[sandbox_workspace_write]`의 `writable_roots`에 볼트 추가, `network_access = true`(URL과 YouTube 수집용). `~/.codex/hooks.json`에 검증 훅
  - 바꾸는 설정 파일은 먼저 `<파일>.osb-bak`으로 백업합니다. 다른 도구의 훅과 설정은 그대로 둡니다.
- 이전 버전(`~/.claude/skills/obsidian-second-brain`)이 있으면 백업 폴더로 옮길지 묻습니다.

설치가 끝나면:

```bash
cd ~/Documents/SecondBrain
claude      # 그리고 /obsidian-init
# 또는
codex       # 그리고 $obsidian-init
```

Codex에서는 처음 실행한 뒤 `/hooks`를 열어 `validate-ai-first` 훅을 신뢰(trust)하세요. 신뢰하기 전까지 Codex는 이 훅을 건너뜁니다. 스킬 안의 검증 단계는 그와 별개로 항상 실행됩니다.

`codex exec`, `claude -p` 같은 비대화형 실행에서는 승인을 받을 수 없으므로 새 노트만 쓰고, 기존 노트 수정안은 "승인 대기"로 보고합니다.

다시 실행하면 업데이트됩니다(같은 명령). 비대화형 설치는 `--hosts claude,codex --vault-dir SecondBrain --name ... --company ... --role ... --language ko --yes`.

## 쓰기 검증

모든 노트는 `references/ai-first-rules.md`를 따릅니다: `## For future agent` 서문, `type`/`date`/`tags`/`ai-first: true` frontmatter, `[[위키링크]]`, 외부 주장의 날짜와 출처. 검증은 두 번 일어납니다.
- 훅: Claude의 `Write|Edit`, Codex의 `apply_patch`로 볼트 안의 노트를 쓸 때마다 `hooks/validate-ai-first.sh`가 검사하고 문제를 에이전트에게 알립니다.
- 스킬의 마지막 단계: 쓴 노트를 `scripts/check_notes.py`로 다시 검사합니다. 셸 명령으로 쓴 파일처럼 훅이 보지 못하는 경우도 여기서 잡습니다.

## 한국어

- 한국어 노트는 그대로 검증을 통과합니다. 한글이 있는 줄은 문장부호 검사에서 예외입니다.
- 검색은 한글을 2글자 단위로 비교해서 조사가 붙어도 찾고(`프로젝트를` 검색 시 `프로젝트` 노트), 맥의 분해형 한글(NFD)도 정규화합니다.
- YouTube 자막은 설정 언어(ko), en 순으로 받고, 둘 다 없으면 있는 자막을 번역합니다.
- 고유명사의 다른 표기는 `aliases:`에 넣습니다.

## 저장소 구조

```
skills/<name>/SKILL.md   스킬 5개 (Claude Code / Codex 공용 형식)
references/              노트 규칙, 폴더 구조, AGENTS.md 템플릿
scripts/                 osb_env (설정), bootstrap_vault, host_config, vault_search,
                         vault_health, link_graph, freshness_lint, verify_quotes,
                         merge_notes, check_notes, youtube_transcript, quick-install.sh
hooks/validate-ai-first.sh
tests/
```

## 개발

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest ruff
.venv/bin/pytest -q && .venv/bin/ruff check .
bash scripts/quick-install.sh --local     # 이 체크아웃으로 설치
```

## 라이선스

MIT. 원작자 Eugeniu Ghelbur([obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain)). 이 포크의 변경도 MIT입니다.
