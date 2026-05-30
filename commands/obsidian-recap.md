---
description: Summarize a time period from the vault - today, week, or month
category: vault
triggers_en: ["recap today", "recap the week", "summarize the week", "month recap"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-recap $ARGUMENTS`:

The argument is the period: `today`, `week`, or `month`. Default to `week` if not specified.

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Determine the date range from the argument
3. List all daily notes in the range with `list_files_in_dir("Daily/")`
4. Spawn parallel subagents - one per daily note - to read and extract key points from each simultaneously
5. Also spawn parallel agents to read dev logs and completed kanban tasks from the same period
6. Synthesize all agent results: what was worked on, decisions made, people interacted with, tasks completed, ideas captured
7. Present as a clean narrative summary - not a raw dump of note content
8. End the recap with a **Suggested questions for future-Claude** section: 4 to 5 questions this period's vault content is uniquely positioned to answer that the user has not asked yet. Each question must cite at least one specific note (with `[[wikilink]]`) so future-Claude can resolve it without re-scanning. Prefer questions that:
   - Surface tensions across notes (e.g., "Why does the X decision in [[note A]] contradict the rationale in [[note B]]?")
   - Connect entities that co-appeared but were never explicitly linked
   - Identify unstated next actions implied by the period's work
   Avoid generic prompts ("What did I work on?") - the recap already answers those.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
