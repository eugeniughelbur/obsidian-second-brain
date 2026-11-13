# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""YouTube transcript + Data API client.

Transcripts work without an API key (youtube-transcript-api).
Metadata + comments require YOUTUBE_API_KEY (free tier of YouTube Data API v3).
"""

import re
from typing import Any

from .config import YOUTUBE_API_KEY, get_optional

_KEY_PARAM = re.compile(r"(?i)\b(key|api_key|apikey|access_token)=[^&\s\"'<>]+")


def _api_error_summary(e: Exception) -> str:
    """A log-safe one-line summary of a Data API failure.

    googleapiclient's HttpError renders the full request URL, and that URL
    carries the API key as a query parameter. Report only the HTTP status and
    reason when the error has them; otherwise redact key-like parameters from
    the message before it is printed.
    """
    resp = getattr(e, "resp", None)
    status = getattr(resp, "status", None) if resp is not None else None
    if status is not None:
        reason = getattr(resp, "reason", None) or ""
        return f"{type(e).__name__}: HTTP {status} {reason}".rstrip()
    message = _KEY_PARAM.sub(r"\1=REDACTED", str(e))
    return f"{type(e).__name__}: {message}"


def parse_video_id(url_or_id: str) -> str:
    s = url_or_id.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, s)
        if m:
            return m.group(1)
    raise ValueError(f"Could not extract YouTube video ID from: {url_or_id}")


def _transcript_languages() -> list[str]:
    """Preferred transcript languages, from TRANSCRIPT_LANGUAGES (comma-separated,
    e.g. "ja,en"). Read per call, not at import, so long-lived callers and tests
    can change it."""
    raw = get_optional("TRANSCRIPT_LANGUAGES", "en")
    return [lang.strip() for lang in raw.split(",") if lang.strip()]


def get_transcript(video_id: str) -> str | None:
    """Return concatenated transcript text, or None if unavailable.

    Tries TRANSCRIPT_LANGUAGES in order, then falls back to whatever language
    the video actually has. A preference miss is not "no captions" (issue
    #210): the old call used youtube-transcript-api's ('en',) default, so every
    non-English video looked caption-less even when its transcript was one
    argument away."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None
    api = YouTubeTranscriptApi()
    try:
        fetched = api.fetch(video_id, languages=_transcript_languages())
    except Exception as pref_err:
        try:
            first = next(iter(api.list(video_id)))
            print(f"[YouTube transcript: none of the preferred languages "
                  f"({','.join(_transcript_languages())}) available; using "
                  f"'{getattr(first, 'language_code', '?')}']")
            fetched = first.fetch()
        except Exception:
            print(f"[YouTube transcript unavailable: {type(pref_err).__name__}: {pref_err}]")
            return None
    return " ".join(seg.text for seg in fetched.snippets if seg.text).strip()


def get_video_metadata(video_id: str) -> dict[str, Any] | None:
    """Returns title, channel, published date, view/like/comment counts. None if no API key or error."""
    key = YOUTUBE_API_KEY()
    if not key:
        return None
    try:
        # An explicit transport timeout. Without one googleapiclient falls back to
        # httplib2's default of none, so a slow (not down) Data API blocks the whole
        # /youtube command - including the plain non-visual path - with no bound and
        # no way for the caller to recover. Matches lib/http.py's DEFAULT_TIMEOUT.
        import httplib2
        from googleapiclient.discovery import build
        yt = build("youtube", "v3", developerKey=key, cache_discovery=False,
                   http=httplib2.Http(timeout=15))
        resp = yt.videos().list(part="snippet,statistics,contentDetails", id=video_id).execute()
        items = resp.get("items", [])
        if not items:
            return None
        item = items[0]
        sn = item.get("snippet", {})
        st = item.get("statistics", {})
        return {
            "title": sn.get("title"),
            "channel": sn.get("channelTitle"),
            "channel_id": sn.get("channelId"),
            "published_at": sn.get("publishedAt"),
            "description": sn.get("description", "")[:500],
            "tags": sn.get("tags", []),
            "duration": item.get("contentDetails", {}).get("duration"),
            "view_count": int(st.get("viewCount", 0)),
            "like_count": int(st.get("likeCount", 0)) if "likeCount" in st else None,
            "comment_count": int(st.get("commentCount", 0)) if "commentCount" in st else None,
        }
    except Exception as e:
        print(f"[YouTube metadata error: {_api_error_summary(e)}]")
        return None


def get_top_comments(video_id: str, max_results: int = 20) -> list[dict[str, Any]]:
    """Return top-rated comments. Empty list if no API key or comments disabled."""
    key = YOUTUBE_API_KEY()
    if not key:
        return []
    try:
        # An explicit transport timeout. Without one googleapiclient falls back to
        # httplib2's default of none, so a slow (not down) Data API blocks the whole
        # /youtube command - including the plain non-visual path - with no bound and
        # no way for the caller to recover. Matches lib/http.py's DEFAULT_TIMEOUT.
        import httplib2
        from googleapiclient.discovery import build
        yt = build("youtube", "v3", developerKey=key, cache_discovery=False,
                   http=httplib2.Http(timeout=15))
        resp = yt.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=min(max_results, 100),
            order="relevance",
            textFormat="plainText",
        ).execute()
        out = []
        for thread in resp.get("items", []):
            top = thread["snippet"]["topLevelComment"]["snippet"]
            out.append({
                "author": top.get("authorDisplayName"),
                "text": top.get("textDisplay"),
                "like_count": top.get("likeCount", 0),
                "published_at": top.get("publishedAt"),
            })
        return out
    except Exception as e:
        print(f"[YouTube comments error: {_api_error_summary(e)}]")
        return []
