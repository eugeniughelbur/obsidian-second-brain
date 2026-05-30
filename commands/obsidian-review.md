---
description: Generate a structured weekly or monthly review note from vault history
category: thinking
triggers_en: ["weekly review", "monthly review", "review my week", "review my month"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-review $ARGUMENTS`:

The optional argument specifies `weekly` or `monthly`. Ask if not clear from context.

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Determine the period: weekly or monthly
3. Read daily notes and dev logs for the period
4. Read active projects and check for status changes
5. Read completed tasks from kanban boards
6. Draft a review note using `Templates/Review.md` if it exists, otherwise use:
   - What I accomplished
   - Key decisions made
   - People I worked with
   - What I learned
   - What to carry forward
   - **Suggested questions for future-Claude** - 4 to 5 questions this period's vault content can answer that the user has not asked yet. Each question must cite at least one specific note (with `[[wikilink]]`). Prefer questions that surface contradictions across notes, connect entities that co-appeared without being explicitly linked, or name an unstated next action. Skip generic prompts the review section already covers.
7. Save to `Reviews/YYYY-MM-DD — Weekly Review.md` (or Monthly)
8. Link from the last daily note of the period

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
