---
description: Live project status from git + local docs - infers all context from vault notes, no config required
category: vault
triggers_en: ["projects overview", "project status", "what am I working on", "show projects"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-projects $ARGUMENTS`:

Optional argument: a specific project name. If given, show deep context for that one project only. If no argument, run the full overview for all tracked projects.

## Step 1 - discover projects

Read `_CLAUDE.md` to find the projects folder name (e.g. `Projects/` or `wiki/projects/`). If not defined, default to `Projects/`.

Scan that folder for all `.md` files. For each file, read its frontmatter. A note is a tracked project if it has `type: project` OR lives in the projects folder and has a `repo:` field. Collect:

- `vault_note` - the file path
- `name` - from `name:` frontmatter or the filename
- `repo` - from `repo:` frontmatter; absent means non-code project (git steps skip)
- `status` - from `status:` frontmatter if present

If the optional argument was given, filter to the matching project only.

## Step 2 - gather state in parallel

Spawn one subagent per project. Each agent runs three checks:

**Vault check:**
- Read the project note
- Extract: `status`, most recent entry in any `Recent Activity` or `## Last overview` section, `next_action`, open questions, blockers

**Git check** (skip if no `repo:` field):
- `git -C "<repo>" log --oneline --no-merges -15`
- `git -C "<repo>" status --short`
- If the path doesn't exist or isn't a git repo, note it and skip

**Docs check** (skip if no `repo:` field):
- Look for `NOTES.md`, `TODO.md`, `docs/NOTES.md`, `docs/TODO.md` in the repo root
- Read the first one found; skip if none exist
- Extract explicit next steps, blockers, or context not in the vault note

## Step 3 - synthesize per project

Merge the three agent results into one status block per project:

- **Status**: infer from activity recency: `active` (commits or vault update in last 7 days), `stalled` (7-30 days), `idle` (30+ days), `blocked` (explicit blocker found). Override with the note's `status:` field if it says `archived` or `paused`.
- **Last session**: what was worked on and when. Prefer git commit dates + messages over vault dates.
- **Next action**: single most concrete next step. Pull from vault open questions or docs TODO. If unclear, say so - do not invent one.
- **Blocked by**: anything explicitly blocking. `none` if nothing found.

## Step 4 - print to conversation

Print the full overview in the conversation immediately. Order: active first, then stalled, then idle, then archived. Use this format per project:

```
## [Project Name]
Status: active | stalled | idle | blocked | archived
Repo: path/to/repo  (or "no repo")
Vault: [[Projects/Project Name]]

Last session: YYYY-MM-DD - one sentence on what was done (source: git / vault / docs)
Next action: specific next step, or "unclear - check vault note"
Blocked by: none | description
```

## Step 5 - update vault notes

For each project note, inject or overwrite a `## Last overview` section with the synthesized status and timestamp. This makes the note self-aware of when it was last reviewed. Use this format:

```markdown
## Last overview

**Reviewed:** YYYY-MM-DD (source: /obsidian-projects)

**Status:** active | stalled | idle | blocked | archived
**Last session:** YYYY-MM-DD - one sentence on what was done (source: git | vault | docs)
**Next action:** specific next step, or "unclear - check vault note"
**Blocked by:** none | description
```

If a project note doesn't exist yet but was discoverable via git (e.g. the repo folder exists but has no matching vault note), mention it at the end as "untracked repos found". Do not create notes automatically.

---

**AI-first rule:** Every vault write MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter, `[[wikilinks]]` for every project referenced, recency markers on git-sourced facts (e.g. `(as of 2026-05-21, git log)`), sources noted inline.
