"""Tunables for the free (key-less) research sources.

Deliberately separate from `config.py`: that module requires
OBSIDIAN_VAULT_PATH at import time (it is the save-to-vault config), whereas
the free sources only fetch and emit JSON, so they must be importable with no
vault configured at all (zero-config free mode, and CI).

No API keys live here - only the polite-pool contact email and rate/cache
tunables. Everything is optional and read from the environment (or the same
`~/.config/obsidian-second-brain/.env` the rest of the toolkit uses), with the
defaults below applied when unset.

Recognized environment variables (all optional):
  RESEARCH_CONTACT_EMAIL          polite-pool email for arXiv/CrossRef/OpenAlex User-Agent
  RESEARCH_CACHE_TTL_HOURS        source-result cache TTL (default 24)
  RESEARCH_SEARXNG_INSTANCES      comma-separated SearXNG base URLs (DuckDuckGo fallback)
  RESEARCH_ARXIV_SECONDS          arXiv politeness delay (default 3.0)
  RESEARCH_REDDIT_SECONDS         Reddit politeness delay (default 0.5)
  RESEARCH_SEMANTIC_SCHOLAR_SECONDS  Semantic Scholar politeness delay (default 3.0)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Load the same optional .env the paid config uses, but never require it.
try:
    from dotenv import load_dotenv

    _ENV_PATH = Path.home() / ".config" / "obsidian-second-brain" / ".env"
    load_dotenv(_ENV_PATH)
except Exception:
    pass


_DEFAULT_SEARXNG = [
    "https://searx.be",
    "https://search.brave4u.com",
    "https://priv.au",
]


@dataclass(frozen=True)
class Config:
    contact_email: str | None = None
    searxng_instances: list[str] = field(default_factory=lambda: list(_DEFAULT_SEARXNG))
    cache_ttl_hours: int = 24
    arxiv_seconds: float = 3.0
    reddit_seconds: float = 0.5
    semantic_scholar_seconds: float = 3.0


_CACHE: Config | None = None


def _env(name: str) -> str | None:
    val = os.environ.get(name, "").strip()
    return val or None


def load() -> Config:
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    instances_raw = _env("RESEARCH_SEARXNG_INSTANCES")
    instances = (
        [s.strip() for s in instances_raw.split(",") if s.strip()]
        if instances_raw
        else list(_DEFAULT_SEARXNG)
    )

    def _float(name: str, default: float) -> float:
        raw = _env(name)
        try:
            return float(raw) if raw is not None else default
        except ValueError:
            return default

    def _int(name: str, default: int) -> int:
        raw = _env(name)
        try:
            return int(raw) if raw is not None else default
        except ValueError:
            return default

    _CACHE = Config(
        contact_email=_env("RESEARCH_CONTACT_EMAIL"),
        searxng_instances=instances,
        cache_ttl_hours=_int("RESEARCH_CACHE_TTL_HOURS", 24),
        arxiv_seconds=_float("RESEARCH_ARXIV_SECONDS", 3.0),
        reddit_seconds=_float("RESEARCH_REDDIT_SECONDS", 0.5),
        semantic_scholar_seconds=_float("RESEARCH_SEMANTIC_SCHOLAR_SECONDS", 3.0),
    )
    return _CACHE


def get_contact_email() -> str | None:
    return load().contact_email


__all__ = ["Config", "load", "get_contact_email"]
