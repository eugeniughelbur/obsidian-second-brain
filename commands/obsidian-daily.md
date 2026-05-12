---
description: Create or update today's daily note — pulls calendar events, overdue tasks, and conversation context
category: vault
---

Use the obsidian-second-brain skill. Execute `/obsidian-daily`:

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Read `CRITICAL_FACTS.md` for timezone

3. Check if `wiki/daily/YYYY-MM-DD.md` exists for today
   - If not: read `templates/Daily Note.md`, fill in date fields, create the file
   - If yes: update existing note (inject, don't overwrite)

4. Pull calendar events (if Google Calendar MCP tools are available):
   - Fetch today's events using `google_calendar_list_events`
   - Add a ## Calendar section to the daily note with:
     - Time, title, attendees for each event
     - For meetings with known entities: link to their `[[Person Name]]` pages
   - If calendar tools aren't available, skip silently (don't error)

5. Pull overdue and due-today tasks from kanban boards:
   - Scan `boards/` for items with `@{date}` that match today or are past due
   - Add to the daily note's Focus section with priority markers

6. Scan the current conversation for anything relevant to today:
   - Tasks in progress, people mentioned, decisions made, what's being worked on
   - Pre-fill or update the note's sections with that context

7. Check `log.md` for last night's sleeptime consolidation:
   - If the nightly agent ran, summarize what it did (reconciled, synthesized, healed)
   - Add a brief "Overnight changes" note so the user knows what happened while they slept

8. Return the path of the daily note when done.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
