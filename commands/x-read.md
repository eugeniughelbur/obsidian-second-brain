---
description: Deep-read an X (Twitter) post via Grok + Live Search — verbatim post, thread, TL;DR, claims, reply sentiment, voices to watch
category: research
---

Use the obsidian-second-brain skill. Execute `/x-read [url]`:

1. Resolve the URL from the user's argument. If no URL was given, ask: "Which X post URL?" Accept any URL containing `x.com/` or `twitter.com/`.

2. Run the Python command from the repo root (`~/Projects/personal/obsidian-second-brain/`):
   ```bash
   uv run -m scripts.research.x_read "<url>"
   ```

3. The script prints a structured analysis (ORIGINAL POST, THREAD, TL;DR, KEY CLAIMS, REPLY SENTIMENT, NOTABLE COUNTER-ARGUMENTS, VOICES TO WATCH) and a one-line cost summary on stderr. Show the analysis to the user verbatim — don't paraphrase or summarize.

4. **Default save behavior: chat only.** Do NOT save the analysis to the vault automatically. The user must ask explicitly ("save this", "save to vault", "/obsidian-save") for it to be archived.

5. If the user asks to save: write an AI-first note to `Research/X-reads/YYYY-MM-DD — <slug>.md` in the vault, following the AI-first vault rule (Section 0 of `_CLAUDE.md`):
   - Frontmatter: `date`, `time`, `type: x-read`, `post-url`, `post-author` (if known), `key-claims` (list), `tags`, `related-people` (wikilinks for any @ handles that map to known people in the vault), `cost-usd`
   - Body starts with **For future Claude:** preamble (2-3 sentences summarizing what this post is about and why it was saved)
   - Then the full structured analysis from the script

6. Plain English triggers that route to this command: "read this tweet", "read this X post", "what's in this tweet", "analyze this X link" — when followed by a URL.

7. If the script fails with a clear error (missing key, network down), surface the error message verbatim. The script handles retry on transient errors automatically.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
