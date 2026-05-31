# AI-First Note Rules

The vault is designed for **future-Claude** to read and reason over, not for human review. The owner rarely opens notes directly - they call Claude to retrieve, synthesize, and connect dots across years of accumulated knowledge. **Every command that writes to the vault must produce notes that follow these rules.**

This document is the canonical specification. It lives at `references/ai-first-rules.md` in the obsidian-second-brain repo and is referenced from `_CLAUDE.md` Section 0, every slash command, and `references/write-rules.md`.

---

## The 7 Rules

### 1. Self-contained context
Each note must explain itself. Future-Claude may pull this single note via `/obsidian-find` or vault scan with no surrounding context. Don't rely on backlinks alone for meaning. State the *what*, the *why*, and the *when* inside the note itself.

### 2. "For future Claude" preamble
Every note begins with a 2-3 sentence summary in plain English under a `## For future Claude` header (immediately after the frontmatter). Future-Claude reads this to decide relevance in 10 seconds before parsing the rest. State what's in the note, why it was saved, and any temporal/staleness caveat.

```markdown
## For future Claude
This note is a [type] about [topic] saved on [date]. It [main purpose].
[Optional caveat about staleness, confidence, or scope.]
```

### 3. Rich, consistent frontmatter
Filterable metadata. Different note types have different schemas (see below) but every note has machine-readable frontmatter.

**Universal fields (every note):**
```yaml
---
date: YYYY-MM-DD              # creation or update date
type: <note-type>             # see Type Schemas below
tags: [...]                   # always include the type as a tag
ai-first: true                # explicit flag
---
```

### 4. Recency markers per claim
When stating external facts, attach the date inline:

```markdown
- Mem0 raised $24M Series A (as of 2026-04, mem0.ai/blog/series-a)
- Anthropic released native memory tool (as of 2026-02, anthropic.com/news/memory)
```

So future-Claude knows what to verify before trusting individual facts.

### 5. Sources preserved verbatim
Every external claim has its source URL inline. Don't paraphrase a citation - keep the actual URL so the claim can be re-verified or refreshed years later.

### 6. Cross-links are mandatory
Every person, project, idea, decision, or concept referenced uses `[[wikilinks]]` so the graph is traversable by future-Claude:

```markdown
Sarah at [[People/Sarah Chen]] decided to ship the [[Projects/Dashboard Refactor]] by Friday.
```

If a linked note doesn't exist, create a stub (per `references/write-rules.md` § Stub Notes).

### 7. Confidence levels
Where applicable, mark claims with confidence:
- `stated` - directly quoted or claimed by a source
- `high` - multiple sources agree
- `medium` - single source, plausible
- `speculation` - your inference

Use this in frontmatter (`confidence: high`) or inline (`(confidence: speculation)`).

---

## Anti-fabrication and search-completeness (hard rules)

Rules 1-7 govern how a note is written. These govern how Claude reads and reasons over the vault before writing. They are non-negotiable because the failure modes below silently corrupt the vault's value as a memory.

### False absence (the most common failure mode)
Never assert that a note, person, project, or file does NOT exist without an exhaustive search first. Saying "no note exists" when one does is the single most common observed failure - more common than fabrication. Verify presence or absence by listing and grepping the vault, not from memory or a single lucky query. Search by every plausible name, alias, and folder before concluding something is missing. When unsure, over-include and label the uncertainty rather than under-report.

### Search completeness
When a command reads or scans the vault, enumerate exhaustively - do not sample. List every matching note, not a representative few. A partial scan that is reported as complete produces confident wrong answers, which are worse than an honest "I only checked X".

### No fabrication
Never invent facts, entities, rates, dates, or relationships that were not actually stated. Mark unknowns as `TBD`. Attach a recency marker and source URL to every external claim (Rules 4-5); mark inferences with a confidence level (Rule 7). Never fabricate a value just to make a section look complete - an empty `## Decisions` section is correct when no decision was made.

---

## Type Schemas

Frontmatter schemas by note type. **Add fields specific to your type - never remove the universal fields.**

### `type: daily`
```yaml
date: YYYY-MM-DD
type: daily
tags: [daily]
mood: ""        # optional
energy: ""      # optional
ai-first: true
```

### `type: project`
```yaml
date: YYYY-MM-DD              # creation
updated: YYYY-MM-DD           # last meaningful update
type: project
status: active                # active | planning | completed | archived | on-hold
tags: [project, ...]
related-people: ["[[People/...]]", ...]
related-projects: ["[[Projects/...]]", ...]
ai-first: true
```

### `type: person`
```yaml
date: YYYY-MM-DD              # first interaction logged
updated: YYYY-MM-DD
type: person
tags: [person, ...]
role: ""
company: "[[Companies/...]]"
relationship: weak | medium | strong
last-interaction: YYYY-MM-DD
related-projects: ["[[Projects/...]]", ...]
ai-first: true
```

### `type: idea`
```yaml
date: YYYY-MM-DD
type: idea
tags: [idea, ...]
status: captured              # captured | exploring | graduated | shelved
related-projects: ["[[Projects/...]]", ...]
ai-first: true
```

### `type: task`
```yaml
date: YYYY-MM-DD
type: task
status: in-progress           # in-progress | done | waiting | cancelled
priority: 🔴 | 🟡 | 🟢
due: YYYY-MM-DD
tags: [task, ...]
related-projects: ["[[Projects/...]]", ...]
related-people: ["[[People/...]]", ...]
ai-first: true
```

### `type: decision`
Decisions usually live INSIDE project notes' Key Decisions sections. When a standalone decision note is needed:
```yaml
date: YYYY-MM-DD
type: decision
tags: [decision, ...]
related-projects: ["[[Projects/...]]", ...]
confidence: stated | high | medium | speculation
sources: [...]                # inline URLs/wikilinks supporting the decision
ai-first: true
```

### `type: devlog` / `type: log`
```yaml
date: YYYY-MM-DD
type: devlog
tags: [devlog, ...]
project: "[[Projects/...]]"
related-people: ["[[People/...]]", ...]
ai-first: true
```

### `type: review`
```yaml
date: YYYY-MM-DD              # the date the review was generated
period-start: YYYY-MM-DD
period-end: YYYY-MM-DD
type: review                  # weekly | monthly
tags: [review, ...]
ai-first: true
```

### `type: research` / `type: research-deep` / `type: x-read` / `type: x-pulse` / `type: youtube` / `type: podcast`
See `commands/research*.md`, `commands/x-*.md`, `commands/youtube.md`, and `commands/podcast.md` for the full schemas. All set `ai-first: true` and follow the universal rules.

### `type: podcast`
```yaml
date: YYYY-MM-DD
time: HH:MM
type: podcast
show: ""                      # podcast show name
host: ""                      # show host or author
episode-title: ""
episode-url: ""               # link to episode page (publisher-provided)
feed-url: ""                  # RSS feed URL
source-url: ""                # the URL the user pasted (Apple, RSS, etc.)
guid: ""                      # episode GUID from RSS
published: ""                 # publisher-provided publish date string
duration: ""                  # publisher-provided duration string
transcript-source: rss-transcript-tag | whisper-api | show-notes
tags: [research, podcast, ...]
cost-usd: 0.0
ai-first: true
```

### `type: adr`
```yaml
date: YYYY-MM-DD
type: adr
tags: [adr, decision]
decision: ""                  # one-line summary
status: proposed | accepted | superseded
related-projects: ["[[Projects/...]]", ...]
supersedes: "[[Knowledge/ADR-...]]"   # optional
ai-first: true
```

### `type: synthesis` / `type: emerge` / `type: connect` / `type: challenge`
Outputs from thinking tools. Each saves to `Knowledge/` or `Ideas/` with:
```yaml
date: YYYY-MM-DD
type: <thinking-tool-type>
tags: [research, thinking, ...]
sources: [...]                # vault notes that informed this
related-people: [...]
related-projects: [...]
ai-first: true
```

### `type: agenda-snapshot`
Written by `/obsidian-agenda`. A re-derivable point-in-time view of the calendar - Google Calendar is the source of truth, not this note. `fetched-at` is the recency anchor.
```yaml
date: YYYY-MM-DD              # date the snapshot was generated
type: agenda-snapshot
range: "YYYY-MM-DD..YYYY-MM-DD"
range-label: today           # today | tomorrow | week | next-week | day | range
calendar-source: google-calendar
calendars: [primary]
fetched-at: "YYYY-MM-DDTHH:MM:SS+HH:MM"   # ISO 8601 with offset
event-count: 0
conflict-count: 0
tags: [agenda, calendar]
ai-first: true
```

### `type: meeting`
Written by `/obsidian-meeting` from a calendar event. Notes / Decisions / Action items sections start empty - never fabricate them (see the anti-fabrication hard rule).
```yaml
date: YYYY-MM-DD
type: meeting
event-id: ""                 # Google Calendar event id (links the note to the event)
event-url: ""
conference-url: ""
start: "YYYY-MM-DDTHH:MM:SS+HH:MM"
end: "YYYY-MM-DDTHH:MM:SS+HH:MM"
duration-min: 0
organizer: ""
attendees: ["[[People/...]]", ...]
tags: [meeting]
ai-first: true
```

### `type: recurring-task`
Written by `/obsidian-recurring`. Tracks a repeating obligation with a cadence and a computed `next-due` that advances on each completion. The History section logs each occurrence.
```yaml
date: YYYY-MM-DD
type: recurring-task
cadence: ""                  # e.g. "monthly day 20", "every quarter", "weekly Mon"
owner: ""
blocker: "[[People/...]]"    # optional - who/what gates it
next-due: YYYY-MM-DD         # computed next occurrence
amount: ""                   # optional - for payments
tags: [recurring-task]
ai-first: true
```

### `type: architecture-overview`
Written by `/obsidian-architect`. The top-level map of a codebase: stack, modules, one diagram, personas. Lives under `Projects/<name>/Architecture/`.
```yaml
date: YYYY-MM-DD
type: architecture-overview
project: "[[Projects/...]]"
stack: []                    # languages / frameworks detected
scanned-commit: ""           # the git short-commit the docs reflect (recency anchor)
tags: [architecture]
ai-first: true
```

### `type: architecture-module`
Written by `/obsidian-architect`, one per core module: what it does, what it depends on, its role.
```yaml
date: YYYY-MM-DD
type: architecture-module
project: "[[Projects/...]]"
module: ""                   # module name
path: ""                     # path within the codebase
scanned-commit: ""
tags: [architecture]
ai-first: true
```

---

## Preamble Templates by Type

### Daily note
```markdown
## For future Claude
Daily note for YYYY-MM-DD. Captures what was worked on, who was met, decisions made, and energy/mood for the day. Skim the section headers; specific work logs link to dev logs and project notes.
```

### Project note
```markdown
## For future Claude
[Project name] is a [type — work / personal / open-source] project with status [status] as of [date]. The Overview section explains what it is and why it exists. Recent Activity captures the last 30 days. Key Decisions documents major directional choices with rationale.
```

### Person note
```markdown
## For future Claude
[Name] is [role] at [[Company]]. Relationship strength: [weak/medium/strong] as of [date]. Last interaction: [date]. The Recent Interactions section logs every conversation chronologically.
```

### Idea note
```markdown
## For future Claude
Idea captured on [date] about [topic]. Status: [captured/exploring/graduated/shelved]. The body explains the idea, why it's interesting, and what would make it real. If shelved, the reason is documented at the bottom.
```

### Decision (standalone)
```markdown
## For future Claude
Decision made on [date] about [topic]. Context section explains what prompted it. Options Considered lists the alternatives evaluated. Rationale captures why this option won. Consequences documents what changed in the vault as a result.
```

### Dev log
```markdown
## For future Claude
Dev log for [date] about [project]. Captures work done, problems encountered, decisions made, and next steps. Specific file paths and commit hashes are preserved verbatim for re-verification.
```

### Review (weekly / monthly)
```markdown
## For future Claude
[Weekly / Monthly] review covering [period-start] through [period-end]. The review summarizes shipped work, decisions made, people met, and patterns that emerged. Use this as a baseline when researching what was true at the end of the period.
```

### Research (any research type)
```markdown
## For future Claude
[Research type] on "[topic]" performed on [datetime]. [Specific scope: what was searched, how many sources, what model.] [Caveat about recency or confidence.] Use the recency markers per claim to know what to verify before relying on individual facts.
```

### ADR
```markdown
## For future Claude
Architectural decision record from [date]. Documents a structural decision in the vault (folder rename, schema change, etc.) so future-Claude can answer "why is the vault structured this way?" without re-deriving the reasoning.
```

---

## Common Anti-Patterns

Don't do these. They produce notes that are useless to future-Claude.

| Anti-pattern | Why it's bad |
|---|---|
| `date: today` | Use the actual `YYYY-MM-DD` - "today" is meaningless when read later |
| Bare claims without dates | "Mem0 is the leader" - leader as of when? |
| External URL omitted | "According to a study, X is true" - which study? |
| Plain text names instead of `[[wikilinks]]` | Breaks the link graph - future-Claude can't traverse |
| "See above" / "as mentioned" | Future-Claude may pull this note in isolation. Repeat the context. |
| Trusting the model to infer | Be explicit. State the type, the rule applied, the source. |
| Multi-paragraph human-readable narratives | Bullets and structure beat prose for retrieval. |
| Forgetting `ai-first: true` | The flag lets future-Claude know which notes meet the standard. |
| Em-dash (`—`), curly quotes (`"`), Unicode math (`≥ ≤ ≠`) | Substitution Unicode slips in silently via LLM defaults. Caught by `validate-ai-first.sh` check 5. Use ` - ` for dashes, straight `"` quotes, ASCII operators (`>=`, `!=`). Allowed: box-drawing (`─`), arrows (`→ ←`), currency (`€ £ ¥`), Nerd Font codepoints - all carry semantic meaning. |

---

## Audit Checklist

When auditing an existing note (Phase 2 work or one-off cleanup), verify:

- [ ] Has `## For future Claude` preamble below frontmatter
- [ ] `ai-first: true` in frontmatter
- [ ] `type:` field set correctly
- [ ] `date:` in YYYY-MM-DD format
- [ ] Tags include the type
- [ ] All people/projects/concepts use `[[wikilinks]]`
- [ ] External claims have recency markers AND source URLs
- [ ] If multi-source, confidence levels marked
- [ ] No "see above" or context-dependent references
- [ ] Self-contained - readable with zero context
- [ ] No fabricated facts, entities, or dates - unknowns marked `TBD`
- [ ] Any "no note / nothing found" claim was verified by an exhaustive search, not from memory

---

## Migration Note

This rule was established 2026-04-25 and shipped as part of obsidian-second-brain v0.5.0 (Research Toolkit). All 5 research commands (`/x-read`, `/x-pulse`, `/research`, `/research-deep`, `/youtube`) follow it from day one. The 26 existing `/obsidian-*` commands were updated in v0.6.0 (Phase 2) to explicitly reference this document. Notes written before that may not yet meet the standard - `/obsidian-health` flags them.
