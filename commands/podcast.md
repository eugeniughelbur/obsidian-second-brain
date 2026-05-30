---
description: Extract metadata, transcript, and summary from a podcast episode, saved as an AI-first note in the vault
category: research
triggers_en: ["summarize this podcast", "podcast episode summary", "extract podcast", "what's in this episode"]
---

Use the obsidian-second-brain skill. Execute `/podcast [url]`:

1. Resolve the podcast URL from the user's argument. Accept any of:
   - Apple Podcasts episode URL (`https://podcasts.apple.com/.../id<show>?i=<episode>`)
   - Direct RSS feed URL (uses the latest episode unless `?episode=<guid>` selector is appended)
   - Direct RSS feed URL with `?episode=<guid-fragment-or-link-fragment>` selector

   If no input given, ask: "Which podcast episode? Paste the Apple Podcasts link or RSS feed URL." Spotify URLs are not supported (DRM blocks audio + transcript access). Surface this clearly if pasted.

2. Run the Python command from the repo root (`~/Projects/personal/obsidian-second-brain/`):
   ```bash
   uv run -m scripts.research.podcast_extract "<url>"
   ```

3. The script:
   - Resolves Apple Podcasts URLs to RSS via the free iTunes Lookup API (no key needed).
   - Parses the RSS feed, extracts episode metadata (title, show, host, published, duration, audio URL, show notes).
   - Tries to obtain a transcript in this order:
     1. **`<podcast:transcript>` tag** in the RSS feed (free, fast, high fidelity).
     2. **Whisper API**, only if `OPENAI_API_KEY` is set. Downloads audio (<=25 MB OpenAI per-file limit), transcribes via `whisper-1`. Approximate cost: $0.006/min.
     3. **Show-notes-only fallback**. If no transcript path works, summarizes from RSS show notes alone. Quality drops; Notable Quotes will be empty.
   - Sends transcript-or-shownotes to Grok for AI-first summarization.
   - Returns: TL;DR, Key Points, Notable Quotes, Themes & Topics, Guests & People Mentioned, Worth Following Up On.

4. Show the script output verbatim to the user.

5. **Default save behavior: saves automatically.** AI-first note written to `Research/Podcasts/YYYY-MM-DD — <episode-title-slug>.md` (em-dash separator, matches the existing `/youtube` and `/research` filename pattern). Frontmatter includes `show`, `host`, `episode-title`, `episode-url`, `feed-url`, `guid`, `published`, `duration`, `transcript-source` (one of `rss-transcript-tag` / `whisper-api` / `show-notes`), and tags.

6. Plain English triggers: "summarize this podcast", "what's in this episode", "transcribe this podcast", or just pasting an Apple Podcasts URL with a question about content.

7. If the podcast publishes neither a transcript tag nor usable show notes AND there's no `OPENAI_API_KEY`, the script will fail with a clear message. Surface it. Suggest the user either picks a podcast that publishes transcripts, or sets `OPENAI_API_KEY` for Whisper transcription.

8. If the user asks to research someone or something mentioned in the "Worth Following Up On" or "Guests & People Mentioned" section, route that to `/research [topic]` (or `/obsidian-person` if it's a vault-worthy contact).

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md`. That means: `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval, not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
