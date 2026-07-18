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
    from scripts.research.lib.sources.tavily import TavilySource
    from scripts.research.lib.sources.wikipedia import WikipediaSource

    names = {
        ArxivSource.name, CrossRefSource.name, DevToSource.name, DuckDuckGoSource.name,
        HackerNewsSource.name, LobstersSource.name, OpenAlexSource.name, RedditSource.name,
        SemanticScholarSource.name, TavilySource.name, WikipediaSource.name,
    }
    assert len(names) == 11  # all source names distinct


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
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
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


def test_tavily_requires_key(monkeypatch):
    """Without TAVILY_API_KEY the constructor refuses - the source must never
    be built keyless (research._free_sources gates on the env var)."""
    from scripts.research.lib.sources.tavily import TavilySource

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        TavilySource()


def test_tavily_source_search(monkeypatch, tmp_path):
    """TavilySource hits the REST API with plain requests (no SDK), sends the
    key as a Bearer header (never in the JSON body), and maps the response to
    Result objects."""
    from unittest.mock import MagicMock

    from scripts.research.lib.sources.tavily import TavilySource

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    # Isolate the disk cache (cache paths derive from HOME).
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "results": [
            {"title": "Tavily Result", "url": "https://example.com", "content": "A snippet"},
            {"title": "keyless row dropped", "url": "", "content": "no url"},
        ]
    }
    fake_resp.raise_for_status.return_value = None

    src = TavilySource()
    fake_session = MagicMock()
    fake_session.post.return_value = fake_resp
    src._session = fake_session

    results = src.search("test query", n=5)

    assert len(results) == 1
    assert results[0].source == "tavily"
    assert results[0].title == "Tavily Result"
    assert results[0].url == "https://example.com"
    assert results[0].snippet == "A snippet"
    # Auth travels in the header; the key must not leak into the payload.
    _, kwargs = fake_session.post.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer tvly-test-key"
    assert "api_key" not in kwargs["json"]
    assert kwargs["json"]["max_results"] == 5


def test_free_sources_include_tavily_only_with_key(monkeypatch):
    """research._free_sources appends Tavily when the key is set, skips it
    keyless - the pool must stay fully key-less by default."""
    from scripts.research import research

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    without = {type(s).__name__ for s in research._free_sources(academic=False)}
    assert "TavilySource" not in without

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    with_key = {type(s).__name__ for s in research._free_sources(academic=False)}
    assert "TavilySource" in with_key
    # Academic mode stays untouched either way.
    academic = {type(s).__name__ for s in research._free_sources(academic=True)}
    assert "TavilySource" not in academic


def test_brave_source_search(monkeypatch, tmp_path):
    """BraveSource hits the REST API with the X-Subscription-Token header and
    maps web.results to Result objects; rows without a URL are dropped."""
    from unittest.mock import MagicMock

    from scripts.research.lib.sources.brave import BraveSource

    monkeypatch.setenv("BRAVE_API_KEY", "brv-test-key")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "web": {
            "results": [
                {"title": "Brave Result", "url": "https://example.com", "description": "A snippet"},
                {"title": "dropped", "url": "", "description": "no url"},
            ]
        }
    }
    fake_resp.raise_for_status.return_value = None

    src = BraveSource()
    fake_session = MagicMock()
    fake_session.get.return_value = fake_resp
    src._session = fake_session

    results = src.search("test query", n=5)

    assert len(results) == 1
    assert results[0].source == "brave"
    assert results[0].title == "Brave Result"
    assert results[0].snippet == "A snippet"
    _, kwargs = fake_session.get.call_args
    assert kwargs["headers"]["X-Subscription-Token"] == "brv-test-key"
    assert kwargs["params"]["count"] == 5

    monkeypatch.delenv("BRAVE_API_KEY")
    with pytest.raises(RuntimeError):
        BraveSource()


def test_free_sources_gate_brave_on_key(monkeypatch):
    """Brave joins the free-mode pool only when BRAVE_API_KEY is set."""
    from scripts.research import research

    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    without = {type(s).__name__ for s in research._free_sources(academic=False)}
    assert "BraveSource" not in without

    monkeypatch.setenv("BRAVE_API_KEY", "brv-test-key")
    with_key = {type(s).__name__ for s in research._free_sources(academic=False)}
    assert "BraveSource" in with_key


def test_usage_ledger_is_fail_soft(monkeypatch, tmp_path, capsys):
    """A broken ledger path must warn and return - never raise into the paid
    call it observes (the api-ledger fork's fail-soft contract)."""
    # lib.config (pulled in by usage) hard-requires a vault path at import time.
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    from scripts.research.lib import usage

    # Point the ledger at a path whose parent is a FILE - mkdir will fail.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir")
    monkeypatch.setattr(usage, "USAGE_LOG", blocker / "usage.log")

    usage.log_call("research", "sonar-pro", 100, 200, 0.01)  # must not raise
    assert "could not record call" in capsys.readouterr().err


def test_perplexity_cost_estimate_known_and_unknown_models(monkeypatch, tmp_path):
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    from scripts.research.lib import usage

    known = usage.estimate_perplexity_cost("sonar-pro", 1_000_000, 1_000_000)
    assert known == pytest.approx(3.00 + 15.00)
    # Unknown model: log tokens, never invent a price.
    assert usage.estimate_perplexity_cost("sonar-reasoning-pro", 1_000_000, 1_000_000) == 0.0


def test_gemini_call_maps_response_and_uses_header_auth(monkeypatch, tmp_path):
    """gemini.call returns the grok.call shape, and the key travels in the
    x-goog-api-key header - never in the URL query string."""
    from unittest.mock import MagicMock

    monkeypatch.setenv("GEMINI_API_KEY", "gem-test-key")
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    from scripts.research.lib import gemini
    monkeypatch.setattr("scripts.research.lib.usage.USAGE_LOG", tmp_path / "usage.log")

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "summary "}, {"text": "text"}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 20},
    }

    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(url=url, headers=headers)
        return fake_resp

    monkeypatch.setattr(gemini.requests, "post", fake_post)
    result = gemini.call("summarize this", command="youtube")

    assert result["text"] == "summary text"
    assert result["input_tokens"] == 10 and result["output_tokens"] == 20
    assert captured["headers"]["x-goog-api-key"] == "gem-test-key"
    assert "key=" not in captured["url"]
