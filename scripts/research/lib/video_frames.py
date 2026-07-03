"""Video download + scene-change frame extraction for the /youtube visual layer.

Ported from claude-watch (github.com/taoufik123-collab/claude-watch), which
extends claude-video (github.com/bradautomates/claude-video) by Bradley Bonanno.
Both MIT licensed. The idea: instead of sampling frames on a fixed timer, grab
one frame per actual scene change so visual substance (diagrams, on-screen code,
UI, b-roll) is captured for a multimodal reader.

Here the multimodal reader is Claude itself: this module only downloads the
video and writes keyframe JPGs to disk, then hands the frame paths + timestamps
back. Claude reads the frames with its own vision and writes the visual notes.
No extra vision-API call, no key needed beyond yt-dlp + ffmpeg on PATH.

Requires the `yt-dlp`, `ffmpeg`, and `ffprobe` binaries (brew install yt-dlp ffmpeg).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

MAX_FPS = 2.0
DEFAULT_RESOLUTION = 512
DEFAULT_SCENE_THRESHOLD = 0.3


class FrameError(RuntimeError):
    """Raised when download or frame extraction cannot proceed."""


def _require(binary: str) -> None:
    if shutil.which(binary) is None:
        raise FrameError(f"{binary} is not installed. Install with: brew install {binary}")


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #

def download_video(url: str, out_dir: Path) -> dict:
    """Download a video via yt-dlp (<=720p, merged to mp4). Returns paths + info.

    yt-dlp may exit non-zero when a subtitle variant fails (e.g. 429) even though
    the video downloaded fine, so success is judged by "video file present", not
    the exit code.
    """
    _require("yt-dlp")
    out_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(out_dir / "video.%(ext)s")

    cmd = [
        "yt-dlp",
        "-N", "8",
        "-f", "bv*[height<=720]+ba/b[height<=720]/bv+ba/b",
        "--merge-output-format", "mp4",
        "--write-info-json",
        "--no-playlist",
        "--ignore-errors",
        "-o", output_template,
        "--", url,
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    video = _pick_video(out_dir)
    if video is None:
        raise FrameError(f"yt-dlp did not produce a video file in {out_dir}")

    info: dict = {}
    info_path = out_dir / "video.info.json"
    if info_path.exists():
        try:
            raw = json.loads(info_path.read_text(encoding="utf-8"))
            info = {
                "title": raw.get("title"),
                "uploader": raw.get("uploader") or raw.get("channel"),
                "duration": raw.get("duration"),
            }
        except Exception:
            info = {}
    return {"video_path": str(video), "info": info}


def _pick_video(out_dir: Path) -> Path | None:
    for ext in (".mp4", ".mkv", ".webm", ".mov"):
        for candidate in out_dir.glob(f"video*{ext}"):
            return candidate
    return None


def is_url(source: str) -> bool:
    parsed = urlparse(source)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


# --------------------------------------------------------------------------- #
# Probe + frame budgeting
# --------------------------------------------------------------------------- #

def get_metadata(video_path: str) -> dict:
    _require("ffprobe")
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", str(Path(video_path).resolve())],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise FrameError(f"ffprobe failed: {result.stderr.strip()}")
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    vstream = next((s for s in streams if s.get("codec_type") == "video"), {})
    duration = float(fmt.get("duration") or vstream.get("duration") or 0)
    return {
        "duration_seconds": duration,
        "width": vstream.get("width"),
        "height": vstream.get("height"),
    }


def _clamp_fps(fps: float, duration_seconds: float, max_frames: int) -> float:
    fps = min(fps, MAX_FPS)
    # Never budget more frames than the cap allows.
    if duration_seconds > 0 and fps * duration_seconds > max_frames:
        fps = max_frames / duration_seconds
    return fps


def auto_fps(duration_seconds: float, max_frames: int) -> float:
    """Pick an fps that targets a frame budget by duration (short = dense, long = capped)."""
    if duration_seconds <= 0:
        return 1.0
    if duration_seconds <= 30:
        target = min(max_frames, max(12, int(round(duration_seconds))))
    elif duration_seconds <= 60:
        target = min(max_frames, 40)
    elif duration_seconds <= 180:
        target = min(max_frames, 60)
    elif duration_seconds <= 600:
        target = min(max_frames, 80)
    else:
        target = max_frames
    return _clamp_fps(target / duration_seconds, duration_seconds, max_frames)


# --------------------------------------------------------------------------- #
# Frame extraction
# --------------------------------------------------------------------------- #

def _clear_frames(out_dir: Path) -> None:
    for existing in out_dir.glob("frame_*.jpg"):
        existing.unlink()


def extract_uniform(
    video_path: str, out_dir: Path, fps: float,
    resolution: int = DEFAULT_RESOLUTION, max_frames: int = 100,
) -> list[dict]:
    _require("ffmpeg")
    out_dir.mkdir(parents=True, exist_ok=True)
    _clear_frames(out_dir)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(Path(video_path).resolve()),
        "-vf", f"fps={fps},scale={resolution}:-2",
        "-frames:v", str(max_frames),
        "-q:v", "4",
        str(out_dir / "frame_%04d.jpg"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise FrameError(f"ffmpeg frame extraction failed: {result.stderr.strip()}")
    frames = sorted(out_dir.glob("frame_*.jpg"))
    return [
        {"index": i, "timestamp_seconds": round(i / fps if fps > 0 else 0.0, 2),
         "path": str(p), "source": "uniform"}
        for i, p in enumerate(frames)
    ]


def extract_scene_change(
    video_path: str, out_dir: Path,
    scene_threshold: float = DEFAULT_SCENE_THRESHOLD,
    resolution: int = DEFAULT_RESOLUTION,
    max_frames: int = 100,
    uniform_fallback_min: int = 8,
) -> list[dict]:
    """One frame per detected shot. Falls back to uniform sampling when too few scenes.

    Uses ffmpeg's `select='gt(scene,T)'` filter - scene-change scores are in [0,1],
    higher = more visual difference. 0.3 catches hard cuts and most dissolves without
    firing on ordinary motion. Frame 0 is always emitted (the filter only fires on
    *changes*, so the opening shot would otherwise be missed). Static videos (screen
    recordings, long talking heads) yield few scenes, so we fall back to uniform
    sampling - sparse frames beat almost none.
    """
    _require("ffmpeg")
    out_dir.mkdir(parents=True, exist_ok=True)
    _clear_frames(out_dir)

    select_expr = f"eq(n\\,0)+gt(scene\\,{scene_threshold})"
    vf = f"select='{select_expr}',metadata=mode=print:file=-,scale={resolution}:-2"
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(Path(video_path).resolve()),
        "-vf", vf,
        "-vsync", "vfr",
        "-frames:v", str(max_frames),
        "-q:v", "4",
        str(out_dir / "frame_%04d.jpg"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise FrameError(f"ffmpeg scene-change extraction failed: {result.stderr.strip()}")

    pts_times: list[float] = []
    for stream in (result.stdout, result.stderr):
        for line in stream.splitlines():
            if "pts_time" in line:
                for tok in line.strip().split():
                    for sep in (":", "="):
                        if tok.startswith(f"pts_time{sep}"):
                            try:
                                pts_times.append(float(tok.split(sep, 1)[1]))
                            except ValueError:
                                pass

    frames = sorted(out_dir.glob("frame_*.jpg"))

    if len(frames) < uniform_fallback_min:
        for f in frames:
            f.unlink()
        duration = get_metadata(video_path)["duration_seconds"]
        fps = auto_fps(max(0.1, duration), max_frames=max_frames)
        return extract_uniform(video_path, out_dir, fps=fps,
                               resolution=resolution, max_frames=max_frames)

    if len(pts_times) < len(frames):
        pts_times += [0.0] * (len(frames) - len(pts_times))
    return [
        {"index": i, "timestamp_seconds": round(pts_times[i], 2),
         "path": str(p), "source": "scene-change"}
        for i, p in enumerate(frames)
    ]


def select_hero_frames(frames: list[dict], hook_end_seconds: float = 10.0,
                        max_hero: int = 4, min_hero: int = 3) -> list[dict]:
    """Pick 3-4 representative frames to embed in the note: an opening (hook) frame
    plus evenly-spaced picks across the video. Deterministic."""
    if not frames:
        return []
    chosen: list[int] = []

    def _add(idx: int) -> None:
        if 0 <= idx < len(frames) and idx not in chosen:
            chosen.append(idx)

    for i, f in enumerate(frames):
        if f["timestamp_seconds"] <= hook_end_seconds:
            _add(i)
            break

    if len(chosen) < min_hero:
        gap = max(1, len(frames) // max_hero)
        for i in range(0, len(frames), gap):
            _add(i)
            if len(chosen) >= max_hero:
                break

    return [frames[i] for i in sorted(set(chosen))[:max_hero]]
