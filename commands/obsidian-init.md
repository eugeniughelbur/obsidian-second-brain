---
description: Scan your vault and generate a _CLAUDE.md operating manual, index.md catalog, and log.md pointer
category: meta
triggers_en: ["init vault", "bootstrap vault", "setup vault", "scan vault"]
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
5. Generate `index.md` at the vault root - a catalog of all pages organized by category:
   - List every note in the vault grouped by folder (Projects, People, Ideas, etc.)
   - Include a one-line description for each note (from frontmatter or first paragraph)
   - Claude reads this file FIRST when navigating the vault - cheaper and faster than searching
   - Format: `- [[Note Name]] — brief description`
6. Initialize the vault operations log:
   - Create `Logs/` directory at the vault root
   - Write `log.md` at the vault root as a thin pointer file: explains the per-day structure, points at `Logs/`, and ships the entry template (do NOT put log entries in `log.md` itself)
   - Write today's `Logs/YYYY-MM-DD.md` with the init entry: `**HH:MM** - init | Vault initialized with _CLAUDE.md, index.md, Logs/`
   - Per-day file format: frontmatter (`type: log`, `date`, `ai-first: true`) + `**HH:MM** - action | description` entries, append-only
7. Write `_CLAUDE.md`, `index.md`, root `log.md` (pointer), and `Logs/YYYY-MM-DD.md` (today's entries)
8. Confirm what was written and tell the user to restart their Claude session so the new files take effect

If `_CLAUDE.md` already exists: show a diff of what would change and ask before overwriting.
If `index.md` already exists: regenerate it (it's always a fresh catalog of current vault state).
If a monolithic `log.md` already exists with `## YYYY-MM-DD` sections: run `python ~/.claude/skills/obsidian-second-brain/scripts/migrate_log.py --vault <vault-path>` to split it into `Logs/YYYY-MM-DD.md` files. Do not overwrite manually.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
