#!/bin/bash

set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
COMMANDS_DIR="$CLAUDE_DIR/commands"
SKILLS_DIR="$CLAUDE_DIR/skills"
CONFIG_DIR="$HOME/.config/obsidian-second-brain"
ENV_FILE="$CONFIG_DIR/.env"

echo "Installing obsidian-second-brain..."

# Create directories if needed
mkdir -p "$COMMANDS_DIR"
mkdir -p "$SKILLS_DIR"

# Link or copy commands to ~/.claude/commands/
echo "Installing slash commands..."
for file in "$SKILL_DIR/commands/"*.md; do
  name=$(basename "$file")
  dest="$COMMANDS_DIR/$name"
  if [ -f "$dest" ]; then
    echo "  skipping $name (already exists)"
  else
    cp "$file" "$dest"
    echo "  installed $name"
  fi
done

# Link skill into ~/.claude/skills/
SKILL_LINK="$SKILLS_DIR/obsidian-second-brain"
if [ -e "$SKILL_LINK" ]; then
  echo "Skill already linked at $SKILL_LINK"
else
  ln -s "$SKILL_DIR" "$SKILL_LINK"
  echo "Skill linked at $SKILL_LINK"
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
  mkdir -p "$CONFIG_DIR"
  if [ -f "$ENV_FILE" ]; then
    echo "  $ENV_FILE already exists — leaving it untouched."
  else
    cp "$SKILL_DIR/.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "  Created $ENV_FILE (permissions 600)."
  fi

  echo ""
  echo "  Now paste your API keys into: $ENV_FILE"
  echo "    XAI_API_KEY=          (https://console.x.ai)"
  echo "    PERPLEXITY_API_KEY=   (https://perplexity.ai/settings/api)"
  echo "    YOUTUBE_API_KEY=      (https://console.cloud.google.com — optional)"
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
