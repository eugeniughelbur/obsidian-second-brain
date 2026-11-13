#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
# One-line installer for obsidian-second-brain (Claude Code).
#   curl -fsSL https://raw.githubusercontent.com/eugeniughelbur/obsidian-second-brain/main/scripts/quick-install.sh | bash
#
# What it does (idempotent, nothing destructive):
#   1. Checks prerequisites (git; uv recommended for the Python helpers)
#   2. Clones the skill into ~/.claude/skills/obsidian-second-brain (pulls if present)
#   3. Runs install.sh (symlinks slash commands, offers the research-toolkit env)
#   4. Prints the two follow-up choices: wire an existing vault, or bootstrap a new one
set -euo pipefail

# Home for config and Claude Code state. On Windows shells (Git Bash, MSYS2,
# Cygwin) that is USERPROFILE, which is what Python's Path.home() and Claude
# Code resolve ~ to there; HOME can point at another drive (a corporate roaming
# home) and would split the config between the bash and Python halves.
# Elsewhere HOME is the home. Uses bash 3.2 features only.
# Inline copy of scripts/platform-home.sh on purpose: this script runs via
# curl | bash before any checkout exists, so there is nothing to source.
# tests/test_platform_home.py fails if the copies drift.
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*)
    OSB_WIN=1
    OSB_HOME="${USERPROFILE:-$HOME}"
    OSB_HOME="$(cygpath -u "$OSB_HOME" 2>/dev/null || printf '%s' "${OSB_HOME//\\//}")" ;;
  *) OSB_WIN=0; OSB_HOME="$HOME" ;;
esac
SKILL_HOME="$OSB_HOME/.claude/skills/obsidian-second-brain"
REPO_URL="https://github.com/eugeniughelbur/obsidian-second-brain"

command -v git >/dev/null 2>&1 || { echo "Error: git is required. Install git and re-run." >&2; exit 1; }
if ! command -v uv >/dev/null 2>&1; then
  echo "Note: 'uv' not found. Core commands work without it, but the health/research"
  echo "      scripts need it: https://docs.astral.sh/uv/getting-started/installation/"
fi

if [ -d "$SKILL_HOME/.git" ]; then
  echo "Skill already present - updating..."
  git -C "$SKILL_HOME" pull --ff-only
else
  mkdir -p "$(dirname "$SKILL_HOME")"
  git clone "$REPO_URL" "$SKILL_HOME"
fi

bash "$SKILL_HOME/install.sh"

cat <<'NEXT'

Installed. Choose a starting point:

  Crew only, no Obsidian needed?
    Restart Claude Code and type /crew setup. Pick ~/crew or an existing vault.

  Have a vault already?
    bash ~/.claude/skills/obsidian-second-brain/scripts/setup.sh "/path/to/your/vault"

  No vault yet? Create one:
    cd ~/.claude/skills/obsidian-second-brain
    uv run python scripts/bootstrap_vault.py --path ~/Documents/MyVault --name "Your Name"
    bash scripts/setup.sh ~/Documents/MyVault

Then open Claude Code and run /obsidian-init inside your vault.
NEXT
