---
name: obsidian-second-brain
description: >
  Operate any Obsidian vault as a living AI-first second brain focused on project
  tracking and knowledge capture. Use this skill whenever the user asks Claude to
  read, write, update, search, or manage their Obsidian vault — including saving
  notes from conversation, logging dev work, tracking decisions, capturing tasks,
  managing people notes, or running the project dashboard. Also triggers when the
  user wants to bootstrap a new vault, run a vault health check, or configure
  _CLAUDE.md. Includes a research toolkit (/research, /research-deep, /youtube,
  /x-read) for pulling external knowledge into the vault. Use proactively whenever
  the conversation produces information worth preserving.
---

# Obsidian Second Brain

> Claude operates your Obsidian vault as a self-rewriting knowledge base. Sources rewrite existing pages instead of just appending. Contradictions reconcile automatically. Everything worth remembering gets saved and propagates everywhere it belongs.

---

## Quick Start

### 0. Choose vault access method (in order of preference)

**Method A - MCP server (`mcp-obsidian`):**
If the MCP tools (`get_file_contents`, `list_files_in_vault`, `search`, `append_content`, `write_file`) are available, use them.

**Method B - Direct filesystem (fallback, always works):**
Use standard file tools (Read, Write, Edit, Glob) against the vault path. The vault is plain markdown.

If MCP is not installed, silently use filesystem access. Tell the user ONCE (first time only):

> "For faster vault access on large vaults, consider installing mcp-obsidian: `claude mcp add obsidian-vault -s user -- npx -y mcp-obsidian \"/path/to/your/vault\"`. Everything works without it."

### 1. First time in a vault - read `_CLAUDE.md`

Before doing anything in a vault, check if `_CLAUDE.md` exists at the vault root:

```
get_file_contents("_CLAUDE.md")
```

If it exists: follow its rules exactly - they override the defaults in this skill.
If it doesn't exist: use the defaults below, then offer to create one.

### 2. First time with a new user - run discovery

```
list_files_in_vault()
```

Scan the structure to understand folder names, template locations, naming conventions, frontmatter patterns. Read 2-3 existing notes to calibrate writing style before creating anything new.

### 3. Bootstrap a new vault

```bash
python scripts/bootstrap_vault.py --path ~/path/to/vault --name "Your Name"
```

Presets:
- `--preset builder` - projects, dev logs, architecture decisions (recommended for this skill)
- `--preset executive` - decisions, people, meetings, strategic planning
- `--preset researcher` - sources, literature notes, hypotheses

Then configure `mcp-obsidian` to point at the new vault path and restart Claude.

---

## Core Operating Principles

### AI-first vault rule (applies to every note)

The vault is designed for **future-Claude** to read and reason over, not for human review. Every note Claude writes must follow `references/ai-first-rules.md`:

1. **Self-contained context** - each note explains itself; don't rely on backlinks alone
2. **"For future Claude" preamble** - 2-3 sentence summary so Claude can decide relevance in 10 seconds
3. **Rich, consistent frontmatter** - `type`, `date`, `tags`, `ai-first: true`, plus type-specific fields
4. **Recency markers per claim** - `(as of 2026-05, source.com)` so future-Claude knows what to verify
5. **Sources preserved verbatim** - every external claim has its source URL inline
6. **Cross-links mandatory** - every person/project/idea/decision uses `[[wikilinks]]`
7. **Confidence levels** - `stated | high | medium | speculation` where applicable

### Never create in isolation

Every write operation must ask: *where else does this belong?*

| You create/update... | Also update... |
|---|---|
| A new project note | Dashboard, today's session log |
| A task completed | Project note (log it) |
| A person note | Project note if they're on it |
| A dev log | Project note (Recent Activity) |
| A decision made | Project note (Key Decisions) |
| Any vault write | `log.md` (append timestamped entry) |

Always propagate. Never create a single orphaned note.

### Bi-temporal facts - never overwrite, always append

When a fact changes (role, company, status, location, tool), NEVER delete the old value. Add a new entry to the `timeline:` frontmatter array with both event time AND transaction time:

```yaml
timeline:
  - fact: "CTO at Single Grain"
    from: 2024-01-01
    until: 2026-04-07
    learned: 2026-02-23
    source: "[[2026-02-23]]"
  - fact: "Architect at Single Grain"
    from: 2026-04-07
    until: present
    learned: 2026-04-07
    source: "[[2026-04-07]]"
```

Top-level fields always reflect CURRENT state. `timeline:` preserves full history with provenance.

### Maintain `index.md` and `log.md`

- **`index.md`** - a catalog of all vault pages organized by category. Read this FIRST when navigating instead of searching. Update whenever a note is created or deleted.
- **`log.md`** - an append-only chronological log of every vault operation. Never delete entries, only append.

### The vault is a living system

When new information enters: existing pages get REWRITTEN with new context, not just appended to. Contradictions get resolved. New patterns trigger synthesis. Stale claims get replaced, with history preserved.

### Search before creating

Before creating any new note, search for an existing one. Duplicate notes are vault rot. Merge or update instead of creating new.

### Match the vault's voice

Read existing notes in the same folder before writing new ones. Match: frontmatter schema, heading style, list formatting, tone.

### Proactive save reminders

After 10+ exchanges, suggest running `/obsidian-save`. When the user signals wrap-up, offer to save. When a logical work block completes (feature shipped, decision made), suggest saving.

---

## Write Rules

See `references/write-rules.md` for the complete guide. Summary:

- **Links**: Use `[[Note Name]]` for internal links. Always link to people, projects, and jobs mentioned.
- **Dates**: ISO format (`YYYY-MM-DD`) in frontmatter. Human format (`March 24`) in body text.
- **Naming**: `YYYY-MM-DD - Title.md` for dated notes. `Title.md` for evergreen notes.
- **Status values**: `active` / `planning` / `completed` / `archived` / `on-hold` for projects. `in-progress` / `done` / `waiting` for tasks.

---

## The `_CLAUDE.md` File

`_CLAUDE.md` lives at the vault root and persists Claude's operating rules across every session. Without it, Claude has to re-learn your vault conventions every conversation.

**Precedence rule:** `_CLAUDE.md` wins on all vault-specific rules. Defaults in this skill file apply only where `_CLAUDE.md` is silent.

**What it contains:**
- Your vault's folder map
- Frontmatter schemas for your note types
- Naming conventions
- The `projects:` block used by `/projects` - list of tracked projects with repo paths and vault note paths
- Links to key files (dashboard, templates)

To generate a `_CLAUDE.md` for an existing vault, run vault discovery then use `references/claude-md-template.md`.

**The `projects:` block (required for `/projects`):**

```yaml
projects:
  - name: Project Name
    repo: C:\Users\you\Documents\Codeing\GitHub\repo-folder
    vault_note: Projects/Project Name.md
  - name: Another Project
    repo: C:\Users\you\Documents\Codeing\GitHub\another-repo
    vault_note: Projects/Another Project.md
```

---

## Commands

16 slash commands. Each one reads context, searches before writing, and propagates everywhere changes belong.

**Name matching:** If a name argument has a typo or is approximate, search the vault for the closest match, confirm with the user before proceeding.

---

### `/projects [optional: project name]`

**The primary command.** Live overview of all tracked projects - reads vault notes, git history, and local docs, then rewrites `Projects/Dashboard.md`.

Run at the start of every session to re-orient. Run mid-session for a specific project by passing its name.

See `commands/projects.md` for full operating instructions.

---

### `/obsidian-save`

**The master save command.** Reads the entire conversation and extracts everything worth preserving.

Steps:
1. Scan the conversation and identify all vault-worthy items: decisions, tasks, people mentioned, projects started, ideas, dev work done
2. Group items by type: people, projects, tasks, decisions, ideas
3. Spawn parallel subagents - one per group - so all note types are handled simultaneously
4. After all agents complete: update `log.md`, link everything from the relevant project notes
5. Report back: a clean list of what was saved and where

---

### `/obsidian-log`

**Logs a work or dev session to the vault.**

Steps:
1. Infer the project from conversation context - search the vault if needed
2. Read `Templates/Dev Log.md` (or `Templates/Work Log.md` if it exists)
3. Fill in: date, project, what was worked on, problems encountered, decisions made, next steps - all inferred from the conversation
4. Save to `Dev Logs/YYYY-MM-DD - Project Name.md`
5. Inject a link into the project note's Recent Activity section

---

### `/obsidian-task [description]`

**Adds a task to the vault.**

Steps:
1. Parse the task from the argument or from recent conversation context
2. Infer: priority (high/medium/low), due date, linked project
3. Add to the relevant project note's open tasks
4. Create a task note in `Tasks/` if the task is substantial (more than a one-liner)
5. Link the task from the relevant project note

---

### `/obsidian-project [name]`

**Creates or updates a project note.**

Steps:
1. Search the vault for an existing project matching the name (fuzzy)
2. If found: show what was found, confirm, then update with new info from conversation
3. If not found: create `Projects/Project Name.md` with full frontmatter schema
4. Fill in everything inferable: description, goals, key people, current status
5. Add the project to `_CLAUDE.md` projects block if not already there

---

### `/obsidian-adr [optional: topic]`

**Generates a decision record.**

Steps:
1. Identify the decision from the argument or conversation context
2. Create `Knowledge/ADR-YYYY-MM-DD - Title.md` with: Decision, Context, Options Considered, Rationale, Consequences, Related
3. Update the relevant project note's Key Decisions section with a link
4. Update `index.md` and append to `log.md`

---

### `/obsidian-person [name]`

**Creates or updates a person note.**

Steps:
1. Search the vault for an existing note matching the name (fuzzy)
2. If found: confirm, then update with new info from conversation
3. If not found: create `People/Full Name.md` with full frontmatter schema
4. Fill in everything inferable: role, company, context, relationship strength, last interaction
5. Link from any relevant project note

---

### `/obsidian-capture [optional: idea text]`

**Quick idea capture with zero friction.**

Steps:
1. Take the argument as the idea, or pull the most recent idea from the conversation
2. Search `Ideas/` for a related existing note - if found, append to it
3. If new: create `Ideas/Title.md` with minimal frontmatter
4. Write the idea with any supporting context from the conversation

---

### `/obsidian-find [query]`

**Smart vault search.**

Steps:
1. Run `search(query="...")` with the provided query
2. Try variations if results are sparse (synonyms, related terms)
3. Return results with context: note title, folder, a relevant excerpt, note type
4. Offer to open, update, or link any of the found notes

---

### `/obsidian-health`

**Runs a vault health check.**

Steps:
1. Run: `python scripts/vault_health.py --path ~/path/to/vault --json`
2. Parse output and split findings by category
3. Spawn parallel subagents: Links, Duplicates, Frontmatter, Staleness, Orphans, Contradictions
4. Group by severity: critical / warning / info
5. For safe fixes (missing frontmatter, obvious duplicates), offer to fix automatically
6. For destructive fixes, list them and ask for explicit confirmation

---

### `/obsidian-reconcile`

**Finds and resolves contradictions across the vault.**

Steps:
1. Read `index.md` to understand the full vault landscape
2. Spawn parallel subagents to find contradictions in: concepts, entities, decisions, source freshness
3. For each contradiction: evaluate which is newer/more authoritative
4. Resolve: rewrite outdated page, create conflict note if ambiguous, update with historical context
5. Rebuild affected `index.md` sections, append to `log.md`

---

### `/obsidian-init`

**Bootstraps `_CLAUDE.md` for the vault.**

Steps:
1. Call `list_files_in_vault()` to map the full structure
2. Spawn parallel subagents to discover vault context: Dashboard, Templates, Boards, sample notes per folder
3. Generate a complete `_CLAUDE.md` using `references/claude-md-template.md`, filled with real vault values
4. Include an empty `projects:` block ready to be filled in
5. Write to `_CLAUDE.md` at the vault root
6. Tell the user to restart their Claude session so the new file takes effect

If `_CLAUDE.md` already exists: show a diff of what would change and ask before overwriting.

---

## Research Commands

Four commands that pull external knowledge into the vault. All output AI-first notes per the vault's rules (preamble, rich frontmatter, recency markers, mandatory wikilinks, sources verbatim).

**Setup:** API keys live at `~/.config/obsidian-second-brain/.env`. Run `install.sh` and answer "y" to the research toolkit prompt, or copy `.env.example` manually. xAI Grok and Perplexity keys are required; YouTube key is optional.

**Stack:** Python 3.10+ with `uv`. Install deps via `uv sync` from the repo root.

---

### `/x-read [url]`

**Deep-read a web page or X post.** Fetches content, extracts key claims, saves an AI-first note to the vault.

Steps:
1. Accept a URL - any web page or `x.com/` post
2. Run `uv run -m scripts.research.x_read "<url>"` from the repo root
3. Show the structured analysis to the user
4. Save an AI-first note to `Research/Web/` or `Research/X-reads/` depending on source type

Plain English triggers: "read this", "summarize this page", "what's in this article", "analyze this post".

---

### `/research [topic]`

**Web research with citations** via Perplexity Sonar Pro. Deep dossier: summary, key facts with recency markers, timeline, key players, contrarian views, further reading, open questions.

Steps:
1. Resolve the topic
2. Run `uv run -m scripts.research.research "<topic>"`
3. Show the dossier verbatim, including citations
4. Auto-save to `Research/Web/YYYY-MM-DD - <slug>.md`
5. All citations stored in frontmatter for later Dataview queries

Plain English: "research X", "look up X", "find me info on X". Note: "do deep research" routes to `/research-deep` instead.

---

### `/research-deep [topic]`

**Vault-first deep research with cross-vault propagation.**

Steps (4 phases):
1. **Vault scan** - find existing notes mentioning the topic (the baseline)
2. **Gap analysis** - Perplexity identifies what's missing or stale, emits 3-5 targeted queries
3. **Gap-fill** - runs each query via Perplexity (web) or Grok (X)
4. **Synthesis** - Perplexity sonar-deep-research produces a delta report (new, confirmed, contradictions, recommended vault updates)

Then: writes synthesis to `Research/Deep/`, propagates updates to People/Projects/Ideas/Decisions via parallel subagents, links from today's relevant project note.

Cost: typically $0.20-$0.80 per run depending on topic depth.

Plain English: "do deep research on X", "research properly", "vault-aware research on X".

---

### `/youtube [url]`

**Extract and digest a YouTube video.** Transcript + metadata + top comments → AI-first summary optimized for learning.

Steps:
1. Parse video ID from URL or 11-char ID
2. Run `uv run -m scripts.research.youtube_extract "<url>"`
3. Fetches transcript via `youtube-transcript-api`
4. If `YOUTUBE_API_KEY` set: also fetches title, channel, view counts, top comments
5. Sends transcript + comments to Grok for AI-first summary: TL;DR, Key Points, Notable Quotes, Themes, Comment Sentiment, Worth Following Up On
6. Auto-save to `Research/YouTube/YYYY-MM-DD - <video-title-slug>.md`

Plain English: "summarize this YouTube video", "what does this video say about X", or paste a YouTube URL with a question.

If the video has no captions and no API key is set, the script fails with a clear message.

---

### Cost tracking

`/x-read` and `/youtube` (Grok summarize step) log usage to `~/.research-toolkit/usage.log`. View monthly totals via:

```bash
uv run python -c "from scripts.research.lib.usage import month_total; t,c = month_total(); print(f'\${t:.2f} across {c} calls')"
```

No hard caps. No blocking. No per-call confirmation prompts.

---

## Reference Files

- `references/vault-schema.md` - complete folder structure + frontmatter specs for all note types
- `references/write-rules.md` - writing, linking, and formatting rules
- `references/claude-md-template.md` - template for generating a vault's `_CLAUDE.md`
- `references/ai-first-rules.md` - canonical spec for AI-first note writing

## Scripts

- `scripts/setup.sh` - one-command installer
- `scripts/bootstrap_vault.py` - bootstrap a complete vault from scratch
- `scripts/vault_health.py` - audit a vault for structural issues
