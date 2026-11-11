#!/usr/bin/env bash
# obsidian-second-brain installer (Claude Code + Codex, macOS / Linux)
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/iies/obsidian-second-brain/main/scripts/quick-install.sh)
#
# One run does everything:
#   1. downloads (or updates) the toolkit to ~/.obsidian-second-brain
#   2. builds its Python environment (.venv)
#   3. installs the 5 skills for Claude Code and/or Codex (user scope)
#   4. creates the vault under ~/Documents/ and records owner, company, role
#   5. registers the vault: Claude settings (additionalDirectories, hook),
#      Codex config.toml (writable_roots, network_access) and hooks.json
# Afterwards: cd into the vault, start claude or codex, run obsidian-init.
#
# Non-interactive use (all optional; anything missing is asked):
#   --hosts claude,codex  --vault-dir SecondBrain  --name NAME  --company CO
#   --role ROLE  --language ko|en  --root DIR  --repo URL  --branch BRANCH
#   --local (use the checkout this script lives in, no git clone)  --yes
set -euo pipefail

REPO_URL="${OSB_REPO_URL:-https://github.com/iies/obsidian-second-brain.git}"
BRANCH="${OSB_BRANCH:-main}"
OSB_ROOT="${OSB_ROOT:-$HOME/.obsidian-second-brain}"
DOCS="$HOME/Documents"
SKILLS=(obsidian-init obsidian-save obsidian-find obsidian-health obsidian-review)

HOSTS="" VAULT_DIR="" NAME="" COMPANY="" ROLE="" LANGUAGE="" LOCAL=0 YES=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --hosts) HOSTS="$2"; shift 2 ;;
    --vault-dir) VAULT_DIR="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --company) COMPANY="$2"; shift 2 ;;
    --role) ROLE="$2"; shift 2 ;;
    --language) LANGUAGE="$2"; shift 2 ;;
    --root) OSB_ROOT="$2"; shift 2 ;;
    --repo) REPO_URL="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --local) LOCAL=1; shift ;;
    --yes|-y) YES=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
ok() { printf '  \033[32mOK\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!!\033[0m %s\n' "$*"; }
die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# Prompts read from the terminal even when the script itself is piped in.
TTY=/dev/tty
[[ -r $TTY ]] || TTY=/dev/stdin
ask() { # ask VAR "prompt" "default"
  local __var="$1" __prompt="$2" __def="${3:-}" __ans
  if [[ -n "$__def" ]]; then printf '%s [%s]: ' "$__prompt" "$__def" >&2; else printf '%s: ' "$__prompt" >&2; fi
  IFS= read -r __ans <"$TTY" || __ans=""
  printf -v "$__var" '%s' "${__ans:-$__def}"
}
ask_required() { # ask until non-empty
  local __var="$1" __prompt="$2" __val=""
  while [[ -z "$__val" ]]; do ask __val "$__prompt" ""; [[ -z "$__val" ]] && warn "필수 입력입니다 (required)."; done
  printf -v "$__var" '%s' "$__val"
}
confirm() { # confirm "question" default(y|n)
  [[ $YES = 1 ]] && return 0
  local def="${2:-y}" ans
  ask ans "$1 (y/n)" "$def"
  [[ "$ans" =~ ^[Yy] ]]
}

bold "obsidian-second-brain 설치 (Claude Code / Codex)"
echo

# ---------------------------------------------------------------- prerequisites
[[ "$(uname -s)" == Darwin || "$(uname -s)" == Linux ]] || die "macOS 또는 Linux만 지원합니다."
command -v git >/dev/null || die "git이 필요합니다."
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
[[ -n "$PY" ]] || die "Python 3.10 이상이 필요합니다 (brew install python)."
if ! command -v jq >/dev/null; then
  warn "jq가 없습니다. 노트 검증(훅과 스킬의 검증 단계)에 필요합니다."
  if command -v brew >/dev/null && confirm "brew로 jq를 설치할까요?" y; then
    brew install jq
  else
    die "jq를 설치한 뒤 다시 실행하세요 (brew install jq / sudo apt install jq)."
  fi
fi
ok "git, $("$PY" --version), jq"

# ---------------------------------------------------------------- hosts
if [[ -z "$HOSTS" ]]; then
  echo
  echo "어느 도구에 설치할까요?"
  echo "  1) Claude Code"
  echo "  2) Codex"
  echo "  3) 둘 다"
  ask choice "선택" "3"
  case "$choice" in 1) HOSTS=claude ;; 2) HOSTS=codex ;; *) HOSTS=claude,codex ;; esac
fi
for h in ${HOSTS//,/ }; do
  case "$h" in claude|codex) ;; *) die "--hosts는 claude, codex 중에서 고르세요: $h" ;; esac
done
[[ ",$HOSTS," == *",claude,"* ]] && ! command -v claude >/dev/null && warn "claude 명령을 찾지 못했습니다. 스킬은 설치하지만 Claude Code를 따로 설치해야 합니다."
[[ ",$HOSTS," == *",codex,"* ]] && ! command -v codex >/dev/null && warn "codex 명령을 찾지 못했습니다. 스킬은 설치하지만 Codex를 따로 설치해야 합니다."

# ---------------------------------------------------------------- vault + profile
echo
if [[ -z "$VAULT_DIR" ]]; then
  ask VAULT_DIR "볼트 폴더 이름 (~/Documents/ 아래)" "SecondBrain"
fi
VAULT_DIR="${VAULT_DIR#"$DOCS"/}"; VAULT_DIR="${VAULT_DIR#\~/Documents/}"; VAULT_DIR="${VAULT_DIR%/}"
[[ -n "$VAULT_DIR" && "$VAULT_DIR" != /* && "$VAULT_DIR" != *..* ]] || die "볼트 폴더는 ~/Documents/ 아래의 상대 경로여야 합니다: $VAULT_DIR"
VAULT="$DOCS/$VAULT_DIR"
if [[ -d "$VAULT" && -n "$(ls -A "$VAULT" 2>/dev/null)" ]]; then
  warn "$VAULT 가 이미 있고 비어 있지 않습니다. 기존 파일은 건드리지 않고 없는 폴더만 추가합니다."
  confirm "이 폴더를 볼트로 사용할까요?" y || die "취소했습니다."
fi
[[ -n "$NAME" ]] || ask_required NAME "이름"
[[ -n "$COMPANY" ]] || ask_required COMPANY "회사명"
[[ -n "$ROLE" ]] || ask_required ROLE "직책"
if [[ -z "$LANGUAGE" ]]; then
  ask LANGUAGE "노트 작성 언어 (ko/en)" "ko"
fi
[[ "$LANGUAGE" == ko || "$LANGUAGE" == en ]] || die "언어는 ko 또는 en 입니다: $LANGUAGE"

echo
bold "설치 내용"
echo "  도구:   $HOSTS"
echo "  볼트:   $VAULT"
echo "  소유자: $NAME / $COMPANY / $ROLE"
echo "  언어:   $LANGUAGE"
echo "  설치 위치: $OSB_ROOT"
confirm "진행할까요?" y || die "취소했습니다."

# ---------------------------------------------------------------- toolkit
echo
bold "1/5 툴킷 받기"
if [[ $LOCAL = 1 ]]; then
  OSB_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  ok "로컬 체크아웃 사용: $OSB_ROOT"
elif [[ -d "$OSB_ROOT/.git" ]]; then
  git -C "$OSB_ROOT" fetch --quiet origin "$BRANCH"
  git -C "$OSB_ROOT" checkout --quiet "$BRANCH"
  git -C "$OSB_ROOT" pull --quiet --ff-only origin "$BRANCH"
  ok "업데이트: $OSB_ROOT"
else
  [[ -e "$OSB_ROOT" ]] && die "$OSB_ROOT 가 이미 있지만 git 저장소가 아닙니다. 옮기거나 지운 뒤 다시 실행하세요."
  git clone --quiet --branch "$BRANCH" "$REPO_URL" "$OSB_ROOT"
  ok "다운로드: $OSB_ROOT"
fi

bold "2/5 Python 환경"
if [[ ! -x "$OSB_ROOT/.venv/bin/python" ]]; then
  "$PY" -m venv "$OSB_ROOT/.venv"
fi
"$OSB_ROOT/.venv/bin/python" -m pip install --quiet --disable-pip-version-check -r "$OSB_ROOT/requirements.txt"
ok "$OSB_ROOT/.venv"

# ---------------------------------------------------------------- legacy cleanup
LEGACY="$HOME/.claude/skills/obsidian-second-brain"
if [[ -d "$LEGACY" && "$LEGACY" != "$OSB_ROOT" ]]; then
  warn "이전 버전 설치가 있습니다: $LEGACY (49개 명령 버전)"
  if confirm "백업 폴더로 옮길까요? (옮기지 않으면 이전 스킬이 같이 보입니다)" y; then
    BK="$HOME/.obsidian-second-brain-legacy-$(date +%Y%m%d%H%M%S)"
    mv "$LEGACY" "$BK"
    ok "옮김: $BK"
  fi
fi
if [[ -d "$HOME/.codex/bin" ]]; then
  stale=$(grep -l 'run-command.sh' "$HOME/.codex/bin"/* 2>/dev/null || true)
  if [[ -n "$stale" ]] && confirm "이전 Codex 래퍼 $(echo "$stale" | wc -l | tr -d ' ')개(~/.codex/bin)를 지울까요?" y; then
    echo "$stale" | while IFS= read -r f; do rm -f "$f"; done
    ok "이전 Codex 래퍼 삭제"
  fi
fi

# ---------------------------------------------------------------- skills
bold "3/5 스킬 설치"
install_skills() { # install_skills <dest-dir>
  local dest="$1" s target
  mkdir -p "$dest"
  for s in "${SKILLS[@]}"; do
    target="$dest/$s"
    if [[ -d "$target" && ! -f "$target/.osb-managed" ]]; then
      mv "$target" "$target.backup-$(date +%Y%m%d%H%M%S)"
      warn "같은 이름의 기존 스킬을 백업했습니다: $target"
    fi
    rm -rf "$target"
    mkdir -p "$target"
    # {{OSB_ROOT}} becomes the absolute toolkit path, so the skill works from any project.
    OSB_ROOT_VALUE="$OSB_ROOT" "$PY" - "$OSB_ROOT/skills/$s/SKILL.md" "$target/SKILL.md" <<'PYEOF'
import os, sys
src, dst = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read().replace("{{OSB_ROOT}}", os.environ["OSB_ROOT_VALUE"])
open(dst, "w", encoding="utf-8").write(text)
PYEOF
    echo "$OSB_ROOT" > "$target/.osb-managed"
  done
  ok "${#SKILLS[@]}개 스킬 -> $dest"
}
[[ ",$HOSTS," == *",claude,"* ]] && install_skills "$HOME/.claude/skills"
[[ ",$HOSTS," == *",codex,"* ]] && install_skills "${CODEX_HOME:-$HOME/.codex}/skills"

# ---------------------------------------------------------------- vault + hosts
bold "4/5 볼트 만들기"
mkdir -p "$DOCS"
"$OSB_ROOT/.venv/bin/python" "$OSB_ROOT/scripts/bootstrap_vault.py" \
  --path "$VAULT" --name "$NAME" --company "$COMPANY" --role "$ROLE" \
  --language "$LANGUAGE" --hosts "$HOSTS" | sed 's/^/  /'

bold "5/5 확인"
"$PY" "$OSB_ROOT/scripts/osb_env.py" >/dev/null && ok "볼트 경로 설정 확인"
chmod +x "$OSB_ROOT/hooks/validate-ai-first.sh" 2>/dev/null || true
if grep -q '"obsidian-second-brain"' "$HOME/.claude.json" 2>/dev/null; then
  warn "이전 버전의 MCP 서버가 등록되어 있습니다. 필요 없으면: claude mcp remove obsidian-second-brain"
fi

echo
bold "설치 완료"
echo
echo "다음 단계: 볼트로 이동해서 에이전트를 실행하고 obsidian-init 을 실행하세요."
echo
echo "  cd \"$VAULT\""
[[ ",$HOSTS," == *",claude,"* ]] && echo "  claude     # 실행 후 입력: /obsidian-init"
[[ ",$HOSTS," == *",codex,"* ]] && echo "  codex      # 실행 후 입력: \$obsidian-init"
[[ ",$HOSTS," == *",codex,"* ]] && echo "  (Codex: 처음 실행하면 /hooks 를 열어 validate-ai-first 훅을 신뢰(trust)하세요."
[[ ",$HOSTS," == *",codex,"* ]] && echo "   신뢰하기 전까지 Codex는 이 훅을 건너뜁니다. 스킬 안의 검증 단계는 그와 별개로 항상 실행됩니다.)"
echo
echo "그 다음부터는 어느 프로젝트에서든 \"이거 볼트에 저장해\", \"볼트에서 찾아줘\","
echo "\"볼트 점검해\", \"이번 주 리뷰\"처럼 말하면 됩니다."
