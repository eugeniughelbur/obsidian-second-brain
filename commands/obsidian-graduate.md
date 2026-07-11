---
description: Promote an idea fragment into a full project spec with tasks, board entries, and structure
category: thinking
triggers_en: ["promote idea", "graduate this to project", "make a project from this", "elevate idea"]
triggers_es: ["promociona esta idea", "convierte esto en proyecto", "haz un proyecto de esto", "eleva esta idea"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-graduate $ARGUMENTS`:

The optional argument is the idea title, tag, or keyword. If not provided, scan recent notes for ideas tagged `#idea` or in the ideas folder (resolved per `references/folder-map.md`) and present them for selection.

1. Read `_CLAUDE.md` first if it exists in the vault root. Resolve the ideas folder and projects folder per `references/folder-map.md` (wiki-style: ideas in `wiki/concepts/`, projects in `wiki/projects/`; Obsidian-style: `Ideas/`, `Projects/`).
2. Find the idea to graduate:
   - If argument given: search the ideas folder, daily notes, and captures for a matching idea (fuzzy match)
   - If no argument: list recent ideas (last 14 days) and ask the user to pick one
3. Read the full idea note and any linked notes for context
4. Research the vault for related content:
   - Existing projects that overlap
   - People who were mentioned in connection with this idea
   - Past decisions that relate
   - Similar ideas that were previously explored (to avoid reinventing)
5. Generate a full project spec:
   - **Project note** in the projects folder (resolved above) with the full `type: project` schema from `references/ai-first-rules.md` (`type: project`, `date`, `updated`, `status: planning`, `tags: [project]`, `related-people`, `related-projects`, `ai-first: true`) plus `graduated-from: "[[Idea Note]]"`
   - **Description**: what this project is and why it matters
   - **Goals**: 3-5 concrete outcomes
   - **Key tasks**: broken into phases with priorities
   - **Open questions**: what still needs answering
   - **Related notes**: links to everything relevant found in step 4
6. Create board entries:
   - Add a card to the relevant kanban board in `Backlog` or `This Week`
   - Add individual task cards if multiple phases
7. Update the original idea note:
   - Add `status: graduated` to frontmatter
   - Add a link to the new project note
8. Link the new project from today's daily note
9. Report: what was created, what was linked, what needs the user's input

The idea doesn't die - it evolves. The original note stays as the origin story, the project note becomes the execution plan.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
