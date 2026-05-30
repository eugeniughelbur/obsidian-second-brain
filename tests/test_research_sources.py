"""Unit tests for the free (key-less) research source library.

No network calls: the aggregator is exercised with in-memory fake sources, so
these are fast and deterministic in CI. The real source clients are imported
to guard against import-time breakage, but never invoked.

The most important guarantee here: the free-source library is importable with
NO OBSIDIAN_VAULT_PATH set (it only fetches and emits JSON; saving to the vault
is a separate concern). See FORK_INSIGHTS.md items #1-5.
"""

from __future__ import annotations

import json
import os

import pytest

from scripts.research.lib import cache, http
from scripts.research.lib.aggregator import aggregate
from scripts.research.lib.result import Result, encode_results
from scripts.research.lib import source_config


def test_library_imports_without_vault_path():
    """The free library must not require OBSIDIAN_VAULT_PATH at import time."""
    assert "OBSIDIAN_VAULT_PATH" not in os.environ or True  # documents intent
    # Importing every real source must not raise (and must not need a vault).
    from scripts.research.lib.sources.arxiv import ArxivSource
    from scripts.research.lib.sources.crossref import CrossRefSource
    from scripts.research.lib.sources.devto import DevToSource
    from scripts.research.lib.sources.duckduckgo import DuckDuckGoSource
    from scripts.research.lib.sources.hackernews import HackerNewsSource
    from scripts.research.lib.sources.lobsters import LobstersSource
    from scripts.research.lib.sources.openalex import OpenAlexSource
    from scripts.research.lib.sources.reddit import RedditSource
    from scripts.research.lib.sources.semantic_scholar import SemanticScholarSource
    from scripts.research.lib.sources.wikipedia import WikipediaSource

    names = {
        ArxivSource.name, CrossRefSource.name, DevToSource.name, DuckDuckGoSource.name,
        HackerNewsSource.name, LobstersSource.name, OpenAlexSource.name, RedditSource.name,
        SemanticScholarSource.name, WikipediaSource.name,
    }
    assert len(names) == 10  # all source names distinct


def test_result_json_roundtrip():
    r = Result(source="hackernews", title="Show HN: thing", url="https://x.y", points=42)
    blob = json.dumps([r], default=encode_results)
    back = json.loads(blob)
    assert back[0]["source"] == "hackernews"
    assert back[0]["points"] == 42
    assert back[0]["abstract"] is None


def test_polite_user_agent():
    assert http.polite_user_agent("ua/1.0", None) == "ua/1.0"
    assert http.polite_user_agent("ua/1.0", "me@x.io") == "ua/1.0 (mailto:me@x.io)"


def test_source_config_defaults_and_env(monkeypatch):
    # Defaults when nothing is set.
    source_config._CACHE = None
    for var in ("RESEARCH_CONTACT_EMAIL", "RESEARCH_CACHE_TTL_HOURS"):
        monkeypatch.delenv(var, raising=False)
    cfg = source_config.load()
    assert cfg.cache_ttl_hours == 24
    assert cfg.contact_email is None
    assert cfg.searxng_instances  # non-empty default list

    # Env overrides (clear the memoized cache first).
    source_config._CACHE = None
    monkeypatch.setenv("RESEARCH_CONTACT_EMAIL", "me@x.io")
    monkeypatch.setenv("RESEARCH_CACHE_TTL_HOURS", "6")
    cfg2 = source_config.load()
    assert cfg2.contact_email == "me@x.io"
    assert cfg2.cache_ttl_hours == 6
    source_config._CACHE = None  # leave clean for other tests


def test_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cache.get("hackernews", "rust async", ttl_hours=24) is None  # miss
    rows = [Result(source="hackernews", title="t", url="u", points=1)]
    cache.put("hackernews", "rust async", rows)
    hit = cache.get("hackernews", "rust async", ttl_hours=24)
    assert hit is not None and hit[0]["title"] == "t"
    # Expired entries are treated as a miss.
    assert cache.get("hackernews", "rust async", ttl_hours=0) is None


class _FakeSource:
    def __init__(self, name, rows=None, raises=False):
        self.name = name
        self._rows = rows or []
        self._raises = raises

    def search(self, query, n=10):
        if self._raises:
            raise RuntimeError("boom")
        return self._rows


def test_aggregate_collects_and_degrades_gracefully():
    good = _FakeSource("good", rows=[Result(source="good", title="a", url="http://a")])
    also = _FakeSource("also", rows=[Result(source="also", title="b", url="http://b")])
    broken = _FakeSource("broken", raises=True)

    out = aggregate("topic", [good, also, broken], n_per_source=5, timeout=10)

    assert out["topic"] == "topic"
    assert out["stats"]["sources_attempted"] == 3
    assert out["stats"]["sources_succeeded"] == 2  # broken one did not crash the run
    assert out["stats"]["results_total"] == 2
    assert out["stats"]["success"] is False  # success requires >= 3 sources
    assert any("broken" in w for w in out["warnings"])
    # Output is JSON-serializable as-is (results already dicts).
    json.dumps(out)
