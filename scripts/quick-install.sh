#!/usr/bin/env bash
# One-line installer for obsidian-second-brain (Claude Code).
#   curl -fsSL https://raw.githubusercontent.com/eugeniughelbur/obsidian-second-brain/main/scripts/quick-install.sh | bash
#
# What it does (idempotent, nothing destructive):
#   1. Checks prerequisites (git; uv recommended for the Python helpers)
#   2. Clones the skill into ~/.claude/skills/obsidian-second-brain (pulls if present)
#   3. Runs install.sh (symlinks slash commands, offers the research-toolkit env)
#   4. Prints the two follow-up choices: wire an existing vault, or bootstrap a new one
set -euo pipefail

SKILL_HOME="$HOME/.claude/skills/obsidian-second-brain"
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

Installed. Two ways to finish:

  Have a vault already?
    bash ~/.claude/skills/obsidian-second-brain/scripts/setup.sh "/path/to/your/vault"

  No vault yet? Create one:
    cd ~/.claude/skills/obsidian-second-brain
    uv run python scripts/bootstrap_vault.py --path ~/Documents/MyVault --name "Your Name"
    bash scripts/setup.sh ~/Documents/MyVault

Then open Claude Code and run /obsidian-init inside your vault.
NEXT
