#!/usr/bin/env bash
# =============================================================================
# validate-ai-first.sh - Enforce the AI-first vault rule on Write/Edit
# =============================================================================
# Fires as a Claude Code PostToolUse hook after Write/Edit (terminal) or
# create_file (VS Code extension). Inspects the written file and warns if it
# does not follow the AI-first rule defined in references/ai-first-rules.md.
#
# This is the write-time enforcement primitive: the vault stays AI-first
# because every write is checked, not because future agent remembers all
# seven rules every time.
#
# Validation (warnings, non-blocking):
#   1. Frontmatter delimiters (--- ... ---) are well-formed
#   2. No tabs inside frontmatter (YAML requires spaces)
#   3. Required AI-first fields present: date, type, tags, ai-first: true
#   4. `## For future agent` preamble exists in the body
#   5. No banned non-ASCII substitution characters (em/en-dashes, curly
#      quotes, smart apostrophes, Unicode math). Reports codepoint +
#      suggested ASCII replacement. Explicit ban list; anything not in
#      the list passes.
#   6. No secret material (API keys, private key blocks, quoted passwords)
#   7. Every tag is valid Obsidian tag syntax. Obsidian renders a bad tag
#      struck through with no error anywhere, so an agent never learns it
#      wrote one (#221). Rules: letters, digits, `_`, `-`, `/` only; no
#      spaces or dots; at least one character that is not a digit.
#
# Scope:
#   - Only inspects files inside OBSIDIAN_VAULT_PATH (env var)
#   - Skips raw/, templates/, _export/, .obsidian/, .claude/ (slash-command
#     copies and settings, not notes - #249), boards/ (kanban exception:
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

# Compare paths in one form: forward slashes and a lowercase drive letter (the
# same normalization hooks/load_vault_context.py applies). On Windows, Claude
# Code hands the hook tool_input.file_path with backslashes ("C:\Users\...")
# while OBSIDIAN_VAULT_PATH may be written with forward slashes, in the MSYS
# form (/c/Users/...), or as /cygdrive/c/..., so a plain prefix match never hit
# and the hook was a silent no-op there. On Windows shells cygpath -m maps
# every spelling to the mixed form (C:/Users/...) first; without cygpath the
# backslash flip below still covers the form Claude Code produces. Uses bash
# 3.2 features only (macOS ships 3.2).
normalize_path() {
  local p="$1"
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*)
      # Each runtime misreads the other's drive spelling (MSYS takes
      # /cygdrive/c/... as a directory under its own root, Cygwin does the
      # same with /c/...), so both are mapped to the drive form by hand before
      # cygpath sees them.
      if [[ "$p" =~ ^/cygdrive/([A-Za-z])(/.*)?$ ]]; then
        p="${BASH_REMATCH[1]}:${BASH_REMATCH[2]:-/}"
      elif [[ "$p" =~ ^/([A-Za-z])(/.*)?$ ]]; then
        p="${BASH_REMATCH[1]}:${BASH_REMATCH[2]:-/}"
      fi
      local mixed
      if mixed=$(cygpath -m -- "$p" 2>/dev/null) && [[ -n "$mixed" ]]; then p="$mixed"; fi
      p="${p//\\//}"
      local drive
      if [[ "$p" =~ ^([A-Za-z]):(.*)$ ]]; then
        drive=$(printf '%s' "${BASH_REMATCH[1]}" | tr '[:upper:]' '[:lower:]')
        p="${drive}:${BASH_REMATCH[2]}"
      fi ;;
  esac
  # Elsewhere the path is returned as given: a backslash is a legal character
  # in a macOS or Linux filename and must stay one.
  printf '%s' "$p"
}

# Comparison form of a normalized path: lowercase on Windows shells, where the
# filesystem is case-insensitive and two spellings of one folder must match;
# unchanged elsewhere. Only ever used for the comparison, never for I/O.
path_key() {
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*) printf '%s' "$1" | tr '[:upper:]' '[:lower:]' ;;
    *) printf '%s' "$1" ;;
  esac
}

INPUT=$(cat)

# Write/Edit: tool_input.file_path. VS Code create_file: tool_input.filePath.
# NotebookEdit: tool_input.notebook_path - an .ipynb, so the .md gate below
# drops it; it is read here so a notebook write is not mistaken for an unknown
# payload shape.
FILE=$(printf '%s' "$INPUT" | jq -r '
  .tool_input.file_path
  // .tool_input.filePath
  // .tool_input.notebook_path
  // .tool_input.notebookPath
  // .args.file_path
  // .args.filePath
  // ""
' 2>/dev/null)

# Unparseable input, or input that names no tool, is not a write this hook was
# asked about: bail silently. A payload that names a tool but carries no path
# key this hook knows is host drift (a new editor, a renamed field): the matcher
# fired, so a write happened, and the hook could not check it. Say so once on
# stderr and exit 1 (non-blocking; the write stands) instead of exiting 0 and
# looking exactly like "not a vault file" (#171).
if [[ -z "$FILE" ]]; then
  TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null)
  [[ -z "$TOOL" ]] && exit 0
  KEYS=$(printf '%s' "$INPUT" | jq -r '[.tool_input, .args] | map(select(type == "object")) | add // {} | keys | join(", ")' 2>/dev/null)
  printf 'AI-first hook: fired on %s but found no file path to check (payload keys: %s). The write was NOT validated.\n' "$TOOL" "${KEYS:-none}" >&2
  exit 1
fi
FILE=$(normalize_path "$FILE")
# Classification (the .md gate, the vault scope, the excluded folders) uses the
# comparison form; FILE itself stays the real path for reading the note.
FILE_KEY=$(path_key "$FILE")
[[ "$FILE_KEY" == *.md ]] || exit 0
[[ -f "$FILE" ]] || exit 0

# Only validate inside the configured vault. Environment wins; fall back to the
# documented config .env, because a plugin-marketplace install configures the
# vault there and never exports the variable - so an env-only check made this
# hook a silent no-op for exactly the installs that need it most. Same root
# cause as #160 (MCP server) and #124 (research toolkit); this is the third code
# path, swept when the hook turned out never to have been wired at all.
VAULT="${OBSIDIAN_VAULT_PATH:-}"
if [[ -z "$VAULT" ]]; then
  # Home for config and Claude Code state. On Windows shells (Git Bash, MSYS2,
  # Cygwin) that is USERPROFILE, which is what Python's Path.home() and Claude
  # Code resolve ~ to there; HOME can point at another drive (a corporate roaming
  # home) and would split the config between the bash and Python halves.
  # Elsewhere HOME is the home. Uses bash 3.2 features only.
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*)
      OSB_WIN=1
      OSB_HOME="${USERPROFILE:-$HOME}"
      OSB_HOME="$(cygpath -u "$OSB_HOME" 2>/dev/null || printf '%s' "${OSB_HOME//\\//}")" ;;
    *) OSB_WIN=0; OSB_HOME="$HOME" ;;
  esac
  ENV_FILE="${OBSIDIAN_ENV_FILE:-$OSB_HOME/.config/obsidian-second-brain/.env}"
  if [[ "$OSB_WIN" = 1 ]]; then ENV_FILE="${ENV_FILE//\\//}"; fi
  if [[ -r "$ENV_FILE" ]]; then
    VAULT=$(sed -n 's/^[[:space:]]*OBSIDIAN_VAULT_PATH[[:space:]]*=[[:space:]]*//p' "$ENV_FILE" \
      | tail -n 1 | tr -d '\r' | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
  fi
fi
[[ -z "$VAULT" ]] && exit 0
VAULT=$(normalize_path "$VAULT")
VAULT="${VAULT%/}"
VAULT_KEY=$(path_key "$VAULT")
case "$FILE_KEY" in
  "$VAULT_KEY"/*) ;;
  *) exit 0 ;;
esac

# Skip non-first-class paths. On Windows shells the match is case-insensitive
# (nocasematch, bash 3.1+), as the filesystem is, so the mixed-case entries
# below keep matching the lowercased key; elsewhere the case is exact.
case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) shopt -s nocasematch ;; esac
case "$FILE_KEY" in
  */raw/*|*/templates/*|*/_export/*|*/.obsidian/*|*/.git/*|*/.trash/*|*/.claude/*|*/boards/*|*/Boards/*|*/Logs/*|*/_CLAUDE.md|*/Home.md|*/index.md|*/log.md|*/catchup.md)
    exit 0 ;;
esac
shopt -u nocasematch

BASENAME=$(basename "$FILE")
WARNINGS=()

# A note saved with CRLF line endings (a Windows editor, git autocrlf) would fail
# every delimiter check below, because each line carries a trailing carriage
# return; the checks read a CR-free copy instead. BASENAME and the warnings
# still name the real file.
READ_FILE="$FILE"
if grep -q $'\r' "$FILE" 2>/dev/null; then
  CR_FREE=$(mktemp "${TMPDIR:-/tmp}/ai-first.XXXXXX" 2>/dev/null) || exit 0
  trap 'rm -f "$CR_FREE"' EXIT
  # A copy that failed halfway is not worth validating: silence beats a false
  # warning raised against the original.
  tr -d '\r' < "$FILE" > "$CR_FREE" || exit 0
  READ_FILE="$CR_FREE"
fi

# ── Check 1: frontmatter delimiters ──────────────────────────────────────────
FIRST_LINE=$(head -1 "$READ_FILE")
if [[ "$FIRST_LINE" != "---" ]]; then
  # Without frontmatter we can't run the other checks meaningfully - surface
  # this single warning and exit.
  emit_ai_first_warning "AI-first warning: $BASENAME has no frontmatter (expected --- on the first line). AI-first notes need date/type/tags/ai-first metadata."
fi

DELIMITER_COUNT=$(grep -c '^---$' "$READ_FILE")
if [[ "$DELIMITER_COUNT" -lt 2 ]]; then
  WARNINGS+=("$BASENAME frontmatter is missing the closing --- delimiter.")
fi

# Extract frontmatter content (between the first and second --- lines)
FRONTMATTER=$(awk '/^---$/{c++; if (c==1) next; if (c==2) exit} c==1' "$READ_FILE")

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

# ── Check 4: 'For future agent' preamble in body ────────────────────────────
BODY=$(awk '/^---$/{c++; if (c<2) next; next} c>=2' "$READ_FILE")
# Two accepted spellings (ai-first-rules.md rule #2): the `## For future agent`
# heading every command writes, and the Obsidian callout form
# `> [!info]- For future agent` (any callout type, folded or not) a vault may
# prefer so a human sees the note content first (#237). Nothing else counts.
PREAMBLE_RE='^(##[[:space:]]+|>[[:space:]]*\[![A-Za-z][A-Za-z0-9_-]*\][-+]?[[:space:]]+)For future (agent|AI|Claude|Codex)[[:space:]]*$'
if ! printf '%s\n' "$BODY" | grep -qE "$PREAMBLE_RE" ; then
  WARNINGS+=("$BASENAME missing '## For future agent' preamble (or its callout form '> [!info]- For future agent'; required by ai-first-rules.md rule #2).")
fi

# ── Check 5: non-ASCII substitution characters ───────────────────────────────
if command -v python3 >/dev/null 2>&1; then
  # The Python scans read the real file: Python's text mode handles CRLF on its
  # own, and the mktemp path is a shell path (/tmp/...) that a native Windows
  # Python cannot open when the shell does not convert arguments, which would
  # have silently disabled these two checks.
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
                    print(f"    line {lineno}: looks like a {label} - secrets never belong in vault notes; keep them in the toolkit's config file (OBSIDIAN_ENV_FILE, or the platform default the README documents) or a password manager and reference them by NAME only")
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

# ── Check 7: Obsidian tag syntax ─────────────────────────────────────────────
# Obsidian's rule: a tag may contain letters (any script), digits, `_`, `-` and
# `/` for nesting, and must contain at least one non-numeric character. `33`,
# `2.0`, `q3 2026` are all silently broken in the UI. Same rule as
# scripts/vault_health.py check_tag_syntax - keep the two in step.
if command -v python3 >/dev/null 2>&1; then
  # The script arrives on stdin (python3 -), so the frontmatter goes in via the
  # environment - piping it would be swallowed by the heredoc.
  TAG_HITS=$(AI_FIRST_FRONTMATTER="$FRONTMATTER" python3 - <<'PYEOF'
import os
import re

ALLOWED = re.compile(r"^[\w/-]+$")   # \w is Unicode-aware: letters, digits, underscore
HAS_NON_DIGIT = re.compile(r"[^\d/]")


def tags_from(frontmatter: str):
    lines = frontmatter.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^tags:\s*(.*)$", line)
        if not m:
            continue
        rest = m.group(1).strip()
        if rest.startswith("["):
            inner = rest.strip("[]")
            for t in inner.split(","):
                t = t.strip().strip("'\"")
                if t:
                    yield t
        elif rest:
            yield rest.strip("'\"")
        else:
            for nxt in lines[i + 1:]:
                lm = re.match(r"^\s+-\s*(.+?)\s*$", nxt)
                if not lm:
                    break
                yield lm.group(1).strip().strip("'\"")
        return


def problem(tag: str):
    t = tag.lstrip("#")
    if not t:
        return "empty tag"
    if " " in t or "\t" in t:
        return "contains whitespace (Obsidian cannot render it) - use `-` between words"
    if "." in t:
        return "contains `.` (Obsidian cannot render it) - use `-` or spell it out"
    if not ALLOWED.match(t):
        return "contains characters outside letters/digits/_/-// (Obsidian cannot render it)"
    if not HAS_NON_DIGIT.search(t):
        return "is digits only (Obsidian renders it struck through) - prefix a word, e.g. `store-" + t + "`"
    return None


for tag in tags_from(os.environ.get("AI_FIRST_FRONTMATTER", "")):
    why = problem(tag)
    if why:
        print(f"    tag `{tag}` {why}")
PYEOF
  )
  if [[ -n "$TAG_HITS" ]]; then
    WARNINGS+=("$BASENAME has tags Obsidian will render broken (no error is ever shown for these):")
    while IFS= read -r hit; do
      [[ -n "$hit" ]] && WARNINGS+=("$hit")
    done <<< "$TAG_HITS"
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
