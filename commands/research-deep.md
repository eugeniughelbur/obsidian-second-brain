---
description: Vault-first deep research - scans the vault, fills gaps (Perplexity + Grok when keyed, free key-less sources otherwise), synthesizes a delta, then propagates updates across people/projects/ideas via /obsidian-save
category: research
triggers_en: ["deep research", "thorough research", "vault-first research", "research gaps"]
---

Use the obsidian-second-brain skill. Execute `/research-deep [topic]`:

1. Resolve the topic from the user's argument. If no topic, ask: "What topic for deep research?"

2. Run the Python command from the repo root (`~/Projects/personal/obsidian-second-brain/`):
   ```bash
   uv run -m scripts.research.research_deep "<topic>"
   ```
   The script auto-selects its mode: if `PERPLEXITY_API_KEY` is set it runs the paid pipeline below; otherwise it falls back to free, key-less sources. Pass `--free` to force free mode, or `--academic` (free mode only) to restrict to scholarly sources. Phase 1 (vault scan) is identical in both modes, so OBSIDIAN_VAULT_PATH must be set either way.

3. **Paid mode** - the script runs a 4-phase pipeline and finishes the work itself:
   - **Phase 1** - vault scan: finds existing notes mentioning the topic (the baseline).
   - **Phase 2** - gap analysis: Perplexity sonar-pro identifies what's missing/stale and emits 3-5 targeted queries (each tagged `web` or `x`).
   - **Phase 3** - gap-fill: runs each query via Perplexity (web) or Grok+Live Search (X discourse).
   - **Phase 4** - synthesis: Perplexity produces a delta report, the script saves it to `Research/Deep/YYYY-MM-DD - <slug>.md`, then emits a JSON payload between `<<<RESEARCH_DEEP_PROPAGATION_PAYLOAD>>>` markers.

   Show the synthesis body verbatim, then do the propagation step (step 5).

4. **Free mode** - the script does Phase 1 (vault scan) plus free-source aggregation and prints a JSON block with `"mode": "free-sources-deep"`, containing `vault_baseline_notes` (path, score, excerpt of what the vault already knew), `sources` (fresh external results), `stats`, `warnings`, and an `instruction`. YOU are the synthesizer:
   - Read the baseline excerpts and the source results. If `stats.success` is false (fewer than 3 sources returned), flag the thin coverage in Open Questions - do not pad.
   - Produce a delta with exactly these sections: What's New Since Vault Baseline, What's Confirmed, Contradictions / Updates Needed (name the `[[vault path]]`), Synthesis, Recommended Vault Updates, Open Questions. Every external claim carries a recency marker and source domain; every vault reference uses `[[wikilinks]]`. Never invent facts to fill a section.
   - Save it yourself to `Research/Deep/YYYY-MM-DD - <slug>.md` per `references/ai-first-rules.md` (preamble; frontmatter with `type: research-deep`, `ai-first: true`, `vault-baseline-notes`, and a `sources` list of every result URL verbatim).
   - Show the synthesis to the user, then do the propagation step (step 5).

5. **Propagation (both modes):**
   - In paid mode, parse the JSON payload; in free mode, use the note you just wrote and its synthesis.
   - Treat the synthesis body as the "conversation context" input to `/obsidian-save`.
   - Run the standard `/obsidian-save` flow: spawn parallel subagents (People, Projects, Tasks, Decisions, Ideas) and update vault notes per the synthesis's "Recommended Vault Updates" bullets.
   - Apply the AI-first vault rule on every note created or updated (preamble, frontmatter, recency markers, wikilinks, sources).
   - Link the new research note from today's daily note.
   - Then report back a clean list - "Updated [[X]], created [[Y]], linked [[Z]] from today's daily note."

6. Plain English triggers: "do deep research on [topic]", "research properly [topic]", "vault-aware research on [topic]", "research and update the vault on [topic]".

7. If any source/phase fails (Grok unavailable in paid mode, or a free source times out), the run continues with what it has and flags the gap in the synthesis. Surface partial results - don't silently fail. The graceful degradation rule: a partial synthesis is better than no synthesis.

8. Cost note: paid mode makes multiple API calls (Perplexity + Grok), typically $0.20-$0.80 depending on topic depth and gap count; the script logs Grok calls to the usage log automatically. Free mode costs nothing (key-less sources) - synthesis is done by the calling Claude.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
