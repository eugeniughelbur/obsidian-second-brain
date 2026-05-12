---
description: Log this work or dev session to the vault — infers project from context
category: vault
---

Use the obsidian-second-brain skill. Execute `/obsidian-log`:

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Infer the project from conversation context — search the vault if needed to find the right project note
3. Read `Templates/Dev Log.md` (or `Templates/Work Log.md` if it exists)
4. Fill in: date, project, what was worked on, problems encountered, decisions made, next steps — all inferred from the conversation
5. Save to `Dev Logs/YYYY-MM-DD — Project Name.md`
6. Inject a link into the project note's Recent Activity section
7. Inject a link into today's daily note Work section

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
