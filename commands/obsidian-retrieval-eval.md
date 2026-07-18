---
description: Measure how well vault search finds the right note for a natural-language question - recall@k and MRR, with the concrete failures
category: meta
triggers_en: ["evaluate retrieval", "how good is my vault search", "retrieval eval", "test vault search quality", "measure find quality"]
triggers_es: ["evalúa la búsqueda", "qué tal funciona la búsqueda de mi vault", "evaluación de recuperación", "prueba la calidad de la búsqueda", "comprueba si encuentra bien mis notas"]
triggers_pt: ["avalie a recuperação", "quão boa é a busca do meu vault", "avaliação de recuperação", "teste a qualidade da busca do vault", "meça a qualidade da busca"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-retrieval-eval $ARGUMENTS`:

You cannot improve retrieval you have not measured. This scores the vault's REAL search (the term-frequency, title-weighted ranking in `integrations/obsidian-mcp-server/vault_ops.py`, the same engine behind `/obsidian-find` and the MCP connector) against natural-language questions whose correct answer note is known - so "should I add a vector index / better ranking?" becomes a number and a list of failures, not a hunch.

The optional argument is a number of cases to (re)generate first (without `XAI_API_KEY` the generator silently falls back to verbatim-sentence heuristics - fine for keyword-style cases, weak for paraphrase-style) (e.g. `30`), or `report` to also write the result to the vault. No argument: evaluate the existing cases.

1. Read `_CLAUDE.md` first if it exists in the vault root.

2. If the user asked to generate (or no cases file exists yet at `scripts/eval/retrieval_cases.jsonl`), bootstrap the eval set from the vault. Run from the skill root (its absolute path was given at session start as **Skill root**; substitute it for `SKILL_ROOT`):
   ```bash
   uv run --directory "SKILL_ROOT" python scripts/eval/retrieval_eval.py --generate 30
   ```
   This samples real notes and, for each, has an LLM write a question whose answer is in that note while AVOIDING the note's title words (so it tests retrieval, not string match). The note's path is the gold answer. Cases are gitignored - they contain private note paths.

3. Run the evaluation (from the same skill root):
   ```bash
   uv run --directory "SKILL_ROOT" python scripts/eval/retrieval_eval.py --json
   ```
   It prints recall@1/3/5/10, MRR, and per-case results: misses (gold note never in the top 10) and buried cases (gold ranked below #3, usually because a noisy high-mention note or a `raw/` transcript outscored the canonical note).

4. Interpret the numbers for the user in plain language: what fraction of natural-language questions surface the right note, and the dominant failure pattern (e.g. long `raw/` sources and `log.md` outranking short canonical notes; title-weighting helping only when the query reuses title words). Name the specific notes that wrongly ranked #1 from the JSON.

5. Turn failures into concrete, testable retrieval fixes ranked by leverage - e.g. exclude `raw/` and `log.md` from search, boost notes by `type:` (canonical concept/entity/project over transcripts), add alias/heading indexing, or add semantic matching. Each fix is a hypothesis: re-run this eval on the SAME cases after the change to confirm it actually raised recall, never assume.

6. If the user passed `report` (or asks to save), write an AI-first baseline note to `wiki/concepts/` (resolve per `references/folder-map.md`), `type: synthesis`, tagged `[retrieval, eval]`, linked from a retrieval-quality project note if one exists: record the engine, the case count, the recall@k / MRR numbers with the date as a recency marker, the top failure patterns with example notes, and the ranked fix hypotheses. This is the before-number every future retrieval change is measured against.

Measure, change one thing, measure again. That loop - not a guess about vector databases - is how retrieval actually improves.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Report the eval numbers exactly as the harness emits them - never round a miss into a hit or invent a recall figure. If the cases are few or the gold labels look weak, say so rather than overclaiming. See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
