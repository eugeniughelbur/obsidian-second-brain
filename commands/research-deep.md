---
description: Vault-first deep research — scans vault, identifies gaps, fills via Perplexity + Grok, synthesizes a delta, then propagates updates across people/projects/ideas via /obsidian-save
category: research
---

Use the obsidian-second-brain skill. Execute `/research-deep [topic]`:

1. Resolve the topic from the user's argument. If no topic, ask: "What topic for deep research?"

2. Run the Python command from the repo root (`~/Projects/personal/obsidian-second-brain/`):
   ```bash
   uv run -m scripts.research.research_deep "<topic>"
   ```

3. The script runs a 4-phase pipeline:
   - **Phase 1** — vault scan: finds existing notes mentioning the topic (the baseline).
   - **Phase 2** — gap analysis: Perplexity sonar-pro identifies what's missing/stale and emits 3-5 targeted queries (each tagged `web` or `x`).
   - **Phase 3** — gap-fill: runs each query via Perplexity (web) or Grok+Live Search (X discourse).
   - **Phase 4** — synthesis: Perplexity sonar-deep-research produces a delta report (what's new, what's confirmed, contradictions, recommended vault updates, open questions).

   Show the synthesis body to the user verbatim.

4. **Save behavior: saves AND propagates.**
   - The script writes the synthesis to `Research/Deep/YYYY-MM-DD — <slug>.md` automatically (AI-first format).
   - Then it emits a JSON payload between `<<<RESEARCH_DEEP_PROPAGATION_PAYLOAD>>>` markers describing what to propagate.

5. **After the script finishes, do the propagation step:**
   - Parse the JSON payload from the script output.
   - Read the saved research note at `vault_baseline_notes` paths and the new research note path.
   - Treat the synthesis body as the "conversation context" input to `/obsidian-save`.
   - Run the standard `/obsidian-save` flow: spawn parallel subagents (People, Projects, Tasks, Decisions, Ideas) and update vault notes per the synthesis's "Recommended Vault Updates" bullets.
   - Apply the AI-first vault rule on every note created or updated (preamble, frontmatter, recency markers, wikilinks, sources).
   - Link the new research note from today's daily note.

6. After propagation: report back to the user a clean list — "Updated [[X]], created [[Y]], linked [[Z]] from today's daily note."

7. Plain English triggers: "do deep research on [topic]", "research properly [topic]", "vault-aware research on [topic]", "research and update the vault on [topic]".

8. If any phase fails (e.g. Grok unavailable), the script continues with what it has and flags the gap in the synthesis. Surface partial results — don't silently fail. The graceful degradation rule: a partial synthesis is better than no synthesis.

9. Cost note: this command makes multiple API calls (Perplexity + Grok). Typical run: $0.20-$0.80 depending on topic depth and gap count. The script logs Grok calls to the usage log automatically.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
