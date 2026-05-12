---
description: Export a clean structured snapshot of the vault that any agent or tool can consume — flat JSON or markdown index
category: meta
---

Use the obsidian-second-brain skill. Execute `/obsidian-export $ARGUMENTS`:

The optional argument is the format: `json` (default) or `markdown`. 

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Read `index.md` for the full vault catalog

3. Build a structured export by scanning the vault:

   **For each note in wiki/**, extract:
   - `path`: file path relative to vault root
   - `title`: note title (first heading or filename)
   - `type`: from frontmatter tags (entity, concept, project, daily, etc.)
   - `date`: from frontmatter
   - `status`: from frontmatter (if exists)
   - `summary`: first paragraph or first 200 characters of body
   - `links_to`: list of all outgoing `[[wikilinks]]`
   - `linked_from`: list of all incoming links (backlinks)
   - `tags`: all frontmatter tags
   - `frontmatter`: full frontmatter as key-value pairs

4. Output format:

   **JSON** (default):
   ```json
   {
     "vault": "Eugeniu's Vault",
     "exported": "2026-04-07",
     "total_notes": 238,
     "notes": [
       {
         "path": "wiki/entities/Eric Siu.md",
         "title": "Eric Siu",
         "type": "entity",
         "summary": "CEO of Single Grain...",
         "links_to": ["Single Grain", "Centralized API Gateway"],
         "tags": ["entity", "person"]
       }
     ]
   }
   ```
   Save to `_export/vault-snapshot.json`

   **Markdown**:
   A flat markdown file with every note listed with its metadata and summary.
   Save to `_export/vault-snapshot.md`

5. Append to `log.md`: `## [YYYY-MM-DD] export | Vault snapshot exported (format, N notes)`

This file is the bridge between your vault and any other AI tool, automation, or agent. They don't need to know your folder structure. They read the snapshot.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
