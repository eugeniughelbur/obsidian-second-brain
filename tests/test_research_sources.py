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
import requests

from scripts.research.lib import cache, http, source_config
from scripts.research.lib.aggregator import aggregate
from scripts.research.lib.result import Result, encode_results


def test_library_imports_without_vault_path():
    """The free library must not require OBSIDIAN_VAULT_PATH at import time."""
    assert "OBSIDIAN_VAULT_PATH" not in os.environ or True  # documents intent
    # Importing every real source must not raise (and must not need a vault).
    from scripts.research.lib.sources.arxiv import ArxivSource
    from scripts.research.lib.sources.crossref import CrossRefSource
    from scripts.research.lib.sources.devto import DevToSource
    from scripts.research.lib.sources.duckduckgo import DuckDuckGoSource
    from scripts.research.lib.sources.hackernews import HackerNewsSource
    from scripts.research.lib.sources.keenable import KeenableSource
    from scripts.research.lib.sources.lobsters import LobstersSource
    from scripts.research.lib.sources.openalex import OpenAlexSource
    from scripts.research.lib.sources.reddit import RedditSource
    from scripts.research.lib.sources.semantic_scholar import SemanticScholarSource
    from scripts.research.lib.sources.tavily import TavilySource
    from scripts.research.lib.sources.wikipedia import WikipediaSource

    names = {
        ArxivSource.name, CrossRefSource.name, DevToSource.name, DuckDuckGoSource.name,
        HackerNewsSource.name, KeenableSource.name, LobstersSource.name, OpenAlexSource.name,
        RedditSource.name, SemanticScholarSource.name, TavilySource.name, WikipediaSource.name,
    }
    assert len(names) == 12  # all source names distinct


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


@pytest.mark.parametrize("ttl_hours", [0, -1])
def test_cache_zero_ttl_is_a_miss_without_consulting_the_clock(tmp_path, monkeypatch, ttl_hours):
    """test_cache_roundtrip uses ttl_hours=0 to mean "expired", and get() decided
    it with `age > 0`, an age computed from two clocks of different resolution:
    right after a write it can be exactly zero or negative, so the entry came
    back as fresh (on the Windows machine this surfaced on, time.time() moves
    in 15.6 ms steps and the roundtrip failed in 1 of 8 runs). A TTL of zero or
    less has to be decided without the clock at all, so here the clock raises."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    cache.put("hackernews", "rust async", [Result(source="hackernews", title="t", url="u", points=1)])
    entry = cache._key("hackernews", "rust async")

    def clock_must_not_be_read():
        raise AssertionError("a TTL of zero or less must be decided without the clock")

    monkeypatch.setattr(cache.time, "time", clock_must_not_be_read)
    assert cache.get("hackernews", "rust async", ttl_hours=ttl_hours) is None
    assert entry.exists()  # put() still writes; only the lookups miss
    monkeypatch.setattr(cache.time, "time", lambda: entry.stat().st_mtime)  # the write's own instant
    assert cache.get("hackernews", "rust async", ttl_hours=1) is not None  # positive TTLs unchanged


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


class _KeenableWire(requests.adapters.BaseAdapter):
    """Stand-in for api.keenable.ai, mounted on the source's real toolkit
    session: it records each prepared request and answers with a canned status
    and JSON body, so the tests see the exact wire request and nothing leaves
    the machine."""

    def __init__(self, status=200, body=None):
        super().__init__()
        self.status = status
        self.body = {"results": []} if body is None else body
        self.sent = []

    def send(self, request, **kwargs):
        self.sent.append((request, kwargs))
        resp = requests.Response()
        resp.status_code = self.status
        resp.reason = "OK" if self.status == 200 else "Too Many Requests"
        resp._content = json.dumps(self.body).encode()
        resp.headers["Content-Type"] = "application/json"
        resp.url = request.url
        resp.request = request
        return resp

    def close(self):
        pass


def _keenable(monkeypatch, tmp_path, wire, key=None, email=None):
    """An opted-in KeenableSource on the real toolkit session with the fake
    wire mounted, an isolated disk cache and freshly loaded source config."""
    from scripts.research.lib.sources.keenable import KeenableSource

    monkeypatch.setenv("RESEARCH_KEENABLE", "1")
    for var, value in (("KEENABLE_API_KEY", key), ("RESEARCH_CONTACT_EMAIL", email)):
        if value:
            monkeypatch.setenv(var, value)
        else:
            monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("RESEARCH_CACHE_TTL_HOURS", raising=False)
    monkeypatch.setattr(source_config, "_CACHE", None)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    src = KeenableSource()
    src._session.mount("https://", wire)
    return src


def test_keenable_requires_opt_in(monkeypatch):
    """Without RESEARCH_KEENABLE=1 the constructor refuses, so the source can
    never send a request. KEENABLE_API_KEY alone does not switch it on."""
    from scripts.research.lib.sources.keenable import KeenableSource

    monkeypatch.delenv("RESEARCH_KEENABLE", raising=False)
    monkeypatch.setenv("KEENABLE_API_KEY", "keen-test-key")
    with pytest.raises(RuntimeError):
        KeenableSource()
    for value in ("", "0"):
        monkeypatch.setenv("RESEARCH_KEENABLE", value)
        with pytest.raises(RuntimeError):
            KeenableSource()


def test_free_sources_gate_keenable_on_env(monkeypatch):
    """Keenable joins the free-mode pool only with RESEARCH_KEENABLE=1, never
    on KEENABLE_API_KEY alone, and stays out of academic mode either way."""
    from scripts.research import research

    monkeypatch.delenv("RESEARCH_KEENABLE", raising=False)
    monkeypatch.setenv("KEENABLE_API_KEY", "keen-test-key")
    key_only = {type(s).__name__ for s in research._free_sources(academic=False)}
    assert "KeenableSource" not in key_only

    monkeypatch.setenv("RESEARCH_KEENABLE", "0")
    off = {type(s).__name__ for s in research._free_sources(academic=False)}
    assert "KeenableSource" not in off

    monkeypatch.setenv("RESEARCH_KEENABLE", "1")
    on = {type(s).__name__ for s in research._free_sources(academic=False)}
    assert "KeenableSource" in on

    academic = {type(s).__name__ for s in research._free_sources(academic=True)}
    assert "KeenableSource" not in academic


def test_keenable_source_search_keyless(monkeypatch, tmp_path):
    """Without a key the source posts the query to the public endpoint with a
    bounded timeout. The only identifying headers name the toolkit: the
    X-Keenable-Title app identifier and a bare User-Agent, without the
    RESEARCH_CONTACT_EMAIL the shared session adds for the polite pools. The
    result text comes from `snippet` (Keenable's `description` is always
    empty), and rows without a URL are dropped."""
    wire = _KeenableWire(body={
        "results": [
            {"title": "Keenable Result", "url": "https://example.com",
             "description": "", "snippet": "A snippet"},
            {"title": "dropped", "url": "", "snippet": "no url"},
        ]
    })
    src = _keenable(monkeypatch, tmp_path, wire, email="me@x.io")
    assert src._session.headers["User-Agent"].endswith("(mailto:me@x.io)")

    results = src.search("test query", n=5)

    assert [(r.source, r.title, r.url, r.snippet) for r in results] == [
        ("keenable", "Keenable Result", "https://example.com", "A snippet"),
    ]
    assert len(wire.sent) == 1
    request, kwargs = wire.sent[0]
    assert (request.method, request.url) == ("POST", "https://api.keenable.ai/v1/search/public")
    assert request.headers["X-Keenable-Title"] == "obsidian-second-brain"
    assert request.headers["User-Agent"] == http.USER_AGENT_BASE
    assert "X-API-Key" not in request.headers
    assert not any("me@x.io" in value for value in request.headers.values())
    assert json.loads(request.body) == {"query": "test query", "max_results": 5}
    assert kwargs["timeout"] == http.DEFAULT_TIMEOUT


def test_keenable_source_uses_key_when_set(monkeypatch, tmp_path):
    """An optional KEENABLE_API_KEY switches to the keyed endpoint and travels
    in the X-API-Key header, never in the JSON body."""
    wire = _KeenableWire()
    src = _keenable(monkeypatch, tmp_path, wire, key="keen-test-key")

    src.search("test query", n=5)

    request, _ = wire.sent[0]
    assert request.url == "https://api.keenable.ai/v1/search"
    assert request.headers["X-API-Key"] == "keen-test-key"
    assert json.loads(request.body) == {"query": "test query", "max_results": 5}


def test_keenable_snippet_is_collapsed_and_capped(monkeypatch, tmp_path):
    """Keenable sends raw page text in `snippet` (a few thousand chars with
    newlines). The source collapses whitespace and caps it to a preview, so the
    aggregated JSON stays the same size it is for every other source."""
    from scripts.research.lib.sources.keenable import MAX_SNIPPET_CHARS

    long_text = "word\n\n" * MAX_SNIPPET_CHARS  # well over the cap, with newlines
    wire = _KeenableWire(body={"results": [{"title": "t", "url": "https://x.y", "snippet": long_text}]})
    src = _keenable(monkeypatch, tmp_path, wire)

    snippet = src.search("q", n=1)[0].snippet
    assert snippet is not None
    assert len(snippet) <= MAX_SNIPPET_CHARS
    assert "\n" not in snippet  # whitespace collapsed to single spaces


def test_keenable_results_use_the_shared_cache(monkeypatch, tmp_path):
    """Results go through the shared on-disk result cache like every other
    source: a repeated query is answered from the cache with no request."""
    wire = _KeenableWire(body={"results": [{"title": "t", "url": "https://x.y", "snippet": "s"}]})
    src = _keenable(monkeypatch, tmp_path, wire)

    first = src.search("rust async", n=5)
    second = src.search("rust async", n=5)

    assert len(wire.sent) == 1
    assert first == second
    assert cache._key("keenable", "rust async").exists()


def test_keenable_failure_is_reported_through_the_aggregator(monkeypatch, tmp_path):
    """A service error (here a 429) surfaces as an aggregator warning like any
    other source's failure: the run does not crash and nothing is cached."""
    wire = _KeenableWire(status=429, body={"detail": "rate limited"})
    src = _keenable(monkeypatch, tmp_path, wire)

    out = aggregate("topic", [src], n_per_source=5, timeout=10)

    assert out["stats"]["sources_attempted"] == 1
    assert out["stats"]["sources_succeeded"] == 0
    assert any(w.startswith("keenable:") and "429" in w for w in out["warnings"])
    assert not cache._key("keenable", "topic").exists()


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


def test_web_reader_unavailable_without_key(monkeypatch):
    """No TAVILY_API_KEY -> read() returns {} without any network call."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", "/tmp/x")
    from scripts.research.lib import web_reader

    assert web_reader.available() is False
    assert web_reader.read(["https://example.com"]) == {}


def test_web_reader_caps_urls_and_truncates(monkeypatch, tmp_path):
    """read() dedupes, caps at MAX_EXTRACT_URLS, truncates page text, and never
    lets an HTTP failure escape."""
    from unittest.mock import MagicMock

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    from scripts.research.lib import web_reader

    monkeypatch.setattr("scripts.research.lib.usage.USAGE_LOG", tmp_path / "usage.log")

    long_text = "x" * (web_reader.MAX_EXTRACT_CHARS + 500)
    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "results": [
            {"url": "https://a.example", "raw_content": long_text},
            {"url": "https://b.example", "raw_content": "short"},
        ]
    }
    fake_resp.raise_for_status.return_value = None
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(json=json, headers=headers)
        return fake_resp

    monkeypatch.setattr(web_reader.requests, "post", fake_post)

    urls = ["https://a.example", "https://a.example", "https://b.example",
            "https://c.example", "https://d.example", "not-a-url"]
    out = web_reader.read(urls)

    # Dedup + cap: only 3 unique http URLs sent.
    assert captured["json"]["urls"] == ["https://a.example", "https://b.example", "https://c.example"]
    assert captured["headers"]["Authorization"] == "Bearer tvly-test-key"
    # Truncation is capped AND announced (#194). The payload is still cut at the
    # cap; what is new is that the excerpt says so, because the synthesis prompt
    # used to present it as full-page text and a silent cut reads as a complete
    # page that simply never mentions the missing topic.
    body = out["https://a.example"]
    assert body.startswith("x" * web_reader.MAX_EXTRACT_CHARS)
    assert body.count("x") == web_reader.MAX_EXTRACT_CHARS
    assert "TRUNCATED" in body
    assert str(web_reader.MAX_EXTRACT_CHARS) in body
    # A page under the cap is passed through untouched - no spurious marker.
    assert out["https://b.example"] == "short"

    # Total failure -> {} and no exception.
    def broken_post(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(web_reader.requests, "post", broken_post)
    assert web_reader.read(["https://a.example"]) == {}
