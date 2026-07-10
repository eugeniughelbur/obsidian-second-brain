---
description: Condense a long note or source into key claims, each tagged with provenance back to the exact source block it came from
category: thinking
triggers_en: ["distill this", "condense this note", "summarize with sources", "distill this source", "boil this down with provenance"]
triggers_es: ["destila esto", "condensa esta nota", "resúmelo con fuentes", "destila esta fuente", "resume esto sin perder la trazabilidad"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-distill $ARGUMENTS`:

The optional argument is a note path, a `[[wikilink]]`, a folder, or a source URL/file. If none is given, ask what to distill (offer the longest recently-touched notes in `raw/` and the research folders as candidates).

A distillation is not a summary. A summary throws the source away; a distillation keeps a verifiable trail, so a teammate (or a future Claude) can check every claim against the exact place it came from. This is the trust primitive: condensed but never unmoored from evidence.

1. Read `_CLAUDE.md` first if it exists in the vault root. Resolve the destination folder per `references/folder-map.md` (a distillation is a concept/reference note: wiki-style `wiki/concepts/`, Obsidian-style `Knowledge/`).

2. Resolve and read the source:
   - A vault note or `[[wikilink]]`: read it in full.
   - A folder: read every note in it and distill them as one corpus (note which file each claim comes from).
   - A URL: fetch it (read the page). A local file: read it. Save the untouched original to `raw/` first if it is not already there - the distillation must point at a stable source.
   - Never distill from memory or a partial read. If the source is too large to read in one pass, read it in ordered chunks and keep going; do not sample (see the anti-fabrication rule).

3. Segment the source into stable, citable **source blocks** and number them. A block is a heading section, a paragraph, a list, or a transcript turn - whatever the source's natural unit is. Record for each block a locator the reader can find again: a heading path, a paragraph index, or a timestamp/line range. These locators are the provenance anchors.

4. Extract the key claims. For each claim, write one tight sentence and attach its provenance: which block(s) it came from, as `(src: B3)` or `(src: B3, B7)`. Every claim MUST carry at least one block reference - a claim with no source does not go in the distillation (if you believe it but the source does not say it, it is your inference, not a distilled claim; see step 6). Mark each claim's confidence (`stated | high | medium | speculation`) and add a recency marker on any time-sensitive external fact (`(as of YYYY-MM, domain)`).

5. Group the claims under short thematic headings (the distilled structure), preserving the provenance tags inline. Keep the source's own terms; do not smooth them into generic phrasing.

6. Keep inference separate from evidence. If the distillation surfaces a conclusion the source implies but never states, put it under a clearly labelled `## Inferences (not in the source)` section, each marked `confidence: speculation`, so distilled fact and your reasoning never blur.

7. Write the distillation note. Path: `<resolved-folder>/Distill - <source-title> (YYYY-MM-DD).md`. It MUST follow `references/ai-first-rules.md`. Frontmatter includes `type: distillation`, `ai-first: true`, `source` (the verbatim path/URL of what was distilled), `source-blocks` (the count), `date`, `tags: [distillation, thinking]`. Body order:
   - `## For future Claude` - 2-3 sentences: what was distilled, why, and that every claim carries a `(src: Bn)` pointer back to the numbered source blocks at the bottom for verification.
   - `## Distilled claims` - the grouped claims with inline provenance tags.
   - `## Inferences (not in the source)` - only if step 6 produced any.
   - `## Source blocks` - the numbered list (`B1`, `B2`, ...) with each block's locator (heading/paragraph/timestamp) and a short quote or first line, so the anchors are resolvable from inside the vault. This is the recency/verification anchor.

8. Link the distillation from the original source note (add a `Distilled: [[...]]` line) and from today's daily note. Append a one-line entry to the operation log (`Logs/YYYY-MM-DD.md` if it exists, else `log.md`).

9. Report: the source, how many blocks and claims, the path written, and any claim you dropped because it had no traceable source (so the gap is visible, never silently cut).

Distillation is what makes a vault trustworthy to more than one person: condensed enough to read fast, anchored enough to audit. Pairs with `/obsidian-ingest` (which brings the source in) and `/vault-deep-synthesis` (which cross-references many notes); this one compresses a single source without losing the thread back to it.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Every distilled claim must trace to a real source block - never invent a claim, a block, or a locator, and never attach a `(src: Bn)` tag to a block that does not support it. Read the source exhaustively rather than sampling; a confident distillation built on a partial read is the failure mode this command exists to prevent. Mark inferences as `speculation` and keep them out of the distilled-claims section. See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
