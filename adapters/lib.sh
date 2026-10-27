#!/usr/bin/env bash
# =============================================================================
# adapters/lib.sh - Shared helpers for platform adapters
# =============================================================================
# Sourced by scripts/build.sh BEFORE the platform-specific adapter.sh.
# Provides parsing helpers, path rewriting, and platform-neutral filtering.
# Do NOT execute directly.
# =============================================================================

# ── Frontmatter parsing ─────────────────────────────────────────────────────

# parse_frontmatter <file> <key>
# Echoes the value of a top-level YAML key from the file's --- ... --- block.
# Empty if the key is not found.
parse_frontmatter() {
  local file="$1" key="$2"
  LC_ALL=C awk -v key="$key" '
    NR == 1 { sub(/^\xef\xbb\xbf/, "") }
    { sub(/\r$/, "") }
    /^---$/ { fm++; next }
    fm == 1 {
      sub(/^[[:space:]]+/, "")
      if (match($0, "^" key ":[[:space:]]*")) {
        value = substr($0, RLENGTH + 1)
        sub(/[[:space:]]+$/, "", value)
        # Block scalar: the value is on the following, more-indented lines.
        # Without this the caller received a literal ">" or "|", which is
        # non-empty and so silently defeats every empty-value fallback.
        if (value == ">" || value == "|" || value == ">-" || value == "|-" ||
            value == ">+" || value == "|+") {
          value = ""
          while ((getline line) > 0) {
            sub(/\r$/, "", line)
            if (line ~ /^---$/) break
            if (line !~ /^[[:space:]]/ || line ~ /^[[:space:]]*$/) {
              if (line ~ /^[[:space:]]*$/) continue
              break
            }
            sub(/^[[:space:]]+/, "", line)
            sub(/[[:space:]]+$/, "", line)
            value = (value == "" ? line : value " " line)
          }
        }
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
  LC_ALL=C awk '
    NR == 1 { sub(/^\xef\xbb\xbf/, "") }
    { sub(/\r$/, "") }
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

# ── Routing table emission (grouped by category) ────────────────────────────

# Display order + human-readable section titles for known categories.
# Unknown categories sort alphabetically AFTER these.
CATEGORY_ORDER="vault thinking research meta"

_category_title() {
  case "$1" in
    vault)    echo "Vault - daily writing, capture, find" ;;
    thinking) echo "Thinking - synthesis, decisions, learning, reviews" ;;
    research) echo "Research - bring external sources into the vault" ;;
    meta)     echo "Meta - vault setup, health, structure" ;;
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

# ── Trigger phrase emission ─────────────────────────────────────────────────
# Each command can declare triggers per language:
#   triggers_en: ["save this", "save the conversation"]
#   triggers_es: ["guardar esto", "guardar la conversación"]
#
# emit_trigger_reference <commands_dir> <platform>
# Prints a "Trigger phrases" section, grouped by language then by category.
# Only languages that have at least one populated triggers_<lang> line in
# at least one command will appear in the output.
emit_trigger_reference() {
  local src_dir="$1" platform="$2"
  [[ -d "$src_dir" ]] || return 0

  local langs; langs="$(_detect_languages "$src_dir")"
  [[ -z "$langs" ]] && return 0

  printf '\n## Trigger phrases\n\n'
  printf 'When the user says any of the phrases below (or a close paraphrase), follow the matching command file.\n'

  local lang
  for lang in $langs; do
    _emit_trigger_lang_block "$src_dir" "$platform" "$lang"
  done
}

# Detect which trigger languages are present across all commands.
# Returns a space-separated list ordered: en first, then alphabetical.
_detect_languages() {
  local src_dir="$1"
  local langs
  langs="$(grep -h -oE '^triggers_[a-z]{2}:' "$src_dir"/*.md 2>/dev/null \
           | sed -E 's/^triggers_([a-z]{2}):.*/\1/' \
           | sort -u)"
  # Move 'en' to the front if present
  local out=""
  if echo "$langs" | grep -qx en; then
    out="en"
    langs="$(echo "$langs" | grep -vx en || true)"
  fi
  for l in $langs; do
    out="${out:+$out }$l"
  done
  echo "$out"
}

# Human-readable label for a language code.
_lang_label() {
  case "$1" in
    en) echo "English" ;;
    es) echo "Español" ;;
    it) echo "Italiano" ;;
    fr) echo "Français" ;;
    de) echo "Deutsch" ;;
    pt) echo "Português" ;;
    ru) echo "Русский" ;;
    ja) echo "日本語" ;;
    zh) echo "简体中文" ;;
    *)  echo "${1^^}" ;;
  esac
}

# Emit one language block: bullet list per command grouped by category.
_emit_trigger_lang_block() {
  local src_dir="$1" platform="$2" lang="$3"
  local label; label="$(_lang_label "$lang")"
  printf '\n### %s (`%s`)\n\n' "$label" "$lang"

  local index; index="$(mktemp)"
  local f name cat raw triggers
  for f in "$src_dir"/*.md; do
    [[ -f "$f" ]] || continue
    should_include "$f" "$platform" || continue
    raw="$(parse_frontmatter "$f" "triggers_$lang")"
    [[ -z "$raw" || "$raw" == "[]" ]] && continue
    name="$(basename "$f" .md)"
    cat="$(parse_frontmatter "$f" category)"
    [[ -z "$cat" ]] && cat="other"
    # Strip [ ] and collapse quoting differences for display
    triggers="$(echo "$raw" | sed -E 's/^\[//; s/\]$//')"
    printf '%s\t%s\t%s\n' "$cat" "$name" "$triggers" >> "$index"
  done

  local all_cats; all_cats="$(awk -F '\t' '{print $1}' "$index" | sort -u)"
  local c emitted=""
  for c in $CATEGORY_ORDER; do
    if echo "$all_cats" | grep -qx "$c"; then
      _emit_one_trigger_category "$c" "$index"
      emitted+=" $c"
    fi
  done
  for c in $all_cats; do
    case " $emitted " in *" $c "*) continue ;; esac
    _emit_one_trigger_category "$c" "$index"
  done

  rm -f "$index"
}

_emit_one_trigger_category() {
  local cat="$1" index_file="$2"
  local title; title="$(_category_title "$cat")"
  printf '\n**%s**\n\n' "$title"
  awk -F '\t' -v c="$cat" '$1 == c { print $2 "\t" $3 }' "$index_file" \
    | sort \
    | while IFS=$'\t' read -r name triggers; do
        printf -- '- `/%s` - %s\n' "$name" "$triggers"
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
# Command bodies name two kinds of path that only resolve under Claude Code:
#
#   1. The SKILL_ROOT placeholder. Claude Code supplies a "Skill root" value at
#      session start; no other platform does. Every Python-backed command reads
#      `uv run --directory "SKILL_ROOT" scripts/foo.py`, so SKILL_ROOT must
#      become the directory that CONTAINS scripts/ and references/ in the built
#      tree. Critically, the bare `scripts/foo.py` that follows is relative to
#      --directory and must be left alone; prefixing it yields a double path.
#
#   2. Bare `references/...` paths in prose (references/ai-first-rules.md alone
#      appears in every command). These are opened directly by the agent, so
#      they need the platform prefix.
#
# Historically only a `.claude/` rule existed here. No command or reference file
# contains a repo-relative `.claude/` path, so that rule matched nothing and the
# real paths shipped unrewritten. It is kept below as a cheap safety net.

# Rewrite SKILL_ROOT to the directory holding scripts/ and references/.
# Pass a path that resolves from the working directory the platform actually
# runs in, not from the built tree. `.` only works where the agent's CWD is the
# install root; hermes points the agent at the vault instead, so it passes the
# concrete install path (#191).
rewrite_skill_root() {
  local file="$1" skill_root="$2"
  [[ -f "$file" ]] || return 0
  SKILL_ROOT_REPL="$skill_root" perl -i -pe 's{SKILL_ROOT}{$ENV{SKILL_ROOT_REPL}}g' "$file"
}

# Rewrite directly-named paths so they resolve inside the built tree.
# Pass an empty platform_dir for builds that ship references/ at the root.
rewrite_platform_paths() {
  local file="$1" platform_dir="$2"
  [[ -f "$file" ]] || return 0
  PLATFORM_DIR="$platform_dir" perl -i -pe '
    my $d = $ENV{PLATFORM_DIR};
    next unless length $d;
    s|\.claude/|.$d/|g;
    s~(^|[^A-Za-z0-9_./-])\.?/?references/~$1.$d/references/~g;
  ' "$file"
}

# ── Shared emit helpers ─────────────────────────────────────────────────────
# These bodies were duplicated across adapters, which is how pi ended up as the
# one build shipping scripts with no pyproject.toml beside them (B19) and how
# the reference-copy step drifted into applying a different set of rewrites per
# platform (S16). One definition, so a fix lands everywhere at once.

# copy_scripts_with_project <src-scripts-dir> <dst-scripts-dir>
# Copies the Python toolkit AND the uv project beside it. `uv run --directory
# <root>` needs the project to resolve both the module path and dependencies.
copy_scripts_with_project() {
  local src="$1" dst="$2"
  [[ -d "$src" ]] || return 0
  mkdir -p "$dst"
  cp -R "$src/." "$dst/"
  cp "$src/../pyproject.toml" "$(dirname "$dst")/pyproject.toml"
  copy_vault_ops "$src/.." "$(dirname "$dst")"
}

# copy_vault_ops <src-root> <dst-root>
# scripts/ imports vault_ops from integrations/obsidian-mcp-server/ beside it:
# the research vault scan (scripts/research/lib/vault_terms.py) and the eval
# scripts. A build that ships scripts/ without it crashes /research-deep and
# /notebooklm with ModuleNotFoundError (#332). Same relative path, so the
# imports resolve unchanged; vault_ops needs only stdlib and scripts/osb_env.py.
copy_vault_ops() {
  local src="$1/integrations/obsidian-mcp-server/vault_ops.py"
  local dst="$2/integrations/obsidian-mcp-server"
  [[ -f "$src" ]] || return 0
  mkdir -p "$dst"
  cp "$src" "$dst/vault_ops.py"
}

# copy_references_rewritten <src-refs-dir> <dst-refs-dir> <platform_dir>
# Copies the shared specs and applies the same rewrites everywhere. Pass an
# empty platform_dir for builds that ship references/ at their tree root.
copy_references_rewritten() {
  local src="$1" dst="$2" platform_dir="${3-}"
  [[ -d "$src" ]] || return 0
  mkdir -p "$dst"
  cp -R "$src/." "$dst/"
  local f
  while IFS= read -r -d '' f; do
    rewrite_tool_neutral "$f"
    rewrite_platform_paths "$f" "$platform_dir"
  done < <(find "$dst" -type f -name '*.md' -print0)
}

# format_triggers <raw-frontmatter-value>
# Turns `["save this", "save the conversation"]` into `save this, save the
# conversation`. Was copy-pasted byte-for-byte into three adapters.
format_triggers() {
  echo "$1" | tr -d '[]"' | sed 's/,/, /g; s/  */ /g; s/^ *//; s/ *$//'
}

# strip_quotes <value>
# Frontmatter values may arrive single- or double-quoted. Four call sites
# stripped a different subset, so the same description rendered clean on one
# platform and garbled on another.
strip_quotes() {
  local v="$1"
  v="${v#\"}"; v="${v%\"}"
  v="${v#\'}"; v="${v%\'}"
  printf '%s' "$v"
}

# skill_display_title <identifier>
# Print an ATX H1 for a skill directory name: obsidian-save -> "# Obsidian Save".
# ASCII only. Skill ids are [a-z0-9-], and locale-aware toupper can turn a
# leading "i" into a non-ASCII capital.
skill_display_title() {
  awk -v name="$1" 'BEGIN {
    n = split(name, parts, "-")
    out = ""
    for (i = 1; i <= n; i++) {
      word = parts[i]
      if (length(word) == 0) continue
      c = substr(word, 1, 1)
      pos = index("abcdefghijklmnopqrstuvwxyz", c)
      if (pos > 0) c = sprintf("%c", pos + 64)
      word = c substr(word, 2)
      out = out (out == "" ? "" : " ") word
    }
    print "# " out
  }'
}

# emit_skill_title <command-file> <skill-name>
# Print the skill's own title as the first body heading, then a blank line.
#
# OpenClaw's skill picker (openclaw/openclaw#184724) takes the display name
# from the first ATX H1. The agent-skills and grok-bot builds embed
# references/ai-first-rules.md, which opens with "# AI-First Note Rules".
# A command whose body has no H1 of its own then publishes that shared
# heading as its name. The title goes first so the embedded spec, which is
# appended unchanged later, is no longer the first heading.
#
# A command that already has an H1 (commands/crew.md opens with "# Crew")
# keeps that heading. Emitting a second one would duplicate it.
emit_skill_title() {
  local file="$1" name="$2"
  if command_body "$file" | grep -q '^# [^#]'; then
    return 0
  fi
  skill_display_title "$name"
  echo
}

# emit_ai_first_rule <references_path>
# Step 3 of every dispatcher's "How to operate" block: the AI-first write spec
# summary. Was hand-copied into four adapters with only the path differing,
# which is exactly how B21 happened - two of the four cited a path that did not
# exist in their own build, and nobody noticed because each was maintained
# separately. CLAUDE.md says this rule must change in lockstep across platforms;
# one definition is what makes that true rather than aspirational.
# emit_ai_first_rule <refs_path> [step_number]
# The single home for the AI-first rule summary. step_number defaults to 3
# with_trigger_policy <description> <trigger-mode>
# Fold the proactive-vs-explicit selection policy into a generated description.
#
# Adapters that emit native skills write their own frontmatter, so a source
# `trigger-mode: proactive` does not travel unless the adapter puts it there.
# It was encoded in agent-skills only, which left codex-cli, hermes and pi
# shipping purely reactive skills - 7 of the 8 commands that declare the field
# are proactive, so those builds lost the signal on all 7 (#181, reported by
# @konsone). The adapters that copy the command body verbatim (claude-code,
# gemini-cli, opencode) keep the frontmatter and do not need this.
#
# One definition rather than four, for the same reason emit_ai_first_rule is:
# copies drift silently, and the drift is invisible per platform.
with_trigger_policy() {
  local desc="$1" trigmode="$2"
  if [[ "$trigmode" == "proactive" ]]; then
    printf '%s' "$desc Use proactively: trigger this whenever the conversation produces something worth capturing, without waiting to be asked."
  else
    printf '%s' "$desc Use only when the user explicitly asks for it."
  fi
}

# because that is its slot in the "How to operate" block; agent-skills passes 4
# for its global-rule snippet. Parameterised rather than copied, so
# test_dispatcher_prose can keep asserting one definition exists.
emit_ai_first_rule() {
  local refs_path="$1" step="${2:-3}"
  cat <<EOF
${step}. Treat the AI-first vault rule as non-negotiable for every note you write:
   \`## For future agent\` preamble, rich frontmatter (\`type\`, \`date\`,
   \`tags\`, \`ai-first: true\`), \`[[wikilinks]]\` for every
   person/project/concept, recency markers per external claim, sources
   verbatim, confidence levels where applicable. The full spec is
   \`${refs_path}\`, a path relative to the install root. If it does not
   resolve from your working directory, search upward for it. If you still
   cannot read it, say so before writing - the seven requirements above still
   apply, and a note written while the spec was unreachable must never look
   the same as one written with it in hand.
EOF
}

# owner_of <platform>
# The claimed owner of a platform build, from the table in adapters/OWNERS.md,
# or empty when unclaimed. OWNERS.md is the single source of truth so the table
# a person edits and the credit that ships are never two separate edits.
owner_of() {
  local platform="$1" owners="${REPO_ROOT:-.}/adapters/OWNERS.md"
  [[ -f "$owners" ]] || return 0
  LC_ALL=C awk -v p="$platform" '
    /<!-- owners:start -->/ { on = 1; next }
    /<!-- owners:end -->/   { on = 0 }
    on && /^\|/ {
      # | platform | owner | previously |
      split($0, f, "|")
      gsub(/^[ \t]+|[ \t]+$/, "", f[2])
      gsub(/^[ \t]+|[ \t]+$/, "", f[3])
      if (f[2] == p && f[3] != "unclaimed" && f[3] != "Owner" && f[3] != "") { print f[3]; exit }
    }
  ' "$owners"
}

# append_owner_credit <dist_dir> <platform>
# Ships the credit inside the artifact rather than only in a table in the repo.
# A named owner on the install page a user actually reads is the whole incentive
# the ownership model runs on; a row in a governance file nobody opens is not.
append_owner_credit() {
  local dst="$1" platform="$2" owner
  owner="$(owner_of "$platform")"
  [[ -n "$owner" ]] || return 0
  [[ -f "$dst/INSTALL.md" ]] || return 0
  printf '\n---\n\nThis build is maintained by %s. Issues specific to this platform are theirs to triage: https://github.com/eugeniughelbur/obsidian-second-brain/issues\n' \
    "$owner" >> "$dst/INSTALL.md"
}
