---
description: Find and resolve contradictions in the vault — the vault maintains its own truth
category: thinking
---

Use the obsidian-second-brain skill. Execute `/obsidian-reconcile $ARGUMENTS`:

The optional argument is a topic or entity to focus on. If not provided, scan the whole vault.

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Read `index.md` to understand the full vault landscape

3. Spawn parallel subagents to find contradictions:
   - **Claims agent**: scan `wiki/concepts/` and `wiki/projects/` for factual claims — find pairs that contradict each other
   - **Entity agent**: scan `wiki/entities/` for outdated roles, companies, or descriptions that conflict with newer sources
   - **Decisions agent**: scan `wiki/decisions/` and project Key Decisions for reversed or superseded decisions that were never updated
   - **Source freshness agent**: compare `raw/` source dates against `wiki/` page dates — flag wiki pages that reference old sources when newer ones exist on the same topic

4. For each contradiction found, evaluate:
   - **Which source is newer?** (date comparison)
   - **Which source is more authoritative?** (peer-reviewed > blog post > transcript > opinion)
   - **Is this a genuine contradiction or an evolution?** (someone changing their mind is not a contradiction — it's growth)

5. Resolve each contradiction:
   - **Clear winner**: rewrite the outdated page with current info. Add a `## History` section noting what changed and why: "Previously stated X (source: raw/articles/old-article.md, 2025-11-01). Updated to Y based on newer evidence (source: raw/articles/new-article.md, 2026-03-15)."
   - **Genuinely ambiguous**: create `wiki/decisions/Conflict — Topic.md` documenting both sides, the evidence for each, and mark as `status: open` for the user to decide
   - **Evolution**: update the entity/concept page to reflect the current state and add the historical context

6. After all resolutions:
   - Rebuild affected sections of `index.md`
   - Append to `log.md`: `## [YYYY-MM-DD] reconcile | X contradictions found, Y auto-resolved, Z flagged for user`
   - Update today's daily note with a reconciliation summary

7. Report back:
   - **Auto-resolved** (list with old claim → new claim and why)
   - **Flagged for user** (genuinely ambiguous — needs human judgment)
   - **Stale pages updated** (pages rewritten with fresher sources)

The vault should never contain two pages that disagree without knowing they disagree. Contradictions are either resolved or explicitly documented as open questions.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
