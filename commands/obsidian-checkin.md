---
description: Ask the owner whether old people and project notes still hold - shows what each note says and when it was last checked, re-asks until answered, saves the news
category: vault
trigger-mode: explicit
triggers_en: ["vault check-in", "check my old notes", "which notes are out of date", "ask me about stale notes"]
triggers_de: ["Vault-Check-in", "prüf meine alten Notizen", "welche Notizen sind veraltet", "frag mich nach veralteten Notizen"]
triggers_es: ["revisión de la bóveda", "revisa mis notas viejas", "qué notas están desactualizadas", "pregúntame por notas viejas"]
triggers_pt: ["check-in do cofre", "revise minhas notas antigas", "quais notas estão desatualizadas", "me pergunte sobre notas antigas"]
triggers_zh: ["知识库核对", "检查我的旧笔记", "哪些笔记过时了", "问我旧笔记有没有更新"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-checkin $ARGUMENTS`:

A fact check compares notes with other notes, so news that never reached the vault (a bill settled, a move, a new job) leaves a note stale and no lint can see it. The owner is the only source. This command asks them, a few notes at a time, and saves what they answer.

The argument picks the mode: `ask` (default), `nudge`, `answer <the owner's reply>`, or `status`. The deterministic work lives in `scripts/checkin.py` (run it from the skill root: its absolute path was given at session start as **Skill root**; substitute it for `SKILL_ROOT`). Every call takes `--path <vault>`. The open questions live in `<vault>/.checkin.json`, never in the chat, so a question the host drops is sent again on the next run until it is answered.

1. Read `_CLAUDE.md` first if it exists in the vault root, for the vault path and privacy rules.

## Mode: ask (once a day)

2. Run `uv run --directory "SKILL_ROOT" scripts/checkin.py --path <vault> pick`. It returns up to 3 notes whose facts are older than 14 days (`--days N` to change), never more than 3 open at once (`--max-open N`). People tagged `family`, `relationship: strong` and `checkin: priority` come first, then active projects, then the most linked notes. Notes with a closed `status`, `checkin: never`, an open card, or a skip in the last 14 days are left out. An empty list means nothing is due: send nothing and stop.
3. For each picked note, read the note itself (the `excerpt` is a hint, not the source) and write **1 to 3 facts**:
   - One short line each, under 140 characters, in plain words.
   - Taken from the note only. Never add, guess, or round a fact. Keep dates and amounts exactly as written.
   - Prefer facts that can change: job, where they live, status, money, health, who they are with. Skip timeless ones like a birth date.
4. Open each card: `checkin.py --path <vault> ask --note "<path>" --fact "..." --fact "..."`.
5. Run `checkin.py --path <vault> message` and send its output to the owner **verbatim**, as one message. Do not add commentary, a summary, or a second message. A host may put its own marker (for example a notification emoji) in front.

## Mode: nudge (every few hours while the owner is awake)

6. Run `checkin.py --path <vault> message`. If it prints nothing, nothing is open: send nothing. Otherwise send the output verbatim. It repeats each card in full (name, date of the facts, the facts) with a reminder count, because the owner will not remember what an earlier message said. Never send a bare "still waiting" without the cards.

## Mode: answer (whenever the owner replies, even days later)

7. Run `checkin.py --path <vault> status` to see the open cards. Numbers in the reply refer to the last message sent (`last_message` in `.checkin.json`), so `--number N` resolves them.
8. Read the reply. It may cover several cards: `1 same`, `2 moved to Rotterdam`, `skip 3`, one per line or comma-separated. Free text with no number answers the only open card, when exactly one is open. If it is ambiguous, ask once which number it is for.
9. For each answer:
   - **same**: `checkin.py --path <vault> done --number N --outcome same`. This stamps `last-checked` with today, and the note stays quiet for 14 days.
   - **skip**: `done --number N --outcome skipped`. Nothing is stamped. The note can come back after 14 days.
   - **news**: update the note first, then `done --number N --outcome updated`.
     - Rewrite the stale claim where it lives. Do not only append. When the old value is still useful as history (an original bill before a settlement), keep it and label it as the earlier value.
     - Stamp the new claim: `(stated by <owner> YYYY-MM-DD)`, confidence `stated`. Anything the reply leaves out (a name, a date, an amount) is `TBD`, never guessed.
     - Set `updated:` to today on every note whose facts changed. Do NOT touch `updated:` on a note you only linked or formatted, or it hides from the check-in for a cycle.
     - Propagate: every person, project, or place in the news gets the change on its own note too, as `/obsidian-save` would, with `[[wikilinks]]` both ways.
10. Check every note you wrote: `uv run --directory "SKILL_ROOT" scripts/check_notes.py --path <vault> --fix "<path>" ...`. It runs the same AI-first check Claude Code runs on every write, fixes banned characters, and exits 1 on anything left. Fix what it reports before you finish.
11. Reply with one short line, for example `Saved: 1 same, 2 updated (Ana, moved to Rotterdam).` If cards are still open, say nothing more: the next nudge will carry them.

## Mode: status

12. Run `checkin.py --path <vault> status` and show the open cards as a short list: name, date of the facts, times sent.

## Rules

- **Private channel only.** Check-in messages and answers can hold family, health, and money facts. Send them only to the owner directly, never to a group chat, a team channel, a post, or a log that others read.
- **Short.** One message per run, at most 3 cards in it. The script does the formatting so every host sends the same shape.
- **Explicit only.** Never start a check-in because a conversation drifted near an old note. It runs when the owner asks or on the owner's own schedule.
- **Per note control.** `checkin: never` in a note's frontmatter keeps it out for good. `checkin: priority` moves it to the front.
- After each mode, append to the operation log: if `Logs/` exists write `**HH:MM** - checkin <mode> | N asked, N answered, N open` to `Logs/YYYY-MM-DD.md`; otherwise append `## [YYYY-MM-DD] checkin <mode> | N asked, N answered, N open` to `log.md`. Names and facts stay out of the log line.

## Scheduling

Hosts with a scheduler run `ask` once a day and `nudge` every 2 to 4 hours inside the owner's waking hours. Hosts without hooks (Grok Bot, cron agents) must run step 10 after every vault write, not only here: it is their write-time check.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future agent` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. If that path does not resolve from your working directory, search upward for it; if you still cannot read it, say so before writing instead of producing a note that silently skips the rule. The vault is for future agent retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.

<!-- author-credit -->

---

From [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain), created by Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator). Questions or consulting: [LinkedIn](https://www.linkedin.com/in/eugeniu-ghelbur/) or [e.ghelbur@gmail.com](mailto:e.ghelbur@gmail.com). More: [The AI Operator](https://theaioperator.io/?utm_source=github&utm_medium=file-credit) | [X](https://x.com/eugeniu_ghelbur) | [GitHub](https://github.com/eugeniughelbur). MIT license.
