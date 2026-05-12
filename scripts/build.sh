#!/usr/bin/env bash
# =============================================================================
# scripts/build.sh — Compile platform-neutral source into dist/<platform>/
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
  claude-code   - Claude Code (slash commands + CLAUDE.md)
  codex-cli     - OpenAI Codex CLI (AGENTS.md + .codex/commands/)
  gemini-cli    - Gemini CLI (GEMINI.md + .gemini/commands/)
  opencode      - OpenCode (AGENTS.md + .opencode/commands/)
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

  success "$platform → dist/$platform/"
}

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
