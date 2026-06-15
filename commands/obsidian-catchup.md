---
description: Review and process everything captured on the go from the Telegram journal bot - voice, text, images, PDFs, links - waiting in the catchup queue. You pull it when you are back at the laptop; nothing is processed autonomously.
category: vault
triggers_en: ["catch up", "catchup", "what did I dump from telegram", "process my captures", "go through my telegram dumps", "anything new from the phone", "process my catchup", "review what I captured", "what did I capture on the go"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-catchup $ARGUMENTS`:

The optional argument is a timeframe filter: `today`, `week`, or `all` (default: `all` unprocessed).

This is the laptop-side companion to the Telegram journal bot (`integrations/telegram-journal/`). The bot captures on the go (voice / text / image / PDF / link) and appends each one to a `catchup.md` queue in the vault. This command is where those captures become real, integrated vault knowledge - on your schedule, with you driving. It is a PULL: nothing was processed automatically, so nothing surprises you.

1. Read `_CLAUDE.md` first if it exists in the vault root (for vault paths + conventions).
2. Read `catchup.md` in the vault root - the queue the bot fills. Each line is `- [ ] date time | kind | summary | -> where`. An unchecked `- [ ]` is unprocessed; `- [x]` is already done.
3. Collect the unchecked items. Apply the timeframe filter if given (`today` = today's date; `week` = the last 7 days; `all` = every unchecked). If there are none, say "nothing to catch up on" and stop.
4. Show the user a tight list, grouped by age (**Today** / **This week** / **Older**): time, kind, summary, and the `[[link]]` to where it landed. Flag stale ones explicitly (e.g. "captured 9 days ago - still relevant?"), since a capture that mattered on a walk may be dead now.
5. Process the items WITH the user (this is a together-review, never an autonomous sweep). For each item - or a sensible batch - open the linked note/entry, read the actual captured content, and propose one of:
   - **Integrate** - fold it into the right existing or new note (person / project / concept / decision), following `references/ai-first-rules.md`: update existing notes, fill and link, reconcile contradictions - exactly as `/obsidian-save` would. Prefer updating an existing note over creating a near-duplicate.
   - **Keep as-is** - it is already filed fine (e.g. a daily-note thought); just acknowledge it.
   - **Discard** - stale or junk; remove the stray entry from where it landed.
   Surface your proposal and let the user confirm or redirect before you write anything.
6. After an item is handled, check it off in `catchup.md`: change its `- [ ]` to `- [x]` and append ` (processed YYYY-MM-DD)`. Never delete queue history - it is the record of what came in.
7. End with a one-line summary: N integrated, M discarded, K left unprocessed.

The split this enforces: the phone is for fast, dumb capture; the laptop is where you think and integrate. Same brain, two speeds - not two silos.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
