# Write Rules

How Claude writes, links, formats, and updates notes in an Obsidian vault.

> **Read `references/ai-first-rules.md` first.** Every note Claude writes must follow the AI-first rule (preamble, rich frontmatter, recency markers, mandatory wikilinks, sources verbatim, confidence levels). The rules below are operational details on top of that foundation.

---

## The Propagation Rule

**Never create a note in isolation.** Every write has ripple effects.

When you create or update something, trace forward: what other notes need to know about this?

```
New project created
  → Add card to kanban board (Backlog column)
  → Link from today's daily note
  → If it has a person involved, link from their note

Task completed
  → Move card in kanban (to ✅ Done, with strikethrough)
  → Update project note (Recent Activity or Delivered section)
  → Log in today's daily note

Person note updated
  → If interaction happened today, log in daily note
  → If they made a mention/shoutout, add to Mentions Log

Dev log created
  → Link from project note (Recent Activity section)
  → Link from today's daily note (Work / Work Log section)

Decision made
  → Log in project note (Key Decisions section)
  → Log in today's daily note

Deal moved forward
  → Update deal file (status, probability, notes)
  → Update Side Biz kanban board
  → Reflect in daily note
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
| Kanban due date tag | `@{YYYY-MM-DD}` | `@{2026-03-28}` |
| Body text references | Human format | `March 24` or `Mar 24` |
| File names (dated) | `YYYY-MM-DD` | `2026-03-24.md` |

---

## Kanban Board Format

Boards use the `kanban-plugin: board` YAML frontmatter.
Columns are H2 headings. Items are task checkboxes with optional indented description.

**Active item:**
```markdown
- [ ] 🔴 **Task Title** · @{2026-03-28}
	One-line description. [[Related Project]] [[Person]]
```

**Waiting item:**
```markdown
- [ ] 🟡 **Task Title** · @{2026-04-07}
	Context for why it's blocked. [[Person responsible]]
```

**Completed item** (move to `## ✅ Done` column):
```markdown
- [x] ~~🔴 **Task Title**~~ ✅ Mar 24
	Brief note on outcome.
```

**Priority emoji convention:**
- 🔴 Critical / blocking
- 🟡 Important / this week
- 🟢 Nice to have / low urgency

**Never delete done items** - move them to the Done column with strikethrough. Done items are the changelog.

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

## Template Usage

When creating notes from templates, strip all Templater syntax (`<% ... %>`) and replace with actual values. Never leave template placeholders in saved notes.

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

For kanban boards: find the correct column heading, insert the new item above the last item in that column (or at top if empty).

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

This lets a command be idempotent and re-runnable without the user fearing it will wipe their additions. Used by `/obsidian-architect`; available to any command that maintains a regenerable note.

---

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
