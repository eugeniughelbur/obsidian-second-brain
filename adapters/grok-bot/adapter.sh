#!/usr/bin/env bash
# =============================================================================
# adapters/grok-bot/adapter.sh - Grok Bot / Sand platform adapter
# =============================================================================
# Grok Bot (aka Sand) reads the obsidian-second-brain MCP server for vault I/O
# and runs SKILL.md workflow files for playbooks. This adapter compiles the
# platform-neutral commands/ into Grok-runnable SKILL.md files.
#
# Emits, at the dist root:
#   skills/<name>/SKILL.md        - one skill per command (45; calendar is
#                                   excluded). Frontmatter is name + description
#                                   (when to use). Body tells the agent to use
#                                   MCP obsidian_* tools for all vault I/O.
#   skills/obsidian-core/         - the shared engine skill carrying references/,
#                                   scripts/, and pyproject.toml for Python-backed
#                                   commands.
#   INSTALL.md                    - how workflows and MCP work on Grok Bot / Sand.
#
# Design notes:
#   - Each skill body opens with that skill's own title (an H1), then MCP vault
#     I/O instructions telling the agent to use obsidian_* tools rather than
#     filesystem operations. The title has to be the first heading: a picker
#     that names a skill from the first body H1 would otherwise show the
#     embedded write spec's heading (openclaw/openclaw#184724).
#   - references/ai-first-rules.md is embedded in every command skill so the
#     non-negotiable write spec survives even a cherry-picked install. The
#     spec is appended after the title and is not rewritten.
#   - The trigger policy (proactive vs explicit) is encoded in each description.
#   - Grok Bot has no hook runtime, so no SessionStart or PostToolUse hooks.
#   - Python-backed research commands still need the scripts/ directory accessible;
#     the preamble tells the agent how to resolve that path.
# =============================================================================

GROK_PLATFORM="grok-bot"
GROK_SKILLS_DIR="skills"
GROK_CORE="obsidian-core"

adapter_build() {
  local src="$1" dst="$2"

  _grok_emit_skills "$src/commands" "$dst/$GROK_SKILLS_DIR" "$src/references/ai-first-rules.md"
  _grok_emit_core "$src" "$dst/$GROK_SKILLS_DIR/$GROK_CORE"
  _grok_emit_install_hint "$dst"
}

# Emit one Grok Bot skill per command at skills/<name>/SKILL.md.
_grok_emit_skills() {
  local src="$1" dst="$2" ai_rules="$3"
  [[ -d "$src" ]] || return 0
  local f name desc triggers category trigmode trig_clean out
  for f in "$src"/*.md; do
    [[ -f "$f" ]] || continue
    should_include "$f" "$GROK_PLATFORM" || continue

    name="$(basename "$f" .md)"
    desc="$(parse_frontmatter "$f" description)"
    triggers="$(parse_frontmatter "$f" triggers_en)"
    category="$(parse_frontmatter "$f" category)"
    trigmode="$(parse_frontmatter "$f" trigger-mode)"
    [[ -z "$category" ]] && category="other"
    [[ -z "$desc" ]] && desc="Run the $name command of the obsidian-second-brain skill."
    desc="$(strip_quotes "$desc")"

    # Fold English triggers into the description for implicit selection.
    if [[ -n "$triggers" ]]; then
      trig_clean="$(format_triggers "$triggers")"
      [[ -n "$trig_clean" ]] && desc="$desc Triggers: $trig_clean."
    fi

    # Encode the selection policy.
    desc="$(with_trigger_policy "$desc" "$trigmode")"

    mkdir -p "$dst/$name"
    out="$dst/$name/SKILL.md"
    {
      echo "---"
      echo "name: $name"
      printf 'description: "%s"\n' "${desc//\"/\\\"}"
      echo "---"
      echo
      # Title H1 first. See emit_skill_title in adapters/lib.sh.
      emit_skill_title "$f" "$name"
      if [[ "$name" == "crew" ]]; then
        # Crew needs a Python runner and shared folder, not the vault MCP.
        command_body "$f" | sed 's|SKILL_ROOT|skills/obsidian-core|g'
      else
        _grok_preamble
        _grok_rewrite_command_body "$f"
      fi
      echo
      echo "---"
      echo
      echo "## AI-first vault rule (embedded)"
      echo
      echo "The write spec below is non-negotiable for every note this skill creates or"
      echo "updates. It is embedded here so it applies even on a partial install."
      echo
      cat "$ai_rules"
    } > "$out"

    rewrite_tool_neutral "$out"
    # Rewrite bare references/ paths to .agents/skills/obsidian-core/references/
    # (the perl adds the leading dot, so pass without it)
    rewrite_platform_paths "$out" "agents/skills/obsidian-core"
    if [[ "$name" == "crew" ]]; then
      # The Grok tree is installed as skills/, not .agents/skills/.
      perl -i -pe 's|\.agents/skills/obsidian-core/|skills/obsidian-core/|g' "$out"
    fi
  done
}

# The MCP-first preamble prepended to every command skill body.
_grok_preamble() {
  cat <<'EOF'
## Setup (read first)

**MCP vault I/O.** All vault operations go through the `user-obsidian-second-brain`
MCP server. Use these MCP tools for vault reads, writes, and queries:

- `obsidian_search(query, limit)` - search the vault (lexical + semantic)
- `obsidian_read_note(path)` - read a note by vault-relative path
- `obsidian_save_note(title, content, note_type, tags)` - create a new note
- `obsidian_update_note(path, append, heading, set_fields)` - update an existing note
- `obsidian_replace_note_section(path, heading, new_content)` - replace a section
- `obsidian_move_note(path, new_path)` - move or rename a note
- `obsidian_capture(idea_text)` - quick-capture an idea (minimal schema)
- `obsidian_validate_note(path)` - validate against the AI-first spec
- `obsidian_backlinks(target)` - find notes linking to a target
- `obsidian_vault_health()` - run a full vault health check

**After writing any note, always call `obsidian_validate_note` with the path** to
ensure it meets the AI-first spec. The validator will report any issues.

**Vault root.** The MCP server resolves it from `$OBSIDIAN_VAULT_PATH` or the
configured vault path. You do not need to resolve it yourself - the MCP tools
handle vault-relative paths.

**Python-backed commands.** A few research commands shell out to Python helpers.
The scripts live in the `obsidian-core` skill alongside this one. When a command
body below references a Python script, run it via the MCP server's environment or
locate the `scripts/` directory from the distributed skill tree.

EOF
}

# Rewrite command body to use MCP tools instead of filesystem operations.
# Transform Read/Write/Edit tool language into MCP tool calls.
_grok_rewrite_command_body() {
  local file="$1"
  command_body "$file" | perl -pe '
    # Rewrite SKILL_ROOT to point at obsidian-core location
    # Use a path that won`t be picked up as a false reference citation
    s/SKILL_ROOT\/references\//skills\/obsidian-core\/references\//g;
    s/SKILL_ROOT/skills\/obsidian-core/g;
    s/its absolute path was given at session start as \*\*Skill root\*\*/locate the obsidian-core skill in your skill tree/g;
    s/from the skill root \(/from the obsidian-core skill \(/g;
    
    # Rewrite filesystem Read operations to obsidian_read_note
    s/Read `([^`]+\.md)`/call obsidian_read_note("$1")/g;
    s/read `([^`]+\.md)`/call obsidian_read_note("$1")/g;
    
    # Rewrite general "read files" to MCP read/search
    s/\bread files?\b/use MCP obsidian_read_note or obsidian_search/g;
    
    # Rewrite Write/create operations to obsidian_save_note
    s/\bWrite\s+([^\s]+)\s+to\s+/call obsidian_save_note to create /g;
    s/\bcreate\s+`([^`]+\.md)`/call obsidian_save_note/g;
    
    # Rewrite Edit/update operations to obsidian_update_note
    s/\bEdit\s+([^\s]+)\b/call obsidian_update_note("$1")/g;
    s/\bupdate\s+([^\s]+)\b/call obsidian_update_note("$1")/g;
    
    # Remove Claude-specific agent spawning language
    s/\bSpawn parallel subagents\b/Process in parallel where possible/g;
    s/\bsubagent\b/separate process/g;
    
    # Remove /execute and slash command references (Grok uses @ or plain invocation)
    s/Execute `\/obsidian-([a-z-]+)`/Run obsidian-$1/g;
    s/`\/obsidian-([a-z-]+)`/obsidian-$1/g;
  '
}

# Emit the shared obsidian-core skill carrying references/ and scripts/.
_grok_emit_core() {
  local src="$1" dst="$2"
  mkdir -p "$dst"

  # references/
  if [[ -d "$src/references" ]]; then
    mkdir -p "$dst/references"
    cp -R "$src/references/." "$dst/references/"
  fi
  # scripts/ + pyproject.toml (for Python-backed research commands)
  if [[ -d "$src/scripts" ]]; then
    mkdir -p "$dst/scripts"
    cp -R "$src/scripts/." "$dst/scripts/"
    copy_vault_ops "$src" "$dst"  # see adapters/lib.sh (#332)
  fi
  [[ -f "$src/pyproject.toml" ]] && cp "$src/pyproject.toml" "$dst/pyproject.toml"

  # SKILL.md - not invoked directly, just carries the support files
  cat > "$dst/SKILL.md" <<'EOF'
---
name: obsidian-core
description: "Shared engine for the obsidian-second-brain skills - the AI-first write spec (references/), the Python research toolkit (scripts/), and its uv project (pyproject.toml). Support files only; the other skills reference it. Do not invoke directly."
---

## What this is

The shared support tree the other obsidian-second-brain skills depend on. It is
not a task skill - do not run it on its own.

- `references/` - shared specs. `references/ai-first-rules.md` is the canonical,
  non-negotiable vault-write spec; `vault-schema.md`, `folder-map.md`, and
  `freshness-policy.md` back the other skills. These paths are relative to the
  install root, which is load-bearing: if one does not resolve from your working
  directory, search upward for it, and say so before writing if you still cannot
  read it. Every command skill also embeds the AI-first spec inline, so the rule
  survives an unreachable path - but an unreachable path must never pass in
  silence.
- `scripts/` - Python helpers for the research toolkit (research, research-deep,
  x-read, x-pulse, youtube, podcast, notebooklm, obsidian-architect). The command
  skills invoke them as `uv run -m scripts.research.<name> ...` or
  `uv run scripts/<name>.py ...`.
- `pyproject.toml` - makes this directory a self-contained uv project, so both
  modules and dependencies resolve without a separate install step.

When a command needs these, locate the obsidian-core skill directory in your
skill tree and reference it there.
EOF
}

_grok_emit_install_hint() {
  local dst="$1"
  local GROK_CMD_COUNT=0
  GROK_CMD_COUNT="$(find "$dst/$GROK_SKILLS_DIR" -mindepth 1 -maxdepth 1 -type d \
                    ! -name "$GROK_CORE" 2>/dev/null | wc -l | tr -d ' ')"
  cat > "$dst/INSTALL.md" <<EOF
# Install on Grok Bot / Sand

This build compiles the obsidian-second-brain commands into workflow SKILL.md
files that Grok Bot and Sand agents run. The \`user-obsidian-second-brain\` MCP
server (already connected in Grok Bot) provides the vault I/O layer; the compiled
skills are the playbooks.

The tree contains \`skills/<name>/SKILL.md\` (${GROK_CMD_COUNT} command skills) plus the shared
\`skills/${GROK_CORE}/\` engine skill (references, scripts, pyproject for Python-backed
research commands).

## How it works

- **Workflows are invoked with \`/\` or \`@\`.** Each SKILL.md is a self-contained
  playbook: name, description (when to use it), and operating instructions. Grok Bot
  and Sand load these as workflows you invoke by name.
- **MCP is the I/O layer.** Every vault read, write, search, or validation goes
  through the \`user-obsidian-second-brain\` MCP server's \`obsidian_*\` tools
  (\`obsidian_search\`, \`obsidian_read_note\`, \`obsidian_save_note\`,
  \`obsidian_update_note\`, \`obsidian_validate_note\`, etc.). The skills tell the
  agent which tool to call and how to structure the data.
- **No filesystem operations.** Unlike Claude Code or Codex (which use Read/Write
  tools on markdown files directly), Grok Bot skills exclusively use MCP tools.
  The agent never touches \`.md\` files - all vault I/O is mediated by the MCP server.

## Prerequisites

What you need: a plan that includes Grok Bot. Premium, Super and Ultra on The X Subscription include it, with one weekly usage pool shared with Grok and Cursor. Older paid Cursor plans and linked SuperGrok or X Premium+ accounts work too (https://cursor.com/help/grok-bot/plans).

1. **MCP server connected.** Grok Bot already has the \`user-obsidian-second-brain\`
   MCP server available. Verify it by asking: "Do you have access to obsidian_search
   and obsidian_save_note?" The agent should confirm these MCP tools are present.

2. **Vault path configured.** The MCP server needs to know your vault location.
   The \`user-obsidian-second-brain\` MCP is pre-configured in Grok Bot. If you're
   using a different vault, ensure \`OBSIDIAN_VAULT_PATH\` points to your vault root
   (configured in the MCP server settings, not in Grok Bot itself).

## Installation

Grok Bot and Sand workflows are loaded from wherever you store your SKILL.md files.
The exact mechanism depends on your Grok Bot / Sand setup. Common patterns:

**Option A: Load skills into your workspace**

Place the skills where your Grok Bot session can access them:

\`\`\`bash
# From the repo root, after: bash scripts/build.sh --platform grok-bot
cp -R dist/grok-bot/skills /path/to/your/grok-workspace/
\`\`\`

**Option B: Reference skills directly**

If your Grok Bot setup supports skill directories, point it at the built tree:

\`\`\`bash
# After building
ls dist/grok-bot/skills/
# obsidian-save/, obsidian-find/, obsidian-daily/, ...
\`\`\`

Consult your Grok Bot / Sand documentation for the canonical skill loading path.

## Usage

Once loaded, invoke skills by name:

- "Save this conversation to my vault" → triggers \`obsidian-save\`
- "Find notes about the new project" → triggers \`obsidian-find\`
- "What's on my daily note today?" → triggers \`obsidian-daily\`
- Or explicitly: \`@obsidian-save\` or \`/obsidian-save\`

The agent will use the MCP \`obsidian_*\` tools under the hood, format the notes
according to the AI-first spec (embedded in every skill), and validate the output
automatically via \`obsidian_validate_note\`.

Grok Bot can write a live Page, such as a report, a dashboard, or a plan. The Page opens from a card in the chat, stays in the bot's Library, and you can share it with only you, your team, or anyone with the link. A weekly review or a project dashboard from your vault fits this.

On an iPhone 15 Pro or later, pressing and holding the Action Button starts a voice chat with Grok Bot. You need Grok Bot 1.16 or later, and you set it in iPhone Settings > Action Button > Shortcut. Use it to speak a thought and save it into the vault.

## What is NOT covered

- **Hooks** - Grok Bot has no hook runtime. There are no SessionStart or PostToolUse
  hooks. The skills are self-contained and do not rely on hooks.
- **Scheduled agents** - The morning/nightly/weekly/health routines are not included
  in this build. They remain a Claude Code / Hermes extra.
- **Calendar command** - \`/obsidian-calendar\` requires the Google Calendar MCP and
  is excluded from this build. It ships on Claude Code only.
- **Direct file access** - This build does not emit \`.agents/skills/\` or
  \`~/.agents/skills/\` paths (those are Codex / agent-skills conventions). Grok Bot
  workflows are standalone SKILL.md files, not Agent Skills.

## Verification

After installation:

1. Ask the agent: "Do you have the obsidian-save skill?"
2. Try a simple command: "Search my vault for project notes"
3. Save something: "Save this conversation with AI-first formatting"

The agent should confirm it has the skills and use the MCP tools to execute them.

## Troubleshooting

- **"I don't have access to obsidian_search"** → The MCP server is not connected.
  Verify \`user-obsidian-second-brain\` MCP is enabled in your Grok Bot settings.
- **"I can't find the skill"** → The SKILL.md files are not in a location Grok Bot
  is scanning. Check your skill loading path.
- **"The note wasn't saved"** → Check \`OBSIDIAN_VAULT_PATH\` in the MCP server
  configuration. The MCP server needs to know where your vault is.
EOF
}
