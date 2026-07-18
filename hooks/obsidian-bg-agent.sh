#!/usr/bin/env bash
# obsidian-bg-agent.sh - PostCompact vault propagation hook
#
# Fires after Claude compacts the conversation context. Reads the session
# summary from stdin (JSON), then runs a headless Claude agent to propagate
# everything worth preserving to the vault.
#
# TRUST CAVEAT: this agent writes to the vault UNATTENDED using
# --dangerously-skip-permissions. For that reason it is OPT-IN and ships INERT.
# It requires BOTH of the following before it does anything:
#   - OBSIDIAN_VAULT_PATH set (where to write), AND
#   - OBSIDIAN_BG_AGENT_ENABLED=1 (a second, deliberate enable flag)
# setup.sh sets the first but never the second, so the agent stays inert after a
# normal install. See hooks/postcompact.hook.example.json for the opt-in steps.
#
# Setup:
#   1. Set OBSIDIAN_VAULT_PATH in the env section of ~/.claude/settings.json
#   2. Set OBSIDIAN_BG_AGENT_ENABLED=1 in the same env section to enable
#   3. Register this script as a PostCompact hook (see postcompact.hook.example.json)
#   4. Make executable: chmod +x hooks/obsidian-bg-agent.sh
# To disable again: clear OBSIDIAN_BG_AGENT_ENABLED (the gate below makes that enough).
#
# Optional:
#   - CLAUDE_VAULT_PROPAGATION=1 lets the origin project's CLAUDE.md steer
#     propagation. If set, and the compacting project has a "## Vault
#     propagation hints" section in its CLAUDE.md, that section (only) is
#     injected into the prompt as project-specific rules, ranked below the
#     vault's own _CLAUDE.md. Ships inert (same philosophy as the enable flag).
#
# Logs:
#   - /tmp/obsidian-bg-agent.log        - stdout/stderr of the headless run
#   - $VAULT/.claude-runs/YYYY-MM-DD.jsonl - one JSONL line per run outcome
#     (early-exit reason, or starting + completed with duration and exit code)

VAULT="${OBSIDIAN_VAULT_PATH:-}"
[[ -z "$VAULT" ]] && exit 0

# Opt-in gate: no-op unless the user deliberately enabled the agent. This is the
# second of the two flags; without it the hook does nothing even when registered.
[[ "${OBSIDIAN_BG_AGENT_ENABLED:-0}" != "1" ]] && exit 0

# --- Observability -----------------------------------------------------------
# Every decision point below used to be a bare `exit 0`, indistinguishable from
# "nothing to do", and the headless run's exit code vanished into a detached
# subshell. We now record one JSONL line per outcome under the vault so a run
# that decided not to propagate - or failed - is never silent.
RUN_ID="$(date +%s)-$$"
START_TIME=$(date +%s)
RUNS_DIR="$VAULT/.claude-runs"
mkdir -p "$RUNS_DIR" 2>/dev/null || true

# Portable file mtime in epoch seconds: GNU / Git-Bash `stat -c`, BSD / macOS
# `stat -f`; 0 if neither works so callers never divide by a missing value.
file_mtime() {
  stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo 0
}

# log_run <status> [key val [key val ...]]  - append one JSONL line.
# JSON is built by jq (integers via --argjson, strings via --arg) so escaping is
# correct even for Windows backslash paths - hand-rolling the JSON in shell was
# fragile. Fails loud: any jq error leaves a degraded marker line rather than
# silently dropping the record.
log_run() {
  local status="$1"; shift
  local file="$RUNS_DIR/$(date +%Y-%m-%d).jsonl"
  local jq_args=(--arg run_id "$RUN_ID" --arg status "$status" --argjson ts "$(date +%s)")
  local filter='{run_id:$run_id, status:$status, ts:$ts'
  while [[ $# -ge 2 ]]; do
    local key="$1" val="$2"; shift 2
    if [[ "$val" =~ ^-?[0-9]+$ ]]; then jq_args+=(--argjson "$key" "$val")
    else jq_args+=(--arg "$key" "$val"); fi
    filter+=", ${key}:\$${key}"
  done
  jq -nc "${jq_args[@]}" "$filter}" >> "$file" 2>/dev/null \
    || printf '{"run_id":"%s","status":"_log_run_error","for":"%s"}\n' "$RUN_ID" "$status" >> "$file"
}

# --- Burst-dedup lock --------------------------------------------------------
# Two sessions compacting within seconds of each other fire two hooks at the
# same vault. A short-TTL lock drops the second. The trap releases on hook exit,
# so this dedups burst double-fires; it does not serialize the full headless run
# (that would need a TTL longer than a real run). The 120s TTL also reaps a lock
# orphaned by a hook that died before its trap ran.
LOCK="$VAULT/.claude-lock"
if [[ -f "$LOCK" ]]; then
  AGE=$(( $(date +%s) - $(file_mtime "$LOCK") ))
  if [[ $AGE -lt 120 ]]; then
    log_run "lock_contention" lock_age_sec "$AGE"; exit 0
  fi
fi
touch "$LOCK"
trap 'rm -f "$LOCK"' EXIT

# PostCompact stdin includes `transcript_path`; the compaction summary itself
# is written into the transcript JSONL as entries with `isCompactSummary: true`.
# We read the most recent one here.
INPUT=$(cat)
TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // ""' 2>/dev/null || true)
if [[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then
  log_run "no_transcript"; exit 0
fi

# Stream the JSONL (transcripts can be 100MB+). base64-encode each match so the
# multi-line content stays on one line, then decode the most recent one.
SUMMARY=$(jq -rc 'select(.isCompactSummary == true) | .message.content // "" | @base64' "$TRANSCRIPT" 2>/dev/null | tail -n 1 | base64 -d 2>/dev/null || true)
if [[ -z "$SUMMARY" ]]; then
  log_run "no_summary"; exit 0
fi

TODAY=$(date +%Y-%m-%d)

# Optional: pull project-specific propagation rules from the compacting
# project's CLAUDE.md. Marker-based extraction so the agent ingests only the
# section addressed to it, never the whole repo CLAUDE.md.
ORIGIN_CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // ""' 2>/dev/null || true)
PROJECT_HINTS=""
if [[ "${CLAUDE_VAULT_PROPAGATION:-0}" == "1" && -n "$ORIGIN_CWD" && -f "$ORIGIN_CWD/CLAUDE.md" ]]; then
  PROJECT_HINTS=$(awk '
    /^## Vault propagation hints/ { capture=1; next }
    /^## / && capture { exit }
    capture { print }
  ' "$ORIGIN_CWD/CLAUDE.md")
fi

# Build prompt in a temp file to handle special characters in the summary safely
PROMPT_FILE=$(mktemp /tmp/obsidian-bg-XXXXXX.txt)

cat > "$PROMPT_FILE" << HEADER
You are an autonomous Obsidian vault agent. The Claude session was just compacted.
Propagate everything worth preserving from the summary to the vault. Run silently.

VAULT: $VAULT
TODAY: $TODAY

SESSION SUMMARY:
HEADER

printf '%s\n\n' "$SUMMARY" >> "$PROMPT_FILE"

# Inject project-specific rules between the summary and the standing
# instructions, with explicit precedence below the vault's own _CLAUDE.md so a
# sloppy or hostile repo CLAUDE.md can never override vault authority.
if [[ -n "$PROJECT_HINTS" ]]; then
  cat >> "$PROMPT_FILE" << PROJECTRULES
PROJECT-SPECIFIC RULES (from $ORIGIN_CWD/CLAUDE.md section "Vault propagation hints"):
$PROJECT_HINTS

Precedence: vault _CLAUDE.md > project rules (above) > skill defaults.

PROJECTRULES
fi

cat >> "$PROMPT_FILE" << 'INSTRUCTIONS'
INSTRUCTIONS:
1. Read _CLAUDE.md at the vault root first - follow its rules exactly. Where silent, use defaults.
2. Identify all vault-worthy items in the summary:
   - Decisions made or confirmed
   - Tasks created, assigned, or completed
   - People mentioned (new interactions, context added)
   - Projects worked on or updated
   - Dev work done (code written, bugs fixed, features shipped)
   - Ideas, learnings, or insights
   - Shoutouts or mentions worth logging
3. Before creating any note, search for an existing one. Never duplicate.
4. Update or create notes as appropriate. Resolve every folder from _CLAUDE.md's
   Folder Map (wiki-style wiki/entities|projects|logs|daily, Obsidian-style
   People/|Projects/|Dev Logs/|Daily/ - use whichever layout the vault has):
   - People: update the person's note interaction log; create a stub if missing
   - Projects: update status, Recent Activity, Key Decisions sections
   - Dev work: create or update the dev log YYYY-MM-DD - Project.md; link from project note
   - Tasks: add to the right kanban board column (use TODAY date from above)
   - Ideas: save to the ideas/concepts folder
   - Decisions: append to the relevant project note's Key Decisions section
5. Update today's daily note ([TODAY].md in the resolved daily folder):
   - Create it from the Daily Note template if it does not exist
   - Link everything you touched - people, projects, dev logs, decisions
6. Propagate everywhere:
   - Nothing is saved in isolation
   - Every write ripples to the daily note, boards, and linked notes per the write rules

CONSTRAINTS:
- Use filesystem tools only (Read, Write, Edit, Glob, Grep) - MCP is not available in this subprocess.
- Run completely silently. No output to the user. No questions.
- If the summary contains nothing vault-worthy, exit without making any changes.
- Match the vault's existing writing style, frontmatter schemas, and naming conventions exactly.
- Do not archive, delete, or merge anything - only add or update.
- SENSITIVE CONTENT stays out of entity/project/concept notes when running
  unattended. If the summary contains credentials or secrets (API keys,
  passwords, tokens), health details, personal finances, intimate or
  relationship matters, or legal disputes: do NOT propagate them into normal
  notes. Instead append a one-line pointer (topic only, no details) to a
  staging note "Staging [TODAY].md" in the vault's inbox/capture folder per
  _CLAUDE.md (vault root if none), so the human reviews and places it
  deliberately. Raw secrets (the actual key/password strings) are NEVER
  written anywhere - not even in staging; name that they exist, nothing more.
INSTRUCTIONS

log_run "starting" summary_chars "${#SUMMARY}" hints_chars "${#PROJECT_HINTS}"

# Run headless agent in vault directory - async, logs to /tmp for debugging.
# Feed the prompt via stdin, NOT as an argv element. `claude -p "$PROMPT"`
# passes the whole prompt as one command-line argument and hits the ~32K
# CreateProcess limit on Git Bash for Windows ("Argument list too long",
# exit 126) - silently, because this subshell is detached and its exit code is
# never read. stdin has no such limit. Real compaction summaries reach 24K+
# chars, so this is not a theoretical edge. Delete the temp file after the
# subprocess exits (not before spawn), then record the outcome.
#
# --strict-mcp-config: this agent uses filesystem tools only (see CONSTRAINTS in
# the prompt: "MCP is not available in this subprocess"). Without the flag the
# headless run still loads every enabled MCP server, contradicting that contract
# and wasting startup - and worse, for users running an MCP-based bot (e.g. a
# Telegram/Slack integration) alongside Claude Code, this background run can
# seize the bot's single MCP session and disrupt the live poller.
(
  cd "$VAULT" || exit 1
  claude --dangerously-skip-permissions --strict-mcp-config -p < "$PROMPT_FILE" >> /tmp/obsidian-bg-agent.log 2>&1
  EXIT_CODE=$?
  rm -f "$PROMPT_FILE"
  log_run "completed" duration_sec "$(( $(date +%s) - START_TIME ))" exit_code "$EXIT_CODE"
) &

exit 0
