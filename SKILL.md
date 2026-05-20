---
name: obsidian-second-brain
description: >
  Operate any Obsidian vault as a living, self-rewriting second brain (an evolution
  of Karpathy's LLM Wiki pattern: sources rewrite existing pages, contradictions
  reconcile automatically, scheduled agents maintain the vault while you sleep).
  Use this skill whenever
  the user asks Claude to read, write, update, search, or manage their Obsidian
  vault — including saving notes from conversation, creating daily entries, updating
  kanban boards, logging dev work, managing people notes, capturing decisions,
  tracking deals, or maintaining any vault structure. Also triggers when the user
  wants to bootstrap a new vault from scratch, run a vault health check, or drop
  a _CLAUDE.md into their vault so all Claude surfaces share the same operating rules.
  Includes a research toolkit (6 commands: /x-read, /x-pulse, /research, /research-deep,
  /notebooklm, /youtube) for AI-powered research via Grok, Perplexity, NotebookLM, and YouTube — findings save
  to the vault automatically following the AI-first vault rule. Use proactively whenever
  the conversation produces information worth preserving (decisions, people met, projects
  started, tasks completed, lessons learned, research findings).
---

# Obsidian Second Brain

> Claude operates your Obsidian vault as a self-rewriting knowledge base. An evolution of [Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): sources rewrite existing pages instead of just appending, contradictions reconcile automatically, and scheduled agents maintain the vault while you sleep.
> Everything worth remembering gets saved. Every update propagates everywhere it belongs.

---

## Quick Start

### 0. Choose vault access method (in order of preference)

Try these methods in order. Use the first one available:

**Method 0 — SessionStart hook (if configured):**
If `hooks/load_vault_context.py` is wired as a SessionStart hook in `~/.claude/settings.json`, `_CLAUDE.md` is injected into context automatically at session start. Skip step 1 below.
To wire it: `bash scripts/setup.sh "/path/to/vault"` or run `/obsidian-setup`.

**Method A — MCP server (`mcp-obsidian`):**
If the MCP tools (`get_file_contents`, `list_files_in_vault`, `search`, `append_content`, `write_file`) are available, use them.

**Method B — Direct filesystem (fallback, always works):**
Use standard file tools (Read, Write, Edit, Glob) against the vault path. The vault is plain markdown — all operations work without MCP, just more verbosely.

If MCP is not installed, silently use filesystem access. Tell the user ONCE (first time only):

> "For faster vault access on large vaults, consider installing mcp-obsidian: `claude mcp add obsidian-vault -s user -- npx -y mcp-obsidian \"/path/to/your/vault\"`. Everything works without it."

### 1. First time in a vault → read `_CLAUDE.md`

Before doing anything in a vault, check if `_CLAUDE.md` exists at the vault root:

```
get_file_contents("_CLAUDE.md")
```

If it exists: follow its rules exactly — they override the defaults in this skill. Where `_CLAUDE.md` is silent, fall back to the defaults below.
If it doesn't exist: use the defaults in this skill, then offer to create one.

If the SessionStart hook is active, `_CLAUDE.md` is already in context — skip this step.

### 2. First time with a new user → run discovery

```
list_files_in_vault()
```

Scan the structure to understand: folder names, template locations, naming conventions, frontmatter patterns. Then read 2–3 existing notes with `get_file_contents(path)` to calibrate writing style before creating anything new.

### 3. Bootstrap a new vault

If the user has no vault yet, run:
```bash
# One-line install + bootstrap (asks 3 questions: vault path, your name, preset)
curl -sL https://raw.githubusercontent.com/eugeniughelbur/obsidian-second-brain/main/scripts/quick-install.sh | bash

# Or manual:
python scripts/bootstrap_vault.py --path ~/path/to/vault --name "Your Name"

# With a preset:
python scripts/bootstrap_vault.py --path ~/my-vault --name "Your Name" --preset executive
python scripts/bootstrap_vault.py --path ~/my-vault --name "Your Name" --preset builder
python scripts/bootstrap_vault.py --path ~/my-vault --name "Your Name" --preset creator
python scripts/bootstrap_vault.py --path ~/my-vault --name "Your Name" --preset researcher

# With style override:
python scripts/bootstrap_vault.py --path ~/my-vault --name "Your Name" --style obsidian

# With assistant mode (maintaining vault for someone else):
python scripts/bootstrap_vault.py --path ~/my-vault --name "Your Name" --mode assistant --subject "Boss Name"
```

Then configure `mcp-obsidian` to point at the new vault path and restart Claude.

**Presets** customize the vault for different use cases:
- **`executive`** — Decisions, people, meetings, strategic planning. Kanban: OKRs, Quarterly, Weekly.
- **`builder`** — Projects, dev logs, architecture decisions, debugging. Kanban: Backlog, Sprint, Done.
- **`creator`** — Content calendar, ideas pipeline, audience notes, publishing. Kanban: Ideas, Drafts, Published.
- **`researcher`** — Sources, literature notes, hypotheses, methodology. Kanban: Reading, Processing, Synthesized.

Default (no preset) gives a general-purpose vault. All presets use wiki-style by default.

**Assistant mode** creates a `_CLAUDE.md` configured for operating a vault on behalf of someone else. See `references/claude-md-assistant-template.md`.

See `references/vault-schema.md` for full structural details.

---

## Core Operating Principles

### AI-first vault rule (applies to every note)
The vault is designed for **future-Claude** to read and reason over, not for human review. Every note Claude writes — across all 32 commands — must follow `references/ai-first-rules.md`:

1. **Self-contained context** — each note explains itself; don't rely on backlinks alone
2. **"For future Claude" preamble** — 2-3 sentence summary so Claude can decide relevance in 10 seconds
3. **Rich, consistent frontmatter** — `type`, `date`, `tags`, `ai-first: true`, plus type-specific fields (see `ai-first-rules.md` for schemas per note type)
4. **Recency markers per claim** — "Mem0 raised $24M (as of 2026-04, mem0.ai)" so future-Claude knows what to verify
5. **Sources preserved verbatim** — every external claim has its source URL inline
6. **Cross-links mandatory** — every person/project/idea/decision uses `[[wikilinks]]`
7. **Confidence levels** — `stated | high | medium | speculation` where applicable

This rule lives in `_CLAUDE.md` Section 0 of every vault using this skill, and in `references/ai-first-rules.md` (the canonical specification with frontmatter schemas + preamble templates per note type).

### Never create in isolation
Every write operation must ask: *where else does this belong?*

| You create/update... | Also update... |
|---|---|
| A new project note | Kanban board (add to Backlog), today's daily note (link it) |
| A task completed | Kanban board (move to Done), project note (log it), daily note |
| A person note | Daily note (mention interaction), People index if it exists |
| A dev log | Daily note (link it), project note (Recent Activity) |
| A deal update | Side Biz / Deals kanban, Dashboard totals |
| A decision made | Project note (Key Decisions), daily note |
| A mention/shoutout | Mentions Log, person's note, daily note |
| A hook, contrarian angle, or content idea | `social-media/ideas.md` (if folder exists) |
| A specific reusable number or stat | `social-media/data-points.md` (if folder exists) |
| An external post that performed well + why | `social-media/swipe-file.md` (if folder exists) |
| Research findings worth keeping | `social-media/research/YYYY-MM-DD — topic.md` (if folder exists) |
| Any vault write | `log.md` (append timestamped entry), `index.md` (update if new note created) |

Always propagate. Never create a single orphaned note.

### Bi-temporal facts — never overwrite, always append
When a fact changes (role, company, status, location, tool), NEVER delete the old value. Add a new entry to the `timeline:` frontmatter array with both event time AND transaction time:

```yaml
timeline:
  - fact: "CTO at Single Grain"
    from: 2024-01-01            # event time: when it was true
    until: 2026-04-07
    learned: 2026-02-23         # transaction time: when the vault learned it
    source: "[[2026-02-23]]"    # where from
  - fact: "Architect at Single Grain"
    from: 2026-04-07
    until: present
    learned: 2026-04-07
    source: "[[2026-04-07]]"
```

Top-level fields (`role:`, `status:`, `company:`) always reflect the CURRENT state. The `timeline:` preserves the full history with provenance.

This enables:
- Historical queries ("who was my manager in February?")
- Reflective thinking ("you believed X on Tuesday, then ingested Y on Wednesday and shifted to Z")
- Smart reconciliation (different facts at different times = not a contradiction)
- Full audit trail (when did the vault learn each fact, from what source?)

### CRITICAL_FACTS.md — always loaded
A tiny file (~120 tokens) loaded alongside `SOUL.md` at L0 in every session. Contains facts needed in every conversation:
- Timezone
- Current manager
- Current location
- Current company and role
- Any other fact that's true RIGHT NOW and relevant to every interaction

Update this file whenever a critical fact changes. Keep it under 150 tokens.

### Raw is immutable
In wiki-style vaults, the `raw/` folder contains original sources (articles, transcripts, PDFs). Claude reads these but NEVER modifies them. They are the source of truth. If a wiki page gets corrupted, re-derive it from the raw source. When ingesting, always save the original to `raw/` and the derived pages to `wiki/`.

### Maintain `index.md` and `log.md`
Two structural files that keep the vault navigable and auditable:

- **`index.md`** — A catalog of all vault pages organized by category. Claude reads this FIRST when navigating the vault instead of searching — faster and cheaper on tokens. Update it whenever a new note is created or deleted. Format: `- [[Note Name]] — brief description` grouped under folder headings.

- **`log.md`** — An append-only chronological log of every vault operation. Every save, ingest, health check, and structural change gets a timestamped entry. Never delete or rewrite entries — only append. Format: `## [YYYY-MM-DD] action | Description`

### The vault is a living system
The vault is not a filing cabinet. It is a living knowledge base that rewrites itself with every input. When new information enters:
- Existing pages get REWRITTEN with new context, not just appended to
- Contradictions between old and new claims get resolved or explicitly documented
- New patterns across multiple sources trigger automatic synthesis pages
- Stale claims get replaced with current information, with history preserved

The vault after an ingest should be DIFFERENT — not just bigger. If pages that existed before aren't smarter, more connected, and more current, the ingest wasn't deep enough.

### Two-Output Rule
Every interaction that produces insight must generate two outputs:
1. **The answer** — what the user sees in the conversation
2. **A vault update** — the insight filed back into the relevant note(s)

This applies to all thinking tools and any query where Claude synthesizes information from the vault.

### Synthesis Hook
When Claude notices a pattern during any operation (ingest, query, challenge, emerge), it should automatically create a synthesis page in `wiki/concepts/`. Patterns include:
- The same concept appearing in 3+ unrelated sources
- A claim being reinforced by multiple independent sources
- A trend emerging across time-sequenced notes
- Two entities sharing unexpected connections

Synthesis pages are the vault thinking for itself — connecting dots the user hasn't connected yet.

### Reconciliation
The vault should never contain two pages that disagree without knowing they disagree. When contradictions are found (during ingest, health checks, or queries), either:
- Resolve them: rewrite the outdated page, preserve history
- Document them: create an explicit conflict page marked as an open question

Use `/obsidian-reconcile` for vault-wide truth maintenance.

### Proactive save reminders
Unsaved conversations are lost knowledge. Claude should proactively remind the user to save:
- After 10+ exchanges: suggest "Want me to run /obsidian-save before we continue?"
- When the user signals wrap-up (e.g., "ok", "thanks", "done", "bye", "that's it"): suggest "Before you go — want me to /obsidian-save this conversation?"
- When a logical work block completes (feature shipped, decision made, problem solved): suggest saving
- Never skip the reminder. This is especially critical on Claude Desktop where there's no background agent.

### Search before creating
Before creating any new note, search for an existing one:
```
search(query="keyword from title")
```
Duplicate notes are vault rot. Merge or update instead of creating new.

### Match the vault's voice
Read existing notes in the same folder before writing new ones.
Match: frontmatter schema, heading style, list formatting, tone, emoji usage (or lack of it).
Never introduce new conventions — extend what's already there.

### Frontmatter is mandatory
Every note gets frontmatter. At minimum:
```yaml
---
date: 2026-03-24
tags:
  - <note-type>
---
```
See `references/vault-schema.md` for full frontmatter specs by note type.

---

## Write Rules

See `references/write-rules.md` for the complete guide. Summary:

- **Links**: Use `[[Note Name]]` for internal links. Always link to people, projects, and jobs mentioned in a note.
- **Dates**: ISO format (`YYYY-MM-DD`) in frontmatter. Human format (`March 24`) in body text.
- **Naming**: `YYYY-MM-DD — Title.md` for dated notes. `Title.md` for evergreen notes. No special characters except `—` (em dash).
- **Status values**: `active` / `planning` / `completed` / `archived` / `on-hold` for projects. `in-progress` / `done` / `waiting` for tasks.
- **Kanban**: Items follow the format `- [ ] 🔴 **Title** · @{YYYY-MM-DD}\n\tDescription [[Link]]`

---

## The `_CLAUDE.md` File

This is the most important concept in this skill.

`_CLAUDE.md` lives at the vault root and persists Claude's operating rules across every session and every surface (Claude Desktop, Claude Code, VS Code, terminal). Without it, Claude has to re-learn your vault conventions every conversation.

**Precedence rule:** `_CLAUDE.md` wins on all vault-specific rules (folder names, naming conventions, frontmatter fields, auto-save behavior, private folders). The defaults in this skill file apply only where `_CLAUDE.md` is silent. Never let skill defaults override an explicit `_CLAUDE.md` rule.

**What it contains:**
- Your vault's folder map and what each folder is for
- Frontmatter schemas for your specific note types
- Naming conventions you use
- What to auto-save vs. what to ask first
- People and projects that need special handling
- Links to key files (boards, dashboard, templates)

To generate a `_CLAUDE.md` for an existing vault, run vault discovery then use the template in `references/claude-md-template.md`.

To install it: write the file to the vault root. Every Claude session that starts in that vault should read it first.

---

## Common Operations

### Save info from conversation
When a conversation produces something vault-worthy:
1. Identify the note type (decision → project note, person met → People/, task → board + Tasks/, etc.)
2. Check if a relevant note already exists
3. Write or update — always frontmatter-first
4. Propagate to boards, daily note, linked notes

### Create today's daily note
```
date = today in YYYY-MM-DD format
path = Daily/{date}.md
```
Read `Templates/Daily Note.md`, fill in the date fields, create the file.
Then scan recent conversation for anything worth logging in today's sections.

### Log a dev session
Read `Templates/Dev Log.md`. Fill: date, project name, what was worked on, problems solved, decisions made, next steps.
Save to `Dev Logs/YYYY-MM-DD — Project Name.md`.
Link from project note's Recent Activity section and today's daily note.

### Update a kanban board
Boards use the `kanban-plugin: board` frontmatter.
Columns are `## Column Name` headers.
Items are `- [ ] **Title** · @{due-date}\n\tDescription [[Links]]`
Completed items move to the `## ✅ Done` column with a strikethrough: `- [x] ~~**Title**~~ ✅ Date`

### Run vault health check
```bash
python scripts/vault_health.py --path ~/path/to/vault
```
Reports: duplicate notes, orphaned files (no incoming links), stale tasks (overdue), empty folders, broken links, notes missing frontmatter.

Proactively suggest running this when the user says the vault feels messy, notes are hard to find, they mention duplicates, or they haven't mentioned a health check in a long time. Offer: *"Want me to run a vault health check?"*

---

## Commands

These slash commands can be used in any Claude surface. Each one is smart — it reads context, searches before writing, and propagates everywhere changes belong.

**Name matching:** If a name argument has a typo or is approximate, search the vault for the closest match, show what was found, and confirm with the user before proceeding. Never silently create a note with a misspelled name.

---

### `/obsidian-save`

**The master save command.** Reads the entire conversation and extracts everything worth preserving.

Steps:
1. Scan the conversation and identify all vault-worthy items: decisions, tasks, people mentioned, projects started, ideas, learnings, deals, mentions/shoutouts
2. Group items by type: people, projects, tasks, decisions, ideas, deals
3. Spawn parallel subagents — one per group — so all note types are handled simultaneously:
   - **People agent**: search for each person, create or update notes, log interactions
   - **Projects agent**: search for each project, create or update notes
   - **Tasks agent**: parse tasks, add to the right kanban columns
   - **Decisions agent**: find relevant project notes, append to Key Decisions sections
   - **Ideas agent**: search Ideas/ for related notes, create or append
4. After all agents complete: update today's daily note with links to everything saved
5. Report back: a clean list of what was saved and where

Do not ask for guidance on where to save things — infer it. Only ask if something is genuinely ambiguous (e.g. a person mentioned with no context on who they are).

---

### `/obsidian-daily`

**Creates or updates today's daily note.**

Steps:
1. Check if `Daily/YYYY-MM-DD.md` exists for today
2. If not: read `Templates/Daily Note.md`, fill in date fields, create the file
3. Scan the current conversation for anything relevant to today: tasks in progress, people mentioned, decisions made, what's being worked on
4. Pre-fill or update the note's sections with that context
5. If the note already exists, inject new content into the right sections rather than overwriting

Return the path of the daily note when done.

---

### `/obsidian-log`

**Logs a work or dev session to the vault.**

Steps:
1. Infer the project from conversation context — search the vault if needed to find the right project note
2. Read `Templates/Dev Log.md` (or `Templates/Work Log.md` if it exists)
3. Fill in: date, project, what was worked on, problems encountered, decisions made, next steps — all inferred from the conversation
4. Save to `Dev Logs/YYYY-MM-DD — Project Name.md`
5. Inject a link into the project note's Recent Activity section
6. Inject a link into today's daily note Work section

---

### `/obsidian-task [description]`

**Adds a task to the vault and the right kanban board.**

Steps:
1. Parse the task from the argument or from recent conversation context if no argument given
2. Infer: priority (🔴/🟡/🟢), due date, linked project, linked person
3. Search for the right kanban board — use `_CLAUDE.md` board list or search `Boards/`
4. Add the task card to the correct column (`📋 This Week` or `📥 Backlog` depending on due date)
5. Create a task note in `Tasks/` if the task is substantial (more than a one-liner)
6. Link the task from the relevant project note and today's daily note

---

### `/obsidian-person [name]`

**Creates or updates a person note.**

Steps:
1. Search the vault for an existing note matching the name (fuzzy — handle typos and partial names)
2. If found: confirm with user, then update with new info from conversation
3. If not found: create `People/Full Name.md` with full frontmatter schema
4. Fill in everything inferable from the conversation: role, company, context, relationship strength, last interaction date
5. Log the interaction in today's daily note
6. If a People index file exists, add or update the entry there

---

### `/obsidian-decide [optional: topic]`

**Extracts and logs decisions from the conversation.**

Steps:
1. Scan the conversation for decisions made — look for conclusions, choices, commitments, direction changes
2. If a topic argument is given, focus on decisions related to that topic
3. Find the relevant project note(s) — search if needed
4. Append each decision to the project note's `## Key Decisions` section with date
5. Log a summary in today's daily note
6. If a decision affects multiple projects, log it in all of them

---

### `/obsidian-capture [optional: idea text]`

**Quick idea capture with zero friction.**

Steps:
1. Take the argument as the idea, or pull the most recent idea/thought from the conversation
2. Search `Ideas/` for a related existing note — if found, append to it
3. If new: create `Ideas/Title.md` with minimal frontmatter (`date`, `tags: [idea]`)
4. Write the idea with any supporting context from the conversation
5. Add a brief mention in today's daily note under an Ideas or Captures section

---

### `/obsidian-find [query]`

**Smart vault search.**

Steps:
1. Run `search(query="...")` with the provided query
2. Also try variations if results are sparse (synonyms, related terms)
3. Return results with context: note title, folder, a relevant excerpt, and what type of note it is
4. If results are ambiguous, group them by type (people, projects, tasks, etc.)
5. Offer to open, update, or link any of the found notes

Do not just return filenames — return enough context for the user to act.

---

### `/obsidian-recap [today|week|month]`

**Summarizes a time period from the vault.**

Steps:
1. Determine the date range from the argument (default: `week` if not specified)
2. List all daily notes in the range with `list_files_in_dir("Daily/")`
3. Spawn parallel subagents — one per daily note — to read and extract key points from each simultaneously
4. Also spawn parallel agents to read dev logs and completed kanban tasks from the same period
5. Synthesize all agent results: what was worked on, decisions made, people interacted with, tasks completed, ideas captured
6. Present as a clean narrative summary — not a raw dump of note content

---

### `/obsidian-review`

**Generates a structured weekly or monthly review note.**

Steps:
1. Ask: weekly or monthly? (or infer from context)
2. Read daily notes and dev logs for the period
3. Read active projects and check for status changes
4. Read completed tasks from kanban boards
5. Draft a review note using `Templates/Review.md` if it exists, otherwise use a standard structure:
   - What I accomplished
   - Key decisions made
   - People I worked with
   - What I learned
   - What to carry forward
6. Save to `Reviews/YYYY-MM-DD — Weekly Review.md` (or Monthly)
7. Link from the last daily note of the period

---

### `/obsidian-board [optional: board name]`

**Shows or updates a kanban board.**

Steps:
1. If a board name is given, search `Boards/` for it (fuzzy match)
2. If no name given, list available boards and ask which one
3. Read and display the current board state: columns, item counts, overdue items (past `@{date}`)
4. Ask if the user wants to make updates — if yes, infer changes from conversation context
5. Move completed items to ✅ Done with strikethrough, add new items in the right column
6. Flag any items that are overdue or have been in the same column for more than a week

---

### `/obsidian-project [name]`

**Creates or updates a project note.**

Steps:
1. Search the vault for an existing project matching the name (fuzzy — handle typos)
2. If found: show what was found, confirm, then update with new info from conversation
3. If not found: create `Projects/Project Name.md` with full frontmatter schema (`date`, `tags: [project]`, `status: active`, `job`)
4. Fill in everything inferable from the conversation: description, goals, key people, current status
5. Add a card to the relevant kanban board in the `📥 Backlog` or `🔨 In Progress` column
6. Link from today's daily note

---

### `/obsidian-health`

**Runs a vault health check and summarizes findings.**

Steps:
1. Run: `python scripts/vault_health.py --path ~/path/to/vault --json`
2. Parse the JSON output and split findings into categories
3. Spawn parallel subagents to handle each category simultaneously:
   - **Links agent**: verify broken links, attempt to resolve them
   - **Duplicates agent**: confirm duplicates are truly the same concept, not just similar names
   - **Frontmatter agent**: identify notes missing required fields by type
   - **Staleness agent**: check overdue tasks and unfilled template syntax
   - **Orphans agent**: check orphaned notes and empty folders
   - **Contradictions agent**: scan Key Decisions and Knowledge/ for claims that conflict or are superseded
   - **Concept gaps agent**: find terms mentioned 3+ times without a dedicated page
   - **Stale claims agent**: flag Knowledge/ notes older than 6 months on fast-moving topics
4. Merge agent results and group by severity:
   - 🔴 Critical: broken links, unfilled template syntax, contradictions
   - 🟡 Warning: duplicates, stale tasks, missing frontmatter, stale claims, concept gaps
   - ⚪ Info: orphaned notes, empty folders
5. Present a clean summary with counts per category
6. For safe fixes (missing frontmatter, obvious duplicates, creating pages for concept gaps), offer to fix them automatically
7. For destructive fixes (archiving, merging, resolving contradictions), list them and ask for explicit confirmation before touching anything
8. Append to `log.md` with severity counts

---

### `/obsidian-reconcile`

**Finds and resolves contradictions across the vault.**

Steps:
1. Read `index.md` to understand the full vault landscape
2. Spawn parallel subagents to find contradictions:
   - **Claims agent**: scan `wiki/concepts/` and `wiki/projects/` for conflicting factual claims
   - **Entity agent**: scan `wiki/entities/` for outdated roles, companies, or descriptions
   - **Decisions agent**: scan `wiki/decisions/` for reversed or superseded decisions never updated
   - **Source freshness agent**: compare `raw/` dates against `wiki/` pages for stale references
3. For each contradiction, evaluate: which is newer, which is more authoritative, is it a genuine conflict or an evolution
4. Resolve:
   - **Clear winner**: rewrite the outdated page, add a History section noting what changed
   - **Ambiguous**: create `wiki/decisions/Conflict — Topic.md` with both sides, mark `status: open`
   - **Evolution**: update the page to current state with historical context
5. Rebuild affected `index.md` sections, append to `log.md`, update daily note

---

### `/obsidian-synthesize`

**Automatic synthesis — the vault thinks for itself.**

Can run manually or as a scheduled agent. Scans the vault for patterns nobody asked about.

Steps:
1. Read `index.md` and `log.md` (last 20 entries) for recent activity
2. Spawn parallel subagents:
   - **Cross-source agent**: find concepts appearing in 2+ unrelated sources from the last 7 days
   - **Entity convergence agent**: find people who appear together in multiple contexts but have no connection page
   - **Concept evolution agent**: find concepts updated 3+ times and document how thinking changed
   - **Orphan rescue agent**: find unlinked notes that should be connected to existing pages
3. For each pattern: create `wiki/concepts/Synthesis — Title.md` with evidence, interpretation, and suggested action
4. Link synthesis pages FROM all source notes they reference
5. Update `index.md`, `log.md`, and today's daily note

---

### `/obsidian-export`

**Export a clean snapshot any agent or tool can consume.**

Steps:
1. Scan all notes in `wiki/` and extract: path, title, type, date, status, summary, links, tags, frontmatter
2. Output as JSON (default) to `_export/vault-snapshot.json` or markdown to `_export/vault-snapshot.md`
3. The snapshot is a flat, structured representation of the vault — no folder structure knowledge needed
4. Any AI tool, automation, or agent can read this file and understand the vault
5. Append to `log.md`

---

### `/obsidian-init`

**Bootstraps `_CLAUDE.md` for the vault — the operating manual.**

Steps:
1. Call `list_files_in_vault()` to map the full structure
2. Spawn parallel subagents to discover vault context simultaneously:
   - **Dashboard agent**: read `Home.md` or equivalent dashboard
   - **Templates agent**: read all files in `Templates/`
   - **Boards agent**: read all files in `Boards/`
   - **Samples agent**: read one existing note per major folder to capture naming conventions and frontmatter patterns
3. Merge all agent results into a complete picture of the vault
4. Generate a complete `_CLAUDE.md` using the template in `references/claude-md-template.md`, filled with real values from the vault
5. Write it to `_CLAUDE.md` at the vault root via `append_content("_CLAUDE.md", content)`
6. Confirm what was written and tell the user to restart their Claude session so the new file takes effect

If `_CLAUDE.md` already exists: show a diff of what would change and ask before overwriting.

---

### `/obsidian-ingest`

**Ingests a source into the vault — one source touches many pages.**

Steps:
1. Accept a URL, file path, or pasted text as the source
2. Classify the source type before full read: article, PDF, transcript, video, or raw text
3. Read or fetch the full source content
4. Extract: entities (people, companies, tools), concepts, claims, action items, notable quotes
5. Save the raw source to `Knowledge/YYYY-MM-DD — Source Title.md` with full summary and source link
6. Spawn parallel subagents to distribute knowledge across the vault:
   - **People agent**: create or update People/ notes for each person mentioned
   - **Projects agent**: update existing project notes with new findings
   - **Ideas agent**: create or append to Ideas/ for new concepts
   - **Knowledge agent**: create or update Knowledge/ notes for factual claims and frameworks
7. Update `index.md` with all newly created notes
8. Append to `log.md`: `## [YYYY-MM-DD] ingest | Source Title (type) — X created, Y updated`
9. Update today's daily note with an ingest summary

A single ingest should touch 5-15 files. Compile knowledge once, distribute everywhere.

---

## Thinking Tools

These commands use the vault as a thinking partner — not just storage. They surface insights, challenge assumptions, and generate connections that the user cannot see on their own.

---

### `/obsidian-challenge`

**Red-teams your current idea against your own vault history.**

Steps:
1. Identify the user's current claim, plan, or assumption — from the argument or conversation context
2. Extract the key premises behind that position
3. Spawn parallel subagents to search for counter-evidence:
   - **Decisions agent**: search Key Decisions sections for past decisions that contradicted similar thinking
   - **Failures agent**: search dev logs, daily notes, and archives for past failures or lessons related to this topic
   - **Contradictions agent**: search for notes where the user held the opposite position or flagged risks
4. Synthesize a structured "Red Team" analysis:
   - **Your position**: restate the claim
   - **Counter-evidence from your vault**: cite specific notes, dates, and quotes
   - **Blind spots**: what the user might be ignoring based on their own history
   - **Verdict**: consistent with past experience, or does the vault suggest caution?
5. Log the challenge in today's daily note under a Thinking section

Do not be agreeable. The entire point is to pressure-test. Cite specific vault files.

---

### `/obsidian-emerge`

**Surfaces unnamed patterns from recent notes — recurring themes and conclusions you haven't explicitly stated.**

Steps:
1. Determine the date range from the argument (default: last 30 days)
2. Spawn parallel subagents to scan vault content:
   - **Daily notes agent**: extract recurring topics, complaints, observations, energy patterns
   - **Dev logs agent**: extract repeated blockers, tools, architectural patterns
   - **Decisions agent**: look for directional trends across project notes
   - **Ideas agent**: look for thematic clusters in Ideas/ notes
3. Identify:
   - **Recurring themes**: topics that appeared 3+ times without being named as a priority
   - **Emotional patterns**: what energizes vs. drains (based on language)
   - **Unnamed conclusions**: things the notes imply but never state outright
   - **Emerging directions**: where the vault suggests the user is heading
4. Present a "Pattern Report" — each pattern with evidence (cited notes), interpretation, and suggested action
5. Offer to save the report to `Ideas/` or a relevant project note
6. Log a summary in today's daily note

The goal is insight the user cannot see themselves. Surface what they haven't named yet.

---

### `/obsidian-connect [topic A] [topic B]`

**Bridges two unrelated domains using the vault's link graph to spark new ideas.**

Steps:
1. Parse two domains from arguments (e.g., `/obsidian-connect "distributed systems" "cooking"`)
2. For each domain, search the vault: find all related notes, map backlinks and outgoing links to build a local cluster
3. Find the bridge:
   - Shared links, tags, or people between the two clusters
   - If a direct path exists in the link graph, trace it and explain each hop
   - If no direct path, find the closest semantic overlap
4. Generate creative connections:
   - **Structural analogy**: how a pattern in A maps to B
   - **Transfer opportunities**: what works in A that could apply to B
   - **Collision ideas**: new concepts that only exist at the intersection
5. Present 3-5 specific, actionable connections — not vague analogies but concrete ideas
6. Offer to save the best connections to `Ideas/` with links to both source domains
7. Log the connection exercise in today's daily note

The value is in unexpected links. If the connection is obvious, dig deeper.

---

### `/obsidian-graduate`

**Promotes an idea fragment into a full project spec with tasks, board entries, and structure.**

Steps:
1. If argument given: search `Ideas/`, daily notes, and captures for a matching idea (fuzzy)
2. If no argument: list recent ideas (last 14 days) and ask the user to pick one
3. Read the full idea note and any linked notes for context
4. Research the vault for related content: overlapping projects, related people, past decisions, similar ideas explored before
5. Generate a full project spec:
   - **Project note** in `Projects/` with complete frontmatter (status: planning, linked idea)
   - **Goals**: 3-5 concrete outcomes
   - **Key tasks**: broken into phases with priorities
   - **Open questions**: what still needs answering
   - **Related notes**: links to everything relevant
6. Add cards to the relevant kanban board
7. Update the original idea note: add `status: graduated` and link to the new project
8. Link the new project from today's daily note

The idea doesn't die — it evolves. The original note stays as the origin story.

---

## Context Engine

### `/obsidian-world`

**Loads your identity, values, priorities, and current state in one shot — with progressive context levels.**

Uses token budgets to avoid loading the entire vault. Start light, go deeper only as needed.

Steps:
1. **L0 — Identity (~200 tokens)**: read `SOUL.md`/`About Me.md` and `CORE_VALUES.md`/`Values.md`
2. **L1 — Navigation (~1-2K tokens)**: read `index.md` (vault catalog) and `log.md` (last 10 entries)
3. **L2 — Current State (~2-5K tokens)**: read `Home.md`/`Dashboard.md`, today's daily note, last 3 daily notes, active kanban boards, previous session digests
4. **L3 — Deep Context (on demand, ~5-20K tokens)**: only load if needed — active project notes, full Knowledge/ articles, recently mentioned people

Present a brief status after L0-L2 (do NOT load L3 unless needed):
- **Who I am to you**: persona and communication style
- **Your current priorities**: top 3-5 active threads (from index.md + boards)
- **Open threads from last session**: anything unfinished (from log.md + daily notes)
- **Overdue / needs attention**: stale tasks or projects
- **Today so far**: what's already logged

Keep output concise — this is a boot-up sequence, not a report.

If identity files don't exist, offer to create them by asking 5-7 quick questions about the user's role, values, and preferences.
If `index.md` doesn't exist, offer to run `/obsidian-init` to generate it.

---

### `/obsidian-adr`

**Generates a decision record when the vault structure changes.**

Steps:
1. Identify the structural decision from the argument or conversation context
2. Create `Knowledge/ADR-YYYY-MM-DD — Title.md` with:
   - **Decision**: one-line summary
   - **Context**: what prompted this
   - **Options Considered**: 2-3 alternatives evaluated
   - **Rationale**: why this option won
   - **Consequences**: what changed — notes created, moved, or restructured
   - **Related**: links to affected notes
3. Update the relevant project note's Key Decisions section with a link to the ADR
4. Update `index.md` and append to `log.md`
5. Link from today's daily note

The vault knows why it's structured the way it is. When a future session asks "why?" — the ADR has the answer.

Can also be triggered automatically by `/obsidian-graduate`, `/obsidian-health` structural fixes, or folder reorganizations. In those cases, offer to create an ADR — don't force it.

---

## Research Commands

Five commands that pull external knowledge into the vault — X posts, X discourse, web research with citations, and YouTube videos. All output AI-first notes per the vault's Section 0 rule (preamble, rich frontmatter, recency markers, mandatory wikilinks, sources verbatim).

**Setup:** API keys live at `~/.config/obsidian-second-brain/.env`. Run `install.sh` and answer "y" to the research toolkit prompt, or copy `.env.example` manually. xAI Grok and Perplexity keys are required; YouTube key is optional (transcripts work without it).

**Stack:** Python 3.10+ with `uv`. Install deps via `uv sync` from the repo root.

---

### `/x-read [url]`

**Deep-read an X post** via Grok + Live Search. Verbatim post + thread + TL;DR + key claims + reply sentiment + voices to watch.

Steps:
1. Validate the URL contains `x.com/` or `twitter.com/`
2. Run `uv run -m scripts.research.x_read "<url>"` from the repo root
3. Show the structured analysis verbatim to the user
4. **Default save: chat only.** If the user asks "save this", write an AI-first note to `Research/X-reads/`

Plain English triggers: "read this tweet", "analyze this X post", "what's in this tweet".

---

### `/x-pulse [topic]`

**Scan X for what's trending** in a topic. Themes (with rep posts + voices), gaps, hooks working, voice/tone, post ideas.

Steps:
1. Resolve the topic (multi-word fine)
2. Run `uv run -m scripts.research.x_pulse "<topic>"`
3. Show the pulse output verbatim
4. **Default save: auto-saves** to `Research/X-pulse/YYYY-MM-DD — <slug>.md` (AI-first format)
5. Append one-line entry to `log.md`

Plain English: "what's hot on X about AI", "X pulse on vibe coding", "what should I post today on AI automation".

---

### `/research [topic]`

**Web research with citations** via Perplexity Sonar Pro. Deep dossier: summary, key facts (with recency markers), timeline, key players, contrarian views, further reading, open questions.

Steps:
1. Resolve the topic
2. Run `uv run -m scripts.research.research "<topic>"`
3. Show the dossier verbatim, including citations
4. **Default save: auto-saves** to `Research/Web/YYYY-MM-DD — <slug>.md`
5. All citations stored in frontmatter for later Dataview queries

Plain English: "research X", "look up X", "find me info on X". Note: "do deep research" routes to `/research-deep` instead.

---

### `/research-deep [topic]`

**Vault-first deep research with cross-vault propagation.** The chain-everything command.

Steps (4 phases):
1. **Vault scan** — find existing notes mentioning the topic (the baseline)
2. **Gap analysis** — Perplexity sonar-pro identifies what's missing/stale, emits 3-5 targeted queries
3. **Gap-fill** — runs each query via Perplexity (web) or Grok+Live Search (X)
4. **Synthesis** — Perplexity sonar-deep-research produces a delta report (what's new, what's confirmed, contradictions, recommended vault updates, open questions)

Then:
- Writes synthesis to `Research/Deep/YYYY-MM-DD — <slug>.md`
- Emits a JSON propagation payload between `<<<RESEARCH_DEEP_PROPAGATION_PAYLOAD>>>` markers
- Calling Claude reads that payload and runs `/obsidian-save`-style propagation: spawns parallel subagents to update People/Projects/Ideas/Decisions per the synthesis's "Recommended Vault Updates" bullets
- Links new research note from today's daily note

Cost: typically $0.20-$0.80 per run depending on topic depth.

Plain English: "do deep research on X", "research properly", "vault-aware research on X", "research and update the vault".

Graceful degradation: if any phase fails partially (e.g. Grok unavailable), continues with available sources and flags the gap.

---

### `/notebooklm [topic]`

**Vault-first source-grounded research.** The parallel to `/research-deep` — but grounded in your own sources instead of the open web.

Steps (4 phases + manual NotebookLM step):
1. **Vault scan** — same logic as `/research-deep` Phase 1, finds top 12 most relevant notes
2. **Bundle** — concatenates them into a single markdown source file at `Research/NotebookLM/YYYY-MM-DD — <slug> — bundle.md` (well under NotebookLM's 500K-char/source limit)
3. **Prompt template** — script prints a structured prompt with sections: Source summary / Confirmed claims / Contradictions / Gaps / Recommended next reads / Confidence
4. **User does the manual NotebookLM step:** open notebooklm.google.com, create a notebook, paste the bundle as a "Pasted Text" source, optionally add PDFs/URLs/Google Docs, paste the prompt, copy the response
5. **Save response** — user runs `uv run -m scripts.research.notebooklm --save-response --topic "<topic>" --slug "<slug>"` and pastes response via stdin
6. **Propagation** — same `/obsidian-save` flow as `/research-deep`

When to use `/notebooklm` over `/research-deep`:
- `/research-deep` (Perplexity + Grok): open-web + X-discourse coverage. Cost: $0.20-0.80
- `/notebooklm`: GROUNDED IN your own sources (vault + any PDFs/URLs you add). Cost: ~$0 (uses your free NotebookLM access)
- Run both for high-value topics — the open-web view and the grounded view rarely contradict, and the contradictions are where the insight is

Why a manual step: NotebookLM's API is workspace-gated beta as of 2026-01. The pasted-source workflow works for every user with a free Google account.

Plain English: "notebooklm this", "ask my notebook about X", "ground a research on X using my vault", "source-grounded research on X".

---

### `/youtube [url]`

**Extract and summarize a YouTube video.** Transcript (free, no API key) + metadata + top comments (Data API v3, optional) → summarized via Grok.

Steps:
1. Parse video ID from URL or 11-char ID
2. Run `uv run -m scripts.research.youtube_extract "<url>"`
3. Fetches transcript via `youtube-transcript-api`
4. If `YOUTUBE_API_KEY` set: also fetches title, channel, view counts, top comments
5. Sends transcript + comments to Grok for AI-first summary: TL;DR, Key Points, Notable Quotes, Themes, Comment Sentiment, Worth Following Up On
6. **Default save: auto-saves** to `Research/YouTube/YYYY-MM-DD — <video-title-slug>.md`

Plain English: "summarize this YouTube video", "extract this video", or just paste a YouTube URL with a question.

If the video has no captions and no API key set, the script fails with a clear message.

---

### Cost tracking

`/x-read`, `/x-pulse`, and `/youtube` (Grok summarize step) log usage to `~/.research-toolkit/usage.log`. View monthly totals via:
```bash
uv run python -c "from scripts.research.lib.usage import month_total; t,c = month_total(); print(f'\${t:.2f} across {c} calls')"
```

No usage tracking on Perplexity calls (intentional — user opted out).

No hard caps. No blocking. No per-call confirmation prompts. Trust the user to monitor.

---

## Scheduled Agents

Four autonomous agents designed to run on a schedule with no user intervention. Each runs a focused vault operation at a set time, then stops. They are conservative by default — they never delete or archive anything autonomously, and they never ask the user questions mid-run.

Set these up once using the `/schedule` skill in Claude Code.

---

### `obsidian-morning` — Daily at 8:00 AM

**Creates today's daily note and surfaces what needs attention.**

Prompt to schedule:
```
Read _CLAUDE.md. Create today's daily note in Daily/ using the Daily Note template.
Pull in any tasks from kanban boards that are due today or overdue.
List any projects with status active that have no recent activity in the last 7 days.
Do not ask questions — infer everything from the vault. Save and stop.
```

Setup:
```
/schedule obsidian-morning — daily 8:00 AM
```

---

### `obsidian-nightly` — Daily at 10:00 PM

**Sleeptime consolidation — the vault gets smarter overnight.**

This agent does more than close the day. It actively consolidates and improves the vault while you sleep.

Prompt to schedule:
```
Read _CLAUDE.md. This is a sleeptime consolidation pass — the vault should be smarter when the user wakes up.

Phase 1 — Close the day:
- Read today's daily note. Append a ## End of Day section with a 3-5 bullet summary.
- Move any completed kanban tasks to Done.

Phase 2 — Reconcile:
- Scan wiki/entities/ for outdated roles, companies, or descriptions that conflict with newer daily notes.
- Scan wiki/concepts/ for claims contradicted by recently ingested sources.
- Auto-resolve clear winners. Flag ambiguous ones in wiki/decisions/.

Phase 3 — Synthesize:
- Scan sources ingested today and yesterday. Find concepts that appear in 2+ unrelated sources.
- If patterns found: create wiki/concepts/Synthesis — Title.md with evidence and interpretation.

Phase 4 — Heal:
- Find notes created today with no incoming links. Add links from relevant existing pages.
- Check if any entity pages reference old timeline entries without an "until" date that should be closed.
- Rebuild index.md to reflect today's changes.

Phase 5 — Log:
- Append to log.md: ## [YYYY-MM-DD] nightly | End of day + X reconciled, Y synthesized, Z orphans linked

Do not ask questions. Do not fix anything destructive — only add, update, link. Save and stop.
```

Setup:
```
/schedule obsidian-nightly — daily 10:00 PM
```

---

### `obsidian-weekly` — Every Friday at 6:00 PM

**Generates a weekly review note from the vault.**

Prompt to schedule:
```
Read _CLAUDE.md. Run /obsidian-recap week to gather this week's activity.
Generate a weekly review note using the Review template (or standard structure if none exists).
Save to Reviews/YYYY-MM-DD — Weekly Review.md.
Link it from this week's last daily note.
Do not ask questions. Save and stop.
```

Setup:
```
/schedule obsidian-weekly — every Friday 6:00 PM
```

---

### `obsidian-health-check` — Every Sunday at 9:00 PM

**Runs the vault health check and logs a report.**

Prompt to schedule:
```
Read _CLAUDE.md. Run: python scripts/vault_health.py --path ~/path/to/vault --json
Parse the output. Write a health report to Knowledge/Vault Health YYYY-MM-DD.md
summarizing findings by severity (critical, warning, info).
Do not fix anything autonomously — only report.
Do not ask questions. Save and stop.
```

Setup:
```
/schedule obsidian-health-check — every Sunday 9:00 PM
```

---

### Setting up scheduled agents

All four can be configured at once:

```
/schedule
```

Then tell Claude which agents you want and at what times. Claude Code's scheduling system will handle the rest — agents run autonomously in the background on the defined cron schedule.

To list or remove scheduled agents:
```
/schedule list
/schedule remove obsidian-morning
```

---

## Background Agent (PostCompact Hook)

A background agent that fires automatically whenever Claude compacts the conversation context. It reads the session summary and propagates everything worth preserving to the vault — no user action required.

**What it does:** After each compaction, a headless `claude -p` subprocess wakes up, reads `_CLAUDE.md`, scans the summary for vault-worthy items (people, projects, decisions, tasks, dev work, ideas), and writes updates everywhere they belong — people notes, project notes, dev logs, kanban boards, and today's daily note.

**How it works:**
1. `PostCompact` hook fires in Claude Code after context compaction
2. Hook script reads the JSON summary from stdin
3. Spawns a headless `claude --dangerously-skip-permissions -p` subprocess in the vault directory
4. Agent runs silently, propagates updates, and exits — user sees nothing

**Setup:**

1. Make the hook script executable (one-time):
   ```bash
   chmod +x ~/.claude/skills/obsidian-second-brain/hooks/obsidian-bg-agent.sh
   ```

2. Set `OBSIDIAN_VAULT_PATH` in `~/.claude/settings.json`:
   ```json
   {
     "env": {
       "OBSIDIAN_VAULT_PATH": "/path/to/your/vault"
     }
   }
   ```

3. Add the `PostCompact` hook to `~/.claude/settings.json`:
   ```json
   {
     "hooks": {
       "PostCompact": [
         {
           "matcher": "",
           "hooks": [
             {
               "type": "command",
               "command": "/Users/you/.claude/skills/obsidian-second-brain/hooks/obsidian-bg-agent.sh",
               "timeout": 10,
               "async": true
             }
           ]
         }
       ]
     }
   }
   ```

**Debugging:** The agent logs to `/tmp/obsidian-bg-agent.log`. Check there if updates aren't appearing.

**Safety:** The agent never deletes, archives, or merges anything. It only adds or updates. If the summary has nothing vault-worthy, it exits without touching the vault.

---

## Write-Time AI-First Validator (PostToolUse Hook)

A non-blocking validator that fires after every `Write` or `Edit` on a markdown file inside the configured vault. It warns when the file fails the AI-first rule (missing required frontmatter, missing `## For future Claude` preamble, broken YAML) and surfaces the warning back to Claude on stderr so the agent can repair the note in the same turn.

**What it checks:**
1. The file has frontmatter delimiters (`--- ... ---`)
2. No tabs in frontmatter (YAML requires spaces)
3. Required AI-first fields present: `date:`, `type:`, `tags:`, `ai-first: true`
4. The body contains a `## For future Claude` preamble (rule #2 of [`references/ai-first-rules.md`](references/ai-first-rules.md))

**What it skips:**
- Files outside `OBSIDIAN_VAULT_PATH`
- Files under `raw/`, `templates/`, `_export/`, `.obsidian/`, `.git/`, `.trash/`

**Setup:**

1. Make the script executable (one-time):
   ```bash
   chmod +x ~/.claude/skills/obsidian-second-brain/hooks/validate-ai-first.sh
   ```

2. `OBSIDIAN_VAULT_PATH` must already be set in `~/.claude/settings.json` (the background agent setup above covers this).

3. Add the `PostToolUse` hook to `~/.claude/settings.json`:
   ```json
   {
     "hooks": {
       "PostToolUse": [
         {
           "matcher": "Write|Edit",
           "hooks": [
             {
               "type": "command",
               "command": "bash ~/.claude/skills/obsidian-second-brain/hooks/validate-ai-first.sh"
             }
           ]
         }
       ]
     }
   }
   ```

**Behavior:** Non-blocking. If a write fails the AI-first rule, Claude sees the warning text on stderr (with one line per missing requirement) and can re-write the file in the same conversation turn to fix it. The original write is NOT reverted.

**Other platforms (Codex CLI / Gemini CLI / OpenCode):** The hook script ships in `dist/<platform>/hooks/` for all four platform builds, but each platform's hook system differs. Wiring it up beyond Claude Code is left to the platform's own configuration. See [`hooks/validate-ai-first.hook.yaml`](hooks/validate-ai-first.hook.yaml) for the platform-neutral spec.

---

## Reference Files

- `references/vault-schema.md` — Complete folder structure + frontmatter specs for all note types
- `references/write-rules.md` — Detailed writing, linking, and formatting rules
- `references/claude-md-template.md` — Template for generating a vault's `_CLAUDE.md`

## Scripts

- `scripts/setup.sh` — One-command installer (wires hook + env var + MCP)
- `scripts/bootstrap_vault.py` — Bootstrap a complete vault from scratch
- `scripts/vault_health.py` — Audit a vault for structural issues
