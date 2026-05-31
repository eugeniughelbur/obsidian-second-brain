#!/usr/bin/env bash
set -euo pipefail

# Install one PATH shim per command so Codex users can run them by name:
#   obsidian-init
#   obsidian-daily
#   research "topic"
# Each shim delegates to scripts/run-command.sh. (Claude Code users do not need
# this - they use the slash commands directly.)

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${OBSIDIAN_CODEX_BIN_DIR:-$HOME/.codex/bin}"
mkdir -p "$BIN_DIR"

count=0
for file in "$SKILL_DIR/commands/"*.md; do
  name="$(basename "$file" .md)"
  wrapper="$BIN_DIR/$name"
  cat > "$wrapper" <<EOF
#!/usr/bin/env bash
exec "$SKILL_DIR/scripts/run-command.sh" "$name" "\$@"
EOF
  chmod +x "$wrapper"
  count=$((count + 1))
done

echo "Installed $count command wrappers to $BIN_DIR"
echo "If $BIN_DIR is not on your PATH, add:"
echo "  export PATH=\"$BIN_DIR:\$PATH\""
