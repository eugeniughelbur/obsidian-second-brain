---
description: Smart vault search - returns results with context, not just filenames
category: vault
triggers_en: ["find in vault", "search my notes", "where is", "what did I write about"]
triggers_es: ["busca en el vault", "busca en mis notas", "dónde está", "qué escribí sobre"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-find $ARGUMENTS`:

The argument is the search query.

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Search the vault for the query using the ranked keyword search where it is available: the `obsidian_search` MCP tool, or `vault_ops.search` directly (`integrations/obsidian-mcp-server/`). It applies stopword filtering and length-normalized ranking, so a short note with the term in its title outranks a long note that merely repeats it. In Claude Code (where no search tool is bound), grep the vault and read the top matches directly, applying the same judgement: ignore filler words, and do not let long `raw/` transcripts or `log.md` outrank a canonical `wiki/` note.
3. Also try variations if results are sparse (synonyms, related terms)
4. Return results with context: note title, folder, a relevant excerpt, and what type of note it is
5. If results are ambiguous, group them by type (people, projects, tasks, etc.)
6. Offer to open, update, or link any of the found notes

Do not just return filenames - return enough context for the user to act on the results.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
