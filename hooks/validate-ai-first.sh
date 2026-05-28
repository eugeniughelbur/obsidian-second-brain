#!/usr/bin/env bash
# =============================================================================
# validate-ai-first.sh — Enforce the AI-first vault rule on Write/Edit
# =============================================================================
# Fires as a Claude Code PostToolUse hook after Write/Edit. Inspects the
# written file and warns if it does not follow the AI-first rule defined in
# references/ai-first-rules.md.
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
#      quotes, smart apostrophes, Unicode math/arrows). Reports codepoint +
#      suggested ASCII replacement. Whitelist: box-drawing U+2500-257F,
#      currency (EUR/GBP/JPY), private-use/Nerd Fonts, emoji.
#
# Scope:
#   - Only inspects files inside OBSIDIAN_VAULT_PATH (env var)
#   - Skips raw/, templates/, _export/, .obsidian/, and any path containing
#     /.git/ — those are system/template paths, not first-class notes
#   - Skips any file not ending in .md
#
# Exit codes:
#   0 = pass (silent)
#   1 = warn (issue surfaced; write is NOT reverted)
# =============================================================================

INPUT=$(cat)

# Extract the written file path. Claude Code hook payload puts it at
# .tool_input.file_path for Write and Edit.
FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // .args.file_path // ""' 2>/dev/null)

# Bail silently on unparseable input or empty path
[[ -z "$FILE" ]] && exit 0
[[ "$FILE" == *.md ]] || exit 0
[[ -f "$FILE" ]] || exit 0

# Only validate inside the configured vault
VAULT="${OBSIDIAN_VAULT_PATH:-}"
[[ -z "$VAULT" ]] && exit 0
case "$FILE" in
  "$VAULT"/*) ;;
  *) exit 0 ;;
esac

# Skip non-first-class paths
case "$FILE" in
  */raw/*|*/templates/*|*/_export/*|*/.obsidian/*|*/.git/*|*/.trash/*)
    exit 0 ;;
esac

BASENAME=$(basename "$FILE")
WARNINGS=()

# ── Check 1: frontmatter delimiters ──────────────────────────────────────────
FIRST_LINE=$(head -1 "$FILE")
if [[ "$FIRST_LINE" != "---" ]]; then
  WARNINGS+=("$BASENAME has no frontmatter (expected --- on the first line). AI-first notes need date/type/tags/ai-first metadata.")
  # Without frontmatter we can't run the other checks meaningfully — surface
  # this single warning and exit.
  printf 'AI-first warning: %s\n' "${WARNINGS[0]}" >&2
  exit 1
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

def allowed(cp):
    if 0x2500 <= cp <= 0x257F: return True   # box-drawing chars
    if cp in (0x20AC, 0x00A3, 0x00A5): return True  # EUR, GBP, JPY
    if 0xE000 <= cp <= 0xF8FF: return True   # private use / Nerd Fonts
    if 0x2600 <= cp <= 0x27BF: return True   # misc symbols + dingbats
    if 0x1F300 <= cp <= 0x1FFFF: return True # emoji
    return False

path = sys.argv[1]
seen = set()
try:
    with open(path, encoding='utf-8', errors='replace') as fh:
        for lineno, line in enumerate(fh, 1):
            for ch in line:
                cp = ord(ch)
                if cp <= 127 or allowed(cp) or ch not in BANNED:
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

# ── Emit warnings ────────────────────────────────────────────────────────────
if [[ ${#WARNINGS[@]} -gt 0 ]]; then
  printf 'AI-first warnings on %s:\n' "$BASENAME" >&2
  for w in "${WARNINGS[@]}"; do
    printf '  - %s\n' "$w" >&2
  done
  printf '\nSee references/ai-first-rules.md for the full spec.\n' >&2
  exit 1
fi

exit 0
