---
description: Scan your vault and generate a _CLAUDE.md operating manual, index.md catalog, and log.md pointer
category: meta
triggers_en: ["init vault", "bootstrap vault", "setup vault", "scan vault"]
triggers_de: ["Vault einrichten", "Vault initialisieren", "Vault konfigurieren", "Vault scannen"]
triggers_es: ["inicializa el vault", "arranca el vault", "configura el vault", "escanea el vault", "inicia el vault", "deja listo el vault"]
triggers_pt: ["inicialize o vault", "bootstrap do vault", "configure o vault", "escaneie o vault"]
triggers_zh: ["初始化知识库", "为这个知识库生成初始配置", "扫描并配置我的知识库", "生成知识库操作手册"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-init`:

1. Glob the vault (`<vault>/**/*.md`) to map the full vault structure
2. Spawn parallel subagents to discover vault context simultaneously:
   - **Dashboard agent**: read `Home.md` or equivalent dashboard
   - **Templates agent**: read all files in `Templates/`
   - **Boards agent**: read all files in `Boards/`
   - **Samples agent**: read one existing note per major folder to capture naming conventions and frontmatter patterns
3. Merge all agent results into a complete picture of the vault
4. Generate a complete `_CLAUDE.md` using the template bundled with the skill at `SKILL_ROOT/references/claude-md-template.md` (its absolute path was given at session start as **Skill root**), filled with real values from the vault
5. Generate `index.md` at the vault root - a catalog of all pages organized by category:
   - List every note in the vault grouped by folder (Projects, People, Ideas, etc.)
   - Include a one-line description for each note (from frontmatter or first paragraph)
   - Claude reads this file FIRST when navigating the vault - cheaper and faster than searching
   - Format: `- [[Note Name]] - brief description`
6. Initialize the vault operations log:
   - Create `Logs/` directory at the vault root
   - Write `log.md` at the vault root as a thin pointer file: explains the per-day structure, points at `Logs/`, and ships the entry template (do NOT put log entries in `log.md` itself)
   - Write today's `Logs/YYYY-MM-DD.md` with the init entry: `**HH:MM** - init | Vault initialized with _CLAUDE.md, index.md, Logs/`
   - Per-day file format: frontmatter (`type: log`, `date`, `ai-first: true`) + `**HH:MM** - action | description` entries, append-only
7. Create `Bases/` at the vault root if it does not exist. Stamp the four premade base files from `SKILL_ROOT/references/bases/` (the skill root given at session start):

   | Template | Output file | Obsidian-style folder | Wiki-style folder |
   |---|---|---|---|
   | `projects.base.template` | `Bases/Projects.base` | `Projects` | `wiki/projects` |
   | `people.base.template` | `Bases/People.base` | `People` | `wiki/entities` |
   | `tasks.base.template` | `Bases/Tasks.base` | `Tasks` | `wiki/tasks` |
   | `daily.base.template` | `Bases/Daily.base` | `Daily` | `wiki/daily` |

   Detect vault style from the folder structure discovered in step 1: if `wiki/` exists at the root, use wiki-style folder names; otherwise use obsidian-style. For each template, replace its named placeholder (`{{DAILY_FOLDER}}`, `{{PEOPLE_FOLDER}}`, `{{PROJECTS_FOLDER}}`, `{{TASKS_FOLDER}}`) with the correct folder name, then write to `Bases/`.

   Skip any base file that already exists in `Bases/` - never overwrite.

8. Rewrite policy, asked once (#250). If `<vault>/.vault-config.json` has no `rewrite_policy` key, ask one question: does this vault keep the confirm-before-rewrite gate on `/obsidian-ingest` (the default, `confirm`), or does it run unattended with its own review layer such as git history (`unattended`)? Say the cost of `unattended` in one sentence: a poisoned source can then rewrite existing notes with nobody asked. Write the key only when the answer is `unattended`; the default needs no key. Merge into the existing file if there is one - never drop its other keys (`exclude-dirs`, `exclude-paths`, `exclude-link-scan`). If the key already exists, do not ask again.

9. Write `_CLAUDE.md`, `index.md`, root `log.md` (pointer), `Logs/YYYY-MM-DD.md` (today's entries), and any new `Bases/*.base` files
10. Write `<vault>/.claude/CLAUDE.md` holding a single import line, `@../_CLAUDE.md`, unless that file already exists with other content - in which case add the import line to it and leave the rest alone. This is what loads the manual for a Claude Code session started in the vault: Claude Code follows the import natively, with a 4 MiB limit, while the SessionStart hook is capped at 10,000 characters of context and cannot carry a real manual (#270).
11. Confirm what was written and tell the user to restart their Claude session so the new files take effect

If `_CLAUDE.md` already exists: show a diff of what would change and ask before overwriting.
If `index.md` already exists: regenerate it (it's always a fresh catalog of current vault state).
If a monolithic `log.md` already exists with `## YYYY-MM-DD` sections: run `uv run --directory "SKILL_ROOT" scripts/migrate_log.py --vault <vault-path>` (its absolute path was given at session start as **Skill root**; substitute it for `SKILL_ROOT`) to split it into `Logs/YYYY-MM-DD.md` files. Do not overwrite manually.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future agent` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. If that path does not resolve from your working directory, search upward for it; if you still cannot read it, say so before writing rather than producing a note that silently skips the rule. The vault is for future agent retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
