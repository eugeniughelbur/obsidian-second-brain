---
description: Load your identity, values, priorities, and current state in one shot — with progressive context levels to avoid burning tokens
category: vault
---

Use the obsidian-second-brain skill. Execute `/obsidian-world`:

1. Read `_CLAUDE.md` first if it exists in the vault root

2. Load context progressively — start light, go deeper only as needed:

   **L0 — Identity (~170 tokens)**
   Read these files if they exist (search for them if paths differ):
   - `SOUL.md` or `About Me.md` — who the user is, communication style, thinking preferences
   - `CRITICAL_FACTS.md` — ~120 tokens of always-needed context: timezone, manager, location, company, role
   - `CORE_VALUES.md` or `Values.md` — decision-making principles and non-negotiables

   **L1 — Navigation (~1-2K tokens)**
   - Read `index.md` — the catalog of all vault pages. This tells Claude what exists without loading everything.
   - Read `log.md` (last 10 entries only) — what happened recently in the vault

   **L2 — Current State (~2-5K tokens)**
   - Read `Home.md` or `Dashboard.md` — current top-level priorities
   - Read today's daily note (if it exists) for what's already in progress
   - Read the last 3 daily notes for recent momentum and open threads
   - Scan active kanban boards for in-progress and overdue items
   - Check for session digests from previous conversations (look for "End of Day" or "Session Digest" sections)

   **L3 — Deep Context (on demand, ~5-20K tokens)**
   - Only load if needed for a specific question or task
   - Read active project notes (status: active) for current goals and blockers
   - Read full source articles from Knowledge/ if the user asks about a specific topic
   - Identify key people interacted with recently (last 7 days of daily notes)

3. Present a brief status after L0-L2 (do NOT load L3 unless needed):
   - **Who I am to you**: confirm the persona and communication style
   - **Your current priorities**: top 3-5 active threads (from index.md + boards)
   - **Open threads from last session**: anything unfinished (from log.md + daily notes)
   - **Overdue / needs attention**: tasks or projects that are stale
   - **Today so far**: what's already logged today

Keep output concise — this is a boot-up sequence, not a report. The user should glance at it and say "yes, Claude is up to speed" and start working immediately.

4. **Core memory pinning** — during the session, if the user is working on a specific task that requires persistent context (debugging a complex API, reviewing a long document, planning a project), Claude can PIN critical information to a `PINNED.md` file at the vault root:
   - Write task-specific facts, schemas, or reference data to `PINNED.md`
   - This file is loaded at L0 alongside SOUL.md and CRITICAL_FACTS.md
   - When the task is done, clear `PINNED.md`
   - This prevents critical session context from being lost during long conversations or context compaction
   - Claude should proactively suggest pinning when it detects the user is deep in a complex task

If identity files (SOUL.md, CRITICAL_FACTS.md) don't exist, offer to create them by asking 5-7 quick questions about the user's role, values, and communication preferences.

If `index.md` doesn't exist, offer to run `/obsidian-init` to generate it.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
