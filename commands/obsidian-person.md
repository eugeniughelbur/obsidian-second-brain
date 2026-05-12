---
description: Create or update a person note from conversation context
category: vault
---

Use the obsidian-second-brain skill. Execute `/obsidian-person $ARGUMENTS`:

The argument is a person's name — handle typos and partial matches.

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Search the vault for an existing note matching the name (fuzzy — handle typos and partial names)
3. If found: confirm with user, then update with new info from conversation
4. If not found: create `People/Full Name.md` with full frontmatter schema
5. Fill in everything inferable from the conversation: role, company, context, relationship strength, last interaction date
6. Log the interaction in today's daily note
7. If a People index file exists, add or update the entry there

If the name has a typo or is approximate, search the vault, show what was found, and confirm before proceeding. Never silently create a note with a misspelled name.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
