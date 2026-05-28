#!/usr/bin/env python3
"""/podcast [url] - extract metadata, transcript, and summary from a podcast episode.

Inputs: Apple Podcasts URL OR RSS feed URL (with optional ?episode=<guid> selector).

Transcript priority:
  1. <podcast:transcript> tag in the RSS feed (free)
  2. Whisper API if OPENAI_API_KEY is set (paid, ~$0.006/min)
  3. Show-notes-only fallback (no audio fetch)

Then summarizes via Grok and saves an AI-first note to Research/Podcasts/.
Spotify URLs are not supported in v1 (DRM blocks audio access).
"""

import os
import sys
from datetime import datetime
from .lib import grok, podcast, vault

SUMMARIZE_PROMPT = """You are summarizing a podcast episode for a knowledge vault. The note will be read by future-Claude (an AI), not by a human. Optimize for AI retrieval.

SHOW: {show}
HOST: {host}
EPISODE: {episode}
PUBLISHED: {published}
DURATION: {duration}
TRANSCRIPT SOURCE: {transcript_source}

CONTENT (first {chars} chars):
\"\"\"
{content}
\"\"\"

Produce EXACTLY this structure (markdown):

## TL;DR
[2-3 sentences capturing the core thesis or value of the episode.]

## Key Points
- [Specific concrete claim, idea, or method from the episode]
- [...continue for 5-12 bullets covering the actual substance, not filler]

## Notable Quotes
- "[Verbatim quote]" - [speaker if identifiable; max 5 quotes]

## Themes & Topics
[2-3 sentences naming the broader themes / domains this episode touches]

## Guests & People Mentioned
- [[Person Name]] - short context. List every named person referenced; mark unknowns as [uncertain].

## Worth Following Up On
- [Specific things mentioned that would be worth a deeper /research call later]

Rules:
- Be specific. "Talks about AI" is useless to future-Claude. "Argues that LLM context windows over 1M tokens degrade reasoning quality after 200k tokens" is useful.
- Don't pad. If a section is genuinely thin, write one bullet and move on.
- Don't invent quotes. If TRANSCRIPT SOURCE is "show-notes" you have no transcript - leave Notable Quotes empty.
- Don't add commentary outside this structure.
- **Wikilinks are mandatory.** Wrap every named person, company, project, product, book, and named concept in `[[Name]]` so future-Claude can traverse the vault graph. Examples: `[[Sam Altman]]`, `[[OpenAI]]`, `[[GPT-5]]`, `[[Attention Is All You Need]]`. This applies in every section - TL;DR, Key Points, Notable Quotes (the speaker attribution), Themes, Guests & People Mentioned, Worth Following Up On.
"""


MIN_TRANSCRIPT_CHARS = 200


def _resolve_transcript(episode: dict) -> tuple[str | None, str]:
    """Return (transcript_text_or_None, source_label).

    Falls through silently to the next path only when the prior path is unavailable;
    every rejection (transcript tag too short, Whisper too short, JSON unparseable)
    is logged so the user knows why a costlier path is being attempted.
    """
    if episode.get("transcript_url"):
        print(f"[/podcast] Fetching transcript tag: {episode['transcript_url']}", file=sys.stderr)
        text = podcast.fetch_transcript_tag(episode["transcript_url"])
        if text is None:
            print(
                "[/podcast] Transcript tag returned no usable text "
                "(unsupported JSON schema, fetch error, or empty body) - falling through.",
                file=sys.stderr,
            )
        elif len(text) <= MIN_TRANSCRIPT_CHARS:
            print(
                f"[/podcast] Transcript tag content too short ({len(text)} chars, "
                f"minimum {MIN_TRANSCRIPT_CHARS}) - likely a stub or redirect page. Falling through.",
                file=sys.stderr,
            )
        else:
            return text, "rss-transcript-tag"

    if episode.get("audio_url"):
        if not os.environ.get("OPENAI_API_KEY", "").strip():
            print(
                "[/podcast] Skipping Whisper: OPENAI_API_KEY not set. "
                "Falling through to show-notes summary.",
                file=sys.stderr,
            )
        else:
            print("[/podcast] Trying Whisper API...", file=sys.stderr)
            text = podcast.transcribe_via_whisper(episode["audio_url"])
            if text and len(text) > MIN_TRANSCRIPT_CHARS:
                return text, "whisper-api"
            if text is not None:
                print(
                    f"[/podcast] Whisper returned content too short ({len(text)} chars) - falling through to show notes.",
                    file=sys.stderr,
                )
    else:
        print(
            "[/podcast] No audio enclosure in feed entry; skipping Whisper. "
            "Falling through to show-notes summary.",
            file=sys.stderr,
        )

    return None, "show-notes"


def main(argv: list[str]) -> int:
    if len(argv) < 2 or not argv[1].strip():
        print("Usage: /podcast <apple-podcasts-url-or-rss-url>", file=sys.stderr)
        return 2

    user_input = argv[1].strip()
    if "spotify.com" in user_input.lower():
        print(
            "❌ Spotify URLs aren't supported (DRM blocks audio + transcript access).\n"
            "   Try the Apple Podcasts URL or the show's RSS feed instead.",
            file=sys.stderr,
        )
        return 2

    print(f"[/podcast] Resolving {user_input}...", file=sys.stderr)
    try:
        episode = podcast.resolve_input(user_input)
    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2

    show = episode["show_title"]
    host = episode.get("show_author") or "(unknown)"
    title = episode["episode_title"]
    published = episode.get("published") or "(unknown date)"
    duration = episode.get("duration") or "(unknown)"
    show_notes = episode.get("show_notes") or ""

    transcript_text, transcript_source = _resolve_transcript(episode)

    if transcript_text:
        TX_LIMIT = 24000  # ~6k tokens
        content = transcript_text[:TX_LIMIT]
        if len(transcript_text) > TX_LIMIT:
            content += f"\n\n[Transcript truncated at {TX_LIMIT} chars from total {len(transcript_text)} chars]"
    else:
        if not show_notes or len(show_notes) < 100:
            print(
                "❌ No transcript available and show notes are empty/too short. "
                "Try a podcast that publishes <podcast:transcript> tags or set OPENAI_API_KEY for Whisper.",
                file=sys.stderr,
            )
            return 1
        content = f"(No transcript available; using show notes only)\n\n{show_notes[:8000]}"

    prompt = SUMMARIZE_PROMPT.format(
        show=show,
        host=host,
        episode=title,
        published=published,
        duration=duration,
        transcript_source=transcript_source,
        chars=len(content),
        content=content,
    )

    print(f"[/podcast] Summarizing via Grok (source: {transcript_source})...\n", file=sys.stderr)
    try:
        result = grok.call(prompt, command="podcast", max_output_tokens=3000)
    except Exception as e:
        print(f"\n❌ /podcast summarize failed: {e}", file=sys.stderr)
        return 1

    print(f"# {title}")
    print(f"**Show:** {show} · **Host:** {host} · **Published:** {published}")
    print(f"**URL:** {episode.get('episode_url') or episode['source_url']}\n")
    print(result["text"])

    # AI-first save
    now = datetime.now()
    preamble = (
        f"For future Claude: This note is a {transcript_source}-grounded summary of podcast episode "
        f"\"{title}\" from {show} ({host}, published {published}), processed on "
        f"{now.strftime('%Y-%m-%d %H:%M')}. Summarized via Grok. "
        f"Source label '{transcript_source}' indicates transcript provenance: "
        f"'rss-transcript-tag' (publisher-provided, high fidelity), 'whisper-api' "
        f"(Whisper transcription, may have errors on names), or 'show-notes' "
        f"(notes only, no transcript - quotes will be absent). Use Worth Following Up On bullets to spawn deeper research."
    )
    fm = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "type": "podcast",
        "show": show,
        "host": host,
        "episode-title": title,
        "episode-url": episode.get("episode_url") or "",
        "feed-url": episode.get("feed_url") or "",
        "source-url": episode["source_url"],
        "guid": episode.get("guid") or "",
        "published": published,
        "duration": duration,
        "transcript-source": transcript_source,
        "tags": ["research", "podcast", _slug_show_tag(show)],
        "cost-usd": round(result["cost_usd"], 4),
        "ai-first": True,
    }
    show_link = f"[[{show}]]" if show and show != "(unknown show)" else show
    host_link = f"[[{host}]]" if host and host != "(unknown)" else host
    note_body = (
        f"## For future Claude\n\n{preamble}\n\n"
        f"## Episode\n\n"
        f"- **Show:** {show_link}\n"
        f"- **Host:** {host_link}\n"
        f"- **Episode:** {title}\n"
        f"- **Published:** {published}\n"
        f"- **Duration:** {duration}\n"
        f"- **URL:** {episode.get('episode_url') or episode['source_url']}\n"
        f"- **Transcript source:** {transcript_source}\n\n"
        f"## Summary\n\n{result['text']}\n"
    )
    path = vault.write_note("podcast", title, fm, note_body)
    vault.print_save_links(path)
    vault.append_to_log(f"podcast on \"{title}\" - saved to {path.name}")
    tx_len = len(transcript_text) if transcript_text else 0
    print(
        f"---\n[cost: ${result['cost_usd']:.4f} · transcript: {tx_len} chars · source: {transcript_source}]",
        file=sys.stderr,
    )
    return 0


def _slug_show_tag(show: str) -> str:
    import re
    s = show.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s[:40] or "podcast"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
