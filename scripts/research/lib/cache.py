# scripts/research/lib/cache.py
"""File-based JSON cache for source results.

Cache layout: ~/.cache/obsidian-second-brain/research/<source>-<sha1(q)>.json
TTL is enforced via file mtime. Misses return None; callers fetch from network
and call put() to seed the cache.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any


def _cache_dir() -> Path:
    p = Path(os.path.expanduser("~/.cache/obsidian-second-brain/research"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _normalize(query: str) -> str:
    return " ".join(query.lower().split())


def _key(source: str, query: str) -> Path:
    sha = hashlib.sha1(_normalize(query).encode("utf-8")).hexdigest()[:16]
    return _cache_dir() / f"{source}-{sha}.json"


def get(source: str, query: str, ttl_hours: int) -> list[dict[str, Any]] | None:
    path = _key(source, query)
    if not path.exists():
        return None
    age_s = time.time() - path.stat().st_mtime
    if age_s > ttl_hours * 3600:
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def put(source: str, query: str, results: list[Any]) -> None:
    path = _key(source, query)
    try:
        # results may contain Result objects; pass through encode_results
        from .result import encode_results
        path.write_text(json.dumps(results, default=encode_results))
    except OSError:
        pass  # cache failure is non-fatal


def clear() -> int:
    """Remove all cache entries. Returns count removed."""
    count = 0
    for f in _cache_dir().glob("*.json"):
        try:
            f.unlink()
            count += 1
        except OSError:
            pass
    return count


__all__ = ["get", "put", "clear"]
