---
description: Review vault learnings, prune stale ones, surface active patterns — the vault's lessons compound or expire
category: thinking
---

Use the obsidian-second-brain skill. Execute `/obsidian-learn $ARGUMENTS`:

The optional argument is a scope: `recent` (last 30 days, default), `all` (entire vault), or a topic name.

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Read `index.md` and `log.md` for vault context

3. Spawn parallel subagents to gather learnings:

   - **Lessons agent**: scan all daily notes for "Lesson learned" sections, "What didn't" sections, evening review insights
   - **Decisions agent**: read all ADRs in `wiki/decisions/` — extract the rationale and outcome of each
   - **Reports agent**: read recent emerge/synthesize/connect/challenge reports in `wiki/concepts/` (the auto-generated pattern reports)
   - **Mistakes agent**: scan dev logs and daily notes for "what didn't work", "wasted time on", "next time", "lesson", phrases indicating learning from failure
   - **Wins agent**: scan for patterns that worked — "this saved time", "this approach worked", recurring success patterns

4. For each learning found, classify:
   - **Active**: still relevant, recurring, reinforced by recent activity
   - **Stale**: 6+ months old with no recent reinforcement, or contradicted by newer evidence
   - **Superseded**: explicitly replaced by a newer ADR or pattern
   - **Promoted**: appeared 3+ times — should become a permanent rule in `_CLAUDE.md`

5. Generate the Learnings Report:

   ## Active Learnings (still applies)
   - List learnings reinforced in the last 90 days
   - Cite the original source and most recent reinforcement

   ## Stale Learnings (consider archiving)
   - List learnings with no recent reinforcement
   - Suggest: keep, archive, or convert to history note

   ## Superseded Learnings (already replaced)
   - Old position → New position with ADR reference

   ## Promotion Candidates (appeared 3+ times)
   - Learnings strong enough to become permanent rules in `_CLAUDE.md`
   - Suggest exact wording for the operating manual

   ## Top 5 Lessons of the Period
   - Most impactful learnings ranked by frequency × recency × consequence

6. Save the report to `wiki/concepts/YYYY-MM-DD — Learnings Review.md`
7. Append to `log.md`: `## [YYYY-MM-DD] learn | X active, Y stale, Z superseded, N promotion candidates`
8. Update today's daily note with a brief summary
9. Offer to:
   - Promote candidates to `_CLAUDE.md` (with user confirmation)
   - Archive stale learnings (with user confirmation)
   - Export top 5 as a shareable markdown for content/journaling

Lessons that aren't reviewed don't compound. This command turns scattered notes into a living rulebook.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
