#!/usr/bin/env python3
"""Fetch a YouTube video's title, channel and transcript. No API key.

Usage:
    python youtube_transcript.py URL [--lang ko,en] [--out FILE]

- Metadata comes from YouTube's public oEmbed endpoint (title, channel).
- The transcript comes from youtube-transcript-api. Languages are tried in the
  order given (default: the configured vault language, then en). If none of
  them exists, the first available transcript is used, translated to the first
  preferred language when YouTube allows it, otherwise taken as is.
- With --out the transcript text (with [mm:ss] timestamps) is written to that
  file and stdout carries only the JSON metadata, so a long video does not
  flood the agent's context. Without --out the JSON includes the text.

Exit codes: 0 ok, 2 bad input, 3 no transcript available, 4 network/library error.
Network access is required (in Codex: sandbox_workspace_write.network_access).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import osb_env  # noqa: E402

_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})")


def video_id(url: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    m = _ID_RE.search(url)
    return m.group(1) if m else ""


def oembed(vid: str) -> dict:
    q = urllib.parse.urlencode({"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"})
    endpoint = f"https://www.youtube.com/oembed?{q}"
    try:
        try:
            # requests ships certifi; python.org builds on macOS often lack a CA
            # bundle for urllib. requests is a dependency of the transcript lib.
            import requests

            data = requests.get(endpoint, timeout=15).json()
        except ImportError:
            with urllib.request.urlopen(endpoint, timeout=15) as r:
                data = json.loads(r.read().decode("utf-8"))
        return {"title": data.get("title", ""), "channel": data.get("author_name", ""),
                "channel_url": data.get("author_url", "")}
    except Exception as exc:  # metadata is best effort; the transcript is the payload
        return {"title": "", "channel": "", "channel_url": "", "metadata_error": str(exc)}


def fmt_ts(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def fetch_transcript(vid: str, langs: list[str]):
    from youtube_transcript_api import NoTranscriptFound, YouTubeTranscriptApi

    listing = YouTubeTranscriptApi().list(vid)
    try:
        tr = listing.find_transcript(langs)
        translated = False
    except NoTranscriptFound:
        available = list(listing)
        if not available:
            raise
        tr = available[0]
        translated = False
        if tr.is_translatable and tr.language_code != langs[0]:
            try:
                tr = tr.translate(langs[0])
                translated = True
            except Exception:
                pass
    fetched = tr.fetch()
    lines = [f"[{fmt_ts(s.start)}] {s.text.strip()}" for s in fetched if s.text.strip()]
    return {
        "language": tr.language_code,
        "is_generated": bool(tr.is_generated),
        "translated": translated,
    }, "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("url")
    ap.add_argument("--lang", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    vid = video_id(args.url.strip())
    if not vid:
        print(json.dumps({"ok": False, "error": "not a YouTube URL or video id"}))
        return 2
    langs = [x.strip() for x in (args.lang or f"{osb_env.language()},en").split(",") if x.strip()]
    langs = list(dict.fromkeys(langs))

    result = {"ok": False, "video_id": vid, "url": f"https://www.youtube.com/watch?v={vid}"}
    result.update(oembed(vid))
    try:
        info, text = fetch_transcript(vid, langs)
    except ImportError:
        result["error"] = ("youtube-transcript-api is not installed in this Python. "
                           "Use the toolkit venv python printed by osb_env.py.")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 4
    except Exception as exc:
        name = type(exc).__name__
        result["error"] = f"{name}: {str(exc).strip().splitlines()[0] if str(exc).strip() else ''}"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        no_tx = name in {"NoTranscriptFound", "TranscriptsDisabled", "VideoUnavailable"}
        return 3 if no_tx else 4

    result.update(info, ok=True, chars=len(text))
    if args.out:
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        result["transcript_file"] = str(out)
    else:
        result["transcript"] = text
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
