---
description: Create or update a project note — adds to board and daily note automatically
category: vault
---

Use the obsidian-second-brain skill. Execute `/obsidian-project $ARGUMENTS`:

The argument is a project name. Handle typos and partial matches.

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Search the vault for an existing project matching the name (fuzzy — handle typos)
3. If found: show what was found, confirm with user, then update with new info from conversation
4. If not found: create `Projects/Project Name.md` with full frontmatter schema (`date`, `tags: [project]`, `status: active`, `job`)
5. Fill in everything inferable from the conversation: description, goals, key people, current status
6. Add a card to the relevant kanban board in the `📥 Backlog` or `🔨 In Progress` column
7. Link from today's daily note

If the name has a typo or is approximate, search the vault, show what was found, and confirm before proceeding. Never silently create a note with a misspelled name.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
