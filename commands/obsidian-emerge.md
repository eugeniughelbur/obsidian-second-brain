---
description: Surface unnamed patterns from your recent notes — recurring themes, hidden connections, and conclusions you haven't explicitly stated
category: thinking
---

Use the obsidian-second-brain skill. Execute `/obsidian-emerge $ARGUMENTS`:

The optional argument is a timeframe (e.g., "2 weeks", "this month"). Default: last 30 days.

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Determine the date range from the argument (default: last 30 days)
3. Spawn parallel subagents to read vault content from the period:
   - **Daily notes agent**: read all daily notes in the date range, extract recurring topics, complaints, observations, and energy patterns
   - **Dev logs agent**: read all dev logs in the range, extract repeated blockers, tools mentioned, architectural patterns
   - **Decisions agent**: read Key Decisions sections across project notes, look for directional trends
   - **Ideas agent**: read Ideas/ notes created in the range, look for thematic clusters
4. Merge results and identify:
   - **Recurring themes**: topics that appeared 3+ times without being named as a priority
   - **Emotional patterns**: what energizes vs. drains the user (based on language and context)
   - **Unnamed conclusions**: things the notes imply but never state outright (e.g., "you've mentioned onboarding friction in 4 different projects — this is a systemic issue, not a project-specific one")
   - **Emerging directions**: where the vault suggests the user is heading, even if they haven't committed to it
5. Present findings as a structured "Pattern Report" — each pattern gets: the evidence (cited notes), the interpretation, and a suggested action
6. Offer to save the pattern report to `Ideas/` or a relevant project note
7. Log a brief summary in today's daily note

The goal is insight the user cannot see themselves. Do not restate what they already know — surface what they haven't named yet.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
