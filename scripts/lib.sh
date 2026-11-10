#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
# =============================================================================
# scripts/lib.sh - Shared utility helpers for build orchestration
# =============================================================================
# Sourced by scripts/build.sh. Provides logging primitives and error helpers.
# Do NOT execute directly.
# =============================================================================

# Colour codes for terminal output
if [[ -t 1 ]]; then
  _C_RESET="$(printf '\033[0m')"
  _C_INFO="$(printf '\033[36m')"
  _C_OK="$(printf '\033[32m')"
  _C_WARN="$(printf '\033[33m')"
  _C_ERR="$(printf '\033[31m')"
else
  _C_RESET="" _C_INFO="" _C_OK="" _C_WARN="" _C_ERR=""
fi

info()    { printf '%s[info]%s %s\n' "$_C_INFO" "$_C_RESET" "$*"; }
success() { printf '%s[ok]%s %s\n'   "$_C_OK"   "$_C_RESET" "$*"; }
warn()    { printf '%s[warn]%s %s\n' "$_C_WARN" "$_C_RESET" "$*" >&2; }
die()     { printf '%s[err]%s %s\n'  "$_C_ERR"  "$_C_RESET" "$*" >&2; exit 1; }
