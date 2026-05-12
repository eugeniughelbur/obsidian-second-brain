---
description: Extract decisions from this conversation and log them to the right project notes
category: thinking
---

Use the obsidian-second-brain skill. Execute `/obsidian-decide $ARGUMENTS`:

The optional argument narrows focus to a specific topic.

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Scan the conversation for decisions made — look for conclusions, choices, commitments, direction changes
3. If a topic argument is given, focus on decisions related to that topic
4. Find the relevant project note(s) — search the vault if needed
5. Append each decision to the project note's `## Key Decisions` section with today's date
6. Log a summary in today's daily note
7. If a decision affects multiple projects, log it in all of them

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
