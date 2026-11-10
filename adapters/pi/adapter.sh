#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
# =============================================================================
# adapters/pi/adapter.sh - Pi Coding Agent platform adapter
# =============================================================================
# Pi loads prompt templates from .pi/prompts/ and skills from
# .pi/skills/<name>/SKILL.md. This adapter emits a Pi package under dist/pi/
# that can be installed with:
#   pi install ./dist/pi
# or copied into a vault root:
#   cp -R dist/pi/.pi/ /path/to/your/vault/
# =============================================================================

PI_PLATFORM="pi"
PI_DIR="pi"
PI_SKILL_ROOT=".pi/skills/obsidian-second-brain"

adapter_build() {
  local src="$1" dst="$2"

  _pi_emit_package_json "$src" "$dst"
  _pi_emit_prompts "$src/commands" "$dst/.pi/prompts"
  _pi_emit_skill "$src" "$dst/.pi/skills/obsidian-second-brain"
  _pi_copy_references "$src/references" "$dst/.pi/skills/obsidian-second-brain/references"
  _pi_copy_scripts "$src/scripts" "$dst/.pi/skills/obsidian-second-brain/scripts"
  _pi_emit_install_hint "$dst"
}

_pi_emit_package_json() {
  local src="$1" dst="$2"
  local version
  version="$(grep -m1 '^version' "$src/pyproject.toml" 2>/dev/null | sed 's/.*=[[:space:]]*"//; s/".*//')"
  [[ -n "$version" ]] || version="0.0.0"

  mkdir -p "$dst"
  cat > "$dst/package.json" <<EOF
{
  "name": "obsidian-second-brain-pi",
  "version": "${version}",
  "description": "Pi package for obsidian-second-brain: prompt templates and skill to operate an Obsidian vault as a self-rewriting second brain.",
  "keywords": ["pi-package", "obsidian", "second-brain", "pkm"],
  "license": "MIT",
  "author": "Eugeniu Ghelbur",
  "repository": {
    "type": "git",
    "url": "https://github.com/eugeniughelbur/obsidian-second-brain.git"
  },
  "pi": {
    "prompts": [".pi/prompts"],
    "skills": [".pi/skills"]
  }
}
EOF
}

_pi_emit_prompts() {
  local src="$1" dst="$2"
  [[ -d "$src" ]] || return 0
  mkdir -p "$dst"

  local f name desc out
  for f in "$src"/*.md; do
    [[ -f "$f" ]] || continue
    should_include "$f" "$PI_PLATFORM" || continue

    name="$(basename "$f" .md)"
    desc="$(parse_frontmatter "$f" description)"
    [[ -z "$desc" ]] && desc="Run the /$name command of the obsidian-second-brain skill."
    desc="$(strip_quotes "$desc")"

    # This build writes its own frontmatter, so a source trigger-mode does not
    # travel unless it is encoded here (#181).
    local trigmode
    trigmode="$(parse_frontmatter "$f" trigger-mode)"
    desc="$(with_trigger_policy "$desc" "$trigmode")"

    out="$dst/$name.md"
    {
      echo "---"
      printf 'description: "%s"\n' "${desc//\"/\\\"}"
      if _pi_command_takes_args "$f"; then
        printf 'argument-hint: "[args]"\n'
      fi
      echo "---"
      echo
      echo "Run the obsidian-second-brain /$name command:"
      echo
      command_body "$f"
    } > "$out"

    _pi_rewrite_paths_for_prompt "$out"
    rewrite_tool_neutral "$out"
  done
}

_pi_command_takes_args() {
  local file="$1"
  command_body "$file" | grep -qE '<[^>]+>' \
    || parse_frontmatter "$file" description | grep -qE '<[^>]+>'
}

_pi_rewrite_paths_for_prompt() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  # Home-dir install path is pi-specific; the SKILL_ROOT and references/
  # rewrites are shared (see adapters/lib.sh).
  perl -i -pe 's|~/.claude/skills/obsidian-second-brain/|'"$PI_SKILL_ROOT"'/|g;' "$file"
  rewrite_skill_root "$file" "$PI_SKILL_ROOT"
  rewrite_platform_paths "$file" "${PI_SKILL_ROOT#.}"
  # NB: `scripts/` is deliberately not rewritten. Every invocation is
  # `uv run --directory "SKILL_ROOT" scripts/foo.py`, so the path is relative to
  # --directory. The previous rule prefixed it and produced a double path.
}

_pi_emit_skill() {
  local src="$1" dst="$2"
  mkdir -p "$dst"
  local out="$dst/SKILL.md"

  {
    cat <<'EOF'
---
name: obsidian-second-brain
description: >
  Operate any Obsidian vault as a living, self-rewriting second brain.
  Use this skill when the user asks to save, search, update, or manage their
  Obsidian vault, or when they invoke any /obsidian-* or /research command.
---

# Obsidian Second Brain - Pi Operating Manual

This vault can run the **obsidian-second-brain** skill. The skill ships prompt
templates under `.pi/prompts/` (type `/obsidian-save`, `/obsidian-daily`, etc.)
and this discovery skill (`/skill:obsidian-second-brain`).

## How to operate

1. Read `_CLAUDE.md` in the vault root, if it exists, to learn the user's vault
   conventions.
2. When the user types a prompt template like `/obsidian-save`, follow its
   instructions step by step.
EOF

  emit_ai_first_rule "./references/ai-first-rules.md"

  cat <<'EOF'
4. If `_CLAUDE.md` is missing, run `/obsidian-init` to generate it.

## Command routing table
EOF

    emit_routing_table_grouped "$src/commands" "$PI_PLATFORM" ".pi/prompts"
    emit_trigger_reference "$src/commands" "$PI_PLATFORM"

    cat <<'EOF'

---

*Generated by adapters/pi/adapter.sh - do not edit manually.*
EOF
  } > "$out"

  rewrite_tool_neutral "$out"
  perl -i -pe '
    s|~/.claude/skills/obsidian-second-brain/||g;
    s|\.pi/skills/obsidian-second-brain/||g;
    s~(^|[^A-Za-z0-9_./-])\.?/?references/~$1./references/~g;
    s~(^|[^A-Za-z0-9_./-])\.?/?scripts/(?!build\.sh)~$1./scripts/~g;
  ' "$out"
}

_pi_copy_references() { copy_references_rewritten "$1" "$2" "${PI_SKILL_ROOT#.}"; }  # see adapters/lib.sh

_pi_copy_scripts() { copy_scripts_with_project "$1" "$2"; }  # see adapters/lib.sh

_pi_emit_install_hint() {
  local dst="$1"
  cat > "$dst/INSTALL.md" <<'EOF'
# Install on Pi

Build the Pi package from the repo:

```bash
git clone https://github.com/eugeniughelbur/obsidian-second-brain.git
cd obsidian-second-brain
bash scripts/build.sh --platform pi
```

Then either install the package into Pi:

```bash
pi install ./dist/pi
```

Or copy the built `.pi/` tree into your vault so Pi discovers the prompt
templates and skill from the project root:

```bash
cp -R dist/pi/.pi/ /path/to/your/vault/
```

Then start Pi from your vault root. The `/obsidian-*` and `/research` prompt
templates will be available, and the discovery skill loads via
`/skill:obsidian-second-brain`.

## Research toolkit

The research commands (`/research`, `/research-deep`, `/x-read`, `/x-pulse`,
`/youtube`, `/notebooklm`, `/podcast`) need the same API keys as the other
platforms. Copy `.env.example` to `~/.config/obsidian-second-brain/.env`, set
permissions to `600`, and paste in the required keys. Pi reads those same
environment variables, or you can export them before running Pi.

## Background agents

Pi has no background-bash or PostCompact-hook equivalent. The scheduled agents
(`obsidian-nightly` and the others) are prompts, not commands, so there is no
`/obsidian-nightly` prompt template. To run one, copy its prompt from the
scheduled agents section of `SKILL.md` into a Pi session, by hand or from your
own scheduler.
EOF
}
