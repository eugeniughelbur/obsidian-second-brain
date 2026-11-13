#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
# obsidian-hermes-session-end.sh - Hermes on_session_finalize vault-maintenance hook
#
# The Hermes-runtime analog of the Claude PostCompact hook (obsidian-bg-agent.sh).
# Hermes fires `on_session_finalize` hooks declared under `hooks:` in
# ~/.hermes/config.yaml, piping a JSON payload to stdin and reading JSON back
# from stdout. This hook runs the vault
# consolidation pass (the obsidian-nightly procedure) when a session is
# finalized, so the vault stays current without waiting for the nightly cron.
#
# Why not `on_session_end`: Hermes fires that event after every turn, not once
# per session, and the `hermes -z` run this hook starts fires it again. It would
# start a consolidation per turn, and each consolidation would start another.
#
# Re-entry guard: the consolidation child gets OBSIDIAN_HERMES_CONSOLIDATING=1
# and a hook that sees it exits at once; a per-user lock file (mode 0600) also
# stops a second consolidation while one is running, even from another process.
# Neither holds if the hook runs inside the Hermes gateway (the marker never
# reaches it) and the child's finalize event lands after its lock is released,
# so a per-user stamp file (mode 0600) holds the start time of the last
# consolidation, and none starts within OBSIDIAN_HERMES_MIN_INTERVAL seconds
# of it (default 21600, 6 hours; 0 turns the interval off).
#
# TRUST CAVEAT: like the Claude bg-agent, this writes to the vault UNATTENDED, so
# it is OPT-IN and ships INERT. It does nothing unless BOTH are set:
#   - OBSIDIAN_VAULT_PATH                 (where to write), AND
#   - OBSIDIAN_HERMES_HOOK_ENABLED=1      (a second, deliberate enable flag)
# It also no-ops on interrupted sessions, and never deletes/archives - add/update
# /link only.
#
# Setup:
#   1. Register this script as an on_session_finalize hook in ~/.hermes/config.yaml
#      (see hooks/hermes-hooks.config.example.yaml).
#   2. Put OBSIDIAN_VAULT_PATH and OBSIDIAN_HERMES_HOOK_ENABLED=1 in ~/.hermes/.env
#      (a shell export does not reach a gateway that is already running).
#   3. chmod +x this script.
#   4. Run `hermes --accept-hooks -z "reply OK"` once: Hermes skips a shell hook
#      nobody consented to, and only a foreground `hermes chat` asks.
# To disable: clear OBSIDIAN_HERMES_HOOK_ENABLED (the gate below makes that enough).
#
# The consolidation runs headlessly via `hermes -z` (one-shot mode: prompt as
# the argument, only the final response printed). Override with
# OBSIDIAN_HERMES_CONSOLIDATE_CMD if your build differs; the prompt is appended
# as the command's final argument.
#
# Contract: always print `{}` to stdout (silent no-op for an observer hook).
# Logs: $TMPDIR/obsidian-hermes-session-end-$(id -u).log, mode 0600

emit_noop() { printf '{}\n'; }

# Re-entry guard: the consolidation below runs a Hermes session of its own,
# which fires this hook again. The child inherits this marker, so a hook that
# finds it set is that nested run and does nothing.
[[ -n "${OBSIDIAN_HERMES_CONSOLIDATING:-}" ]] && { emit_noop; exit 0; }

VAULT="${OBSIDIAN_VAULT_PATH:-}"
[[ -z "$VAULT" ]] && { emit_noop; exit 0; }

# Opt-in gate: the second, deliberate flag. Without it the hook is inert even
# when registered.
[[ "${OBSIDIAN_HERMES_HOOK_ENABLED:-0}" != "1" ]] && { emit_noop; exit 0; }

INPUT=$(cat)

# Only consolidate sessions that finished cleanly. Interrupted sessions are
# skipped so a half-finished context is not propagated.
INTERRUPTED=$(printf '%s' "$INPUT" | jq -r '.extra.interrupted // false' 2>/dev/null || echo "false")
[[ "$INTERRUPTED" == "true" ]] && { emit_noop; exit 0; }

SESSION_ID=$(printf '%s' "$INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null || echo "unknown")
TODAY=$(date +%Y-%m-%d)

PROMPT="Read _CLAUDE.md at the vault root and follow its rules exactly. Run the \
obsidian-nightly consolidation pass for VAULT=$VAULT (TODAY=$TODAY): close the \
day, reconcile conflicting entity/concept claims, synthesize cross-source \
patterns, heal orphan links, rebuild index.md, and append a line to log.md. \
Add/update/link only - never delete, archive, or merge. Run silently, ask \
nothing. Triggered by Hermes on_session_finalize for session $SESSION_ID."

# Default headless invocation: `hermes -z` one-shot mode. Override
# OBSIDIAN_HERMES_CONSOLIDATE_CMD if your Hermes build uses a different
# non-interactive entrypoint. The prompt is passed as the final argument.
CONSOLIDATE_CMD="${OBSIDIAN_HERMES_CONSOLIDATE_CMD:-hermes -z}"

# Per-user lock file, mode 0600 (same reasoning as the log below): one
# consolidation at a time. Created with noclobber so two hooks cannot both win.
# It holds the PID of the running consolidation; a lock whose PID is gone (the
# run was killed) is stale and is replaced.
LOCK="${TMPDIR:-/tmp}/obsidian-hermes-session-end-$(id -u).lock"
acquire_lock() { ( set -C; umask 077; printf '%s\n' "$$" > "$LOCK" ) 2>/dev/null; }
if ! acquire_lock; then
  HOLDER=$(cat "$LOCK" 2>/dev/null)
  if [[ -n "$HOLDER" ]] && kill -0 "$HOLDER" 2>/dev/null; then
    emit_noop; exit 0
  fi
  rm -f "$LOCK"
  acquire_lock || { emit_noop; exit 0; }
fi

# Minimum interval, checked under the lock so two hooks cannot both pass it.
# The stamp sits next to the lock, holds the start time (epoch seconds) of the
# last consolidation, and is trusted only when it is a regular file of ours.
STAMP="${TMPDIR:-/tmp}/obsidian-hermes-session-end-$(id -u).stamp"
MIN_INTERVAL="${OBSIDIAN_HERMES_MIN_INTERVAL:-21600}"
[[ "$MIN_INTERVAL" =~ ^[0-9]+$ ]] || MIN_INTERVAL=21600
NOW=$(date +%s)
LAST=""
[[ -f "$STAMP" && ! -L "$STAMP" && -O "$STAMP" ]] && LAST=$(head -n 1 "$STAMP" 2>/dev/null)
if [[ "$LAST" =~ ^[0-9]+$ ]] && (( NOW >= LAST && NOW - LAST < MIN_INTERVAL )); then
  rm -f "$LOCK"; emit_noop; exit 0
fi
# Written to a fresh temp file and renamed over the stamp, so a symlink
# planted at the stamp path is replaced rather than followed.
if STAMP_TMP=$(umask 077; mktemp "$STAMP.XXXXXX" 2>/dev/null); then
  { printf '%s\n' "$NOW" > "$STAMP_TMP" && mv -f "$STAMP_TMP" "$STAMP"; } 2>/dev/null \
    || rm -f "$STAMP_TMP"
fi

export OBSIDIAN_HERMES_CONSOLIDATING=1

# The background run must not keep the hook's stdout open: the caller reads the
# `{}` until EOF, so an inherited pipe holds the hook open until the whole
# consolidation ends (measured: a 2 s consolidation kept the hook running 2.2 s).
# Its output goes to the log below.

(
  trap 'rm -f "$LOCK"' EXIT
  cd "$VAULT" 2>/dev/null && \
  # Per-user log path. A fixed name in the shared /tmp is world-readable
  # under a default umask and predictable, so on a multi-user host anyone
  # can read the running commentary on this vault - and can pre-create the
  # path as a symlink, since macOS does not enable protected_symlinks.
  HERMES_LOG="${TMPDIR:-/tmp}/obsidian-hermes-session-end-$(id -u).log"
  ( umask 077; : >> "$HERMES_LOG" ) 2>/dev/null || true
  $CONSOLIDATE_CMD "$PROMPT" >> "$HERMES_LOG" 2>&1
) >/dev/null 2>&1 </dev/null &
printf '%s\n' "$!" > "$LOCK" 2>/dev/null || true

emit_noop
exit 0
