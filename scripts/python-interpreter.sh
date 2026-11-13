#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
# =============================================================================
# python-interpreter.sh - find a Python that actually runs
# =============================================================================
# Sourced by scripts that shell out to Python, and copied inline into the two
# hooks (hooks/load_vault_context.sh, hooks/validate-ai-first.sh) because those
# are handed to other harnesses' hook systems by hand and must stay standalone.
# tests/test_python_interpreter.py fails when a copy drifts.
#
# Usage:
#   . "<repo>/scripts/python-interpreter.sh"
#   PYTHON=$(osb_python) || { echo "no python" >&2; exit 1; }
#   $PYTHON script.py          # unquoted: the value may be several words
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
