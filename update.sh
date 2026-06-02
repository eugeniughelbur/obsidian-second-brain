#!/bin/bash

set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMANDS_DIR="$HOME/.claude/commands"

# Pull latest if this is a git repo
if [ -d "$SKILL_DIR/.git" ]; then
  echo "Pulling latest changes..."
  git -C "$SKILL_DIR" pull
else
  echo "Not a git repo - skipping pull. Copy the latest files manually into $SKILL_DIR first."
fi

# Refresh command files
echo "Updating slash commands..."
updated=0
for file in "$SKILL_DIR/commands/"*.md; do
  name=$(basename "$file")
  dest="$COMMANDS_DIR/$name"
  cp "$file" "$dest"
  echo "  updated $name"
  updated=$((updated + 1))
done

echo ""
echo "Done. $updated command(s) updated."
echo "Restart Claude Code to pick up the changes."
