#!/usr/bin/env bash
# =============================================================================
# adapters/lib.sh — Shared helpers for platform adapters
# =============================================================================
# Sourced by scripts/build.sh BEFORE the platform-specific adapter.sh.
# Provides parsing helpers, path rewriting, and platform-neutral filtering.
# Do NOT execute directly.
# =============================================================================

# ── Vocabulary constants ────────────────────────────────────────────────────
# Closed set of capabilities a command may declare (optional in Phase 1).
CAPABILITY_VOCAB="read write edit bash webfetch websearch task todo"

# ── Frontmatter parsing ─────────────────────────────────────────────────────

# parse_frontmatter <file> <key>
# Echoes the value of a top-level YAML key from the file's --- ... --- block.
# Empty if the key is not found.
parse_frontmatter() {
  local file="$1" key="$2"
  awk -v key="$key" '
    /^---$/ { fm++; next }
    fm == 1 {
      sub(/^[[:space:]]+/, "")
      if (match($0, "^" key ":[[:space:]]*")) {
        value = substr($0, RLENGTH + 1)
        sub(/[[:space:]]+$/, "", value)
        print value
        exit
      }
    }
    fm >= 2 { exit }
  ' "$file"
}

# command_body <file>
# Echoes everything after the closing --- of the frontmatter block.
command_body() {
  local file="$1"
  awk '
    fm < 2 && /^---$/ { fm++; next }
    fm >= 2 { print }
  ' "$file"
}

# should_include <file> <platform>
# Exit 0 if the command should be included for this platform.
# Exit 1 if its `exclude:` frontmatter list contains the platform.
should_include() {
  local file="$1" platform="$2"
  local raw; raw="$(parse_frontmatter "$file" exclude)"
  [[ -z "$raw" || "$raw" == "[]" ]] && return 0
  local tokens; tokens="$(echo "$raw" | tr -d '[]' | tr ',' ' ' | xargs)"
  for t in $tokens; do
    [[ "$t" == "$platform" ]] && return 1
  done
  return 0
}

# enumerate_commands <dir>
# Echoes one command file path per line.
enumerate_commands() {
  local dir="$1"
  [[ -d "$dir" ]] || return 0
  for f in "$dir"/*.md; do
    [[ -f "$f" ]] && echo "$f"
  done
}

# ── Routing table emission (grouped by category) ────────────────────────────

# Display order + human-readable section titles for known categories.
# Unknown categories sort alphabetically AFTER these.
CATEGORY_ORDER="vault thinking research meta"

_category_title() {
  case "$1" in
    vault)    echo "Vault — daily writing, capture, find" ;;
    thinking) echo "Thinking — synthesis, decisions, learning, reviews" ;;
    research) echo "Research — bring external sources into the vault" ;;
    meta)     echo "Meta — vault setup, health, structure" ;;
    *)        echo "${1^}" ;;
  esac
}

# emit_routing_table_grouped <commands_dir> <platform> <command_path_prefix>
# Prints a Markdown routing table grouped by category. One section per
# category in CATEGORY_ORDER order (skipping empty ones), then any unknown
# categories alphabetically.
#
# Arguments:
#   commands_dir         - source commands/ directory
#   platform             - platform name (passed to should_include)
#   command_path_prefix  - the path prefix used in the "Read this file" column
#                          (e.g. ".codex/commands" or ".gemini/commands")
emit_routing_table_grouped() {
  local src_dir="$1" platform="$2" path_prefix="$3"
  [[ -d "$src_dir" ]] || return 0

  local tmp_index; tmp_index="$(mktemp)"
  local f name desc cat
  for f in "$src_dir"/*.md; do
    [[ -f "$f" ]] || continue
    should_include "$f" "$platform" || continue
    name="$(basename "$f" .md)"
    desc="$(parse_frontmatter "$f" description)"
    desc="${desc#\"}"; desc="${desc%\"}"
    desc="${desc#\'}"; desc="${desc%\'}"
    cat="$(parse_frontmatter "$f" category)"
    [[ -z "$cat" ]] && cat="other"
    printf '%s\t%s\t%s\n' "$cat" "$name" "$desc" >> "$tmp_index"
  done

  local all_cats; all_cats="$(awk -F '\t' '{print $1}' "$tmp_index" | sort -u)"

  # Emit known categories in fixed order
  local emitted=""
  local c
  for c in $CATEGORY_ORDER; do
    if echo "$all_cats" | grep -qx "$c"; then
      _emit_one_category_section "$c" "$tmp_index" "$path_prefix"
      emitted+=" $c"
    fi
  done

  # Then any unknown categories alphabetically
  for c in $all_cats; do
    case " $emitted " in *" $c "*) continue ;; esac
    _emit_one_category_section "$c" "$tmp_index" "$path_prefix"
  done

  rm -f "$tmp_index"
}

_emit_one_category_section() {
  local cat="$1" index_file="$2" path_prefix="$3"
  local title; title="$(_category_title "$cat")"
  printf '\n### %s\n\n' "$title"
  printf '| Command | What it does | Read this file |\n'
  printf '|---|---|---|\n'
  # Sort rows in this category by command name
  awk -F '\t' -v c="$cat" '$1 == c { print $2 "\t" $3 }' "$index_file" \
    | sort \
    | while IFS=$'\t' read -r name desc; do
        printf '| `/%s` | %s | `%s/%s.md` |\n' "$name" "$desc" "$path_prefix" "$name"
      done
}

# ── Tool-name neutralization for non-Claude platforms ───────────────────────
# Rewrites Claude Code tool references to platform-neutral wording so the
# instructions still make sense in tools that don't have Claude's tool names.
rewrite_tool_neutral() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  perl -i -pe '
    s/\bRead tool\b/read files/g;
    s/\bWrite tool\b/write files/g;
    s/\bEdit tool\b/edit files/g;
    s/\bBash tool\b/run shell commands/g;
    s/\bWebFetch tool\b/fetch web pages/g;
    s/\bWebSearch tool\b/search the web/g;
    s/\bGlob tool\b/find files/g;
    s/\bGrep tool\b/search file contents/g;
    s/\bTask tool\b/spawn a subagent/g;
    s/\bTodoWrite tool\b/track tasks/g;
    s/\bAskUserQuestion tool\b/ask the user/g;
    s/\bSkill tool\b/invoke the skill/g;
    s/\bAgent tool\b/spawn a subagent/g;
  ' "$file"
}

# ── Path placeholder rewriting ──────────────────────────────────────────────
# Source files may reference .claude/ paths directly (because the repo's
# canonical use was Claude Code). The path-rewrite helper translates them to
# platform-specific equivalents (.codex/, .gemini/, .opencode/).
rewrite_platform_paths() {
  local file="$1" platform_dir="$2"
  [[ -f "$file" ]] || return 0
  perl -i -pe "s|\\.claude/|.${platform_dir}/|g;" "$file"
}
