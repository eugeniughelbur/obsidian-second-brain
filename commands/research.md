---
description: Web research with citations - Perplexity Sonar when an API key is set, free key-less sources (Wikipedia, HackerNews, arXiv, Reddit, and more) otherwise. Deep dossier with summary, facts, timeline, players, contrarian views, open questions
category: research
triggers_en: ["research this", "look up", "find information about", "perplexity research"]
---

Use the obsidian-second-brain skill. Execute `/research [topic]`:

1. Resolve the topic from the user's argument. Multi-word topics fine ("AI memory tools", "vector databases for RAG"). If no topic, ask: "What topic should I research?"

2. Run the Python command from the repo root (`~/Projects/personal/obsidian-second-brain/`):
   ```bash
   uv run -m scripts.research.research "<topic>"
   ```
   The script auto-selects its mode: if `PERPLEXITY_API_KEY` is set it uses Perplexity Sonar (paid); otherwise it falls back to free, key-less sources. Pass `--free` to force free mode even when a key is set, or `--academic` (free mode only) to restrict to scholarly sources (arXiv, Semantic Scholar, OpenAlex, CrossRef).

3. Handle the output by mode:
   - **Paid mode** - the script prints a finished dossier (Summary, Key Facts with recency markers, Timeline, Key Players, Contrarian Views, Further Reading, Open Questions, Sources) and saves the AI-first note itself to `Research/Web/` plus a log line. Show the dossier verbatim, then surface the saved file path. Nothing else to do.
   - **Free mode** - the script prints a JSON block with `"mode": "free-sources"`, containing `results` (raw items per source: title, url, snippet/abstract, authors, year, points, comments), `stats`, and `warnings`. YOU synthesize the dossier from it:
     a. Read the JSON. If `stats.success` is false (fewer than 3 sources returned results), say so plainly and flag the thin coverage in Open Questions - do not pad.
     b. Write a dossier with the same structure as paid mode. Every Key Fact carries a recency marker and the source domain/URL it came from. Never invent facts to fill a section; if the sources are thin, the section is short or empty (see the anti-fabrication rule below).
     c. Save it yourself as an AI-first note at `Research/Web/YYYY-MM-DD - <slug>.md` per `references/ai-first-rules.md` (preamble, frontmatter with `type: research`, `ai-first: true`, a `sources` list of every result URL verbatim, tags). Append a one-line entry to the operation log (`Logs/YYYY-MM-DD.md` if it exists, else `log.md`).
     d. Show the dossier to the user and surface the saved path.

4. Plain English triggers: "research [topic]", "look up [topic]", "deep research on [topic]" (note: "do deep research" or "research deep" should route to `/research-deep` instead - the chained version), "find me info on [topic]".

5. If the user wants ALSO X discourse on the same topic, suggest running `/x-pulse [topic]` after this. If they want full vault-aware synthesis with propagation, suggest `/research-deep [topic]`.

6. Errors handled inside the script with auto-retry on transient failures. Surface fatal errors verbatim.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
