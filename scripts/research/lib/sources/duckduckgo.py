"""DuckDuckGo HTML + SearXNG fallback. Free, no key.

DDG occasionally serves a CAPTCHA page; we detect by absence of results
in the HTML and fall through to SearXNG public instances.
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

from .. import cache, http
from ..source_config import load
from ..result import Result

DDG = "https://html.duckduckgo.com/html/"
RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>'
    r'.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL,
)


class DuckDuckGoSource:
    name = "duckduckgo"

    def __init__(self, retries: int = 1, searxng_instances: list[str] | None = None) -> None:
        self._session = http.get_session(retries=retries, backoff=1.0)
        cfg = load()
        self._ttl = cfg.cache_ttl_hours
        self._searxng = searxng_instances if searxng_instances is not None else cfg.searxng_instances

    def search(self, query: str, n: int = 10) -> list[Result]:
        cached = cache.get(self.name, query, ttl_hours=self._ttl)
        if cached is not None:
            return [Result(**r) for r in cached]

        results = self._try_ddg(query, n)
        if not results:
            results = self._try_searxng(query, n)
        cache.put(self.name, query, results)
        return results

    def _try_ddg(self, query: str, n: int) -> list[Result]:
        try:
            r = self._session.get(
                DDG,
                params={"q": query},
                timeout=http.DEFAULT_TIMEOUT,
                headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            if r.status_code != 200:
                return []
            results: list[Result] = []
            for m in list(RESULT_RE.finditer(r.text))[:n]:
                raw_url, title, snippet = m.group(1), m.group(2), m.group(3)
                final_url = _strip_ddg_redirect(raw_url)
                clean_snippet = re.sub(r"<[^>]+>", "", snippet).strip()
                results.append(Result(
                    source="duckduckgo",
                    title=unescape(title).strip(),
                    url=final_url,
                    snippet=unescape(clean_snippet) or None,
                ))
            return results
        except Exception:
            return []

    def _try_searxng(self, query: str, n: int) -> list[Result]:
        for inst in self._searxng:
            try:
                r = self._session.get(
                    f"{inst.rstrip('/')}/search",
                    params={"q": query, "format": "json"},
                    timeout=http.DEFAULT_TIMEOUT,
                )
                if r.status_code != 200:
                    continue
                payload = r.json()
                items = payload.get("results", [])[:n]
                return [
                    Result(
                        source="duckduckgo",  # report as ddg for consistency
                        title=i.get("title") or "",
                        url=i.get("url") or "",
                        snippet=i.get("content"),
                        extra={"engine": i.get("engine"), "via_searxng": inst},
                    )
                    for i in items
                ]
            except Exception:
                continue
        return []


def _strip_ddg_redirect(raw: str) -> str:
    """DDG wraps URLs in /l/?uddg=<encoded>. Unwrap."""
    if raw.startswith("//"):
        raw = "https:" + raw
    parsed = urlparse(raw)
    if "duckduckgo.com" in parsed.netloc and "uddg" in parsed.query:
        q = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(q)
    return raw


__all__ = ["DuckDuckGoSource"]
