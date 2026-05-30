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
# Logs: /tmp/obsidian-bg-agent.log

VAULT="${OBSIDIAN_VAULT_PATH:-}"
[[ -z "$VAULT" ]] && exit 0

# Opt-in gate: no-op unless the user deliberately enabled the agent. This is the
# second of the two flags; without it the hook does nothing even when registered.
[[ "${OBSIDIAN_BG_AGENT_ENABLED:-0}" != "1" ]] && exit 0

# PostCompact stdin includes `transcript_path`; the compaction summary itself
# is written into the transcript JSONL as entries with `isCompactSummary: true`.
# We read the most recent one here.
INPUT=$(cat)
TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // ""' 2>/dev/null || true)
[[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]] && exit 0

# Stream the JSONL (transcripts can be 100MB+). base64-encode each match so the
# multi-line content stays on one line, then decode the most recent one.
SUMMARY=$(jq -rc 'select(.isCompactSummary == true) | .message.content // "" | @base64' "$TRANSCRIPT" 2>/dev/null | tail -n 1 | base64 -d 2>/dev/null || true)
[[ -z "$SUMMARY" ]] && exit 0

TODAY=$(date +%Y-%m-%d)

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
4. Update or create notes as appropriate:
   - People: update People/Name.md interaction log; create a stub if missing
   - Projects: update status, Recent Activity, Key Decisions sections
   - Dev work: create or update Dev Logs/YYYY-MM-DD - Project.md; link from project note
   - Tasks: add to the right Boards/ kanban column (use TODAY date from above)
   - Ideas: save to Ideas/ folder
   - Decisions: append to the relevant project note's Key Decisions section
5. Update today's daily note (Daily/[TODAY].md using the TODAY value above):
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
INSTRUCTIONS

PROMPT=$(cat "$PROMPT_FILE")
rm -f "$PROMPT_FILE"

# Run headless agent in vault directory - async, logs to /tmp for debugging
(
  cd "$VAULT" && \
  claude --dangerously-skip-permissions -p "$PROMPT" >> /tmp/obsidian-bg-agent.log 2>&1
) &

exit 0
