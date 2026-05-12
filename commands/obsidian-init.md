---
description: Scan your vault and generate a _CLAUDE.md operating manual, index.md catalog, and log.md
category: meta
---

Use the obsidian-second-brain skill. Execute `/obsidian-init`:

1. Call `list_files_in_vault()` to map the full vault structure
2. Spawn parallel subagents to discover vault context simultaneously:
   - **Dashboard agent**: read `Home.md` or equivalent dashboard
   - **Templates agent**: read all files in `Templates/`
   - **Boards agent**: read all files in `Boards/`
   - **Samples agent**: read one existing note per major folder to capture naming conventions and frontmatter patterns
3. Merge all agent results into a complete picture of the vault
4. Generate a complete `_CLAUDE.md` using the template in `~/.claude/skills/obsidian-second-brain/references/claude-md-template.md`, filled with real values from the vault
5. Generate `index.md` at the vault root — a catalog of all pages organized by category:
   - List every note in the vault grouped by folder (Projects, People, Ideas, etc.)
   - Include a one-line description for each note (from frontmatter or first paragraph)
   - Claude reads this file FIRST when navigating the vault — cheaper and faster than searching
   - Format: `- [[Note Name]] — brief description`
6. Generate `log.md` at the vault root — a chronological activity log:
   - Start with a header explaining the format
   - Add an entry for this init: `## [YYYY-MM-DD] init | Vault initialized with _CLAUDE.md, index.md, log.md`
   - Future commands append to this file: every ingest, save, health check, and structural change gets a timestamped entry
   - Format: `## [YYYY-MM-DD] action | Description`
7. Write all three files to the vault root
8. Confirm what was written and tell the user to restart their Claude session so the new file takes effect

If `_CLAUDE.md` already exists: show a diff of what would change and ask before overwriting.
If `index.md` already exists: regenerate it (it's always a fresh catalog of current vault state).
If `log.md` already exists: do NOT overwrite — only append the init entry.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
