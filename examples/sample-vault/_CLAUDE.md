# _CLAUDE.md

Operating manual for this vault. Loaded by Claude Code on every session that touches it.

This is a sample vault belonging to the fictional **Alex Rivera**. The structure shown here is what `/obsidian-init` produces, lightly edited to feel lived-in. Treat every name, project, and URL inside as fictional.

## Section 0 - AI-first rule (non-negotiable)

This vault is for **future-Claude**, not human reading. Every note Claude writes or updates must follow [`references/ai-first-rules.md`](https://github.com/eugeniughelbur/obsidian-second-brain/blob/main/references/ai-first-rules.md):

1. Self-contained context (no "see above")
2. `## For future Claude` preamble after frontmatter
3. Rich frontmatter with `type`, `date`, `tags`, `ai-first: true`
4. Recency markers per external claim
5. Source URLs preserved verbatim
6. `[[wikilinks]]` for every person, project, idea, decision
7. Confidence levels (`stated | high | medium | speculation`) where applicable

If a note Claude is about to write would not pass this rule, fix the note before saving. No exceptions for "small" or "quick" entries.

## Section 1 - Identity

- **Owner:** Alex Rivera, indie hacker building [[Projects/Tide]]
- **Location:** Lisbon, Portugal
- **Working hours:** roughly 09:00 to 18:00 WET, hard stop on weekends
- **Time zone:** Europe/Lisbon

## Section 2 - Folder structure

- `Daily/` - one file per day, `YYYY-MM-DD.md`
- `Projects/` - one file per active project, status-tagged
- `people/` - one file per person worth remembering
- `Ideas/` - fragment captures, dated filenames
- `Decisions/` - standalone decision records (most decisions live inside project notes)
- `Knowledge/` - synthesis, ADRs, learning notes
- `Research/` - outputs from `/research`, `/research-deep`, `/x-read`, `/x-pulse`, `/youtube`
- `wiki/logs/` - dev logs and session logs
- `social-media/` - content pipeline (ideas, swipe file, data points)
- `Boards/` - kanban boards for tasks per project
- `Archive/` - archived notes, never deleted

## Section 3 - Active projects (as of 2026-04-27)

- [[Projects/Tide]] - habit-tracking SaaS, status: active, retention rebuild in progress

## Section 4 - Key relationships

- [[people/Alex Rivera]] - vault owner
- [[people/Sam Patel]] - co-founder of Tide, technical lead

## Section 5 - Defaults Claude should follow

- Always search before creating a new note (duplicates are vault rot)
- Always update boards and the daily note when adding a task
- Never create an orphaned note (every note links to at least one other)
- Confidence levels are mandatory for any external claim
- When in doubt about a fact, mark it `TBD` rather than guessing
