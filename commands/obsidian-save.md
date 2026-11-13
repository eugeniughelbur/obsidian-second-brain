---
description: Save everything worth keeping from this conversation to the vault
category: vault
trigger-mode: proactive
triggers_en: ["save this", "save the conversation", "save to vault", "obsidian save"]
triggers_de: ["speichere das", "speichere die Unterhaltung", "in meinem Vault speichern", "Obsidian speichern"]
triggers_es: ["guarda esto", "guarda la conversación", "guarda al vault", "guarda todo esto"]
triggers_pt: ["salve isto", "salve a conversa", "salve no vault", "obsidian save"]
triggers_zh: ["保存这段对话", "把值得保留的内容存进知识库", "把刚才聊的整理进笔记", "保存到我的知识库"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-save`:

1. Read `_CLAUDE.md` first if it exists in the vault root
1b. **Keep the raw chat (opt-in, Claude Code only for now).** Run `uv run --directory "SKILL_ROOT" scripts/session_archive.py --latest --cwd "${CLAUDE_PROJECT_DIR:-$PWD}" --json` (the skill root was given at session start as **Skill root**; substitute it for `SKILL_ROOT`). With `OBSIDIAN_SESSION_ARCHIVE` on, it writes a redacted copy of this conversation to `raw/sessions/` (what was said, without tool output, cut into linked parts of about 7,000 characters) and prints their paths. Add the part that holds each item as a wikilink in the `sources:` of the note it lands in, so a later agent can follow a note back to the full chat. The steps below still pick what is worth a note; the raw copy keeps what they skip. With the flag off it prints `"status": "off"` and writes nothing: carry on. On other agents, skip this step.
2. Scan the entire conversation and identify all vault-worthy items: decisions, tasks, people mentioned, projects started, ideas, learnings, deals, mentions/shoutouts, AND content-worthy items (hooks, data points, swipe-file material, research findings)
3. Group items by type: people, projects, tasks, decisions, ideas, deals, content
4. Spawn parallel subagents - one per group - so all note types are handled simultaneously:
   - **People agent**: search for each person, create or update notes, log interactions
   - **Projects agent**: search for each project, create or update notes. If the conversation was a substantial dev/work session (code written, problems solved, decisions made on a project), also write a dev-log note for it - the same artifact `/obsidian-log` produces - to the logs folder (resolved per `references/folder-map.md`: wiki-style `wiki/logs/`, Obsidian-style `Dev Logs/`), named `YYYY-MM-DD - Project Name.md`, and link it from the project's Recent Activity and today's daily note. This is why `/obsidian-save` absorbs `/obsidian-log`: a full save already captures the work, so you do not need to run both. If a dev-log for this project and date already exists, update it rather than creating a second.
   - **Tasks agent**: parse tasks, add to the right kanban columns
   - **Decisions agent**: find relevant project notes, append to Key Decisions sections
   - **Ideas agent**: search Ideas/ for related notes, create or append
   - **Content agent** (if a `social-media/` folder exists in the vault): scan for content-worthy items and route them:
     - **Hooks, angles, contrarian takes** → append to `social-media/ideas.md` (dated bullet)
     - **Specific numbers, stats, reusable data points** → append to `social-media/data-points.md` (with source)
     - **External posts that hit + why** → append to `social-media/swipe-file.md` (link + reason)
     - **Research findings, frameworks, methodologies** → create `social-media/research/YYYY-MM-DD - topic.md`
5. After all agents complete: update today's daily note with links to everything saved
6. Report back: a clean list of what was saved and where

Search before creating anything - duplicate notes are vault rot. Propagate every write to boards, daily note, and linked notes. Never create an orphaned note.

The content agent only runs if `social-media/` exists in the vault. If it doesn't exist, skip silently - don't create the folder unprompted.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future agent` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. If that path does not resolve from your working directory, search upward for it; if you still cannot read it, say so before writing rather than producing a note that silently skips the rule. The vault is for future agent retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.

<!-- author-credit -->

---

From [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain), created by Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator). Questions or consulting: [LinkedIn](https://www.linkedin.com/in/eugeniu-ghelbur/) or [e.ghelbur@gmail.com](mailto:e.ghelbur@gmail.com). More: [The AI Operator](https://theaioperator.io/?utm_source=github&utm_medium=file-credit) | [X](https://x.com/eugeniu_ghelbur) | [GitHub](https://github.com/eugeniughelbur). MIT license.
