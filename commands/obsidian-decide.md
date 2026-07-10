---
description: Record decisions - lightweight by default (logged to project notes), or a full ADR record with --formal
category: thinking
triggers_en: ["extract decisions", "log decisions", "what did we decide", "log this decision", "ADR", "record decision", "decision record"]
triggers_es: ["saca las decisiones de esta conversación", "registra las decisiones", "¿qué decidimos?", "anota esta decisión", "ADR", "acta de decisión formal"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-decide $ARGUMENTS`:

Two depths, one command. The optional argument narrows focus to a topic. Add `--formal` (or lead with `adr`) to write a full Architecture Decision Record instead of a one-line log entry.

- **Default (lightweight):** capture decisions from the conversation as dated one-liners in the relevant project notes. Use for the steady stream of choices made while working.
- **`--formal` (ADR):** write one structured decision record with context, options, rationale, and consequences. Use for a structural or directional decision worth a full writeup (a folder reorg, a convention adopted, an idea graduated, a stack choice).

1. Read `_CLAUDE.md` first if it exists in the vault root.

### Lightweight mode (default)

2. Scan the conversation for decisions made - conclusions, choices, commitments, direction changes. If a topic argument is given, focus there.
3. Find the relevant project note(s) - search the vault if needed.
4. Append each decision to the project note's `## Key Decisions` section with today's date.
5. Log a summary in today's daily note. If a decision affects multiple projects, log it in all of them.

### Formal mode (`--formal`)

2. Identify the structural decision - from the argument or recent conversation (a project graduated, a folder reorganized, a convention adopted, a concept promoted to hub). To surface decisions already made in code but never recorded, run `python scripts/mine_commit_decisions.py --repo <project> --json` from the skill repo - it scans git history for decision-shaped commits ("switch to", "replace", "adopt", "rename", "migrate") and returns ADR candidates.
3. Create a decision record in the decisions folder resolved per `references/folder-map.md` (wiki-style `wiki/decisions/YYYY-MM-DD - Title.md`, Obsidian-style `Knowledge/ADR-YYYY-MM-DD - Title.md`), with frontmatter `date`, `type: adr`, `status: accepted`, `tags: [decision-record]`, `ai-first: true`. Structure:
   - **Decision** - one-line summary of what was decided.
   - **Context** - what prompted it (the problem or trigger).
   - **Options Considered** - 2-3 alternatives evaluated.
   - **Rationale** - why this option over the others.
   - **Consequences** - what changes as a result (notes created, moved, restructured).
   - **Related** - links to affected project notes, people, ideas.
4. Update the relevant project note's `## Key Decisions` section with a link to the record, and update `index.md`.
5. Append to the operation log (`Logs/YYYY-MM-DD.md` if it exists, else `log.md`) and link from today's daily note.

Decision records keep the vault from becoming a black box: when a future session asks "why is it structured this way?", the ADR answers. Other commands may offer to call the formal mode - when `/obsidian-graduate` promotes an idea, when `/obsidian-health` recommends a structural fix, or when folders are reorganized - offer, do not force.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
