#!/usr/bin/env bash
# =============================================================================
# adapters/agent-skills/adapter.sh - unified Agent Skills adapter
# =============================================================================
# One spec-compliant Agent Skills tree that every harness on the open
# `.agents/skills/` standard reads: Google Antigravity, OpenAI Codex CLI, and
# OpenCode. The three converged on the same path and the same progressive-
# disclosure contract (name + description always visible, body lazy-loaded), so
# a single build serves all of them instead of a near-duplicate adapter each.
#
# Emits, at the dist root:
#   skills/<name>/SKILL.md        - one skill per command (43; calendar is
#                                   Claude-only). Frontmatter is spec-minimal
#                                   (name, description, metadata.category) so
#                                   OpenCode's strict validator accepts it.
#   skills/obsidian-core/         - the shared engine skill: references/,
#                                   scripts/, and pyproject.toml. The command
#                                   skills' `uv run --directory SKILL_ROOT ...`
#                                   invocations are rewritten to point here.
#   INSTALL.md                    - skills.sh story + manual `cp -R` fallback.
#   global-rule-snippet.md        - optional always-on vault-routing rule.
#
# Design notes that matter:
#   - NO SKILL.md at the tree root: a shallow SKILL.md shadows every nested
#     skill in skills.sh discovery. The tree root carries docs only.
#   - Each skill body opens with that skill's own title (an H1), then a
#     vault-root resolution preamble ($OBSIDIAN_VAULT_PATH else the working
#     directory) so the skills are self-sufficient - no session-start hook
#     required. The title has to be the first heading: a picker that names a
#     skill from the first body H1 would otherwise show the embedded write
#     spec's heading (openclaw/openclaw#184724).
#   - references/ai-first-rules.md is embedded in every command skill so the
#     non-negotiable write spec survives even a cherry-picked install. The
#     spec is appended after the title and is not rewritten.
#   - The trigger policy (proactive vs explicit) is encoded in each description,
#     the only signal these harnesses use for implicit selection. Source
#     `trigger-mode: proactive` opts a command in; default is explicit.
# =============================================================================

ASK_PLATFORM="agent-skills"
ASK_SKILLS_DIR="skills"
ASK_CORE="obsidian-core"
# Workspace-relative location of the shared engine skill once installed. The
# command skills' script/reference paths are rewritten to this.
ASK_CORE_PATH=".agents/skills/${ASK_CORE}"

adapter_build() {
  local src="$1" dst="$2"

  _ask_emit_skills "$src/commands" "$dst/$ASK_SKILLS_DIR" "$src/references/ai-first-rules.md"
  _ask_emit_core "$src" "$dst/$ASK_SKILLS_DIR/$ASK_CORE"
  _ask_emit_install_hint "$dst"
  _ask_emit_global_rule "$dst"
}

# Emit one Agent Skill per command at skills/<name>/SKILL.md.
_ask_emit_skills() {
  local src="$1" dst="$2" ai_rules="$3"
  [[ -d "$src" ]] || return 0
  local f name desc triggers category trigmode trig_clean out
  for f in "$src"/*.md; do
    [[ -f "$f" ]] || continue
    should_include "$f" "$ASK_PLATFORM" || continue

    name="$(basename "$f" .md)"
    desc="$(parse_frontmatter "$f" description)"
    triggers="$(parse_frontmatter "$f" triggers_en)"
    category="$(parse_frontmatter "$f" category)"
    trigmode="$(parse_frontmatter "$f" trigger-mode)"
    [[ -z "$category" ]] && category="other"
    [[ -z "$desc" ]] && desc="Run the $name command of the obsidian-second-brain skill."
    # Strip any surrounding quotes the source may carry.
    desc="$(strip_quotes "$desc")"

    # Fold English triggers into the description for implicit selection.
    if [[ -n "$triggers" ]]; then
      trig_clean="$(format_triggers "$triggers")"
      [[ -n "$trig_clean" ]] && desc="$desc Triggers: $trig_clean."
    fi

    # Encode the selection policy - the one lever these harnesses read.
    desc="$(with_trigger_policy "$desc" "$trigmode")"

    mkdir -p "$dst/$name"
    out="$dst/$name/SKILL.md"
    {
      echo "---"
      echo "name: $name"
      printf 'description: "%s"\n' "${desc//\"/\\\"}"
      echo "metadata:"
      echo "  category: $category"
      echo "---"
      echo
      # Title H1 first. See emit_skill_title in adapters/lib.sh.
      emit_skill_title "$f" "$name"
      # Crew can run without a vault; its command owns setup and discovery.
      [[ "$name" == "crew" ]] || _ask_preamble
      command_body "$f"
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
    rewrite_skill_root "$out" "$ASK_CORE_PATH"
    # Bare `references/...` paths in command prose resolve against the installed
    # obsidian-core skill, not the harness CWD. ASK_CORE_PATH already carries the
    # leading dot, so strip it for the platform-dir argument.
    rewrite_platform_paths "$out" "${ASK_CORE_PATH#.}"
  done
}

# The self-sufficiency preamble prepended to every command skill body.
_ask_preamble() {
  cat <<EOF
## Setup (read first)

**Vault root.** Resolve it before reading or writing: use the \`\$OBSIDIAN_VAULT_PATH\`
environment variable if it is set, otherwise use your current working directory.
Read \`_CLAUDE.md\` at the vault root first if it exists - it holds the user's vault
conventions (folder map, daily-note format, naming).

**Shared engine.** Script and reference paths below point at \`${ASK_CORE_PATH}\` -
the \`${ASK_CORE}\` skill installed alongside this one. Run script commands from your
workspace root so that relative path resolves; if you installed skills globally, use
the absolute path to the installed \`${ASK_CORE}\` directory instead.

EOF
}

# Emit the shared obsidian-core skill: a SKILL.md (so skills.sh treats it as an
# installable skill and lands it in .agents/skills/obsidian-core/) plus the
# references/, scripts/, and pyproject.toml the command skills call into.
_ask_emit_core() {
  local src="$1" dst="$2"
  mkdir -p "$dst"

  # references/
  if [[ -d "$src/references" ]]; then
    mkdir -p "$dst/references"
    cp -R "$src/references/." "$dst/references/"
  fi
  # scripts/ + pyproject.toml (self-contained uv project)
  if [[ -d "$src/scripts" ]]; then
    mkdir -p "$dst/scripts"
    cp -R "$src/scripts/." "$dst/scripts/"
    copy_vault_ops "$src" "$dst"  # see adapters/lib.sh (#332)
  fi
  [[ -f "$src/pyproject.toml" ]] && cp "$src/pyproject.toml" "$dst/pyproject.toml"

  # SKILL.md - carries the discovery frontmatter; instructs the agent not to
  # invoke it directly. metadata.category is spec-minimal like the rest.
  cat > "$dst/SKILL.md" <<EOF
---
name: ${ASK_CORE}
description: "Shared engine for the obsidian-second-brain skills - the AI-first write spec (references/), the Python research + health toolkit (scripts/), and its uv project (pyproject.toml). Support files only; the other skills call into it. Do not invoke directly. Install it alongside the command skills."
metadata:
  category: meta
---

## What this is

The shared support tree the other obsidian-second-brain skills depend on. It is
not a task skill - do not run it on its own.

- \`references/\` - shared specs. \`references/ai-first-rules.md\` is the canonical,
  non-negotiable vault-write spec; \`vault-schema.md\`, \`folder-map.md\`, and
  \`freshness-policy.md\` back the other skills. These paths are relative to the
  install root, which is load-bearing: if one does not resolve from your working
  directory, search upward for it, and say so before writing if you still cannot
  read it. Every command skill also embeds the AI-first spec inline, so the rule
  survives an unreachable path - but an unreachable path must never pass in
  silence.
- \`scripts/\` - Python helpers for the research toolkit and vault health. The
  command skills invoke them as
  \`uv run --directory ${ASK_CORE_PATH} -m scripts.research.<name> ...\`
  (or \`uv run --directory ${ASK_CORE_PATH} scripts/<name>.py ...\`), run from
  your workspace root.
- \`pyproject.toml\` - makes this directory a self-contained uv project, so both
  modules and dependencies resolve without a separate install step.

If you installed the skills globally rather than into a workspace, replace
\`${ASK_CORE_PATH}\` in those commands with the absolute path to this directory.
EOF
}

_ask_emit_install_hint() {
  local dst="$1"
  # Computed, not hardcoded. The previous literals (43 / 44) went stale on every
  # command added or excluded, so the documented verification step told the user
  # to expect a number the build does not produce - worse than no check.
  local ASK_CMD_COUNT=0 f
  for f in "$(dirname "$dst")"/../commands/*.md; do :; done
  ASK_CMD_COUNT="$(find "$dst/$ASK_SKILLS_DIR" -mindepth 1 -maxdepth 1 -type d \
                    ! -name "$ASK_CORE" 2>/dev/null | wc -l | tr -d ' ')"
  cat > "$dst/INSTALL.md" <<EOF
# Install as Agent Skills (Antigravity / Codex CLI / OpenCode)

This build is one spec-compliant Agent Skills tree. Every harness that reads the
open \`.agents/skills/\` standard - Google **Antigravity**, OpenAI **Codex CLI**,
**OpenCode**, and **GitHub Copilot CLI** among them - discovers these skills
automatically: each skill's name and description stay visible, and the full body
loads only when the skill is selected (progressive disclosure).

The tree contains \`skills/<name>/SKILL.md\` (${ASK_CMD_COUNT} command skills) plus the shared
\`skills/${ASK_CORE}/\` engine skill (references, scripts, pyproject). There is
deliberately **no SKILL.md at the tree root** - a root SKILL.md shadows the
nested skills during discovery.

## Where you start the harness is load-bearing

Start your harness **from the vault root**, or have the vault under git. This is
a requirement, not a convenience:

- Codex CLI walks up to the **git root** looking for \`.agents/skills\`. A
  git-backed vault therefore works from any subfolder.
- A plain Obsidian vault is not a git repo. In that case, opening the harness in
  any subfolder registers **zero** skills - no warning, no error, the skill list
  is simply empty.
- The \`.agents/skills/${ASK_CORE}/references/\` paths the skills cite are
  relative to this root too. Start elsewhere and the AI-first spec is a dead
  path, which is why every skill now says so out loud instead of silently
  skipping the rule.

If you keep your vault outside git and want to work from subfolders, run
\`git init\` in the vault root once. Reported by @Palo-Alto-AI-Research-Lab on
codex-cli 0.144.4 (issue #171).

## Option A - skills.sh (recommended)

[\`skills\`](https://github.com/vercel-labs/skills) (\`npx skills\`) is a
GitHub-as-registry installer that writes one shared \`.agents/skills/\` tree all
three harnesses read. Run from your vault root:

\`\`\`bash
# preview what would install (should list $((ASK_CMD_COUNT + 1)): ${ASK_CMD_COUNT} commands + ${ASK_CORE})
npx skills add ./dist/agent-skills --list

# project-scope install for one or more harnesses (one physical tree serves all)
npx skills add ./dist/agent-skills -a antigravity -a codex -a opencode

# global scope instead of project scope
npx skills add ./dist/agent-skills -g -a antigravity -a codex -a opencode

# refresh after a rebuild
npx skills update
\`\`\`

Install the full set. The research and health skills call into
\`${ASK_CORE}\`, so cherry-picking individual skills breaks those; the full-set
install is the supported path.

## Option B - manual copy (no skills.sh)

\`\`\`bash
# From the repo root, after: bash scripts/build.sh --platform agent-skills
mkdir -p /path/to/your/vault/.agents/skills
cp -R dist/agent-skills/skills/. /path/to/your/vault/.agents/skills/
\`\`\`

## Per-harness notes

- **Antigravity** - discovers workspace skills at \`.agents/skills/<name>/SKILL.md\`
  and also surfaces each as a slash command (\`/skills\`). In \`--print\` (headless)
  mode the workspace must be registered explicitly with \`--add-dir <workspace>\`;
  running from inside the directory is not enough for headless skill discovery.
  Interactive sessions that open the workspace normally are unaffected. Global
  rules live in \`~/.gemini/GEMINI.md\` - see \`global-rule-snippet.md\`.
- **Codex CLI** - native Agent Skills at the same path. Invoke with \`\$<name>\`,
  via \`/skills\`, or let Codex match implicitly on the description.
- **OpenCode** - reads \`.agents/skills/\` (project) and \`~/.agents/skills/\`
  (global). Its validator is strict: only \`name\`, \`description\`, \`license\`,
  \`compatibility\`, and a string-map \`metadata\` are accepted, and \`name\` must
  match the directory - this build already conforms.
- **GitHub Copilot CLI** - loads project skills from \`.agents/skills/\` (and
  \`.github/skills/\`, \`.claude/skills/\`) and personal skills from
  \`~/.agents/skills/\` or \`~/.copilot/skills/\` (as of 2026-07,
  docs.github.com). The same tree works unchanged; the skills.sh agent target
  is \`github-copilot\`.
- **Anything else on the Agent Skills standard** - any harness that reads
  \`.agents/skills/<name>/SKILL.md\` picks this build up with zero changes.

## What is NOT covered

Agent Skills cover the commands only. The MCP vault server, Claude Code hooks,
and the scheduled maintenance agents remain Claude Code / Hermes extras. The
skills are made self-sufficient (vault-root resolution + the embedded write
spec) to compensate. For the optional always-on vault-routing rule, see
\`global-rule-snippet.md\`.
EOF
}

_ask_emit_global_rule() {
  local dst="$1"
  cat > "$dst/global-rule-snippet.md" <<EOF
# Optional: always-on vault-routing rule

Agent Skills are selected per request. If you want your agent to always treat the
current workspace as an obsidian-second-brain vault - reading \`_CLAUDE.md\` up
front and honoring the AI-first write spec on every note - add the snippet below
to your harness's global rules file:

- **Antigravity**: \`~/.gemini/GEMINI.md\`
- **Codex CLI**: \`~/.codex/AGENTS.md\`
- **OpenCode**: \`~/.agents/AGENTS.md\` (or the project \`AGENTS.md\`)

\`\`\`markdown
## Obsidian second brain

This workspace may be an Obsidian vault managed by the obsidian-second-brain
Agent Skills. When it is:

1. Resolve the vault root: \`\$OBSIDIAN_VAULT_PATH\` if set, else the workspace root.
2. Read \`_CLAUDE.md\` at the vault root first, if present, for vault conventions.
3. Prefer the installed \`.agents/skills/\` skills for vault actions (save, capture,
   log, decide, research, health, ...).
$(emit_ai_first_rule "${ASK_CORE_PATH}/references/ai-first-rules.md" 4)
\`\`\`
EOF
}
