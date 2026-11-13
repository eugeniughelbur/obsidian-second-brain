#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
# =============================================================================
# load_vault_context.sh - SessionStart hook entry point
# =============================================================================
# hooks.json used to run `python3 load_vault_context.py` directly. On Windows
# that name belongs to the Microsoft Store App Execution Alias, which prints
# nothing and exits non-zero, so the hook injected no skill root and no vault
# manual and left one line in the session transcript to say so (#269). This
# wrapper finds an interpreter that runs, and when there is none it says so on
# stderr instead of failing mutely.
#
# stdin (the SessionStart payload) passes straight through to the Python half.
# =============================================================================

# ── osb_python ───────────────────────────────────────────────────────────────
# Echo a Python that actually runs, or nothing with a non-zero status.
# `command -v python3` is not enough, and on Windows it is actively wrong: the
# python.org installers - the default way to get Python there - ship python.exe
# and py.exe and never python3.exe, so `python3` resolves to the Microsoft Store
# App Execution Alias. That stub exists, prints nothing and exits non-zero, so an
# existence test passes and the caller silently does nothing (#269). Every
# candidate is therefore executed, not looked up. Uses bash 3.2 features only.
osb_python() {
  local candidate
  # Unquoted on purpose: "py -3" is a command plus an argument.
  for candidate in python3 python "py -3"; do
    if $candidate -c "import sys" >/dev/null 2>&1; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  # Last resort: uv, which the toolkit already requires for its research scripts
  # and which brings its own interpreter when the system has none on PATH.
  if uv run --no-project python -c "import sys" >/dev/null 2>&1; then
    printf '%s' "uv run --no-project python"
    return 0
  fi
  return 1
}

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON=$(osb_python) || {
  printf 'obsidian-second-brain: no working Python found (tried python3, python, py -3, uv run). SessionStart context was NOT injected - this session has no skill root and no vault manual. Install Python from python.org or uv from astral.sh, then start a new session.\n' >&2
  exit 1
}

# Unquoted: PYTHON may be several words ("py -3", "uv run --no-project python").
exec $PYTHON "$HOOK_DIR/load_vault_context.py"
