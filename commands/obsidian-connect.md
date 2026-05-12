---
description: Bridge two unrelated domains using your vault's link graph — forces creative friction to spark new ideas
category: thinking
---

Use the obsidian-second-brain skill. Execute `/obsidian-connect $ARGUMENTS`:

Two arguments required: the two topics, domains, or note names to connect. If only one is given or none, ask the user for both.

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Parse the two domains from arguments (e.g., `/obsidian-connect "distributed systems" "cooking"`)
3. For each domain, search the vault:
   - Find all notes related to that domain (by title, tags, content)
   - Map their backlinks and outgoing links to build a local cluster
4. Find the bridge:
   - Look for shared links, shared tags, or shared people between the two clusters
   - If a direct path exists in the link graph, trace it and explain each hop
   - If no direct path exists, find the closest semantic overlap — concepts, metaphors, or structural similarities
5. Generate creative connections:
   - **Structural analogy**: how a pattern in domain A maps to domain B (e.g., "load balancing is like mise en place — both are about distributing work before the rush")
   - **Transfer opportunities**: what works in A that could be applied to B
   - **Collision ideas**: new concepts that only exist at the intersection of both
6. Present 3-5 specific, actionable connections — not vague analogies but concrete ideas the user could act on
7. Offer to save the best connections to `Ideas/` with links to both source domains
8. Log the connection exercise in today's daily note

The value is in unexpected links. If the connection is obvious, dig deeper. The best output makes the user say "I never thought of it that way."

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
