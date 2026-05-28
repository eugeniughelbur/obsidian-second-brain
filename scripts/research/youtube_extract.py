#!/usr/bin/env python3
"""/youtube [url] - extract transcript, metadata, and top comments from a YouTube video.

Transcript: free, no API key needed (youtube-transcript-api).
Metadata + comments: free, requires YOUTUBE_API_KEY (Data API v3).
Without YOUTUBE_API_KEY: transcript-only mode.

Then summarizes via Grok (cheap call, no live_search).
Default behavior: print to chat AND save AI-first note to Research/YouTube/.
"""

import sys
from datetime import datetime
from .lib import youtube, grok, vault

SUMMARIZE_PROMPT = """You are summarizing a YouTube video for a knowledge vault. The note will be read by future-Claude (an AI), not by a human. Optimize for AI retrieval.

VIDEO TITLE: {title}
CHANNEL: {channel}
PUBLISHED: {published}

TRANSCRIPT (first {tx_chars} chars):
\"\"\"
{transcript}
\"\"\"

{comments_section}

Produce EXACTLY this structure (markdown):

## TL;DR
[2-3 sentences capturing the core thesis or value of the video.]

## Key Points
- [Specific concrete claim, idea, or method from the video]
- [...continue for 5-12 bullets covering the actual substance, not filler]

## Notable Quotes
- "[Verbatim quote]" - [if you can locate it; max 5 quotes]

## Themes & Topics
[2-3 sentences naming the broader themes / domains this video touches]

## Comment Sentiment
[If comments were provided: 1-2 sentence summary of audience reaction. Note dominant praise, criticism, or question patterns. If no comments provided, write "No comments available."]

## Worth Following Up On
- [Specific things mentioned that would be worth a deeper /research call later]

Rules:
- Be specific. "Talks about AI" is useless to future-Claude. "Argues that LLM context windows over 1M tokens degrade reasoning quality after 200k tokens" is useful.
- Don't pad. If a section is genuinely thin, write one bullet and move on.
- Don't add commentary outside this structure.
"""


def main(argv: list[str]) -> int:
    if len(argv) < 2 or not argv[1].strip():
        print("Usage: /youtube <video-url-or-id>", file=sys.stderr)
        return 2

    url_or_id = argv[1].strip()
    try:
        video_id = youtube.parse_video_id(url_or_id)
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2

    print(f"[/youtube] Extracting video {video_id}...", file=sys.stderr)

    transcript = youtube.get_transcript(video_id)
    metadata = youtube.get_video_metadata(video_id)
    comments = youtube.get_top_comments(video_id, max_results=15)

    if not transcript and not metadata:
        print("❌ Could not fetch transcript or metadata. Is the video public and does it have captions?", file=sys.stderr)
        return 1

    title = (metadata or {}).get("title") or f"Video {video_id}"
    channel = (metadata or {}).get("channel") or "(unknown channel)"
    published = (metadata or {}).get("published_at") or "(unknown date)"

    if transcript:
        TX_LIMIT = 24000  # ~6k tokens - plenty for grok-4 context
        tx_truncated = transcript[:TX_LIMIT]
        tx_note = "" if len(transcript) <= TX_LIMIT else f"\n\n[Transcript truncated at {TX_LIMIT} chars from total {len(transcript)} chars]"
    else:
        tx_truncated = "(transcript not available)"
        tx_note = ""

    comments_section = ""
    if comments:
        comments_section = "TOP COMMENTS (relevance order):\n"
        for c in comments[:15]:
            comments_section += f"- {c['author']} ({c['like_count']} 👍): {c['text'][:200]}\n"

    prompt = SUMMARIZE_PROMPT.format(
        title=title,
        channel=channel,
        published=published,
        tx_chars=len(tx_truncated),
        transcript=tx_truncated + tx_note,
        comments_section=comments_section,
    )

    print(f"[/youtube] Summarizing via Grok...\n", file=sys.stderr)
    try:
        result = grok.call(prompt, command="youtube", max_output_tokens=3000)
    except Exception as e:
        print(f"\n❌ /youtube summarize failed: {e}", file=sys.stderr)
        return 1

    print(f"# {title}")
    print(f"**Channel:** {channel} · **Published:** {published}")
    print(f"**URL:** https://www.youtube.com/watch?v={video_id}\n")
    print(result["text"])

    # AI-first save
    now = datetime.now()
    preamble = (
        f"For future Claude: This note is a transcript-grounded summary of YouTube video \"{title}\" "
        f"by {channel} (published {published}), processed on {now.strftime('%Y-%m-%d %H:%M')}. "
        f"Transcript was extracted via youtube-transcript-api and summarized via Grok. "
        f"Quotes are sourced from the transcript verbatim where attributed. Use Worth Following Up On bullets to spawn deeper research."
    )
    fm = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "type": "youtube",
        "video-id": video_id,
        "video-url": f"https://www.youtube.com/watch?v={video_id}",
        "title": title,
        "channel": channel,
        "channel-id": (metadata or {}).get("channel_id", ""),
        "published": published,
        "view-count": (metadata or {}).get("view_count"),
        "like-count": (metadata or {}).get("like_count"),
        "comment-count": (metadata or {}).get("comment_count"),
        "duration": (metadata or {}).get("duration"),
        "tags": ["research", "youtube"] + ((metadata or {}).get("tags") or [])[:5],
        "cost-usd": round(result["cost_usd"], 4),
        "ai-first": True,
    }
    note_body = (
        f"## For future Claude\n\n{preamble}\n\n"
        f"## Video\n\n"
        f"- **Title:** {title}\n"
        f"- **Channel:** {channel}\n"
        f"- **Published:** {published}\n"
        f"- **URL:** https://www.youtube.com/watch?v={video_id}\n\n"
        f"## Summary\n\n{result['text']}\n"
    )
    path = vault.write_note("youtube", title, fm, note_body)
    vault.print_save_links(path)
    vault.append_to_log(f"youtube on \"{title}\" - saved to {path.name}")
    print(
        f"---\n[cost: ${result['cost_usd']:.4f} · transcript: {len(transcript) if transcript else 0} chars · comments: {len(comments)}]",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
