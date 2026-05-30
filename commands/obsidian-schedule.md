---
description: Create or move a Google Calendar event - standalone, from a vault task, or via suggested-time slots - and propagate the link back to the task
category: vault
exclude: [codex-cli, gemini-cli, opencode]
triggers_en: ["schedule a meeting", "book a meeting", "put this on my calendar", "schedule this task", "find a time for"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-schedule $ARGUMENTS`:

This command writes to Google Calendar. It requires the Google Calendar MCP tools (`mcp__claude_ai_Google_Calendar__list_events`, `mcp__claude_ai_Google_Calendar__create_event`, `mcp__claude_ai_Google_Calendar__update_event`, `mcp__claude_ai_Google_Calendar__suggest_time`, `mcp__claude_ai_Google_Calendar__list_calendars`). If they are not available, fail with a clear message and stop.

Three modes, selected from the first argument shape:

**Mode A - Standalone**: `/obsidian-schedule "<title>" <when> <duration>`
Example: `/obsidian-schedule "Sync with Acme" 2026-06-02 14:00 60min`
Use when the meeting has no corresponding vault task yet.

**Mode B - From task**: `/obsidian-schedule task:<path-or-fuzzy-title> <when> [duration]`
Example: `/obsidian-schedule task:wiki/tasks/2026-05-28-renew-aws-cert.md 2026-06-02 14:00 30min`
Use when you want the calendar event tied to an existing task. `<path-or-fuzzy-title>` accepts either a direct path or a fuzzy task title that gets searched in `wiki/tasks/` and on kanban boards.

**Mode C - Suggest time**: `/obsidian-schedule task:<path-or-fuzzy-title> suggest:<window> [duration]`
Example: `/obsidian-schedule task:onboarding-call suggest:next-week 45min`
Calls `mcp__claude_ai_Google_Calendar__suggest_time`, presents the proposed slots, and waits for the user to pick one before creating the event. Window accepts `today`, `tomorrow`, `week`, `next-week`, or `YYYY-MM-DD..YYYY-MM-DD`.

Steps:

1. Read `_CLAUDE.md` and `CRITICAL_FACTS.md` for vault conventions and timezone.

2. Parse the arguments and classify into Mode A, B, or C. If the parse is ambiguous, ask the user one clarifying question. Do not guess.

3. If Mode B or C, locate the task:
   - If `task:` is a path, read it directly.
   - If `task:` is a fuzzy title, search `wiki/tasks/` (or `Tasks/` per `_CLAUDE.md`) and kanban boards under `boards/` (or `Boards/`). Show what was found, confirm with the user before proceeding.
   - Extract from the task's frontmatter and body: `title` (heading or `task-title:`), `description` (the body up to the first `##`), `participants` or `related-people` (list of `[[Person Name]]` wikilinks), `due` if present, `related-projects`.

4. Resolve attendee emails:
   - For each `[[Person Name]]` participant, open `wiki/entities/Person Name.md` (or `People/`) and read the `email:` field from frontmatter.
   - If a person note is missing an `email:` field, surface this to the user and ask whether to (a) proceed without inviting that person, (b) prompt for the email and update the person note, or (c) abort.
   - Never invent or guess an email address.

5. Build the event payload:
   - `summary`: from the task title (Mode B/C) or the quoted string (Mode A).
   - `description`: from the task description in Mode B/C, plus a backlink line `Vault task: <vault-relative-path>`. In Mode A, leave description empty unless additional context was supplied.
   - `start.dateTime` and `end.dateTime`: ISO 8601 with the user's timezone offset. Use the resolved time and duration.
   - `attendees`: the resolved emails. Always include the user as organizer (the MCP defaults to the authenticated account).
   - `reminders`: leave Google Calendar defaults unless the user specified otherwise.
   - If the task has a Google Meet expectation (e.g. participants from multiple domains, or the task body contains "video"/"call"/"remote"), set `conferenceData` to request a Google Meet link via `conferenceDataVersion: 1`.

6. Conflict check before writing:
   - Call `mcp__claude_ai_Google_Calendar__list_events` with `timeMin`/`timeMax` covering the proposed slot.
   - If any existing event overlaps, show the conflict to the user with title, time, and attendee count, and ask: proceed anyway, pick a different time, or abort. Default to "ask, do not double-book".

7. Mode C only - suggest time:
   - Resolve the window into `timeMin`/`timeMax` (ISO 8601).
   - Call `mcp__claude_ai_Google_Calendar__suggest_time` with the resolved window, the duration, and the attendee emails.
   - Present up to 5 proposed slots ranked by the MCP. Wait for user selection.
   - After selection, fall through to step 6 (conflict check) and step 8 (create) with the chosen slot.

8. Create the event:
   - Call `mcp__claude_ai_Google_Calendar__create_event` with the payload.
   - Capture the response: `id`, `htmlLink`, `start`, `end`, `hangoutLink` if any.

9. Mode B and C only - propagate back to the task:
   - Use the Edit tool to merge into the task's frontmatter (never overwrite the file):
     ```yaml
     scheduled-at: "YYYY-MM-DDTHH:MM:SS±HH:MM"
     calendar-event-id: <event-id>
     calendar-event-url: <htmlLink>
     calendar-meet-url: <hangoutLink>     # only if present
     ```
   - If the task already had a `calendar-event-id`, this is a reschedule. Call `mcp__claude_ai_Google_Calendar__update_event` instead of `create_event` (move the start/end), and update the same fields in place. Do not leave orphan events on the calendar.
   - Add one line at the end of the task body: `Scheduled: <htmlLink> at <when>`.

10. If a person note's `email:` was used and the person note has no `last-interaction:` or it is older than this event, update `last-interaction:` to the scheduled date - same pattern as `/obsidian-person`.

11. Append one timestamped entry to `log.md`: `## [YYYY-MM-DDTHH:MM:SS±HH:MM] schedule | <mode> - "<title>" at <when> with <n> attendees → <event-id>`.

12. If today's daily note exists, inject (do not overwrite) a one-line entry under a `## Scheduled today` section: the event title, time, and link.

13. Confirm in chat:
    - The event title and time
    - The list of attendees that were invited (and any that were skipped because of missing emails)
    - The event URL and the Meet URL if any
    - The path of the task that was updated (Mode B/C)
    - A reminder if any person notes need an `email:` field filled in

Never schedule an event that overlaps an existing one without explicit confirmation. Never create a duplicate event for a task that is already scheduled - reschedule instead. Never write an attendee whose email you had to guess.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
