#!/bin/bash
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur

set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Home for config and Claude Code state (OSB_HOME, OSB_WIN): USERPROFILE on
# Windows shells, HOME elsewhere. See scripts/platform-home.sh.
. "$SKILL_DIR/scripts/platform-home.sh"
osb_platform_home
# osb_python: a Python that actually runs, found by running it (#269).
. "$SKILL_DIR/scripts/python-interpreter.sh"
CLAUDE_DIR="$OSB_HOME/.claude"
COMMANDS_DIR="$CLAUDE_DIR/commands"
SKILLS_DIR="$CLAUDE_DIR/skills"
CONFIG_DIR="$OSB_HOME/.config/obsidian-second-brain"
# osb_env_file sets OSB_ENV_FILE: the config path, OBSIDIAN_ENV_FILE honoured and
# a native C:\... override normalized so it survives dirname. One helper, so this
# installer and every reader of the file it writes agree on where it is.
osb_env_file
ENV_FILE="$OSB_ENV_FILE"

echo "Installing obsidian-second-brain..."

# Create directories if needed
mkdir -p "$COMMANDS_DIR"
mkdir -p "$SKILLS_DIR"

# Detect platform once
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) IS_WINDOWS=1 ;;
  *) IS_WINDOWS=0 ;;
esac

# Link commands into ~/.claude/commands/ (copy on Windows without Developer Mode)
echo "Installing slash commands..."
COMMANDS_COPIED=0
for file in "$SKILL_DIR/commands/"*.md; do
  name=$(basename "$file")
  dest="$COMMANDS_DIR/$name"
  if [ -e "$dest" ] || [ -L "$dest" ]; then
    echo "  skipping $name (already exists)"
  elif [ "$IS_WINDOWS" -eq 0 ]; then
    ln -s "$file" "$dest"
    echo "  linked $name"
  elif MSYS=winsymlinks:nativestrict ln -s "$file" "$dest" 2>/dev/null; then
    echo "  linked $name"
  else
    cp "$file" "$dest"
    COMMANDS_COPIED=1
    echo "  installed $name"
  fi
done
if [ "$COMMANDS_COPIED" -eq 1 ]; then
  echo "  (symlinks require Developer Mode - commands were copied; run update.sh to refresh)"
fi

# Link skill into ~/.claude/skills/
SKILL_LINK="$SKILLS_DIR/obsidian-second-brain"
if [ -e "$SKILL_LINK" ]; then
  echo "Skill already linked at $SKILL_LINK"
elif [ "$IS_WINDOWS" -eq 0 ]; then
  ln -s "$SKILL_DIR" "$SKILL_LINK"
  echo "Skill linked at $SKILL_LINK"
else
  if MSYS=winsymlinks:nativestrict ln -s "$SKILL_DIR" "$SKILL_LINK" 2>/dev/null; then
    echo "Skill linked at $SKILL_LINK"
  else
    echo "Symlink failed (requires Developer Mode). For the cleanest setup,"
    echo "clone the repo directly into the skills folder:"
    echo "  git clone https://github.com/eugeniughelbur/obsidian-second-brain \"$SKILLS_DIR/obsidian-second-brain\""
    echo "Then re-run install.sh from that location."
  fi
fi

# Register the SessionStart context hook so slash commands can locate the skill's
# bundled scripts. The plugin install wires this up automatically via its manifest;
# the skill install needs it in settings.json. Idempotent, safe to re-run.
# The interpreter is found by running it, never by looking the name up: on a
# stock Windows install `python3` is the Microsoft Store alias, which passes
# `command -v` and exits non-zero, and under `set -e` that ended this installer
# on the spot, with no hook registered and the steps below never reached (#281).
echo "Registering session context hook..."
if PYTHON=$(osb_python); then
  # Unquoted: PYTHON may be several words ("py -3", "uv run --no-project python").
  $PYTHON "$SKILL_DIR/scripts/setup_settings_hook.py"
  # Another vault plugin's SessionStart hook is not replaced by ours, it runs
  # beside it and puts a second folder and frontmatter schema in the same
  # context (#300). Said here, while the user can still choose, instead of
  # leaving it to surface through notes written under the wrong schema.
  $PYTHON "$SKILL_DIR/scripts/vault_plugin_scan.py" --quiet || true
else
  echo "  no working Python found (tried python3, python, py -3, uv run) - add this SessionStart hook to $CLAUDE_DIR/settings.json manually:"
  echo "    \"$SKILLS_DIR/obsidian-second-brain/hooks/load_vault_context.sh\""
fi

# ── Research toolkit setup (optional) ──────────────────────────────
echo ""
echo "Research toolkit (optional): /x-read, /x-pulse, /research, /research-deep, /youtube"
echo "These commands need API keys for Grok (xAI) and Perplexity. YouTube key is optional."
echo ""
read -r -p "Set up research toolkit now? [y/N] " setup_research
setup_research=${setup_research:-N}

if [[ "$setup_research" =~ ^[Yy]$ ]]; then
  # Verify uv is available
  if ! command -v uv >/dev/null 2>&1; then
    case "$(uname -s)" in
      Darwin)               uv_hint="brew install uv" ;;
      Linux)                uv_hint="curl -LsSf https://astral.sh/uv/install.sh | sh" ;;
      MINGW*|MSYS*|CYGWIN*) uv_hint="powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\"" ;;
      *)                    uv_hint="see https://docs.astral.sh/uv/getting-started/installation/" ;;
    esac
    echo "  ⚠️  'uv' not found. Install with: $uv_hint"
    echo "     Then re-run this installer to finish research toolkit setup."
  else
    echo "  Installing Python deps via uv..."
    (cd "$SKILL_DIR" && uv sync --quiet)
    echo "  Python deps ready."
  fi

  # Set up config dir + .env
  mkdir -p "$CONFIG_DIR" "$(dirname "$ENV_FILE")"
  if [ -f "$ENV_FILE" ]; then
    echo "  $ENV_FILE already exists - leaving it untouched."
  else
    cp "$SKILL_DIR/.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "  Created $ENV_FILE (permissions 600)."
  fi

  echo ""
  echo "  Now paste your API keys into: $ENV_FILE"
  echo "    XAI_API_KEY=          (https://console.x.ai)"
  echo "    PERPLEXITY_API_KEY=   (https://perplexity.ai/settings/api)"
  echo "    YOUTUBE_API_KEY=      (https://console.cloud.google.com - optional)"
  echo ""
  read -r -p "  Press Enter to open the file in your default editor (or Ctrl+C to skip)... " _
  # Pick a default opener if $EDITOR is unset. Original used `open` (macOS-only).
  default_editor=open
  case "$(uname -s)" in
    Linux)                default_editor=xdg-open ;;
    MINGW*|MSYS*|CYGWIN*) default_editor=notepad ;;
  esac
  ${EDITOR:-$default_editor} "$ENV_FILE"
fi

echo ""
echo "Done. Restart Claude Code to activate the commands."
echo ""
echo "Next steps:"
echo "  1. Run /obsidian-init to generate your vault's _CLAUDE.md"
echo "  2. (If research toolkit installed) Verify keys: cat $ENV_FILE"
