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
COMMANDS_DIR="$OSB_HOME/.claude/commands"

# Pull latest
if [ -d "$SKILL_DIR/.git" ]; then
  echo "Pulling latest changes..."
  git -C "$SKILL_DIR" pull
else
  echo "Not a git repo - skipping pull. Update the files in $SKILL_DIR manually."
fi

# Symlinked commands pick up git pull automatically.
# Copied commands (Windows without Developer Mode) need an explicit refresh.
echo "Updating slash commands..."
updated=0
for file in "$SKILL_DIR/commands/"*.md; do
  name=$(basename "$file")
  dest="$COMMANDS_DIR/$name"
  if [ -L "$dest" ]; then
    : # symlink - already current after git pull
  else
    cp "$file" "$dest"
    echo "  updated $name"
    updated=$((updated + 1))
  fi
done
[ "$updated" -gt 0 ] && echo "  $updated command(s) refreshed (copied, not symlinked)"

echo ""
echo "Done. Restart Claude Code to pick up the changes."
