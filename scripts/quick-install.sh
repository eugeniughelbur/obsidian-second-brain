#!/usr/bin/env bash
# quick-install.sh — one-liner installer for obsidian-second-brain
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/eugeniughelbur/obsidian-second-brain/main/scripts/quick-install.sh | bash
#
# What it does:
#   1. Clones the repo to ~/.claude/skills/obsidian-second-brain (or pulls if it exists)
#   2. Prompts for the vault path
#   3. Runs scripts/setup.sh with that path
#
# Environment:
#   OBSIDIAN_VAULT_PATH — skip the prompt and use this path
#   SKILL_DIR           — override the install location (default: ~/.claude/skills/obsidian-second-brain)

set -euo pipefail

REPO_URL="https://github.com/eugeniughelbur/obsidian-second-brain"
SKILL_DIR="${SKILL_DIR:-$HOME/.claude/skills/obsidian-second-brain}"

red()    { printf '\033[0;31m%s\033[0m\n' "$1"; }
green()  { printf '\033[0;32m%s\033[0m\n' "$1"; }
yellow() { printf '\033[0;33m%s\033[0m\n' "$1"; }

if ! command -v git &>/dev/null; then
  red "Error: git not found. Install git and retry."
  exit 1
fi

# ── clone or update ──────────────────────────────────────────────────────────

if [[ -d "$SKILL_DIR/.git" ]]; then
  yellow "Repo already at $SKILL_DIR — pulling latest..."
  git -C "$SKILL_DIR" pull --ff-only
else
  if [[ -e "$SKILL_DIR" ]]; then
    red "Error: $SKILL_DIR exists and is not a git checkout. Move it aside first."
    exit 1
  fi
  mkdir -p "$(dirname "$SKILL_DIR")"
  git clone "$REPO_URL" "$SKILL_DIR"
fi

green "Skill installed at $SKILL_DIR"

# ── resolve vault path ───────────────────────────────────────────────────────

VAULT="${OBSIDIAN_VAULT_PATH:-}"

if [[ -z "$VAULT" ]]; then
  if [[ ! -t 0 ]]; then
    yellow ""
    yellow "Vault path required. Re-run with OBSIDIAN_VAULT_PATH set, or run setup.sh directly:"
    echo "  bash $SKILL_DIR/scripts/setup.sh \"/path/to/your/vault\""
    exit 0
  fi
  printf "Path to your Obsidian vault: "
  read -r VAULT
fi

# ── hand off to setup.sh ─────────────────────────────────────────────────────

bash "$SKILL_DIR/scripts/setup.sh" "$VAULT"
