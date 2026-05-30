---
description: Read Google Calendar and write an AI-first snapshot to the vault - today, week, next week, or a custom range
category: vault
exclude: [codex-cli, gemini-cli, opencode]
triggers_en: ["review my agenda", "check my calendar", "what's on my schedule", "what's on the calendar", "agenda for this week", "agenda for next week"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-agenda $ARGUMENTS`:

The optional argument is the range. Accepted values:
- `today` (default if no argument)
- `tomorrow`
- `week` - current ISO week, Monday to Sunday
- `next-week` - next ISO week, Monday to Sunday
- `YYYY-MM-DD` - a single day
- `YYYY-MM-DD..YYYY-MM-DD` - a closed range

This command requires the Google Calendar MCP tools (`mcp__claude_ai_Google_Calendar__list_events`, `mcp__claude_ai_Google_Calendar__list_calendars`). If they are not available, fail with a clear message ("This command requires the Google Calendar MCP - enable it in your Claude.ai integrations") and stop. Do not fall back to asking the user to paste the calendar.

Steps:

1. Read `_CLAUDE.md` at the vault root if it exists. Defer to its folder paths and conventions if it declares any. Default paths used below assume wiki-style.

2. Read `CRITICAL_FACTS.md` if it exists to pick up the user's timezone. If neither file declares a timezone, default to the system timezone of the current session and note that in the snapshot's `## For future Claude` block as a caveat.

3. Resolve the range. Use the user's current date as the anchor. Convert the resolved start and end into ISO 8601 strings (`YYYY-MM-DDTHH:MM:SS±HH:MM`) in the user's timezone. The end bound is exclusive at end-of-day local.

4. Call `mcp__claude_ai_Google_Calendar__list_calendars` once and pick the primary calendar (`primary: true`). If the user has multiple calendars they want included, accept a `--calendars <id1>,<id2>` flag; otherwise primary only.

5. Call `mcp__claude_ai_Google_Calendar__list_events` with `timeMin`, `timeMax`, `singleEvents: true`, `orderBy: "startTime"`. Include cancelled events filtered out client-side.

6. For each event, capture verbatim: id, htmlLink, summary, start, end, location, description, hangoutLink/conferenceData URL, attendees (email + displayName + responseStatus), organizer, status, recurringEventId if any.

7. Cross-link attendees against the vault:
   - For each attendee, search for an existing person note. Default search path: `wiki/entities/` (wiki-style) or `People/` (Obsidian-style) per `_CLAUDE.md`.
   - Match by full name first, then by the local-part of the email if the name is missing. Fuzzy match - handle missing diacritics and short forms.
   - If a person note is found, render the attendee as `[[Person Name]]`. If not found, render the plain name and append `(unknown person)` so future-Claude can decide whether to run `/obsidian-person` for them.

8. Detect quality issues across the range:
   - **Conflicts**: events whose intervals overlap on the same calendar.
   - **Back-to-back stretches**: 3+ meetings with no gap, flag the start and length.
   - **Focus gaps**: working-hours blocks (09:00-18:00 local by default unless overridden in `_CLAUDE.md`) with no meeting at all - call these out as available focus blocks.
   - **Externally-organized events**: events whose organizer email domain does not match the user's own domain.

9. Write the snapshot to the vault. Path (wiki-style default):
   - Single day: `wiki/agenda/YYYY-MM-DD - <today|tomorrow|day>.md`
   - Week or next-week: `wiki/agenda/YYYY-MM-DD - week.md` (using the Monday of the week as the date prefix)
   - Custom range: `wiki/agenda/YYYY-MM-DD - range.md` (using the start date)

   If a snapshot for the same range already exists, overwrite it (the calendar is the source of truth; the snapshot is a re-derivable view) and add a `superseded-at: <previous fetched-at>` field to the frontmatter so future-Claude knows it has been refreshed.

10. The snapshot must follow `references/ai-first-rules.md`:
    - Frontmatter (universal fields + agenda-specific):
      ```yaml
      ---
      date: YYYY-MM-DD              # the date the snapshot was generated
      type: agenda-snapshot
      range: "YYYY-MM-DD..YYYY-MM-DD"
      range-label: today | tomorrow | week | next-week | day | range
      calendar-source: google-calendar
      calendars: [primary]          # list of calendar IDs included
      fetched-at: "YYYY-MM-DDTHH:MM:SS±HH:MM"   # ISO 8601 with offset
      event-count: <n>
      conflict-count: <n>
      tags: [agenda, calendar]
      ai-first: true
      ---
      ```
    - `## For future Claude` preamble must state: this is a point-in-time snapshot of the user's calendar; the source of truth is Google Calendar, not this note; to refresh, re-run `/obsidian-agenda <range>`; the `fetched-at` timestamp is the recency anchor.
    - Body sections, in order:
      - `## Range` - start, end, timezone.
      - `## Summary` - one-line count per day, total events, focus blocks, conflicts.
      - `## Events` - one subsection per day (`### YYYY-MM-DD - <Weekday>`), each event rendered as a bullet with start-end time, title, attendees as `[[wikilinks]]`, location, conference link verbatim, and `event-id: <id>` so future commands (`/obsidian-meeting`, `/obsidian-schedule update:`) can locate it.
      - `## Conflicts` - only if conflicts were detected.
      - `## Focus blocks` - only if focus blocks were detected.
      - `## External organizers` - only if any.
    - Every person referenced uses `[[wikilinks]]`. Every URL (event htmlLink, conference link) is preserved verbatim.

11. Append one timestamped entry to `log.md`: `## [YYYY-MM-DDTHH:MM:SS±HH:MM] agenda | <range-label> - <event-count> events, <conflict-count> conflicts`.

12. Update today's daily note if it exists. Inject (do not overwrite) a brief reference under a `## Calendar` section with a link to the new snapshot file. Do not duplicate the event list inside the daily note.

13. Return to the user in chat:
    - The path of the snapshot file
    - Event count per day
    - Any conflicts, back-to-back stretches, and focus blocks
    - Any externally-organized events
    - One-line note if any attendees were marked `(unknown person)` so the user can run `/obsidian-person` to fill them in

Do not paraphrase event titles. Do not infer attendees that the calendar did not list. If the calendar is empty for the range, still write the snapshot (with `event-count: 0`) - future-Claude will use the absence of meetings as a signal too.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
