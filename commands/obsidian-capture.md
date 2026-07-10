---
description: Quick idea capture - zero friction, saves to your ideas folder and mentions in daily note
category: vault
triggers_en: ["capture this idea", "save this idea", "quick note", "drop a thought"]
triggers_es: ["captura esta idea", "guarda esta idea", "nota rápida", "apunta esto"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-capture $ARGUMENTS`:

The optional argument is the idea text. If not provided, pull the most recent idea or thought from the conversation.

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Take the argument as the idea, or pull from recent conversation context
3. Resolve the idea folder per `references/folder-map.md` (read the vault's `_CLAUDE.md` Folder Map first; wiki-style ideas live in `wiki/concepts/`, Obsidian-style in `Ideas/`). Search it for a related existing note - if found, append to it
4. If new: create `<idea-folder>/Title.md` with minimal frontmatter (`date`, `tags: [idea]`)
5. Write the idea with any supporting context from the conversation
6. Add a brief mention in today's daily note under an Ideas or Captures section

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
