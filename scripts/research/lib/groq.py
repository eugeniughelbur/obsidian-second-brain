# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""Groq-hosted Whisper transcription for the /podcast fallback chain.

Why Groq: free tier (7,200 audio-sec/hour ASH), whisper-large-v3-turbo, and a
single POST accepted per chunk - same provider family the repo already uses
via /x-read (openai-compatible endpoint). Used when an RSS housing feed has no
<podcast:transcript> tag and no OPENAI_API_KEY, or runs before it in the chain.

Design (binding redesign, 2026-08-30): DOWN_SAMPLE_FIRST. One 32kbps mono
re-encode pass puts ~4.5h of audio under Groq's 25MB per-request cap, so the
common case is one request with no seams. Only longer episodes hit the split
path, where bitrate is exactly known (we just wrote the file), so chunk
durations can be computed rather than guessed, and chunks are cut with real
~10s audio overlap so seam dedup has something to work with.

On ANY Groq HTTP failure at any chunk (429 ASH exhaustion, network, upstream)
we bail out entirely (return None) - the caller treats the whole episode as
Groq-unavailable and falls through to the OpenAI Whisper / show-notes chain.
Quota per-chunk retry/backoff is deliberately NOT built: episode-level
granularity keeps the fallback chain simple, avoids mixed-provider transcripts
breaking provenance, and the natural hourly reset makes long-running retries a
non-issue for /podcast's interactive usage pattern.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

from . import config

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3-turbo"

# Groq per-request cap (26,214,400 bytes, verified 2026-08-30 from live headers
# and console.groq.com). Re-encoded files larger than this must be split.
GROQ_MAX_BYTES = 25 * 1024 * 1024

# Re-encode target. Whisper resamples to 16kHz mono server-side anyway (standard
# ASR preprocessing), so we lose nothing by handing it a small mono file, and we
# gain: ~4.5h fits in one request, so the common case never hits the split path.
DOWNSAMPLE_BITRATE_KBPS = 32
DOWNSAMPLE_SAMPLE_HZ = 16000

# Deliberate audio overlap between split chunks. Gives seam dedup real audio
# context instead of a hard cut that can split a word in half with no recovery.
SPLIT_OVERLAP_SECONDS = 10


def is_groq_configured() -> bool:
    return bool(config.get_optional("GROQ_API_KEY", ""))


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess[bytes]:
    """Run a subprocess, raising on failure. Bounded, foreground, never detached.

    WHY: user-space constraint from a 2026-08-30 incident where long ffmpeg jobs
    lost their process group under a detached-run harness and left zombie tmp
    files. Keeping it foreground with a generous timeout keeps cleanup in-band.
    """
    return subprocess.run(cmd, capture_output=True, timeout=timeout, check=True)


def _ffprobe_duration_seconds(path: Path) -> float:
    """Return audio duration in seconds via ffprobe."""
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    return float(result.stdout.strip())


def _download_audio(audio_url: str, dest_path: Path, safe_fetch_url) -> None:
    """Stream-download episode audio to dest_path.

    Accepts the caller's safe_fetch_url helper (podcast.py's private/loopback
    guard) instead of importing it - keeps this module decoupled from podcast.py
    and lets tests substitute a stub.
    """
    bad = safe_fetch_url(audio_url)
    if bad:
        raise RuntimeError(f"refused unsafe audio url: {bad}")
    with requests.get(audio_url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        with dest_path.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                f.write(chunk)


def _downsample_to_mono_mp3(src: Path, dest: Path) -> None:
    """Re-encode src to 32kbps mono mp3. Real re-encode (not -c copy): the whole
    point is a predictable, small, single-bitrate file whose size can be checked
    exactly against the Groq cap.

    `-map_metadata -1` is load-bearing: some publishers ship multi-MB ID3 tags
    (cover art, Adobe XMP blobs - measured 18MB on a Lex Fridman episode), which
    would otherwise ride along and eat a large slice of the 25MB request cap,
    and would be duplicated into every split chunk.
    """
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(src),
            "-vn",
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-ac",
            "1",
            "-ar",
            str(DOWNSAMPLE_SAMPLE_HZ),
            "-b:a",
            f"{DOWNSAMPLE_BITRATE_KBPS}k",
            str(dest),
        ]
    )


def _split_reencoded_chunks(
    reencoded: Path, chunk_duration_seconds: float, workdir: Path
) -> list[Path]:
    """Split a re-encoded file into fixed-duration mp3 chunk files with overlap.

    Uses explicit `ffmpeg -ss <start> -t <dur> -c copy` (stream-copy from the
    already re-encoded file, where bitrate is exactly known) rather than the
    `-f segment` muxer, because we want deliberate overlap *between* chunks,
    which the segment muxer cannot produce. Chunks live (and die) inside workdir.
    """
    duration = _ffprobe_duration_seconds(reencoded)
    # Effective per-chunk advance minus the overlap that buys dedup context.
    effective = chunk_duration_seconds - SPLIT_OVERLAP_SECONDS
    chunks: list[Path] = []
    start = 0.0
    while start < duration:
        chunk_dur = min(chunk_duration_seconds, duration - start)
        out = workdir / f"chunk_{len(chunks):03d}.mp3"
        _run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-ss",
                f"{start:.3f}",
                "-t",
                f"{chunk_dur:.3f}",
                "-i",
                str(reencoded),
                "-c",
                "copy",
                str(out),
            ]
        )
        chunks.append(out)
        start += effective
    return chunks


def _groq_request(api_key: str, audio_path: Path, context: str) -> str:
    """Single Groq transcription POST. Raises on any failure - caller decides."""
    with audio_path.open("rb") as f:
        resp = requests.post(
            GROQ_TRANSCRIPTION_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (audio_path.name, f, "audio/mpeg")},
            data={"model": GROQ_MODEL, "response_format": "json"},
            timeout=300,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Groq HTTP {resp.status_code} ({context})")
    text = resp.json().get("text", "").strip()
    if not text:
        raise RuntimeError(f"Groq returned empty text ({context})")
    return text


_SEAM_CHARS = ".!?"  # sentence terminators for seam trimming


def _norm_sentence(s: str) -> str:
    """Loose key for sentence-level duplicate detection at seams."""
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _sentences(s: str) -> list[str]:
    """Split on sentence terminators, keeping the terminators attached."""
    parts = re.split(r"(?<=[.!?])\s+", s.strip())
    return [p for p in parts if p.strip()]


def _drop_leading_duplicate(prev_last: str, nxt: str) -> str:
    """Drop nxt's leading sentence when it duplicates prev_last.

    The 10s audio overlap means the sentence spanning the seam is transcribed in
    BOTH chunks. Trimming to sentence boundaries narrows this to at most one
    duplicated full sentence per seam; this removes it. Matching is on the
    normalized key (lowercase alphanumerics) because Whisper's punctuation/
    casing can differ between the two passes over the same audio.
    """
    sents = _sentences(nxt)
    if sents and _norm_sentence(sents[0]) == _norm_sentence(prev_last) and sents[0]:
        return " ".join(sents[1:]).strip()
    return nxt


def _trim_to_full_sentence(text: str, tail: bool) -> str:
    """Trim text to a full sentence boundary: drop the trailing partial sentence
    (tail=True) or the leading partial sentence (tail=False).

    WHY: cut points at chunk seams land mid-sentence. With deliberate audio
    overlap between chunks, the same sentence appears fully-formed in the peer
    chunk, so dropping the partial copy here loses nothing and removes the
    duplicate the overlap would otherwise produce. A text with no sentence
    terminators on the relevant side is returned unchanged - dropping the only
    content would be worse than a possible duplicate word.
    """
    s = text.strip()
    if not s:
        return s
    if tail:
        idx = max(s.rfind(c) for c in _SEAM_CHARS)
        return s[: idx + 1].strip() if idx >= 0 else s
    idx = min((i for i in (s.find(c) for c in _SEAM_CHARS) if i >= 0), default=-1)
    return s[idx + 1 :].strip() if idx >= 0 else s


def _join_chunk_texts(texts: list[str]) -> str:
    """Join chunk texts, deduplicating the overlap at each seam.

    For each seam, BOTH sides are trimmed to full-sentence boundaries: chunk i's
    tail (partial sentence dropped) and chunk i+1's head (partial sentence
    dropped). The ~10s audio overlap between chunks means the sentence spanning
    the cut is fully present in the peer chunk, so dropping both partials loses
    nothing while removing the duplicated words the overlap would produce.
    A chunk with no sentence terminator on the trimmed side is kept as-is -
    losing the only content would be worse than a possible duplicate.
    """
    if not texts:
        return ""
    trimmed = []
    prev_last_sentence = ""
    for i, t in enumerate(texts):
        s = t.strip()
        if i > 0:
            # Head-trim: the overlap region's partial lead-in is duplicated
            # (fully formed) at the tail of the previous chunk.
            s = _trim_to_full_sentence(s, tail=False)
            # The overlap can contain a whole sentence, which survives on both
            # sides of the seam after trimming - drop the repeated copy here.
            s = _drop_leading_duplicate(prev_last_sentence, s)
        if i < len(texts) - 1:
            # Tail-trim: the partial sentence at the cut is fully present in
            # the next chunk's head. The last chunk keeps its tail - the
            # episode's final words have no peer chunk to recover from.
            s = _trim_to_full_sentence(s, tail=True)
        if s:
            sent = _sentences(s)
            prev_last_sentence = sent[-1] if sent else s[-40:]
            trimmed.append(s)
    return " ".join(trimmed)


def _cleanup(paths: list[Path]) -> None:
    for p in paths:
        try:
            p.unlink()
        except OSError:
            pass


def transcribe_via_groq(audio_url: str, safe_fetch_url) -> str | None:
    """Transcribe an episode via Groq Whisper, downsample-first.

    Returns the full transcript text, or None on any failure (missing key,
    download/encode error, any Groq HTTP error at any chunk, empty result).
    Caller is expected to fall through to the next provider on None - exactly
    how transcribe_via_whisper in podcast.py behaves.

    Never logs the key. Never raises (returns None instead) so the /podcast
    chain degrade path stays uniform.
    """
    api_key = config.get_optional("GROQ_API_KEY", "")
    if not api_key:
        return None

    paths: list[Path] = []
    try:
        with tempfile.TemporaryDirectory(prefix="groq_whisper_") as tmpdir_str:
            tmp = Path(tmpdir_str)
            paths = [tmp]
            raw = tmp / "original_audio"
            reencoded = tmp / "reencoded.mp3"
            _download_audio(audio_url, raw, safe_fetch_url)
            duration = _ffprobe_duration_seconds(raw)
            print(
                f"[/podcast] Groq: downloaded audio ({duration / 60:.1f} min), "
                f"re-encoding to {DOWNSAMPLE_BITRATE_KBPS}kbps mono...",
                file=sys.stderr,
            )
            _downsample_to_mono_mp3(raw, reencoded)
            size = reencoded.stat().st_size
            print(f"[/podcast] Groq: re-encoded size {size} bytes", file=sys.stderr)

            if size > GROQ_MAX_BYTES:
                # Only for long (>~4.5h) episodes. Bitrate is exactly known
                # (we just wrote the file), so chunk math is exact, not heuristic.
                # Request-body overhead (multipart boundary etc.) is negligible
                # vs 25MB, but subtract a small margin anyway - mp3 frame
                # quantization can edge a chunk slightly over its nominal size.
                bytes_per_second = size / duration
                chunk_duration = (GROQ_MAX_BYTES * 0.98) / bytes_per_second
                print(
                    f"[/podcast] Groq: still over cap after re-encode; splitting into "
                    f"{chunk_duration:.0f}s chunks.",
                    file=sys.stderr,
                )
                chunks = _split_reencoded_chunks(reencoded, chunk_duration, tmp)
                texts = [
                    _groq_request(api_key, chunk, f"chunk {i + 1}")
                    for i, chunk in enumerate(chunks)
                ]
                return _join_chunk_texts(texts)

            # Common case: whole episode under cap → ONE Groq call, no seams.
            return _groq_request(api_key, reencoded, "full episode")
    except Exception as e:
        # Any failure (including a Groq 429 at any chunk) means this episode is
        # Groq-unavailable as a whole: caller falls through to OpenAI/show-notes.
        print(f"[podcast groq: {type(e).__name__}: {e}]", file=sys.stderr)
        return None
    finally:
        _cleanup(paths)