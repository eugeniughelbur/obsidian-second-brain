---
description: Vault-first source-grounded research via Gemini File Search. One command, no browser. The grounded parallel to /research-deep (which is open-web via Perplexity).
category: research
triggers_en: ["notebooklm", "research grounded", "ground research in vault", "ask my notebook", "source-grounded research"]
---

Use the obsidian-second-brain skill. Execute `/notebooklm [topic]`:

1. Resolve the topic from the user's argument. If no topic, ask: "What topic for source-grounded research?"

2. Run the Python command from the repo root (`~/Projects/personal/obsidian-second-brain/`):
   ```bash
   uv run -m scripts.research.notebooklm --topic "<topic>"
   ```

3. The script does the whole flow end-to-end:
   - Scans the vault for the top 12 relevant notes (same shape as `/research-deep` Phase 1).
   - Uploads them to a fresh Gemini File Search store.
   - Asks Gemini (default `gemini-2.5-pro`, override via `NOTEBOOKLM_MODEL` env) for a synthesis grounded against those sources.
   - Writes the AI-first synthesis to `Research/NotebookLM/YYYY-MM-DD - <slug>.md`.
   - Deletes the File Search store so nothing is left behind.
   - Emits a `<<<NOTEBOOKLM_PROPAGATION_PAYLOAD>>>` JSON block.

4. **After save, do the propagation step.** Same flow as `/research-deep`:
   - Parse the propagation payload.
   - Read the saved synthesis at `saved_note`.
   - Treat the synthesis as the "conversation context" input to `/obsidian-save`.
   - Run the standard `/obsidian-save` flow: spawn parallel subagents (People, Projects, Tasks, Decisions, Ideas) and update vault notes per any "Recommended next reads or angles" bullets if they map to entities or projects.
   - Link the new synthesis note from today's daily note.

5. Report back to the user: "Saved [[YYYY-MM-DD - <slug>]] to Research/NotebookLM/. Linked from today's daily note. Updated [[X]], created [[Y]]."

6. Plain English triggers: "notebooklm this", "ground research on X using my vault", "source-grounded research on X", "ask my own notes about X".

7. When to choose `/notebooklm` over `/research-deep`:
   - `/research-deep` (Perplexity + Grok): when you want OPEN-WEB + X-discourse coverage. Cost: $0.20-0.80.
   - `/notebooklm` (Gemini File Search): when you want answers GROUNDED IN your own vault. Cost: ~$0.01-0.05.
   - Run both for high-value topics. The web view and the grounded view rarely contradict, and the contradictions are where the insight is.

8. Configuration: requires `GEMINI_API_KEY` in `~/.config/obsidian-second-brain/.env`. Get one free at https://aistudio.google.com/apikey. Optional `NOTEBOOKLM_MODEL` override (default `gemini-2.5-pro`).

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md`. The saved synthesis at `Research/NotebookLM/YYYY-MM-DD - <slug>.md` follows the template baked into the script (preamble, frontmatter, vault-baseline links, response verbatim). Do not strip those.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.

**Why Gemini File Search and not the browser:** NotebookLM has no public API for personal Google accounts. Gemini File Search (generally available, plain API key, same Gemini model family) gives the same architectural shape: source-grounded retrieval, multi-document context, citation-style synthesis. One HTTP call, no manual paste step.

**Cost:** $0.15 per million tokens indexed, storage free, generation at standard Gemini token rates. For a 12-note vault bundle (~30K tokens), expect $0.01-0.05 per run.
