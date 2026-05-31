---
description: Surface 3-5 next-direction candidates by reading ungraduated ideas, open project questions, and orphan research notes - what is worth working on next
category: thinking
triggers_en: ["what should I work on next", "idea discovery", "surface next directions", "what's worth pursuing"]
---

Use the obsidian-second-brain skill. Execute `/idea-discovery`:

Answers "what is worth doing next" from material already in the vault. Distinct from `/obsidian-emerge` (which names unstated patterns) and `/obsidian-graduate` (which promotes one chosen idea into a project) - this ranks several candidate directions so you can pick one.

1. Gather candidate signals - list and grep exhaustively (see the anti-fabrication rule):
   - Ungraduated ideas in `Ideas/` (status `captured` or `exploring`, not yet `graduated`).
   - Open questions in active project notes (Open Questions sections, unresolved decisions).
   - Orphan research notes in `Research/` that no project links to.
2. Rank the candidates by a simple, stated heuristic: recency (touched recently), pull (how many notes reference or depend on it), and momentum (does anything already build toward it). State the heuristic in the output so the ranking is auditable.
3. For each of the top 3-5, write: the candidate, why now, the `[[source notes]]`, and the smallest next step that would move it forward.
4. Optionally suggest running `/research [topic]` on a candidate to pull external signal before committing, or `/obsidian-graduate` to promote one into a full project.
5. Save the shortlist to `Ideas/YYYY-MM-DD - discovery.md` (`type: synthesis`, tagged `[thinking, idea-discovery]`) with source links in frontmatter. Do NOT auto-graduate anything - this command only surfaces and ranks.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Rank only real candidates found in the vault - never invent an idea, an open question, or a research note to pad the shortlist. Enumerate `Ideas/`, project Open Questions, and orphan research exhaustively rather than sampling. See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
