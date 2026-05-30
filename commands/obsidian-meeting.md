---
description: Generate a meeting note in the vault from a Google Calendar event - pre-fills attendees, time, and link so notes/decisions/action items can be captured
category: vault
exclude: [codex-cli, gemini-cli, opencode]
triggers_en: ["create a meeting note", "log this meeting", "meeting note for", "prep this meeting", "notes for last meeting"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-meeting $ARGUMENTS`:

The argument selects the event. Accepted forms:
- `last` - the most recent past event from the primary calendar (default if no argument)
- `next` - the next upcoming event from the primary calendar
- `today` - list today's events and ask which one
- `event-id:<id>` - a specific Google Calendar event ID
- A fuzzy event title - search the last 14 days and next 14 days for a matching title

This command requires the Google Calendar MCP tools (`mcp__claude_ai_Google_Calendar__list_events`, `mcp__claude_ai_Google_Calendar__get_event`, `mcp__claude_ai_Google_Calendar__list_calendars`). If they are not available, fail with a clear message and stop.

Steps:

1. Read `_CLAUDE.md` and `CRITICAL_FACTS.md` for vault conventions and timezone.

2. Resolve the event:
   - `last`: call `list_events` with `timeMin = now - 7d`, `timeMax = now`, `orderBy: "startTime"`, take the last one whose `end` is in the past.
   - `next`: call `list_events` with `timeMin = now`, `timeMax = now + 14d`, take the first.
   - `today`: list today's events and ask the user to pick one. Do not guess.
   - `event-id:<id>`: call `get_event` with the ID.
   - Fuzzy title: list events in `now ± 14d`, fuzzy-match titles, show top 3, confirm with the user.

3. Capture from the event: id, htmlLink, summary, start, end, location, description, hangoutLink/conferenceData URL, attendees (email + displayName + responseStatus), organizer, recurringEventId if any.

4. Cross-link attendees against the vault:
   - For each attendee email, search `wiki/entities/` (or `People/` per `_CLAUDE.md`) for a person note matching the displayName or the email.
   - If found: render as `[[Person Name]]` and capture the path.
   - If not found: render the plain displayName (or email local-part) and append `(unknown person - run /obsidian-person to add)`.

5. Locate a linked vault task, if any:
   - Search `wiki/tasks/` (and kanban boards under `boards/`) for any task whose frontmatter contains `calendar-event-id: <this-event-id>`.
   - If found, capture its path and title - the meeting note will backlink to it.

6. Build the meeting note. Path (wiki-style default):
   `wiki/meetings/YYYY-MM-DD - <slug>.md`
   - `YYYY-MM-DD` is the event's start date in the user's timezone.
   - `<slug>` is a kebab-case slug of the event summary (ASCII, lowercase, max 60 chars). Strip emojis and punctuation. Example summary `"Q3 planning with Acme"` → `q3-planning-with-acme`.
   - If a meeting note already exists at that path: do NOT overwrite. Read it and inject any missing structural sections (frontmatter additions only if fields are missing; never replace existing user-written content). Tell the user the note already exists and ask whether to open it or create a `-002` variant.

7. The note must follow `references/ai-first-rules.md`. Frontmatter:
   ```yaml
   ---
   date: YYYY-MM-DD              # the event's start date in user's TZ
   type: meeting
   event-id: <google-event-id>
   event-url: <htmlLink>
   conference-url: <hangoutLink>     # only if present
   start: "YYYY-MM-DDTHH:MM:SS±HH:MM"
   end: "YYYY-MM-DDTHH:MM:SS±HH:MM"
   duration-min: <integer>
   location: ""                       # verbatim from event; empty string if none
   organizer: "<organizer-email>"
   attendees: ["[[Person Name]]", ...]
   recurrence: "<recurringEventId>"   # only if recurring; otherwise omit
   linked-task: "[[wiki/tasks/...]]"  # only if a linked task was found in step 5
   related-projects: []               # fill in by inference; leave empty if unsure
   calendar-source: google-calendar
   tags: [meeting]
   ai-first: true
   ---
   ```

8. Body sections, in order:
   - `## For future Claude` - 2-3 sentences: this is the vault record of a meeting on <date> with <attendees>; capture intent, notes, decisions, and action items; the event remains the source of truth for time/attendees but this note is the source of truth for what happened.
   - `## Context` - pre-filled with the event's description verbatim (URLs preserved). If the description is empty, write "No agenda was attached to the calendar event."
   - `## Attendees` - bulleted list of `[[Person Name]]` with their `responseStatus` (accepted / tentative / declined / needsAction) in parentheses.
   - `## Notes` - empty section ready for the user to fill in. Do NOT write speculative content here.
   - `## Decisions` - empty section. Once filled by the user, /obsidian-decide can propagate these to project notes.
   - `## Action items` - empty section. Each item the user adds here should later flow into /obsidian-task.
   - `## Source` - the verbatim `event-url` and, if present, the `conference-url`. This is the recency anchor.

9. Propagate, do not orphan:
   - For each attendee that mapped to an existing `[[Person Note]]`, append a one-line entry under that person's `## Recent Interactions` section: `- YYYY-MM-DD - Meeting: [[wiki/meetings/...]]`.
   - If a linked task was found in step 5, append a line to the task body: `Meeting note: [[wiki/meetings/...]]`.
   - If today's daily note exists, inject under a `## Meetings` section: `- <time> - <title> ([[wiki/meetings/...]])`.
   - Append one timestamped entry to `log.md`: `## [YYYY-MM-DDTHH:MM:SS±HH:MM] meeting | "<title>" - <n> attendees, note at <path>`.

10. Confirm in chat:
    - The path of the meeting note
    - The attendees and how many had existing person notes vs. unknown
    - The path of any linked task that was backlinked
    - A reminder if any attendees still need person notes (so the user can run `/obsidian-person` to fill them in)

Do not write fictional notes, decisions, or action items. The Notes/Decisions/Action items sections are empty scaffolding for the human to fill in (or for a later command like `/obsidian-save` to populate from conversation). If the meeting has not happened yet (`next` mode), label the note as a prep document by setting `tags: [meeting, prep]` and noting in the `## For future Claude` preamble that this is pre-meeting prep, not a record of the meeting itself.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
