#!/usr/bin/env bash
# =============================================================================
# adapters/minimax/adapter.sh - Mavis (MiniMax Code) Plugin V1 packaging
# =============================================================================
# Mavis / MiniMax Code reads a Plugin V1 package from <data-dir>/plugins/<name>/.
# The shape is a manifest at .minimax-plugin/plugin.json plus zero or more
# `*.mcp.json` launch configs and `skills/<skill>/SKILL.md` references.
#
# This adapter does NOT compile the per-command skill set the other adapters
# emit. Mavis plugins ship a single root skill (`obsidian-second-brain`) that
# summarises the 45 commands; the per-tool work is exposed through the
# stdio MCP server at `integrations/obsidian-mcp-server/server.py`, which
# the build copies verbatim from upstream.
#
# Per the Plugin V1 spec, the manifest `version` is packaging-local; it does
# NOT mirror the upstream `pyproject.toml` semver. We hardcode `0.0.0` so the
# emitted artifact has no per-user drift and each Mavis user can stamp their
# own packaging version on copy.
#
# The MCP `OBSIDIAN_VAULT_PATH` is templated as `<VAULT_PATH>` (no real path)
# so the emitted package contains no user-specific secrets.
# =============================================================================

MINIMAX_PLATFORM="minimax"
MINIMAX_DIR="minimax"
MINIMAX_MANIFEST_DIR=".minimax-plugin"
MINIMAX_MANIFEST="${MINIMAX_MANIFEST_DIR}/plugin.json"
MINIMAX_MCP_CONFIG="obsidian-second-brain.mcp.json"
MINIMAX_SKILL_DIR="skills/obsidian-second-brain"

# 1x1 transparent PNG, 67 bytes. Used only when upstream `media/icon.png` is
# absent (so the V1 spec's required `icon` field always resolves). Stored as
# a hex string so the adapter stays shell-only and avoids a binary blob.
MINIMAX_ICON_FALLBACK_HEX="89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6300010000000500010d0a2db40000000049454e44ae426082"

adapter_build() {
  local src="$1" dst="$2"

  _minimax_emit_manifest     "$dst"
  _minimax_emit_mcp_config   "$dst"
  _minimax_emit_icon         "$src" "$dst"
  _minimax_emit_placeholder  "$dst"
  _minimax_copy_mcp_server   "$src" "$dst"
  _minimax_copy_skill        "$src" "$dst"
}

# ── .minimax-plugin/plugin.json ─────────────────────────────────────────────
# The Plugin V1 manifest. `version: "0.0.0"` is intentional: each Mavis user
# stamps their own packaging version on copy, and a hardcoded 0.0.0 makes the
# emitted package byte-identical across runs (idempotency gate for the smoke
# test). `OBSIDIAN_VAULT_PATH` is templated as `<VAULT_PATH>` so the artifact
# has no per-user paths.
_minimax_emit_manifest() {
  local dst="$1"
  local out="$dst/$MINIMAX_MANIFEST"
  mkdir -p "$(dirname "$out")"
  cat > "$out" <<'EOF'
{
  "schemaVersion": 1,
  "name": "obsidian-second-brain",
  "displayName": "Obsidian Second Brain",
  "version": "0.0.0",
  "description": "Persistent memory + notes for Mavis, backed by an Obsidian vault. 46 commands plus a stdio MCP server exposing vault search, read, save and capture as native tools.",
  "author": "eugeniughelbur (upstream) — packaged for Mavis by fcojg",
  "icon": "icon.png",
  "category": "Productivity",
  "exampleQueries": [
    "Save this conversation to my Obsidian vault",
    "Find notes about [topic] in my second brain",
    "What did I learn this week?",
    "Research X and update my vault with the findings",
    "Create today's daily note and pull in overdue tasks"
  ],
  "apps": [],
  "mcpServers": [
    "obsidian-second-brain.mcp.json"
  ],
  "skills": [
    "skills/obsidian-second-brain/SKILL.md"
  ]
}
EOF
}

# ── obsidian-second-brain.mcp.json ──────────────────────────────────────────
# stdio MCP launch config. `OBSIDIAN_VAULT_PATH` is templated so users substitute
# their real vault at packaging time. The `mcp<2` pin matches the V1 ecosystem
# guidance and the local installed plugin shape.
_minimax_emit_mcp_config() {
  local dst="$1"
  local out="$dst/$MINIMAX_MCP_CONFIG"
  cat > "$out" <<'EOF'
{
  "schemaVersion": 1,
  "mcpServers": {
    "obsidian-second-brain": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--with",
        "mcp<2",
        "python",
        "./integrations/obsidian-mcp-server/server.py"
      ],
      "env": {
        "OBSIDIAN_VAULT_PATH": "<VAULT_PATH>"
      },
      "description": "Obsidian Second Brain vault tools: obsidian_search, obsidian_read_note, obsidian_save_note, obsidian_capture. Operates on the vault path in OBSIDIAN_VAULT_PATH.",
      "timeout": 30000
    }
  }
}
EOF
}

# ── icon.png ────────────────────────────────────────────────────────────────
# Copy upstream `media/icon.png` if present (we want a real asset, not the
# fallback, when the upstream ships one). Otherwise emit a 1x1 transparent
# PNG from a hex string. The hex is split into 2-byte chunks so the `printf`
# escape fits the line length; the bytes are identical to a real 1x1 PNG.
_minimax_emit_icon() {
  local src="$1" dst="$2"
  local out="$dst/icon.png"
  if [[ -f "$src/media/icon.png" ]]; then
    cp -p "$src/media/icon.png" "$out"
    return
  fi
  printf '\x89\x50\x4e\x47\x0d\x0a\x1a\x0a\x00\x00\x00\x0d\x49\x48\x44\x52\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0a\x49\x44\x41\x54\x78\x9c\x63\x00\x01\x00\x00\x05\x00\x01\x0d\x0a\x2d\xb4\x00\x00\x00\x00\x49\x45\x4e\x44\xae\x42\x60\x82' > "$out"
}

# ── placeholder ─────────────────────────────────────────────────────────────
# V1 packages need a write-tool anchor so the runtime can create the parent
# directory even before any user file lands. Plain ASCII, no per-build drift.
_minimax_emit_placeholder() {
  local dst="$1"
  printf '%s\n' "placeholder to ensure write tool can create the parent" > "$dst/placeholder"
}

# ── integrations/obsidian-mcp-server/* ──────────────────────────────────────
# Copied verbatim from upstream. These are the Python MCP server the
# `obsidian-second-brain.mcp.json` launches.
_minimax_copy_mcp_server() {
  local src="$1" dst="$2"
  local src_dir="$src/integrations/obsidian-mcp-server"
  local dst_dir="$dst/integrations/obsidian-mcp-server"
  [[ -d "$src_dir" ]] || { echo "minimax adapter: missing $src_dir" >&2; return 1; }
  mkdir -p "$dst_dir"
  cp -p "$src_dir/server.py"   "$dst_dir/server.py"
  cp -p "$src_dir/vault_ops.py" "$dst_dir/vault_ops.py"
  cp -p "$src_dir/README.md"    "$dst_dir/README.md"
}

# ── skills/obsidian-second-brain/SKILL.md ───────────────────────────────────
# The single root skill. Copied verbatim from upstream so the V1 spec sees
# `name` and `description` frontmatter that already match the skill directory.
_minimax_copy_skill() {
  local src="$1" dst="$2"
  local src_file="$src/SKILL.md"
  local dst_dir="$dst/$MINIMAX_SKILL_DIR"
  [[ -f "$src_file" ]] || { echo "minimax adapter: missing $src_file" >&2; return 1; }
  mkdir -p "$dst_dir"
  cp -p "$src_file" "$dst_dir/SKILL.md"
}
