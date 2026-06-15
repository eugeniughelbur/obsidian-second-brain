---
description: Export a clean structured snapshot of the vault that any agent or tool can consume - flat JSON, markdown index, or an OKF (Open Knowledge Format) bundle
category: meta
triggers_en: ["export vault", "snapshot vault", "dump vault", "vault export"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-export $ARGUMENTS`:

The optional argument is the format: `json` (default), `markdown`, or `okf`.

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

   **OKF** (Open Knowledge Format - Google Cloud's vendor-neutral "folders of markdown" standard): do NOT build this by hand. Run the deterministic exporter:
   ```bash
   uv run scripts/export_okf.py --path "<vault path from _CLAUDE.md>"
   ```
   It writes an OKF v0.1 bundle to `_export/okf/`: every note becomes an OKF concept doc (frontmatter `type` [required] / `title` / `description` / `resource` [only when the note has a real source URL] / `tags` / ISO-8601 `timestamp`; `[[wikilinks]]` converted to relative-path markdown links), plus a generated `index.md` (progressive disclosure) and a copied `log.md`. The vault's richer AI-first body (incl. the `## For future Claude` preamble) is preserved - OKF is minimally opinionated, so the extra content rides along. This makes the vault "OKF v0.1 compatible" without changing how it works natively.

5. Append to the operation log: if `Logs/` exists write `**HH:MM** - export | Vault snapshot exported (format, N notes)` to `Logs/YYYY-MM-DD.md`; otherwise append `## [YYYY-MM-DD] export | Vault snapshot exported (format, N notes)` to `log.md`

This file is the bridge between your vault and any other AI tool, automation, or agent. They don't need to know your folder structure. They read the snapshot.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
