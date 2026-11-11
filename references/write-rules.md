# Write Rules

How Claude writes, links, formats, and updates notes in an Obsidian vault.

> **Read `references/ai-first-rules.md` first.** Every note Claude writes must follow the AI-first rule (preamble, rich frontmatter, recency markers, mandatory wikilinks, sources verbatim, confidence levels). The rules below are operational details on top of that foundation.

---

## The Propagation Rule

**Never create a note in isolation.** Every write has ripple effects.

When you create or update something, trace forward: what other notes need to know about this?

```
Source processed (obsidian-save)
  -> raw capture in raw/, summary page in wiki/sources/
  -> rewrite the entity and concept pages it touches (proposals for existing pages)
  -> regenerate the changed sections of index.md
  -> append one line to Logs/YYYY-MM-DD.md

Conversation result saved (obsidian-save)
  -> update the project / decision / entity pages it concerns
  -> link the session log from each page it touched

Decision made
  -> log in the project note (Key Decisions section)
  -> link the decision note from the project and the session log

Contradiction resolved (obsidian-health)
  -> rewrite the outdated page with a History entry, or write a conflict note
  -> regenerate the changed sections of index.md
```

---

## Internal Linking

Use `[[Note Name]]` syntax. Always link:
- People mentioned in a note → `[[Jane Smith]]`
- Projects referenced → `[[My Project Name]]`
- Jobs/companies → `[[Acme Corp]]`
- Related tasks → `[[Task Name]]`

**Never hardcode paths** unless necessary. Obsidian resolves `[[Name]]` by filename.

If the linked note doesn't exist yet, create it (stub is fine - frontmatter + title + one line of context).

---

## Date Formatting

| Context | Format | Example |
|---|---|---|
| Frontmatter `date` field | `YYYY-MM-DD` | `2026-03-24` |
| Frontmatter `due` field | `YYYY-MM-DD` | `2026-03-28` |
| Body text references | Human format | `March 24` or `Mar 24` |
| File names (dated) | `YYYY-MM-DD` | `2026-03-24.md` |

---

## Status Values

Use these consistently across all note types:

**Projects:**
`active` | `planning` | `completed` | `archived` | `on-hold`

**Tasks:**
`in-progress` | `done` | `waiting` | `cancelled`

**Deals:**
`prospect` | `negotiating` | `confirmed` | `completed` | `lost`

**Goals:**
`active` | `completed` | `paused` | `abandoned`

**Content:**
`draft` | `scheduled` | `published`

---

## Writing Style Calibration

Before writing a new note in a folder you haven't written in before:
1. Read 1-2 existing notes in that folder
2. Match: heading structure, frontmatter fields present, tone (formal vs casual), emoji usage, list style (bullet vs numbered), section names

Don't introduce new patterns - extend what's there.

---

## Archiving

**Soft archive** (preferred): Add `_archived_` prefix to filename.
`Old Project.md` → `_archived_Old Project.md`

**Update frontmatter**: set `status: archived`

Never delete vault notes - archive them. The vault is a permanent record.

---

## Stub Notes

When a link target doesn't exist yet, create a minimal stub:
```yaml
---
date: 2026-03-24
tags:
  - person    # or project, task, etc.
---

# Person Name

<!-- Note created as stub. Expand when more info is available. -->
```

---

## Section Injection

When updating an existing note (vs creating new), use targeted section injection:

1. Read the full file
2. Find the target section heading
3. Append content below the last item in that section (before the next `---` or next `##`)
4. Write back the full file with `write_file`

---

## Sentinel-safe regeneration

For notes that a command generates AND a human may hand-edit (architecture docs, dashboards, any note meant to be refreshed by re-running a command), use sentinel markers so a refresh never destroys human edits:

```
<!-- @generated:start -->
...machine-generated content - safe to overwrite on the next run...
<!-- @generated:end -->

<!-- @user:start -->
...human notes - NEVER overwritten by a refresh...
<!-- @user:end -->
```

Rules on refresh:
1. Read the existing note.
2. Replace ONLY the content between `@generated:start` and `@generated:end`.
3. Never touch `@user` blocks, and never touch anything outside the markers (treat it as human-owned).
4. On the first run (no markers yet), wrap the content you generate in `@generated` markers so future refreshes are safe.

This lets a command be idempotent and re-runnable without the user fearing it will wipe their additions. Available to any command that maintains a regenerable note.

---

## Batch writes

A run of many `obsidian-save` or `obsidian-save` calls in one sitting has no unit-of-work boundary of its own: every note lands live as it is written, and abandoning the batch halfway means finding each note by hand (#222, raised by @konsone). The boundary has to come from the vault's own history, because it is the only layer that sees every write from every tool - the Python scripts, the MCP server, and the agent's own Write and Edit tools alike. A staging mode inside the commands would cover only the first two and leave the rest of the batch live, which is worse than no staging at all.

**Git-backed vault.** Branch, run, review, then merge or discard:

```bash
cd "$OBSIDIAN_VAULT_PATH"
git checkout -b ingest-2026-08-27        # the batch lives here
# ... run the ingests ...
git status && git diff --stat            # review what changed
git checkout main && git merge ingest-2026-08-27   # accept
# or: git checkout main && git branch -D ingest-2026-08-27   # abandon, nothing reaches main
```

Notes written on the branch are searchable while you are on it, which is what you want mid-batch (later ingests build on earlier ones). Switch back to `main` to see the vault without the batch.

**LiveSync (CouchDB) vault.** Take a snapshot before the batch: Self-hosted LiveSync stores document history in CouchDB, so a `Settings > Sync settings > Hatch > Make a backup` (or a CouchDB replication to a scratch database) before the run is the rollback point. Restore the snapshot to abandon the batch. Pausing sync on the other devices during the batch keeps a half-finished set from propagating.

**Either way**, the ingest log line the command writes (step 7 of `obsidian-save`) is the audit trail for what one batch touched; keep the batch small enough that the log fits in one screen.

## Search Before Write

Before creating any note:
```
search(query="keyword from title")
```

If a match is found:
- Same concept → update the existing note, don't create new
- Different concept, similar name → proceed with creation but choose a distinct name

Duplicate detection is especially important for: people (same person, different name formats), projects (same project, different working title), deals (same client, multiple files).

**Never claim absence from memory.** Before writing "no note exists" or creating a note because you believe none exists, search exhaustively - by every plausible name, alias, and folder, listing and grepping rather than relying on one query. False absence (under-reporting, or "nothing found" when something does exist) is the most common failure mode. When unsure, over-include and label the uncertainty. See the anti-fabrication and search-completeness hard rules in `ai-first-rules.md`.

<!-- author-credit -->

---

From [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain), created by Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator). Questions or consulting: [LinkedIn](https://www.linkedin.com/in/eugeniu-ghelbur/) or [e.ghelbur@gmail.com](mailto:e.ghelbur@gmail.com). More: [The AI Operator](https://theaioperator.io/?utm_source=github&utm_medium=file-credit) | [X](https://x.com/eugeniu_ghelbur) | [GitHub](https://github.com/eugeniughelbur). MIT license.
