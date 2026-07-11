---
description: Bulk-triage a kanban board - surface stale items and archive, reschedule, or mark them done in one pass
category: vault
triggers_en: ["clean up my board", "triage my board", "board hygiene", "archive stale tasks", "my board is a mess"]
triggers_es: ["limpia mi tablero", "haz triaje de mi tablero", "ordena el tablero", "archiva las tareas viejas", "mi tablero es un desastre"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-board-hygiene [board]`:

The board's "This Week" column has quietly become a graveyard - this clears it. The board equivalent of the wanted-notes triage: surface what's stale, then keep / reschedule / done / archive in one guided pass.

1. Read `_CLAUDE.md` first if it exists in the vault root, to find the boards folder and kanban convention (columns, priority markers, `@{date}` format).
2. Read the target board (fuzzy-match the argument; if none given, list boards and ask). Parse every open item per column, extract its `@{date}` if present, and compute age vs today.
3. Group the open items by staleness: **overdue** (`@{date}` in the past), **stale** (in the same column with a date older than N days, default 14), and **undated** (no `@{date}` - can't be scheduled, flag separately). Show counts per column so the bloat is visible at a glance.
4. For each stale/overdue item, propose ONE verdict with a one-line reason: **done** (looks completed elsewhere - move to Done with strikethrough), **reschedule** (still real - set a new `@{date}` or move to Backlog/Next Week), **archive** (dead - move to an `_archived` section or Done with a "dropped" note), or **keep** (genuinely active, leave it). Present as a batch the user can approve, edit, or override - never auto-move destructively without confirmation.
5. Apply the approved verdicts to the board in place (additive moves + strikethrough, never silent deletion), then report what moved where and append a one-line entry to the operation log (`Logs/YYYY-MM-DD.md` if it exists, else `log.md`).

A board only means something if "This Week" means this week. Run this whenever a column stops being trustworthy; pairs with `/obsidian-board` (which only flags) by actually clearing the backlog.

---

**AI-first rule:** Board files follow the kanban exception in `references/ai-first-rules.md`: `kanban-plugin` frontmatter, NO `## For future Claude` heading (the plugin would render it as a phantom column). Every NON-board note this command creates or updates (task notes, project notes) MUST follow the full rule - preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`), `[[wikilinks]]`, sources verbatim.
