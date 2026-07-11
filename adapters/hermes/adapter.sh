#!/usr/bin/env bash
# =============================================================================
# adapters/hermes/adapter.sh - Nous Research Hermes Agent platform adapter
# =============================================================================
# Hermes Agent ships a native Skills System (agentskills.io-compatible): a skill
# is a directory `skills/<category>/<name>/` with a `SKILL.md` (YAML frontmatter
# + body). Hermes loads skills with progressive disclosure, the user installs a
# set by adding the repo as a "tap" (`hermes skills tap add <owner/repo>`) or
# copying into `~/.hermes/skills/`, and invokes them via `/skills` or implicit
# description match.
#
# We emit one native Hermes skill per command, grouped by category. This is the
# Hermes-runtime counterpart to the Codex native-skills adapter (Phase 2 of the
# Hermes work, Issue #79). The MCP connector (integrations/obsidian-mcp-server)
# is the separate bounded-data path; this adapter is the skill/playbook path.
#
# SKILL.md frontmatter (per Hermes creating-skills spec):
#   required: name, description, version, author, license
#   optional: metadata.hermes.tags (+ more we do not need here)
# =============================================================================

HERMES_PLATFORM="hermes"
HERMES_DIR="hermes"
HERMES_SKILLS_DIR="skills"
HERMES_AUTHOR="Eugeniu Ghelbur"
HERMES_LICENSE="MIT"

adapter_build() {
  local src="$1" dst="$2"

  HERMES_VERSION="$(_hermes_version "$src")"
  _hermes_emit_skills "$src/commands" "$dst/$HERMES_SKILLS_DIR"
  _hermes_emit_blueprints "$dst/optional-skills"
  _hermes_copy_references "$src/references" "$dst/references"
  _hermes_copy_scripts "$src/scripts" "$dst/scripts"
  _hermes_copy_hooks "$src/hooks" "$dst/hooks"
  _hermes_emit_install_hint "$dst"
  _hermes_emit_hooks_doc "$dst"
}

# Copy the Hermes lifecycle-hook artifacts (the on_session_end maintenance script
# and its cli-config.yaml template) into the build.
_hermes_copy_hooks() {
  local src="$1" dst="$2"
  [[ -d "$src" ]] || return 0
  mkdir -p "$dst"
  [[ -f "$src/obsidian-hermes-session-end.sh" ]] && cp "$src/obsidian-hermes-session-end.sh" "$dst/"
  [[ -f "$src/hermes-hooks.cli-config.example.yaml" ]] && cp "$src/hermes-hooks.cli-config.example.yaml" "$dst/"
}

# Read the project version from pyproject.toml so SKILL.md `version:` tracks
# releases instead of going stale. Falls back to 0.0.0.
_hermes_version() {
  local src="$1" v
  v="$(grep -m1 '^version' "$src/pyproject.toml" 2>/dev/null | sed 's/.*=[[:space:]]*"//; s/".*//')"
  [[ -n "$v" ]] && echo "$v" || echo "0.0.0"
}

# Emit one native Hermes skill per command:
#   skills/<category>/<name>/SKILL.md
# Frontmatter carries the required fields plus metadata.hermes.tags. The
# command's English triggers are folded into the description (for implicit
# selection) and surfaced as a "## When to use" preamble; the command body
# follows as the procedure, tool-neutralized and path-rewritten.
_hermes_emit_skills() {
  local src="$1" dst="$2"
  [[ -d "$src" ]] || return 0
  local f name desc triggers category out trig_clean
  for f in "$src"/*.md; do
    [[ -f "$f" ]] || continue
    should_include "$f" "$HERMES_PLATFORM" || continue

    name="$(basename "$f" .md)"
    desc="$(parse_frontmatter "$f" description)"
    triggers="$(parse_frontmatter "$f" triggers_en)"
    category="$(parse_frontmatter "$f" category)"
    [[ -z "$category" ]] && category="misc"
    [[ -z "$desc" ]] && desc="Run the $name command of the obsidian-second-brain skill."

    trig_clean=""
    if [[ -n "$triggers" ]]; then
      trig_clean="$(echo "$triggers" | tr -d '[]"' | sed 's/,/, /g; s/  */ /g; s/^ *//; s/ *$//')"
      [[ -n "$trig_clean" ]] && desc="$desc Triggers: $trig_clean."
    fi

    mkdir -p "$dst/$category/$name"
    out="$dst/$category/$name/SKILL.md"
    {
      echo "---"
      echo "name: $name"
      printf 'description: "%s"\n' "${desc//\"/\\\"}"
      echo "version: $HERMES_VERSION"
      printf 'author: "%s"\n' "$HERMES_AUTHOR"
      echo "license: $HERMES_LICENSE"
      echo "metadata:"
      echo "  hermes:"
      echo "    tags: [obsidian-second-brain, $category]"
      echo "---"
      echo
      if [[ -n "$trig_clean" ]]; then
        echo "## When to use"
        echo
        echo "When the user's request matches any of: $trig_clean."
        echo
      fi
      echo "## Procedure"
      echo
      command_body "$f"
    } > "$out"

    rewrite_tool_neutral "$out"
    rewrite_platform_paths "$out" "$HERMES_DIR"
  done
}

# Emit the four scheduled agents (SKILL.md "Scheduled Agents" section) as native
# Hermes blueprint skills - `metadata.hermes.blueprint` with a cron `schedule`.
# They go under optional-skills/ (NOT skills/) on purpose: a blueprint arms as
# soon as its skill is loaded, and the scheduled agents are opt-in by design
# (the Claude side ships inert and requires explicit /schedule). optional-skills
# require an explicit `hermes skills install <name>`, which preserves that
# opt-in arming contract. SKILL.md remains the canonical source for the prompts.
_hermes_emit_blueprints() {
  local dst="$1"
  mkdir -p "$dst"

  _hermes_write_blueprint "$dst" obsidian-morning "0 8 * * *" "daily at 8:00 AM" \
"Create today's daily note and surface what needs attention. Runs unattended on schedule." \
"Read \`_CLAUDE.md\`. Create today's daily note in \`Daily/\` using the Daily Note template.
Pull in any tasks from kanban boards that are due today or overdue.
List any projects with status active that have no recent activity in the last 7 days.
Do not ask questions - infer everything from the vault. Save and stop."

  _hermes_write_blueprint "$dst" obsidian-nightly "0 22 * * *" "daily at 10:00 PM" \
"Sleeptime consolidation - the vault gets smarter overnight. The cron-native counterpart to the Claude PostCompact maintenance pass." \
"Read \`_CLAUDE.md\`. This is a sleeptime consolidation pass - the vault should be smarter when the user wakes up.

Phase 1 - Close the day:
- Read today's daily note. Append a ## End of Day section with a 3-5 bullet summary.
- Move any completed kanban tasks to Done.

Phase 2 - Reconcile:
- Scan \`wiki/entities/\` for outdated roles, companies, or descriptions that conflict with newer daily notes.
- Scan \`wiki/concepts/\` for claims contradicted by recently ingested sources.
- Auto-resolve clear winners. Flag ambiguous ones in \`wiki/decisions/\`.

Phase 3 - Synthesize:
- Scan sources ingested today and yesterday. Find concepts that appear in 2+ unrelated sources.
- If patterns found: create \`wiki/concepts/Synthesis - Title.md\` with evidence and interpretation.

Phase 4 - Heal:
- Find notes created today with no incoming links. Add links from relevant existing pages.
- Close entity timeline entries missing an \"until\" date that should be closed.
- Rebuild \`index.md\` to reflect today's changes.

Phase 5 - Log:
- Append to \`log.md\`: ## [YYYY-MM-DD] nightly | End of day + X reconciled, Y synthesized, Z orphans linked

Do not ask questions. Do not fix anything destructive - only add, update, link. Save and stop."

  _hermes_write_blueprint "$dst" obsidian-weekly "0 18 * * 5" "every Friday at 6:00 PM" \
"Generate a weekly review note from the vault. Runs unattended on schedule." \
"Read \`_CLAUDE.md\`. Run the obsidian-recap skill for the week to gather this week's activity.
Generate a weekly review note using the Review template (or standard structure if none exists).
Save to \`Reviews/YYYY-MM-DD - Weekly Review.md\`.
Link it from this week's last daily note.
Do not ask questions. Save and stop."

  _hermes_write_blueprint "$dst" obsidian-health-check "0 21 * * 0" "every Sunday at 9:00 PM" \
"Run the vault health check and log a report (report only, never auto-fixes)." \
"Read \`_CLAUDE.md\`. Run: \`uv run -m scripts.vault_health --path <vault> --json\`
Parse the output. Write a health report to \`Knowledge/Vault Health YYYY-MM-DD.md\`
summarizing findings by severity (critical, warning, info).
Do not fix anything autonomously - only report.
Do not ask questions. Save and stop."
}

# _hermes_write_blueprint <dst> <name> <schedule> <human_time> <short_prompt> <body>
_hermes_write_blueprint() {
  local dst="$1" name="$2" schedule="$3" human="$4" short="$5" body="$6"
  mkdir -p "$dst/$name"
  {
    echo "---"
    echo "name: $name"
    printf 'description: "%s Schedule: %s."\n' "${short//\"/\\\"}" "$human"
    echo "version: $HERMES_VERSION"
    printf 'author: "%s"\n' "$HERMES_AUTHOR"
    echo "license: $HERMES_LICENSE"
    echo "metadata:"
    echo "  hermes:"
    echo "    tags: [obsidian-second-brain, scheduled]"
    echo "    blueprint:"
    printf '      schedule: "%s"\n' "$schedule"
    echo "      deliver: origin"
    printf '      prompt: "Run the %s scheduled vault maintenance. Follow the procedure below exactly; do not ask questions; save and stop."\n' "$name"
    echo "      no_agent: false"
    echo "---"
    echo
    echo "## When to use"
    echo
    echo "Runs automatically on its blueprint schedule ($human). Can also be run on demand. Opt-in: install with \`hermes skills install $name\` to arm the schedule."
    echo
    echo "## Procedure"
    echo
    echo "$body"
  } > "$dst/$name/SKILL.md"
}

# Box 4 - the lifecycle-hook story, told honestly. Hermes's session-lifecycle
# hook config is not documented as of this build, so we ship guidance rather
# than a config that might not load. The nightly blueprint is the cron-native
# substitute for the Claude PostCompact maintenance pass.
_hermes_emit_hooks_doc() {
  local dst="$1"
  cat > "$dst/HOOKS.md" <<'EOF'
# Hermes: scheduled maintenance and the PostCompact analog

The Claude Code build maintains the vault two ways: opt-in scheduled agents
(`/schedule`) and an opt-in PostCompact hook (`hooks/obsidian-bg-agent.sh`) that
propagates conversation context into the vault after the context is compacted.
This documents the Hermes equivalents.

## Scheduled maintenance (cron) - shipped

The four scheduled agents are emitted as native Hermes blueprint skills under
`optional-skills/`:

| Skill | Schedule | Does |
|---|---|---|
| `obsidian-morning` | `0 8 * * *` | Create today's daily note, surface due/overdue + stale projects |
| `obsidian-nightly` | `0 22 * * *` | Sleeptime consolidation: close day, reconcile, synthesize, heal, log |
| `obsidian-weekly` | `0 18 * * 5` | Generate the weekly review note |
| `obsidian-health-check` | `0 21 * * 0` | Vault health report (report only) |

They live in `optional-skills/` (not `skills/`) on purpose: a Hermes blueprint
arms as soon as its skill is loaded, and these are opt-in by design. Arm one
with `hermes skills install <name>`; it then runs unattended on its schedule.
None of them delete or archive - they only add, update, link.

## PostCompact analog (lifecycle hook) - shipped

The Claude PostCompact hook fires on context compaction to propagate the session
into the vault. Hermes's analog is the `on_session_end` event hook (declared in
`cli-config.yaml`). This build ships it:

- **`hooks/obsidian-hermes-session-end.sh`** - an `on_session_end` hook that, on
  a completed (non-interrupted) session, runs the `obsidian-nightly`
  consolidation pass and prints `{}` (the observer-hook contract). It mirrors the
  Claude bg-agent's trust model exactly: OPT-IN, ships INERT, no-ops unless BOTH
  `OBSIDIAN_VAULT_PATH` and `OBSIDIAN_HERMES_HOOK_ENABLED=1` are set; add/update
  /link only, never delete or archive.
- **`hooks/hermes-hooks.cli-config.example.yaml`** - the paste-in
  `cli-config.yaml` block registering the hook.

Install:

```bash
mkdir -p ~/.hermes/agent-hooks
cp hooks/obsidian-hermes-session-end.sh ~/.hermes/agent-hooks/
chmod +x ~/.hermes/agent-hooks/obsidian-hermes-session-end.sh
# merge hooks/hermes-hooks.cli-config.example.yaml into your cli-config.yaml,
# then: export OBSIDIAN_VAULT_PATH=... OBSIDIAN_HERMES_HOOK_ENABLED=1
```

**The one unverified seam:** how to invoke Hermes headlessly for the
consolidation run. The script defaults to `hermes run --quiet` and lets you
override it with `OBSIDIAN_HERMES_CONSOLIDATE_CMD` if your Hermes version uses a
different non-interactive entrypoint. The hook wiring, payload parsing, trust
gate, and stdout contract are all built to the documented `on_session_end` spec;
confirming the headless invocation on a live Hermes is the remaining check
(Issue #79). The `obsidian-nightly` cron blueprint covers the same maintenance
on a daily cadence regardless.
EOF
}

_hermes_copy_references() {
  local src="$1" dst="$2"
  [[ -d "$src" ]] || return 0
  mkdir -p "$dst"
  cp -R "$src/." "$dst/"
  find "$dst" -type f -name '*.md' -print0 | while IFS= read -r -d '' f; do
    rewrite_platform_paths "$f" "$HERMES_DIR"
  done
}

_hermes_copy_scripts() {
  local src="$1" dst="$2"
  [[ -d "$src" ]] || return 0
  mkdir -p "$dst"
  cp -R "$src/." "$dst/"
  # Ship the Python project next to the scripts so the documented
  # `uv run -m scripts.research.<name>` actually resolves modules AND deps
  # (stress-test fix 24/24: the dist shipped scripts with no project).
  cp "$src/../pyproject.toml" "$(dirname "$dst")/pyproject.toml"
}

_hermes_emit_install_hint() {
  local dst="$1"
  cat > "$dst/INSTALL.md" <<'EOF'
# Install on Hermes Agent

The obsidian-second-brain commands are emitted here as native Hermes skills
under `skills/<category>/<name>/SKILL.md` (agentskills.io-compatible).

## Option A - install from this built tree

```bash
# From the repo root, after `bash scripts/build.sh --platform hermes`:
mkdir -p ~/.hermes/skills/obsidian-second-brain
cp -R dist/hermes/skills/. ~/.hermes/skills/obsidian-second-brain/
# Shared specs + Python helpers the skills reference:
cp -R dist/hermes/references ~/.hermes/skills/obsidian-second-brain/references
cp -R dist/hermes/scripts    ~/.hermes/skills/obsidian-second-brain/scripts
```

## Option B - add as a tap (when published to a skills repo)

```bash
hermes skills tap add <owner>/<repo>
```

Then in Hermes:

- Browse with `hermes skills browse` / the `/skills` command, or just describe
  the task and let Hermes select a skill from its description.
- Skills run in your Hermes session. The AI-first vault rule lives in
  `references/ai-first-rules.md` - it is non-negotiable for every note a skill
  writes (`## For future Claude` preamble, rich frontmatter, `[[wikilinks]]`,
  recency markers, sources verbatim, confidence levels).
- Python helpers under `scripts/` run via `uv run -m scripts.research.<name>`
  from the install directory (it ships a `pyproject.toml`, so modules and
  dependencies both resolve there - e.g. `~/.hermes/skills/obsidian-second-brain/`).

## Scheduled agents (opt-in)

The four scheduled maintenance agents are emitted as native Hermes blueprint
skills under `optional-skills/` (morning / nightly / weekly / health-check).
They are NOT auto-armed - install one explicitly to arm its schedule:

```bash
cp -R dist/hermes/optional-skills/. ~/.hermes/optional-skills/
hermes skills install obsidian-nightly   # arms the 10pm consolidation pass
```

See `HOOKS.md` for the full schedule table and the PostCompact-analog story.

Point Hermes at your vault as the working directory, or pair these skills with
the MCP connector (`integrations/obsidian-mcp-server/`) for bounded vault data
access. Remaining lifecycle-hook wiring is tracked in Issue #79.
EOF
}
