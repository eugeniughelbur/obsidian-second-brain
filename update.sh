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
