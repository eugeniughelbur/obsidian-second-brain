---
description: Track a recurring obligation (payment, filing, ops) with a cadence and a computed next-due date
category: vault
triggers_en: ["recurring task", "monthly obligation", "remind me every month", "recurring payment", "track a recurring"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-recurring $ARGUMENTS`:

The argument states the obligation and its cadence (e.g. "pay social benefits, monthly day 20"). Pull blocker/owner detail from the conversation.

1. Read `_CLAUDE.md` first if it exists in the vault root.
2. Search for an existing note on this obligation before creating one (see the anti-fabrication rule). If one exists, update it instead of duplicating.
3. Build the note with these sections: What, Cadence, Blockers, History. Use the vault's `templates/` version if one exists.
4. Set frontmatter: `type: recurring-task`, `cadence`, `owner`, `blocker` (wikilink if a person/vendor gates it), `next-due` (compute the next occurrence from today and the cadence), and `amount` if it is a payment.
5. Add a card for the next occurrence to the right board so it surfaces before `next-due`.
6. Propagate: link from the relevant project or finance note, and append a one-line entry to today's daily note and the operation log (`Logs/YYYY-MM-DD.md` if it exists, otherwise `log.md`).
7. On each completion: append a row to History and advance `next-due` to the next occurrence.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
