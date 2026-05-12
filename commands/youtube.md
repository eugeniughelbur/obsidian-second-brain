---
description: Extract transcript, metadata, and top comments from a YouTube video — summarized via Grok and saved to vault
category: research
---

Use the obsidian-second-brain skill. Execute `/youtube [url]`:

1. Resolve the YouTube URL or video ID from the user's argument. Accept any of: full URL (`https://www.youtube.com/watch?v=...`), `https://youtu.be/...`, `https://www.youtube.com/shorts/...`, or just the 11-character video ID. If no input given, ask: "Which YouTube video?"

2. Run the Python command from the repo root (`~/Projects/personal/obsidian-second-brain/`):
   ```bash
   uv run -m scripts.research.youtube_extract "<url-or-id>"
   ```

3. The script:
   - Extracts the transcript via `youtube-transcript-api` (free, no API key).
   - If `YOUTUBE_API_KEY` is set, also fetches title, channel, view/like counts, top comments. Otherwise skips metadata silently.
   - Sends the transcript (and optional comments) to Grok for AI-first summarization.
   - Returns: TL;DR, Key Points, Notable Quotes, Themes & Topics, Comment Sentiment, Worth Following Up On.

4. Show the script output verbatim to the user.

5. **Default save behavior: saves automatically.** AI-first note written to `Research/YouTube/YYYY-MM-DD — <video-title-slug>.md`. Frontmatter includes video ID, channel, view counts, etc. for future Dataview queries.

6. Plain English triggers: "summarize this YouTube video", "what's in this video", "extract this YouTube link", "transcribe this video", or just pasting a YouTube URL with a question about content.

7. If the video has no captions (transcript unavailable) AND no metadata (no API key), the script will fail with a clear message — surface it. Suggest the user picks a different video or provides metadata manually.

8. If the user asks to research something mentioned in the "Worth Following Up On" section, route that to `/research [topic]`.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
