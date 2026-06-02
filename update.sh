#!/bin/bash

set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMANDS_DIR="$HOME/.claude/commands"

# Pull latest
if [ -d "$SKILL_DIR/.git" ]; then
  echo "Pulling latest changes..."
  git -C "$SKILL_DIR" pull
else
  echo "Not a git repo - skipping pull. Update the files in $SKILL_DIR manually."
fi

# Refresh command files
echo "Updating slash commands..."
updated=0
for file in "$SKILL_DIR/commands/"*.md; do
  name=$(basename "$file")
  cp "$file" "$COMMANDS_DIR/$name"
  echo "  updated $name"
  updated=$((updated + 1))
done

echo ""
echo "Done. $updated command(s) updated. Restart Claude Code to pick up the changes."
