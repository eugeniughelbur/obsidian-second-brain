#!/usr/bin/env bash
# =============================================================================
# adapters/claude-code/adapter.sh — Claude Code platform adapter
# =============================================================================
# Sourced by scripts/build.sh AFTER adapters/lib.sh.
# Writes dist/claude-code/ containing slash commands and the skill manifest
# in the shape Claude Code expects.
# =============================================================================

CC_PLATFORM="claude-code"

# adapter_build <src_root> <dst_root>
adapter_build() {
  local src="$1" dst="$2"

  _cc_copy_commands "$src/commands" "$dst/commands"
  _cc_copy_skill_manifest "$src" "$dst"
  _cc_copy_references "$src/references" "$dst/references"
  _cc_copy_scripts "$src/scripts" "$dst/scripts"
  _cc_copy_hooks "$src/hooks" "$dst/hooks"
  _cc_emit_install_hint "$dst"
}

# Identity copy of slash commands — Claude Code's source format matches ours.
_cc_copy_commands() {
  local src="$1" dst="$2"
  [[ -d "$src" ]] || return 0
  mkdir -p "$dst"
  local f
  for f in "$src"/*.md; do
    [[ -f "$f" ]] || continue
    should_include "$f" "$CC_PLATFORM" || continue
    cp "$f" "$dst/$(basename "$f")"
  done
}

# Copy SKILL.md (the Claude Code skill manifest) verbatim.
_cc_copy_skill_manifest() {
  local src="$1" dst="$2"
  [[ -f "$src/SKILL.md" ]] && cp "$src/SKILL.md" "$dst/SKILL.md"
}

_cc_copy_references() {
  local src="$1" dst="$2"
  [[ -d "$src" ]] || return 0
  mkdir -p "$dst"
  cp -R "$src/." "$dst/"
}

_cc_copy_scripts() {
  local src="$1" dst="$2"
  [[ -d "$src" ]] || return 0
  mkdir -p "$dst"
  cp -R "$src/." "$dst/"
}

_cc_copy_hooks() {
  local src="$1" dst="$2"
  [[ -d "$src" ]] || return 0
  mkdir -p "$dst"
  cp -R "$src/." "$dst/"
}

_cc_emit_install_hint() {
  local dst="$1"
  cat > "$dst/INSTALL.md" <<'EOF'
# Install on Claude Code

```bash
# From the repo root, after running `bash scripts/build.sh --platform claude-code`:
ln -sf "$(pwd)/dist/claude-code" ~/.claude/skills/obsidian-second-brain
ln -sf "$(pwd)/dist/claude-code/commands/"*.md ~/.claude/commands/
```

Restart Claude Code. The `/obsidian-*`, `/research`, and `/brand-*` commands
will be available.
EOF
}
