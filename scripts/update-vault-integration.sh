#!/usr/bin/env bash
# =============================================================================
# scripts/update-vault-integration.sh - guarded updater for copied dist builds
# =============================================================================
# The plugin-marketplace and symlink installs update themselves; a dist tree
# COPIED into a vault (Codex / OpenCode / Antigravity / Gemini / Hermes / Pi)
# goes stale. This updates it safely:
#
#   1. verify   - clean repo, recognizable remote, vault exists
#   2. pull     - fast-forward only; anything else aborts untouched
#   3. rebuild  - bash scripts/build.sh --platform <name>
#   4. gate     - smoke tests must pass before anything is installed
#   5. backup   - the vault's integration files, to ~/.cache/... (tar.gz)
#   6. install  - copy the fresh build in
#   7. rollback - any failure after step 5 restores the backup
#
# Usage:
#   bash scripts/update-vault-integration.sh --vault /path/to/vault [--platform agent-skills]
#   bash scripts/update-vault-integration.sh --vault /path/to/vault --dry-run
#
# Pattern from fork-insights round 2 (the updater fork), generalized: no
# personal defaults, every platform, backups under ~/.cache instead of Desktop.
# =============================================================================
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UPSTREAM_SLUG="eugeniughelbur/obsidian-second-brain"
BACKUP_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/obsidian-second-brain/backups"

VAULT=""
PLATFORM=""
DRY_RUN=0
SKIP_TESTS=0
SKIP_PULL=0

usage() {
  sed -n '3,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --vault)      VAULT="$2"; shift 2 ;;
    --platform)   PLATFORM="$2"; shift 2 ;;
    --dry-run)    DRY_RUN=1; shift ;;
    --skip-tests) SKIP_TESTS=1; shift ;;
    --skip-pull)  SKIP_PULL=1; shift ;;
    --help|-h)    usage 0 ;;
    *) echo "Unknown argument: $1" >&2; usage 2 ;;
  esac
done

info()  { echo "[update] $*" >&2; }
die()   { echo "[update] ERROR: $*" >&2; exit 1; }

[[ -n "$VAULT" ]] || die "--vault is required"
VAULT="$(cd "$VAULT" 2>/dev/null && pwd)" || die "vault path does not exist"

# ── Platform: explicit flag, else detect from what is installed ─────────────
detect_platform() {
  [[ -d "$VAULT/.agents/skills" ]] && { echo "agent-skills"; return; }
  [[ -d "$VAULT/.codex"        ]] && { echo "codex-cli";    return; }
  [[ -d "$VAULT/.gemini"       ]] && { echo "gemini-cli";   return; }
  [[ -d "$VAULT/.opencode"     ]] && { echo "opencode";     return; }
  [[ -d "$VAULT/.pi"           ]] && { echo "pi";           return; }
  echo ""
}
if [[ -z "$PLATFORM" ]]; then
  PLATFORM="$(detect_platform)"
  [[ -n "$PLATFORM" ]] || die "could not detect an installed platform in $VAULT - pass --platform"
  info "detected platform: $PLATFORM"
fi
[[ -f "$REPO_ROOT/adapters/$PLATFORM/adapter.sh" ]] || die "unknown platform: $PLATFORM"

# ── What each platform installs into the vault (backup + install sets) ──────
integration_paths() {
  case "$PLATFORM" in
    agent-skills) echo ".agents/skills" ;;
    codex-cli)    echo "AGENTS.md INSTALL.md .agents .codex" ;;
    opencode)     echo "AGENTS.md INSTALL.md .opencode" ;;
    gemini-cli)   echo "GEMINI.md INSTALL.md .gemini" ;;
    pi)           echo ".pi package.json INSTALL.md" ;;
    *)            die "no integration map for platform: $PLATFORM" ;;
  esac
}

install_build() {
  case "$PLATFORM" in
    agent-skills)
      mkdir -p "$VAULT/.agents/skills"
      cp -R "$REPO_ROOT/dist/agent-skills/skills/." "$VAULT/.agents/skills/" ;;
    *)
      cp -R "$REPO_ROOT/dist/$PLATFORM/." "$VAULT/" ;;
  esac
}

# ── Step 1: verify ───────────────────────────────────────────────────────────
command -v git >/dev/null || die "git is required"
git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "$REPO_ROOT is not a git repo"
if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
  die "repo has uncommitted changes - commit or stash first (nothing was touched)"
fi
ORIGIN_URL="$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null || true)"
if [[ "$ORIGIN_URL" != *"obsidian-second-brain"* ]]; then
  die "origin remote ($ORIGIN_URL) does not look like an obsidian-second-brain clone or fork"
fi
[[ "$ORIGIN_URL" == *"$UPSTREAM_SLUG"* ]] || info "note: origin is a fork ($ORIGIN_URL); pulling from it, not upstream"

if [[ $DRY_RUN -eq 1 ]]; then
  info "DRY RUN - plan:"
  info "  1. git pull --ff-only origin (in $REPO_ROOT)"
  info "  2. bash scripts/build.sh --platform $PLATFORM"
  [[ $SKIP_TESTS -eq 0 ]] && info "  3. uv run pytest -q tests/test_smoke.py (gate)"
  info "  4. backup: $(integration_paths) -> $BACKUP_ROOT/<timestamp>.tar.gz"
  info "  5. install dist/$PLATFORM into $VAULT (rollback from backup on failure)"
  exit 0
fi

# ── Step 2: pull (fast-forward only - never invents a merge) ────────────────
if [[ $SKIP_PULL -eq 0 ]]; then
  info "pulling latest (fast-forward only)..."
  git -C "$REPO_ROOT" pull --ff-only origin || die "cannot fast-forward - resolve manually; nothing was installed"
else
  info "skipping pull (--skip-pull)"
fi

# ── Step 3: rebuild ──────────────────────────────────────────────────────────
info "building platform: $PLATFORM"
bash "$REPO_ROOT/scripts/build.sh" --platform "$PLATFORM" >&2

# ── Step 4: gate ─────────────────────────────────────────────────────────────
if [[ $SKIP_TESTS -eq 0 ]]; then
  if command -v uv >/dev/null; then
    info "running smoke-test gate..."
    (cd "$REPO_ROOT" && uv run pytest -q tests/test_smoke.py >&2) || die "smoke tests failed - nothing was installed"
  else
    info "uv not found - skipping test gate (install uv for the full guarantee)"
  fi
fi

# ── Step 5: backup ───────────────────────────────────────────────────────────
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_FILE="$BACKUP_ROOT/$PLATFORM-$TS.tar.gz"
mkdir -p "$BACKUP_ROOT"
EXISTING=()
for p in $(integration_paths); do
  [[ -e "$VAULT/$p" ]] && EXISTING+=("$p")
done
if [[ ${#EXISTING[@]} -gt 0 ]]; then
  tar -czf "$BACKUP_FILE" -C "$VAULT" "${EXISTING[@]}"
  info "backup: $BACKUP_FILE"
else
  info "nothing to back up (fresh install)"
  BACKUP_FILE=""
fi

restore_backup() {
  if [[ -n "$BACKUP_FILE" && -f "$BACKUP_FILE" ]]; then
    echo "[update] install failed - restoring backup..." >&2
    tar -xzf "$BACKUP_FILE" -C "$VAULT" && echo "[update] restored." >&2
  fi
}
trap restore_backup ERR

# ── Step 6: install ──────────────────────────────────────────────────────────
info "installing dist/$PLATFORM into $VAULT..."
install_build
trap - ERR

info "done. Updated $PLATFORM integration in $VAULT"
[[ -n "$BACKUP_FILE" ]] && info "previous version kept at: $BACKUP_FILE"
