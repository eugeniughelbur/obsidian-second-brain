---
description: Merge two near-duplicate notes found by /obsidian-health into one - dry run by default, redirects the retired note rather than deleting it
category: meta
triggers_en: ["merge these notes", "merge duplicate notes", "merge near-duplicates", "combine these two notes"]
triggers_de: ["diese Notizen zusammenführen", "doppelte Notizen zusammenführen", "ähnliche Notizen zusammenführen", "diese beiden Notizen kombinieren"]
triggers_es: ["fusiona estas notas", "combina estas notas duplicadas", "une estas dos notas"]
triggers_pt: ["mescle estas notas", "combine estas notas duplicadas", "una estas duas notas"]
triggers_zh: ["合并这两篇笔记", "合并重复笔记", "把这些近似重复的笔记合并"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-merge $ARGUMENTS`:

`/obsidian-health` finds duplicate pairs and stops - it is read-only by contract. This command does the merge: `scripts/merge_notes.py` (SKILL_ROOT's absolute path was given at session start as **Skill root**; substitute it for `SKILL_ROOT` below) handles the mechanical half - frontmatter union, alias folding, and replacing the retired note with a `type: redirect` stub - and you compose the merged body, since deciding what actually contradicts between two notes is judgment, not mechanics.

**Nothing is ever deleted.** The surviving note keeps its path; the retired note's file stays in the vault, its content replaced by a short pointer (`references/write-rules.md`: never delete vault notes).

1. Read `_CLAUDE.md` first to find the vault path.

2. **Resolve which two notes to merge:**
   - If `$ARGUMENTS` gives two note paths, the first is the **canonical** note (its path survives) and the second is **retired** (becomes a redirect). If the ordering isn't obviously what the user wants (e.g. the second path is clearly the richer/more recent note), say which one you'd keep canonical and why, and confirm before continuing.
   - If `$ARGUMENTS` is `--from-health` (or the user just says "merge the duplicates from health"), run:
     `uv run --directory "SKILL_ROOT" scripts/merge_notes.py --path <vault> --from-health`
     with no `--canonical`. This lists every duplicate group from the current scan, split into auto-pairable (exactly 2 files) and groups that need an explicit pick (3+ files, where nothing says which file should survive). Present the list and ask the user which pair to merge, or merge them one at a time with their approval - never guess a canonical note out of a 3+ group.

3. **Read both notes in full.** Note each one's `date`/`updated`, and everything in its body - this is the material the merged body and the frontmatter conflict list are built from.

4. **Compose the merged body**, following `references/ai-first-rules.md`:
   - One `## For future agent` preamble at the top, stating this note is the result of a merge (name both original notes) and what it now covers.
   - Keep both notes' provenance trails - what each note said and when - rather than silently picking a winner's prose and discarding the other's.
   - Where the two notes' bodies actually disagree (not just phrase things differently), list the contradiction explicitly - which note said what, and its date - rather than resolving it silently. An unresolved factual conflict is not this command's job to adjudicate; documenting it is.
   - Carry forward every `[[wikilink]]` from both notes that is still relevant; do not drop cross-links because they came from the retired side.
   - Write the composed body to a scratch file (e.g. via the Write tool, alongside the vault or in a temp path) - this is what `--merged-body-file` reads. Writing it once and reusing the same file for the dry run and the `--apply` run is what guarantees the preview and the actual write are identical.

5. **Preview (dry run, no `--apply`):**
   `uv run --directory "SKILL_ROOT" scripts/merge_notes.py --path <vault> --canonical "<canonical rel path>" --retire "<retired rel path>" --merged-body-file <scratch file>`
   (swap `--retire` for `--from-health` if resolving the pair from the health scan, per step 2). This prints the frontmatter conflicts (canonical's value wins each one; the retired note's value is recorded under `merged_from:`), whether a title was folded into `aliases:`, and the full text of both the proposed canonical note and the proposed redirect stub. Show this to the user - do not summarize it away.

6. **Ask for explicit confirmation before applying.** This rewrites one note and replaces another's entire content - never auto-apply on the strength of the dry run alone, the same rule this skill applies to any destructive vault write.

7. **Apply**, once confirmed, by re-running the exact same command from step 5 with `--apply` appended. Do not hand-edit either file afterward - the write already happened byte-for-byte as previewed.

8. **Report back:** which note survived, which became a redirect, the frontmatter fields that conflicted (and which value won), any alias added, and the contradictions the merged body documented rather than resolved.

9. Append to the operation log: if `Logs/` exists write `**HH:MM** - merge | <retired> -> <canonical>` to `Logs/YYYY-MM-DD.md`; otherwise append `## [YYYY-MM-DD] merge | <retired> -> <canonical>` to `log.md`.

If `merge_notes.py` refuses to run (malformed frontmatter on either note, an ambiguous `--from-health` group, a path that isn't in the vault), it says exactly why on stderr with a nonzero exit - relay that message rather than retrying blindly or picking a canonical note for the user.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future agent` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The retired note is the one documented exception: it becomes `type: redirect` (schema in `references/ai-first-rules.md` § Documented exceptions), which deliberately carries no preamble - its only job is to point at the canonical note. If the reference path does not resolve from your working directory, search upward for it; if you still cannot read it, say so before writing rather than producing a note that silently skips the rule.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). Do not resolve a genuine contradiction between the two notes by picking one side and dropping the other - list it instead. See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
