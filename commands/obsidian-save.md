---
description: Save everything worth keeping from this conversation to the vault
category: vault
---

Use the obsidian-second-brain skill. Execute `/obsidian-save`:

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Scan the entire conversation and identify all vault-worthy items: decisions, tasks, people mentioned, projects started, ideas, learnings, deals, mentions/shoutouts, AND content-worthy items (hooks, data points, swipe-file material, research findings)
3. Group items by type: people, projects, tasks, decisions, ideas, deals, content
4. Spawn parallel subagents — one per group — so all note types are handled simultaneously:
   - **People agent**: search for each person, create or update notes, log interactions
   - **Projects agent**: search for each project, create or update notes
   - **Tasks agent**: parse tasks, add to the right kanban columns
   - **Decisions agent**: find relevant project notes, append to Key Decisions sections
   - **Ideas agent**: search Ideas/ for related notes, create or append
   - **Content agent** (if a `social-media/` folder exists in the vault): scan for content-worthy items and route them:
     - **Hooks, angles, contrarian takes** → append to `social-media/ideas.md` (dated bullet)
     - **Specific numbers, stats, reusable data points** → append to `social-media/data-points.md` (with source)
     - **External posts that hit + why** → append to `social-media/swipe-file.md` (link + reason)
     - **Research findings, frameworks, methodologies** → create `social-media/research/YYYY-MM-DD — topic.md`
5. After all agents complete: update today's daily note with links to everything saved
6. Report back: a clean list of what was saved and where

Search before creating anything — duplicate notes are vault rot. Propagate every write to boards, daily note, and linked notes. Never create an orphaned note.

The content agent only runs if `social-media/` exists in the vault. If it doesn't exist, skip silently — don't create the folder unprompted.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
