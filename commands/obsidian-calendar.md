---
description: Reconcile the vault against your calendar - flag deadlines and commitments implied by notes that are not on the calendar. Flag only, never adds events
category: vault
exclude: [codex-cli, gemini-cli, opencode]
triggers_en: ["calendar check", "reconcile calendar", "what's not on my calendar", "calendar reconciliation", "am I missing anything on my calendar"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-calendar $ARGUMENTS`:

Catch the gap between what the vault knows you need to do and what is actually scheduled. The optional argument is a window (`today`, `this week`, `this month`); default to this week.

This command requires a Google Calendar MCP (the claude.ai connector exposes `mcp__claude_ai_Google_Calendar__list_calendars` and `mcp__claude_ai_Google_Calendar__list_events`; if your calendar MCP namespaces its tools differently, use that server's equivalents). If no calendar MCP is connected, say so and stop.

1. Read `_CLAUDE.md` and `CRITICAL_FACTS.md` (for timezone) if they exist.
2. **Pull the calendar** for the window: find the primary calendar, then list events with times.
3. **Gather what the vault implies** for the same window - by listing and grepping, never from memory (see the anti-fabrication rule):
   - Active project `next_action`s and dated deadlines in project notes.
   - Tasks/board items due in the window.
   - Commitments mentioned in recent daily notes and captures (appointments, calls, travel, filing deadlines, birthdays).
   - Fixed dates from `CRITICAL_FACTS.md` falling in the window.
4. **Reconcile and report**, in two directions:
   - **Vault-implied, not on the calendar** - the headline output. For each, state the item, its source note (`[[wikilink]]`), and the date/urgency.
   - **On the calendar, no vault context** (lighter) - events that might warrant a prep note or project link.
5. **Flag only - never add, move, or change calendar events.** This is a hard boundary. For each gap, propose what the user could do ("add a hold?", "needs a prep note?") but do not touch the calendar.
6. Offer to record the reconciliation in today's daily note (inject into a section, do not overwrite) so the gaps are tracked; on request, add tasks for items the user intends to act on.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Only flag commitments that actually appear in the vault or calendar - never invent a deadline or "should be scheduled" item that is not grounded in a note. Before claiming a calendar event has no vault note, search exhaustively (grep by event name, attendees, and any address across all folders) - false absence is the most common failure mode. Mark unknowns as `TBD`. See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
