---
description: Extract transcript, metadata, and top comments from a YouTube video - summarized via Grok and saved to vault. Add --visual to also read the video's frames (scene detection)
category: research
triggers_en: ["summarize youtube", "youtube transcript", "extract video", "youtube to vault", "watch this video", "what's on screen in this video"]
triggers_es: ["resume este vídeo de youtube", "transcripción de youtube", "extrae este vídeo", "youtube al vault", "mira este vídeo", "qué se ve en este vídeo"]
---

Use the obsidian-second-brain skill. Execute `/youtube [url] [--visual]`:

1. Resolve the YouTube URL or video ID from the user's argument. Accept any of: full URL (`https://www.youtube.com/watch?v=...`), `https://youtu.be/...`, `https://www.youtube.com/shorts/...`, or just the 11-character video ID. If no input given, ask: "Which YouTube video?"

2. Run the Python command from the repo root (`~/Projects/personal/obsidian-second-brain/`):
   ```bash
   uv run -m scripts.research.youtube_extract "<url-or-id>"
   ```
   Add `--visual` when the user wants the video watched, not just transcribed (demos, whiteboards, slides, UI walkthroughs, b-roll, "what's on screen"). Optional `--max-frames N` caps how many frames are read (default 24):
   ```bash
   uv run -m scripts.research.youtube_extract "<url-or-id>" --visual
   ```

3. The script:
   - Extracts the transcript via `youtube-transcript-api` (free, no API key).
   - If `YOUTUBE_API_KEY` is set, also fetches title, channel, view/like counts, top comments. Otherwise skips metadata silently.
   - Sends the transcript (and optional comments) to Grok for AI-first summarization.
   - Returns: TL;DR, Key Points, Notable Quotes, Themes & Topics, Comment Sentiment, Worth Following Up On.
   - With `--visual`: downloads the video (yt-dlp, <=720p) and extracts one frame per scene change (ffmpeg scene detection, not a fixed timer), so visual substance is captured. Hero frames are copied into the vault and embedded in the note; the full keyframe set is left on disk for you to read. Requires `yt-dlp` and `ffmpeg` on PATH (`brew install yt-dlp ffmpeg`). If either is missing or download fails, the visual layer is skipped with a warning and the transcript summary still saves.

4. Show the script output verbatim to the user.

5. **Default save behavior: saves automatically.** AI-first note written to `Research/YouTube/YYYY-MM-DD - <video-title-slug>.md`. Frontmatter includes video ID, channel, view counts, `visual`, `frame-count`, etc. for future Dataview queries.

6. **If `--visual` was used:** the script prints a `FRAMES-FOR-CLAUDE` JSON block (to stderr) listing each extracted keyframe with its timestamp and local path, plus the saved note path. Do this:
   - Read each frame image with the read-files tool (they are local JPGs). This is your own vision doing the watching - there is no extra vision-API call.
   - Then edit the saved note: replace the `<!-- CLAUDE: ... -->` comment in the `## Visual notes` section with a concise, timestamp-keyed reading of what the frames add over the transcript: on-screen text, code, diagrams, slides, UI, demos, b-roll, scene transitions. Cross-reference the Summary; do not restate the audio.
   - Keep the `## Visual timeline` hero-frame embeds intact.
   - If `--max-frames` is high and reading every frame would be excessive, read the hero frames plus an even sample across the timeline, and say in the note that you sampled.

7. Plain English triggers: "summarize this YouTube video", "what's in this video", "extract this YouTube link", "transcribe this video", "watch this video", "what's on screen", or just pasting a YouTube URL with a question about content. When the ask is about what is *shown* (not just said), use `--visual`.

8. If the video has no captions (transcript unavailable) AND no metadata (no API key), the script will fail with a clear message - surface it. Suggest the user picks a different video, adds a `YOUTUBE_API_KEY`, or tries `--visual` (which can read the video even without captions).

9. If the user asks to research something mentioned in the "Worth Following Up On" section, route that to `/research [topic]`.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
