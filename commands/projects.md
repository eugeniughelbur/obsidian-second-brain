---
description: Live overview of all tracked projects - reads vault notes, git history, and local docs, then rewrites Projects/Dashboard.md. Run at session start or any time you need a full picture.
---

Use the obsidian-second-brain skill. Execute `/projects $ARGUMENTS`:

Optional argument: a specific project name. If given, show deep context for that one project only and skip the dashboard rewrite. If no argument, run the full overview for all projects.

## Step 1 - read configuration

Read `_CLAUDE.md` from the vault root. Find the `projects:` block, which lists each tracked project with its vault note path and repo path:

```yaml
projects:
  - name: Project Name
    repo: C:\Users\kroli\Documents\Codeing\GitHub\<repo-folder>
    vault_note: Projects/Project Name.md
```

If `_CLAUDE.md` has no `projects:` block yet:
1. Scan `Projects/` in the vault for existing project notes
2. List what was found and ask the user to confirm or add repo paths
3. Offer to write the `projects:` block into `_CLAUDE.md`
4. Do not proceed with the overview until at least one project is configured

## Step 2 - gather state in parallel

For each project, spawn parallel subagents - one per project:

**Vault agent** (per project):
- Read the project's vault note (`vault_note` path from config)
- Extract: `status`, last session summary from Recent Activity, next action, open questions, blockers
- If the note doesn't exist yet, note it as "no vault note" and skip

**Git agent** (per project):
- Run `git -C "<repo>" log --oneline --no-merges -15` to see recent commits
- Run `git -C "<repo>" status --short` to see uncommitted state
- Extract: what was last worked on and when, any uncommitted work in progress
- If the path doesn't exist or isn't a git repo, note it and skip

**Docs agent** (per project):
- Check for `NOTES.md`, `TODO.md`, `docs/NOTES.md`, `docs/TODO.md` in the repo root
- Read the first one found; skip if none exist
- Extract: any explicit next steps, blockers, or context the vault note doesn't have

## Step 3 - synthesize per project

Merge each project's three agent results into a single status block:

- **Status**: infer from recency and content - `active` (commits or vault updates in last 7 days), `stalled` (no activity 7-30 days), `idle` (30+ days), `blocked` (explicit blocker found)
- **Last session**: what was worked on and when - prefer git commit dates + messages over vault dates
- **Next action**: the single most concrete next step. Pull from vault open questions or docs TODO. If unclear, say so explicitly rather than inventing one.
- **Blocked by**: anything explicitly blocking. `none` if nothing found.

## Step 4 - write the dashboard

Rewrite `Projects/Dashboard.md` with all projects. Use this format:

```markdown
---
type: dashboard
date: YYYY-MM-DD
tags: [dashboard, projects]
ai-first: true
---

# Project dashboard

## For future Claude

This is the live project overview. Each section is synthesized from vault notes + git history + local docs. Status and next actions are inferred - check the linked project note for full context. Run /projects to refresh.

_Last updated: YYYY-MM-DD HH:MM_

---

## [Project Name]

**Status:** active | stalled | idle | blocked
**Repo:** `C:\path\to\repo`
**Vault note:** [[Projects/Project Name]]

**Last session:** YYYY-MM-DD - one sentence on what was done (source: git / vault / docs)
**Next action:** specific thing to do next, or "unclear - check vault note"
**Blocked by:** none | description of blocker

---
```

One section per project, ordered: active first, then stalled, then idle.

Also print the full dashboard to the conversation immediately after writing it - don't make the user open Obsidian to see it.

## Step 5 - update the vault note

For each project with a vault note, inject a `## Last overview` section (or update it if it exists) with the synthesized status and timestamp. This makes the project note self-aware of when it was last reviewed.

---

**AI-first rule:** The dashboard and any vault writes MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter, `[[wikilinks]]` for every project referenced, recency markers on git-sourced facts (e.g. `(as of 2026-05-06, git log)`), sources noted inline. The dashboard is designed for future-Claude to read at session start and immediately understand where everything stands.
