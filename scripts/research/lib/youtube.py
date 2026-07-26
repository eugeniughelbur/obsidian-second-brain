"""YouTube transcript + Data API client.

Transcripts work without an API key (youtube-transcript-api).
Metadata + comments require YOUTUBE_API_KEY (free tier of YouTube Data API v3).
"""

import re
from typing import Any

from .config import YOUTUBE_API_KEY


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


def get_transcript(video_id: str) -> str | None:
    """Return concatenated transcript text, or None if unavailable."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None
    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id)
        return " ".join(seg.text for seg in fetched.snippets if seg.text).strip()
    except Exception as e:
        print(f"[YouTube transcript unavailable: {type(e).__name__}: {e}]")
        return None


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
        print(f"[YouTube metadata error: {type(e).__name__}: {e}]")
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
        print(f"[YouTube comments error: {type(e).__name__}: {e}]")
        return []
