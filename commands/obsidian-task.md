---
description: Add a task to the right kanban board with inferred priority and due date
category: vault
---

Use the obsidian-second-brain skill. Execute `/obsidian-task $ARGUMENTS`:

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Parse the task from the argument, or pull from recent conversation context if no argument given
3. Infer: priority (🔴/🟡/🟢), due date, linked project, linked person
4. Search for the right kanban board — use `_CLAUDE.md` board list or search `Boards/`
5. Add the task card to the correct column (`📋 This Week` or `📥 Backlog` depending on due date)
6. Create a task note in `Tasks/` if the task is substantial (more than a one-liner)
7. Link the task from the relevant project note and today's daily note

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
