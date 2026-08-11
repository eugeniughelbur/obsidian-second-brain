#!/usr/bin/env bash
# =============================================================================
# validate-ai-first.sh - Enforce the AI-first vault rule on Write/Edit
# =============================================================================
# Fires as a Claude Code PostToolUse hook after Write/Edit (terminal) or
# create_file (VS Code extension). Inspects the written file and warns if it
# does not follow the AI-first rule defined in references/ai-first-rules.md.
#
# This is the write-time enforcement primitive: the vault stays AI-first
# because every write is checked, not because future-Claude remembers all
# seven rules every time.
#
# Validation (warnings, non-blocking):
#   1. Frontmatter delimiters (--- ... ---) are well-formed
#   2. No tabs inside frontmatter (YAML requires spaces)
#   3. Required AI-first fields present: date, type, tags, ai-first: true
#   4. `## For future Claude` preamble exists in the body
#   5. No banned non-ASCII substitution characters (em/en-dashes, curly
#      quotes, smart apostrophes, Unicode math). Reports codepoint +
#      suggested ASCII replacement. Explicit ban list; anything not in
#      the list passes.
#
# Scope:
#   - Only inspects files inside OBSIDIAN_VAULT_PATH (env var)
#   - Skips raw/, templates/, _export/, .obsidian/, boards/ (kanban exception:
#     an H2 preamble renders as a phantom column), vault-surface files
#     (_CLAUDE.md, Home.md, index.md, log.md, catchup.md, per-day Logs/ -
#     operating surfaces, not knowledge notes), and any path containing
#     /.git/ - those are system/template paths, not first-class notes
#   - Skips any file not ending in .md
#
# Exit codes:
#   0 = pass (silent), or warn via JSON on stdout (write is NOT reverted)
# =============================================================================

# Warn via Claude Code hook JSON (systemMessage + additionalContext). stderr
# is mirrored for logs; exit 0 so the host parses stdout.
emit_ai_first_warning() {
  local msg="$1"
  printf '%s\n' "$msg" >&2
  jq -n --arg msg "$msg" '{
    systemMessage: $msg,
    decision: "block",
    reason: $msg,
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: $msg
    }
  }'
  exit 0
}

INPUT=$(cat)

# Write/Edit: tool_input.file_path. VS Code create_file: tool_input.filePath.
FILE=$(printf '%s' "$INPUT" | jq -r '
  .tool_input.file_path
  // .tool_input.filePath
  // .args.file_path
  // .args.filePath
  // ""
' 2>/dev/null)

# Bail silently on unparseable input or empty path
[[ -z "$FILE" ]] && exit 0
[[ "$FILE" == *.md ]] || exit 0
[[ -f "$FILE" ]] || exit 0

# Only validate inside the configured vault. Environment wins; fall back to the
# documented config .env, because a plugin-marketplace install configures the
# vault there and never exports the variable - so an env-only check made this
# hook a silent no-op for exactly the installs that need it most. Same root
# cause as #160 (MCP server) and #124 (research toolkit); this is the third code
# path, swept when the hook turned out never to have been wired at all.
VAULT="${OBSIDIAN_VAULT_PATH:-}"
if [[ -z "$VAULT" ]]; then
  ENV_FILE="${OBSIDIAN_ENV_FILE:-$HOME/.config/obsidian-second-brain/.env}"
  if [[ -r "$ENV_FILE" ]]; then
    VAULT=$(sed -n 's/^[[:space:]]*OBSIDIAN_VAULT_PATH[[:space:]]*=[[:space:]]*//p' "$ENV_FILE" \
      | tail -n 1 | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
  fi
fi
[[ -z "$VAULT" ]] && exit 0
VAULT="${VAULT%/}"
case "$FILE" in
  "$VAULT"/*) ;;
  *) exit 0 ;;
esac

# Skip non-first-class paths
case "$FILE" in
  */raw/*|*/templates/*|*/_export/*|*/.obsidian/*|*/.git/*|*/.trash/*|*/boards/*|*/Boards/*|*/Logs/*|*/_CLAUDE.md|*/Home.md|*/index.md|*/log.md|*/catchup.md)
    exit 0 ;;
esac

BASENAME=$(basename "$FILE")
WARNINGS=()

# ── Check 1: frontmatter delimiters ──────────────────────────────────────────
FIRST_LINE=$(head -1 "$FILE")
if [[ "$FIRST_LINE" != "---" ]]; then
  # Without frontmatter we can't run the other checks meaningfully - surface
  # this single warning and exit.
  emit_ai_first_warning "AI-first warning: $BASENAME has no frontmatter (expected --- on the first line). AI-first notes need date/type/tags/ai-first metadata."
fi

DELIMITER_COUNT=$(grep -c '^---$' "$FILE")
if [[ "$DELIMITER_COUNT" -lt 2 ]]; then
  WARNINGS+=("$BASENAME frontmatter is missing the closing --- delimiter.")
fi

# Extract frontmatter content (between the first and second --- lines)
FRONTMATTER=$(awk '/^---$/{c++; if (c==1) next; if (c==2) exit} c==1' "$FILE")

# ── Check 2: tabs in frontmatter ─────────────────────────────────────────────
TAB_CHAR=$'\t'
if printf '%s' "$FRONTMATTER" | grep -q "$TAB_CHAR"; then
  WARNINGS+=("$BASENAME frontmatter contains tab characters. YAML requires spaces only.")
fi

# ── Check 3: required AI-first frontmatter fields ────────────────────────────
has_field() {
  local key="$1"
  printf '%s\n' "$FRONTMATTER" | grep -qE "^${key}:"
}

has_field "date"  || WARNINGS+=("$BASENAME missing 'date:' in frontmatter.")
has_field "type"  || WARNINGS+=("$BASENAME missing 'type:' in frontmatter.")
has_field "tags"  || WARNINGS+=("$BASENAME missing 'tags:' in frontmatter.")

if ! printf '%s\n' "$FRONTMATTER" | grep -qE '^ai-first:[[:space:]]*true[[:space:]]*$'; then
  WARNINGS+=("$BASENAME missing 'ai-first: true' in frontmatter.")
fi

# ── Check 4: 'For future Claude' preamble in body ────────────────────────────
BODY=$(awk '/^---$/{c++; if (c<2) next; next} c>=2' "$FILE")
if ! printf '%s\n' "$BODY" | grep -qE '^##[[:space:]]+For future Claude' ; then
  WARNINGS+=("$BASENAME missing '## For future Claude' preamble (required by ai-first-rules.md rule #2).")
fi

# ── Check 5: non-ASCII substitution characters ───────────────────────────────
if command -v python3 >/dev/null 2>&1; then
  NON_ASCII_HITS=$(python3 - "$FILE" <<'PYEOF'
import sys

BANNED = {
    '—': ('U+2014 em-dash',            ' - '),
    '–': ('U+2013 en-dash',             ' - '),
    '“': ('U+201C left double quote',   '"'),
    '”': ('U+201D right double quote',  '"'),
    '‘': ('U+2018 left single quote',   "'"),
    '’': ('U+2019 right single quote',  "'"),
    '≥': ('U+2265 >=',                  '>='),
    '≤': ('U+2264 <=',                  '<='),
    '≠': ('U+2260 !=',                  '!='),
    '…': ('U+2026 ellipsis',            '...'),
    ' ': ('U+00A0 non-breaking space',  ' '),
}

path = sys.argv[1]
seen = set()
try:
    with open(path, encoding='utf-8', errors='replace') as fh:
        for lineno, line in enumerate(fh, 1):
            for ch in line:
                if ch not in BANNED:
                    continue
                key = (lineno, ch)
                if key in seen:
                    continue
                seen.add(key)
                name, suggest = BANNED[ch]
                print(f"    line {lineno}: {name} -- try {suggest!r}")
except OSError:
    pass
PYEOF
  )
  if [[ -n "$NON_ASCII_HITS" ]]; then
    WARNINGS+=("$BASENAME contains banned non-ASCII substitution characters:")
    while IFS= read -r hit; do
      [[ -n "$hit" ]] && WARNINGS+=("$hit")
    done <<< "$NON_ASCII_HITS"
  fi
fi

# ── Check 6: secrets never belong in a vault note ────────────────────────────
# High-precision patterns only (a false positive here trains people to ignore
# the hook). Catches real key material, not the word "password" in prose.
if command -v python3 >/dev/null 2>&1; then
  SECRET_HITS=$(python3 - "$FILE" <<'PYEOF'
import re
import sys

PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"), "sk- API key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), "GitHub personal token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"), "GitHub fine-grained token"),
    (re.compile(r"\bxox[bpars]-[A-Za-z0-9-]{10,}\b"), "Slack token"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "Google API key"),
    (re.compile(r"(?i)\b(?:password|passwd)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"), "quoted password assignment"),
]

path = sys.argv[1]
try:
    with open(path, encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            for pat, label in PATTERNS:
                if pat.search(line):
                    print(f"    line {lineno}: looks like a {label} - secrets never belong in vault notes; keep them in ~/.config/obsidian-second-brain/.env or a password manager and reference them by NAME only")
                    break
except OSError:
    pass
PYEOF
  )
  if [[ -n "$SECRET_HITS" ]]; then
    WARNINGS+=("$BASENAME appears to contain secret material:")
    while IFS= read -r hit; do
      [[ -n "$hit" ]] && WARNINGS+=("$hit")
    done <<< "$SECRET_HITS"
  fi
fi

# ── Emit warnings ────────────────────────────────────────────────────────────
if [[ ${#WARNINGS[@]} -gt 0 ]]; then
  MSG="AI-first warnings on ${BASENAME}:"$'\n'
  for w in "${WARNINGS[@]}"; do
    MSG+="  - ${w}"$'\n'
  done
  MSG+=$'\n'"See references/ai-first-rules.md for the full spec."
  emit_ai_first_warning "$MSG"
fi

exit 0
