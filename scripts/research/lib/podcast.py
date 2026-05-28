"""Podcast resolver + transcript fetcher.

Inputs accepted:
  - Apple Podcasts URL (https://podcasts.apple.com/.../id<show>?i=<episode>)
  - RSS feed URL pointing at a single episode <item> (uses first episode)
  - Direct RSS URL + ?episode=<guid-or-title-fragment>

Transcript priority:
  1. RSS <podcast:transcript> tag (free, fast)
  2. Whisper API via OPENAI_API_KEY (paid, ~$0.006/min)
  3. None - caller falls back to show-notes-only summary
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from typing import Any
from urllib.parse import urlparse, parse_qs

import requests

ITUNES_LOOKUP = "https://itunes.apple.com/lookup"
APPLE_RE = re.compile(r"podcasts\.apple\.com/.+/id(\d+)(?:\?i=(\d+))?", re.IGNORECASE)


def is_apple_url(s: str) -> bool:
    return bool(APPLE_RE.search(s))


def is_url(s: str) -> bool:
    try:
        u = urlparse(s)
        return u.scheme in ("http", "https") and bool(u.netloc)
    except Exception:
        return False


def resolve_apple_to_rss(apple_url: str) -> tuple[str, str | None]:
    """Resolve Apple Podcasts URL to (feed_url, episode_id_str_or_None) via free iTunes Lookup API."""
    m = APPLE_RE.search(apple_url)
    if not m:
        raise ValueError(f"Not a recognizable Apple Podcasts URL: {apple_url}")
    show_id, episode_id = m.group(1), m.group(2)
    resp = requests.get(ITUNES_LOOKUP, params={"id": show_id, "entity": "podcast"}, timeout=15)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        raise ValueError(f"iTunes lookup returned no results for show id {show_id}")
    feed_url = results[0].get("feedUrl")
    if not feed_url:
        raise ValueError(f"iTunes lookup did not return a feedUrl for show id {show_id}")
    return feed_url, episode_id


def parse_feed(feed_url: str, episode_id: str | None = None) -> dict[str, Any]:
    """Parse an RSS feed and return episode metadata + audio URL + show-notes + transcript-tag-url."""
    try:
        import feedparser
    except ImportError:
        raise RuntimeError(
            "feedparser is required. Install with: uv sync (or pip install feedparser)"
        )
    parsed = feedparser.parse(feed_url)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"Could not parse feed at {feed_url}: {parsed.bozo_exception}")

    show_title = (parsed.feed.get("title") or "").strip() or "(unknown show)"
    show_author = (parsed.feed.get("author") or parsed.feed.get("itunes_author") or "").strip()

    entry = _pick_entry(parsed.entries, episode_id)
    if entry is None:
        raise ValueError("No entries found in feed")

    audio_url = _entry_audio_url(entry)
    transcript_url = _entry_transcript_url(entry)
    duration = entry.get("itunes_duration") or ""
    published = entry.get("published") or entry.get("updated") or ""

    return {
        "show_title": show_title,
        "show_author": show_author,
        "episode_title": (entry.get("title") or "(untitled episode)").strip(),
        "episode_url": entry.get("link") or "",
        "guid": entry.get("id") or "",
        "published": published,
        "duration": duration,
        "audio_url": audio_url,
        "transcript_url": transcript_url,
        "show_notes": _entry_show_notes(entry),
    }


def _pick_entry(entries: list[Any], episode_id: str | None) -> Any | None:
    if not entries:
        return None
    if episode_id:
        for e in entries:
            if str(e.get("id", "")).endswith(episode_id) or episode_id in str(e.get("link", "")):
                return e
        print(
            f"[podcast: episode id '{episode_id}' not found in feed (feed may be paginated "
            f"and only serve recent episodes); falling back to most recent entry.]",
            file=sys.stderr,
        )
    return entries[0]


def _entry_audio_url(entry: Any) -> str | None:
    for enc in entry.get("enclosures") or []:
        url = enc.get("href") or enc.get("url")
        type_ = (enc.get("type") or "").lower()
        if url and ("audio" in type_ or url.endswith((".mp3", ".m4a", ".wav", ".ogg"))):
            return url
    return None


def _entry_transcript_url(entry: Any) -> str | None:
    """Look for <podcast:transcript> namespaced element. feedparser exposes as podcast_transcript."""
    pt = entry.get("podcast_transcript")
    if isinstance(pt, dict):
        return pt.get("url") or pt.get("href")
    if isinstance(pt, list) and pt:
        first = pt[0]
        if isinstance(first, dict):
            return first.get("url") or first.get("href")
    return None


def _entry_show_notes(entry: Any) -> str:
    candidates = [
        entry.get("content"),
        entry.get("summary"),
        entry.get("subtitle"),
        entry.get("description"),
    ]
    for c in candidates:
        if isinstance(c, list) and c:
            text = c[0].get("value") if isinstance(c[0], dict) else str(c[0])
        else:
            text = c if isinstance(c, str) else ""
        if text and text.strip():
            return _strip_html(text).strip()
    return ""


def _strip_html(s: str) -> str:
    s = re.sub(r"<script.*?>.*?</script>", " ", s, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r"<style.*?>.*?</style>", " ", s, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def fetch_transcript_tag(transcript_url: str) -> str | None:
    """Download a <podcast:transcript> resource. Supports text/plain, text/html, text/srt, text/vtt, JSON."""
    try:
        r = requests.get(transcript_url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"[podcast transcript-tag fetch failed: {type(e).__name__}: {e}]", file=sys.stderr)
        return None
    ctype = (r.headers.get("Content-Type") or "").lower()
    body = r.text
    if "json" in ctype or transcript_url.endswith(".json"):
        return _parse_json_transcript(body)
    if "vtt" in ctype or transcript_url.endswith(".vtt"):
        return _strip_vtt_srt(body)
    if "srt" in ctype or transcript_url.endswith(".srt"):
        return _strip_vtt_srt(body)
    if "html" in ctype:
        return _strip_html(body).strip()
    return body.strip()


def _parse_json_transcript(body: str) -> str | None:
    """Parse a JSON transcript body. Currently supports the Podcast Index
    `{"segments": [{"body": "..."}]}` schema. Other schemas (Deepgram,
    AssemblyAI, custom) are not supported and produce a stderr warning so
    the caller knows a JSON transcript was found but unreadable.
    """
    import json
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print("[podcast transcript-tag JSON: invalid JSON]", file=sys.stderr)
        return None
    if isinstance(data, dict) and "segments" in data:
        segments = data["segments"]
        joined = " ".join(s.get("body", "") for s in segments if s.get("body")).strip()
        if joined:
            return joined
        sample_keys: list[str] = []
        if isinstance(segments, list) and segments and isinstance(segments[0], dict):
            sample_keys = list(segments[0].keys())[:6]
        print(
            f"[podcast transcript-tag JSON: `segments` present but no `body` field "
            f"(segment keys: {sample_keys}). Likely Deepgram/AssemblyAI/custom schema. "
            f"Only Podcast Index `segments[].body` is supported in v1.]",
            file=sys.stderr,
        )
        return None
    keys = list(data.keys())[:5] if isinstance(data, dict) else type(data).__name__
    print(
        f"[podcast transcript-tag JSON: unsupported schema (top-level keys/type: {keys}). "
        f"Only Podcast Index `segments[].body` is supported in v1.]",
        file=sys.stderr,
    )
    return None


def _strip_vtt_srt(body: str) -> str:
    out = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith(("WEBVTT", "NOTE")):
            continue
        if "-->" in line or re.fullmatch(r"\d+", line):
            continue
        out.append(line)
    return " ".join(out).strip()


def transcribe_via_whisper(audio_url: str, max_bytes: int = 25 * 1024 * 1024) -> str | None:
    """Download episode audio and transcribe via OpenAI Whisper API. Returns None if no key or failure.

    25 MB is OpenAI's per-file limit. Many full episodes exceed it; we surface a clear error.
    """
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        print("[podcast whisper: openai package not installed]", file=sys.stderr)
        return None

    try:
        with requests.get(audio_url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            content_length = int(resp.headers.get("Content-Length", "0") or "0")
            if content_length and content_length > max_bytes:
                print(
                    f"[podcast whisper: audio is {content_length // (1024*1024)} MB, "
                    f"exceeds OpenAI {max_bytes // (1024*1024)} MB limit]",
                    file=sys.stderr,
                )
                return None
            suffix = _audio_suffix(audio_url)
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                bytes_written = 0
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    bytes_written += len(chunk)
                    if bytes_written > max_bytes:
                        tmp.close()
                        os.unlink(tmp.name)
                        print(
                            f"[podcast whisper: audio exceeds {max_bytes // (1024*1024)} MB while streaming]",
                            file=sys.stderr,
                        )
                        return None
                    tmp.write(chunk)
                tmp_path = tmp.name
    except Exception as e:
        print(f"[podcast whisper: audio download failed: {type(e).__name__}: {e}]", file=sys.stderr)
        return None

    try:
        client = OpenAI(api_key=key)
        with open(tmp_path, "rb") as f:
            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="text",
            )
        if isinstance(result, str):
            return result.strip()
        print(
            f"[podcast whisper: unexpected response type {type(result).__name__} "
            f"(expected str via response_format='text'); SDK contract may have changed.]",
            file=sys.stderr,
        )
        return None
    except Exception as e:
        print(f"[podcast whisper: transcription failed: {type(e).__name__}: {e}]", file=sys.stderr)
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _audio_suffix(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext in (".mp3", ".m4a", ".wav", ".ogg", ".mp4"):
        if path.endswith(ext):
            return ext
    return ".mp3"


def resolve_input(user_input: str) -> dict[str, Any]:
    """Top-level resolver: takes any user input, returns episode metadata + transcript-related fields."""
    s = user_input.strip()
    if not is_url(s):
        raise ValueError("Input must be a URL (Apple Podcasts URL or RSS feed URL)")

    if is_apple_url(s):
        feed_url, episode_id = resolve_apple_to_rss(s)
        episode = parse_feed(feed_url, episode_id=episode_id)
        episode["source_url"] = s
        episode["feed_url"] = feed_url
        return episode

    qs = parse_qs(urlparse(s).query)
    episode_id = (qs.get("episode") or [None])[0]
    feed_url = s.split("?")[0] if episode_id else s
    episode = parse_feed(feed_url, episode_id=episode_id)
    episode["source_url"] = s
    episode["feed_url"] = feed_url
    return episode
