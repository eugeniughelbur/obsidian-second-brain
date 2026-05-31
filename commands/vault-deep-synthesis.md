---
description: Deep cross-reference of everything the vault knows about one topic - agreements, contradictions, stale claims, and coverage gaps. Pure vault, no network
category: thinking
triggers_en: ["synthesize what I know about", "deep synthesis on", "cross-reference my notes on", "what does my vault say about"]
---

Use the obsidian-second-brain skill. Execute `/vault-deep-synthesis [topic]`:

A focused, topic-driven cross-reference of the existing vault. Unlike `/obsidian-synthesize` (which scans the whole vault for unnamed patterns unprompted), this takes a topic you name and reads every note touching it to produce one consolidated view. Pure vault: no network, no API keys.

1. Resolve the topic from the argument. If none, ask what to synthesize.
2. Find every note that references the topic - grep and list exhaustively across `wiki/`, `Research/`, `Knowledge/`, `Ideas/`, and any project folders (do not sample; see the anti-fabrication rule). Match by every plausible name, alias, and folder.
3. Read the matching notes and cross-reference them into:
   - **What the vault agrees on** - claims multiple notes corroborate, with `[[wikilinks]]` to each.
   - **Contradictions** - where notes disagree; name both `[[notes]]` and the specific conflict. Do not resolve them here (that is `/obsidian-reconcile`); just surface them.
   - **Stale claims** - dated facts that may no longer hold (cite the note and the date).
   - **Coverage gaps** - questions the topic raises that the vault does not answer.
4. Write the synthesis to `wiki/concepts/YYYY-MM-DD - synthesis - <topic-slug>.md` (`type: synthesis`, tagged `[research, thinking, vault-deep-synthesis]`), listing the source notes it read in frontmatter.
5. Do NOT modify the source notes - this command only reads and synthesizes. Append a one-line entry to the operation log.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Enumerate the matching notes exhaustively, do not sample - a partial scan reported as complete produces confident wrong answers. Never invent a claim, contradiction, or source; if the vault is thin on the topic, say so. See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
