---
description: One calendar command with four modes - agenda (read a snapshot), reconcile (vault vs calendar gaps), meeting (event to note), schedule (task to event)
category: vault
exclude: [codex-cli, gemini-cli, opencode, hermes]
triggers_en: ["review my agenda", "check my calendar", "what's on my schedule", "what's on the calendar", "agenda for this week", "calendar check", "reconcile calendar", "what's not on my calendar", "am I missing anything on my calendar", "create a meeting note", "log this meeting", "meeting note for", "prep this meeting", "schedule a meeting", "book a meeting", "put this on my calendar", "schedule this task", "find a time for"]
triggers_es: ["revisa mi agenda", "revisa mi calendario", "qué tengo esta semana", "concilia mi calendario con el vault", "qué me falta en el calendario", "crea una nota de reunión", "registra esta reunión", "prepárame para esta reunión", "agenda una reunión", "reserva una reunión", "pon esto en mi calendario", "agenda esta tarea", "búscame un hueco para"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-calendar $ARGUMENTS`:

One command for everything that touches the calendar, selected by the first word (the **mode**):

- `agenda [range]` - read the calendar and write an AI-first snapshot to the vault (read-only on the calendar).
- `reconcile [window]` - flag commitments the vault implies that are NOT on the calendar (read-only; flags, never writes events).
- `meeting [selector]` - turn a calendar event into a meeting note in the vault.
- `schedule <args>` - create or move a calendar event (the only mode that writes to the calendar).

If no mode word is given, infer it: a bare range word (`today`, `week`, `next-week`, a date) means `agenda`; otherwise ask which mode. Default with no argument at all: `agenda today`.

All modes require a Google Calendar MCP. The claude.ai connector exposes `mcp__claude_ai_Google_Calendar__list_calendars`, `list_events`, `get_event`, `create_event`, `update_event`, `suggest_time`; if your calendar MCP namespaces its tools differently, use that server's equivalents. If no calendar MCP is connected, say so clearly and stop - do not fall back to asking the user to paste their calendar.

Always start by reading `_CLAUDE.md` (folder conventions, working hours) and `CRITICAL_FACTS.md` (timezone) if they exist. If neither declares a timezone, default to the session timezone and note that as a caveat. Resolve every folder per `references/folder-map.md` (wiki-style paths shown below).

---

## Mode: agenda - read the calendar into a snapshot note

Range argument: `today` (default), `tomorrow`, `week` (current ISO week Mon-Sun), `next-week`, `YYYY-MM-DD`, or `YYYY-MM-DD..YYYY-MM-DD`.

1. Resolve the range against the user's current date; convert start/end to ISO 8601 (`YYYY-MM-DDTHH:MM:SS+/-HH:MM`) in the user's timezone, end bound exclusive at end-of-day local.
2. `list_calendars` once, pick the primary (`primary: true`). Accept `--calendars <id1>,<id2>` to include more; otherwise primary only.
3. `list_events` with `timeMin`, `timeMax`, `singleEvents: true`, `orderBy: "startTime"`; filter cancelled events client-side.
4. For each event capture verbatim: id, htmlLink, summary, start, end, location, description, hangoutLink/conferenceData URL, attendees (email + displayName + responseStatus), organizer, status, recurringEventId.
5. Cross-link attendees against the entities folder (resolved per `references/folder-map.md`): match by full name then email local-part, fuzzy (handle missing diacritics/short forms). Found -> `[[Person Name]]`; not found -> plain name + `(unknown person)`.
6. Detect quality issues: **conflicts** (overlapping intervals on one calendar), **back-to-back stretches** (3+ with no gap), **focus gaps** (working-hours blocks 09:00-18:00 local unless overridden, with no meeting), **externally-organized events** (organizer domain != user's).
7. Write the snapshot (`type: agenda-snapshot`, schema in `references/ai-first-rules.md`) to the agenda folder (resolved per `references/folder-map.md` - wiki-style `wiki/agenda/`, Obsidian-style `Agenda/`): single day `YYYY-MM-DD - <today|tomorrow|day>.md`, week `YYYY-MM-DD - week.md` (Monday prefix), range `YYYY-MM-DD - range.md` (start prefix). If one exists for the range, overwrite it (the calendar is the source of truth) and add `superseded-at: <previous fetched-at>`. The `## For future Claude` preamble must state the calendar is the source of truth, not this note, and `fetched-at` is the recency anchor. Body: `## Range`, `## Summary`, `## Events` (one `### YYYY-MM-DD - <Weekday>` subsection per day; each event a bullet with start-end, title, `[[attendees]]`, location, conference link verbatim, and `event-id: <id>` so other modes can locate it), then `## Conflicts` / `## Focus blocks` / `## External organizers` only if present.
8. Append to the operation log (`Logs/YYYY-MM-DD.md` if the vault uses a `Logs/` folder - create today's file if needed - else `log.md`): `## [<iso>] agenda | <range-label> - <event-count> events, <conflict-count> conflicts`. Inject (do not overwrite) a `## Calendar` link into today's daily note.
9. Report: snapshot path, events per day, conflicts/back-to-back/focus blocks, external organizers, and any `(unknown person)` attendees. Do not paraphrase event titles or infer attendees. If the range is empty, still write the snapshot (`event-count: 0`).

---

## Mode: reconcile - what the vault expects that the calendar doesn't show

Window argument: `today`, `this week` (default), `this month`. Flag only - never add, move, or change events.

1. Pull the calendar for the window (primary calendar, list events with times).
2. Gather what the vault implies for the same window by listing and grepping (never from memory): active project `next_action`s and dated deadlines; tasks/board items due in the window; commitments in recent daily notes and captures (appointments, calls, travel, filing deadlines, birthdays); fixed dates from `CRITICAL_FACTS.md`.
3. Reconcile in two directions: **vault-implied, not on the calendar** (the headline - state the item, its `[[source note]]`, and date/urgency) and **on the calendar, no vault context** (lighter - events that might warrant a prep note or project link).
4. **Flag only.** For each gap propose an action ("add a hold?", "needs a prep note?") but do not touch the calendar - hard boundary.
5. Offer to record the reconciliation in today's daily note (inject, do not overwrite); on request, add tasks for items the user intends to act on.

---

## Mode: meeting - turn a calendar event into a meeting note

Selector argument: `last` (most recent past event, default), `next` (next upcoming), `today` (list and ask), `event-id:<id>`, or a fuzzy event title (search now +/- 14d, show top 3, confirm).

1. Resolve the event: `last` -> `list_events` timeMin now-7d..now, take last whose `end` is past; `next` -> now..now+14d, take first; `today` -> list and ask (do not guess); `event-id:` -> `get_event`; fuzzy -> match and confirm.
2. Capture: id, htmlLink, summary, start, end, location, description, hangoutLink, attendees (email + displayName + responseStatus), organizer, recurringEventId.
3. Cross-link attendees against the entities folder (resolved per `references/folder-map.md`): found -> `[[Person Name]]`; not found -> displayName + `(unknown person - run /obsidian-person to add)`.
4. Locate a linked task: search the tasks folder (resolved per `references/folder-map.md`) and boards for frontmatter `calendar-event-id: <this-event-id>`; if found, backlink it.
5. Write the meeting note (`type: meeting`, schema in `references/ai-first-rules.md`) to the meetings folder (resolved per `references/folder-map.md` - wiki-style `wiki/meetings/`, Obsidian-style `Meetings/`) as `YYYY-MM-DD - <slug>.md` (event start date in user's TZ; kebab-case ASCII slug, max 60 chars, strip emojis/punctuation). If it already exists, do NOT overwrite - inject only missing structural sections and ask whether to open it or make a `-002` variant. Frontmatter carries event-id, event-url, conference-url (if any), start/end, duration-min, location verbatim, organizer, `attendees: ["[[Person]]"]`, recurrence (if recurring), linked-task (if found), related-projects (by inference, else empty). Body in order: `## For future Claude` (the event is source of truth for time/attendees, this note for what happened), `## Context` (event description verbatim, or "No agenda was attached to the calendar event."), `## Attendees` (`[[Person]]` + responseStatus), then EMPTY `## Notes`, `## Decisions`, `## Action items` sections, and `## Source` (event-url + conference-url verbatim, the recency anchor).
6. Propagate: append `- YYYY-MM-DD - Meeting: [[wiki/meetings/...]]` under each existing attendee's `## Recent Interactions`; add `Meeting note: [[...]]` to a linked task; inject `- <time> - <title> ([[...]])` under today's daily note `## Meetings`; append `## [<iso>] meeting | "<title>" - <n> attendees, note at <path>` to the operation log (`Logs/YYYY-MM-DD.md` if the vault uses a `Logs/` folder - create today's file if needed - else `log.md`).
7. Confirm: note path, attendees (existing vs unknown), any backlinked task, and a reminder for missing person notes. Never fabricate Notes/Decisions/Action items - those sections are empty scaffolding for the human or a later `/obsidian-save`. For a future event (`next`), set `tags: [meeting, prep]` and label the preamble as pre-meeting prep.

---

## Mode: schedule - create or move a calendar event (writes to the calendar)

Three sub-modes from the argument shape:

- **Standalone**: `schedule "<title>" <when> <duration>` - e.g. `schedule "Sync with Acme" 2026-06-02 14:00 60min`. No vault task yet.
- **From task**: `schedule task:<path-or-fuzzy-title> <when> [duration]` - ties the event to an existing task.
- **Suggest time**: `schedule task:<path-or-fuzzy-title> suggest:<window> [duration]` - calls `suggest_time`, presents slots, waits for the user to pick before creating. Window: `today`/`tomorrow`/`week`/`next-week`/`YYYY-MM-DD..YYYY-MM-DD`.

1. Parse the args and classify the sub-mode. If ambiguous, ask ONE clarifying question - do not guess.
2. From-task / suggest: locate the task (`task:` path read directly, else fuzzy-search the tasks folder resolved per `references/folder-map.md` and boards, confirm). Extract title, description (body up to first `##`), participants/`related-people`, `due`, `related-projects`.
3. Resolve attendee emails: for each `[[Person]]`, read `email:` from the person's note in the entities folder (resolved per `references/folder-map.md`). If missing, ask whether to proceed without them, prompt for and save the email, or abort. Never invent an email.
4. Build the event payload: `summary` (task title or quoted string); `description` (task description + backlink `Vault task: <path>` for task modes; empty for standalone unless context supplied); `start.dateTime`/`end.dateTime` ISO 8601 with TZ offset; `attendees` the resolved emails (user is organizer); Google defaults for reminders; set `conferenceData` via `conferenceDataVersion: 1` if a Meet is implied (multi-domain attendees, or body says video/call/remote).
5. Conflict check before writing: `list_events` over the proposed slot; if anything overlaps, show it (title, time, attendee count) and ask: proceed, pick another time, or abort. Default to "ask, do not double-book".
6. Suggest sub-mode only: resolve the window to `timeMin`/`timeMax`, call `suggest_time` with duration + attendee emails, present up to 5 ranked slots, wait for selection, then fall through to the conflict check and creation with the chosen slot.
7. Create with `create_event`; capture `id`, `htmlLink`, `start`, `end`, `hangoutLink`.
8. Task sub-modes - propagate back (Edit, never overwrite): merge `scheduled-at`, `calendar-event-id`, `calendar-event-url`, `calendar-meet-url` (if any) into the task frontmatter; add `Scheduled: <htmlLink> at <when>` to the body. If the task already had a `calendar-event-id`, this is a reschedule: call `update_event` instead of creating, and update fields in place - never leave orphan events.
9. If a person note's `email:` was used and its `last-interaction:` is missing or older than this event, update it to the scheduled date (same pattern as `/obsidian-person`).
10. Append `## [<iso>] schedule | <sub-mode> - "<title>" at <when> with <n> attendees -> <event-id>` to the operation log (`Logs/YYYY-MM-DD.md` if the vault uses a `Logs/` folder - create today's file if needed - else `log.md`); inject a one-line entry under today's daily note `## Scheduled today`.
11. Confirm: title and time, attendees invited (and any skipped for missing emails), event URL + Meet URL, the updated task path (task modes), and a reminder for any person notes needing an `email:`. Never double-book without confirmation, never duplicate an already-scheduled task (reschedule instead), never write a guessed email.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Only flag or schedule commitments grounded in the vault or calendar - never invent a deadline, an attendee, or an email. Before claiming a note, person, or event is absent, search exhaustively (grep by name, attendees, address across all folders) - false absence is the most common failure mode. Mark unknowns as `TBD`. See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
