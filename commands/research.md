---
description: Web research with citations via Perplexity Sonar — deep dossier with summary, facts, timeline, players, contrarian views, open questions
category: research
---

Use the obsidian-second-brain skill. Execute `/research [topic]`:

1. Resolve the topic from the user's argument. Multi-word topics fine ("AI memory tools", "vector databases for RAG"). If no topic, ask: "What topic should I research?"

2. Run the Python command from the repo root (`~/Projects/personal/obsidian-second-brain/`):
   ```bash
   uv run -m scripts.research.research "<topic>"
   ```

3. The script returns a deep dossier (Summary, Key Facts with recency markers, Timeline, Key Players, Contrarian Views, Further Reading, Open Questions, Sources). Show the full output to the user verbatim.

4. **Default save behavior: saves automatically.** The script writes an AI-first note to `Research/Web/YYYY-MM-DD — <slug>.md` with full sources list in frontmatter. Appends to `log.md`.

5. After the dossier prints, surface the saved file path on stderr cleanly to the user.

6. Plain English triggers: "research [topic]", "look up [topic]", "deep research on [topic]" (note: "do deep research" or "research deep" should route to `/research-deep` instead — the chained version), "find me info on [topic]".

7. If the user wants ALSO X discourse on the same topic, suggest running `/x-pulse [topic]` after this. If they want full vault-aware synthesis with propagation, suggest `/research-deep [topic]`.

8. Errors handled inside the script with auto-retry on transient failures. Surface fatal errors verbatim.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
