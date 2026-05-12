---
description: Summarize a time period from the vault — today, week, or month
category: vault
---

Use the obsidian-second-brain skill. Execute `/obsidian-recap $ARGUMENTS`:

The argument is the period: `today`, `week`, or `month`. Default to `week` if not specified.

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Determine the date range from the argument
3. List all daily notes in the range with `list_files_in_dir("Daily/")`
4. Spawn parallel subagents — one per daily note — to read and extract key points from each simultaneously
5. Also spawn parallel agents to read dev logs and completed kanban tasks from the same period
6. Synthesize all agent results: what was worked on, decisions made, people interacted with, tasks completed, ideas captured
7. Present as a clean narrative summary — not a raw dump of note content

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
