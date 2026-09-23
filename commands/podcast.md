---
description: Extract metadata, transcript, and summary from a podcast episode, saved as an AI-first note in the vault
category: research
triggers_en: ["summarize this podcast", "podcast episode summary", "extract podcast", "what's in this episode"]
triggers_de: ["diesen Podcast zusammenfassen", "Zusammenfassung der Podcastfolge", "Podcast auswerten", "was steckt in dieser Folge"]
triggers_es: ["resume este pódcast", "resumen del episodio", "extrae este pódcast", "qué dice este episodio"]
triggers_pt: ["resuma este podcast", "resumo de episódio de podcast", "extraia este podcast", "o que há neste episódio"]
triggers_zh: ["总结这期播客", "提取播客文字稿", "这期节目讲了什么", "把这期播客整理进知识库"]
---

Use the obsidian-second-brain skill. Execute `/podcast [url]`:

1. Resolve the podcast URL from the user's argument. Accept any of:
   - Apple Podcasts episode URL (`https://podcasts.apple.com/.../id<show>?i=<episode>`)
   - Spotify episode URL (`https://open.spotify.com/episode/<id>`) - Spotify's own audio is DRM-locked, so the script bridges it to the show's public RSS feed: it reads the episode title from Spotify's key-free oEmbed endpoint, finds that episode in Apple's index to get the feed URL, then pulls the episode from the open feed by title. Works for any show that also publishes an open feed (most do); fails clearly for Spotify-exclusive shows with no public RSS.
   - Direct RSS feed URL (uses the latest episode unless `?episode=<guid>` selector is appended)
   - Direct RSS feed URL with `?episode=<guid-fragment-or-link-fragment>` selector

   If no input given, ask: "Which podcast episode? Paste the Apple Podcasts, Spotify, or RSS feed URL."

2. Run the script from the skill root (its absolute path was given at session start as **Skill root**; substitute it for `SKILL_ROOT`):
   ```bash
   uv run --directory "SKILL_ROOT" -m scripts.research.podcast_extract "<url>"
   ```

3. The script:
   - Resolves Apple Podcasts URLs to RSS via the free iTunes Lookup API (no key needed).
   - Parses the RSS feed, extracts episode metadata (title, show, host, published, duration, audio URL, show notes).
   - Tries to obtain a transcript in this order:
     1. **`<podcast:transcript>` tag** in the RSS feed (free, fast, high fidelity).
     2. **Groq-hosted Whisper**, only if `GROQ_API_KEY` is set (free tier). Downloads audio, re-encodes it to 32kbps mono so episodes up to ~4.5h fit in Groq's 25MB per-request cap (longer episodes are split into chunks with overlap and stitched). No cost on the free tier, but the free tier also caps audio at 7,200 seconds per hour (as of 2026-08, console.groq.com): an episode longer than about 2h gets a 429 and falls through to the next step, and a second long episode within the same hour does too. Needs `ffmpeg` and `ffprobe` on PATH.
     3. **Whisper API**, only if `OPENAI_API_KEY` is set. Downloads audio (<=25 MB OpenAI per-file limit), transcribes via `whisper-1`. Approximate cost: $0.006/min.
     4. **Show-notes-only fallback**. If no transcript path works, summarizes from RSS show notes alone. Quality drops; Notable Quotes will be empty.
   - Sends transcript-or-shownotes for AI-first summarization: Gemini when `GEMINI_API_KEY` is set (free tier, 1M context), otherwise Grok. The transcript is capped at `PODCAST_TX_LIMIT` characters (default 480,000, about 120k tokens) with a truncation note if the episode is longer; on the Grok path that cap is a real cost, roughly $0.36 per 3h episode at grok-4 rates, so lower it there if that matters.
   - Returns: TL;DR, Key Points, Notable Quotes, Themes & Topics, Guests & People Mentioned, Worth Following Up On.

4. Show the script output verbatim to the user.

5. **Default save behavior: saves automatically.** AI-first note written to `Research/Podcasts/YYYY-MM-DD - <episode-title-slug>.md` (hyphen separator, matches the existing `/youtube` and `/research` filename pattern). Frontmatter includes `show`, `host`, `episode-title`, `episode-url`, `feed-url`, `guid`, `published`, `duration`, `transcript-source` (one of `rss-transcript-tag` / `groq-whisper-api` / `whisper-api` / `show-notes`), and tags.

6. Plain English triggers: "summarize this podcast", "what's in this episode", "transcribe this podcast", or just pasting an Apple Podcasts URL with a question about content.

7. If no transcript path works and the show notes are empty or too short, the script fails with a clear message (exit code 1). Surface it. Suggest the user either picks a podcast that publishes transcripts, or sets `GROQ_API_KEY` (free-tier Groq Whisper) or `OPENAI_API_KEY` (paid Whisper API) for audio transcription.

8. If the user asks to research someone or something mentioned in the "Worth Following Up On" or "Guests & People Mentioned" section, route that to `/research [topic]` (or `/obsidian-person` if it's a vault-worthy contact).

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md`. If that path does not resolve from your working directory, search upward for it; if you still cannot read it, say so before writing rather than producing a note that silently skips the rule. That means: `## For future agent` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future agent retrieval, not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
