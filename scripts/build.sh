#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
# =============================================================================
# scripts/build.sh - Compile platform-neutral source into dist/<platform>/
# =============================================================================
# Usage:
#   bash scripts/build.sh                       # builds all platforms
#   bash scripts/build.sh --platform claude-code
#   bash scripts/build.sh --platform codex-cli
#
# Reads the platform-neutral source (commands/, references/, DISPATCHER.md)
# and emits a platform-specific tree under dist/<platform>/.
#
# Each adapter is a self-contained shell script in adapters/<platform>/
# that defines an adapter_build() function called by this orchestrator.
# =============================================================================
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=scripts/lib.sh
source "$SCRIPT_DIR/lib.sh"

# ── Parse args ──────────────────────────────────────────────────────────────
PLATFORM=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform) PLATFORM="$2"; shift 2 ;;
    --help|-h)
      cat <<'EOF'
Usage: bash scripts/build.sh [--platform <name>]

Without --platform, builds every platform listed under adapters/.

Available platforms:
  agent-skills  - Antigravity / Codex CLI / OpenCode (unified .agents/skills/ tree)
  claude-code   - Claude Code (slash commands + CLAUDE.md)
  codex-cli     - OpenAI Codex CLI (native Agent Skills, .agents/skills/)
  gemini-cli    - Gemini CLI (GEMINI.md + .gemini/commands/)
  grok-bot      - Grok Bot / Sand (SKILL.md + MCP user-obsidian-second-brain)
  hermes        - Nous Research Hermes Agent (native skills, skills/<category>/)
  opencode      - OpenCode (AGENTS.md + .opencode/commands/)
  pi            - Pi Coding Agent (package.json + .pi/prompts/ + .pi/skills/)
EOF
      exit 0
      ;;
    *) die "Unknown argument: $1 (use --help for usage)" ;;
  esac
done

# ── Discover platforms ──────────────────────────────────────────────────────
discover_platforms() {
  local p
  for p in "$REPO_ROOT/adapters"/*/; do
    [[ -d "$p" ]] || continue
    basename "$p"
  done
}

# ── Build a single platform ─────────────────────────────────────────────────
build_one() {
  local platform="$1"
  local adapter="$REPO_ROOT/adapters/$platform/adapter.sh"

  [[ -f "$adapter" ]] || die "Adapter not found: $adapter"

  info "Building platform: $platform"

  # Source shared adapter helpers, then the platform-specific adapter.
  # shellcheck source=adapters/lib.sh
  source "$REPO_ROOT/adapters/lib.sh"
  # shellcheck source=/dev/null
  source "$adapter"

  local dist_dir="$REPO_ROOT/dist/$platform"
  rm -rf "$dist_dir"
  mkdir -p "$dist_dir"

  adapter_build "$REPO_ROOT" "$dist_dir"
  # Credit ships inside the build, not only in adapters/OWNERS.md. Done here
  # rather than in each adapter so claiming a platform stays a one-line edit to
  # one table instead of a change to seven files.
  append_owner_credit "$dist_dir" "$platform"

  success "$platform → dist/$platform/"
}

# ── Validate exclude: tokens ────────────────────────────────────────────────
# `exclude:` is the only mechanism keeping a Claude-only command out of a
# platform where it cannot work, and it was an unvalidated string match. A
# plausible misspelling (codex for codex-cli, agentskills for agent-skills)
# shipped the command everywhere with exit 0 and no warning. The one command
# that relies on this today spells all six correctly by luck.
validate_excludes() (
  # Subshell + its own source: adapters/lib.sh is sourced inside build_one, so
  # parse_frontmatter is not available at this scope.
  source "$REPO_ROOT/adapters/lib.sh"
  local valid; valid=" $(discover_platforms | tr '\n' ' ')"
  local bad=0 f raw tok
  for f in "$REPO_ROOT"/commands/*.md; do
    [[ -f "$f" ]] || continue
    raw="$(parse_frontmatter "$f" exclude)"
    [[ -z "$raw" || "$raw" == "[]" ]] && continue
    for tok in $(echo "$raw" | tr -d '[]"' | tr ',' ' '); do
      [[ -z "$tok" ]] && continue
      case "$valid" in
        *" $tok "*) ;;
        *) echo "error: $(basename "$f") excludes unknown platform '$tok'" >&2
           echo "       valid platforms:$valid" >&2
           bad=1 ;;
      esac
    done
  done
  [[ $bad -eq 0 ]]
)
validate_excludes || exit 1

# ── Main ────────────────────────────────────────────────────────────────────
if [[ -n "$PLATFORM" ]]; then
  build_one "$PLATFORM"
else
  info "No --platform given; building all"
  for p in $(discover_platforms); do
    ( build_one "$p" )
  done
  success "All platforms built"
fi

# Never ship Python bytecode into user vaults (stress-test fix 22/24).
# Anchored to $REPO_ROOT, not the caller's cwd. scripts/update-vault-integration.sh
# invokes build.sh by absolute path with no cd, so `find dist ...` resolved against
# whatever directory the user was in, found nothing, and the `|| true` swallowed it -
# then install_build copied the bytecode straight into the user's vault.
find "$REPO_ROOT/dist" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$REPO_ROOT/dist" -name "*.pyc" -delete 2>/dev/null || true
