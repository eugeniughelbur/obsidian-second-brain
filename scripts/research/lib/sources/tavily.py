"""Tavily search source. Optional paid extra for the free-mode pool.

Joins the aggregation pool only when TAVILY_API_KEY is set (the caller checks;
see research._free_sources). Plain requests against the REST API - no
tavily-python SDK, so the dependency list stays unchanged and the test suite
never needs the vendor package installed.
"""

from __future__ import annotations

import os

from .. import cache, http
from ..result import Result
from ..source_config import load

API_URL = "https://api.tavily.com/search"


class TavilySource:
    name = "tavily"

    def __init__(self, retries: int = 1) -> None:
        key = os.environ.get("TAVILY_API_KEY", "").strip()
        if not key:
            raise RuntimeError("TavilySource requires TAVILY_API_KEY")
        self._key = key
        self._session = http.get_session(retries=retries, backoff=1.0)
        self._ttl = load().cache_ttl_hours

    def search(self, query: str, n: int = 10) -> list[Result]:
        cached = cache.get(self.name, query, ttl_hours=self._ttl)
        if cached is not None:
            return [Result(**r) for r in cached]

        resp = self._session.post(
            API_URL,
            json={"query": query, "max_results": min(n, 20)},
            headers={"Authorization": f"Bearer {self._key}"},
            timeout=http.DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        results = [
            Result(
                source=self.name,
                title=item.get("title") or "",
                url=item.get("url") or "",
                snippet=item.get("content") or None,
            )
            for item in data.get("results", [])
            if item.get("url")
        ]
        if results:
            cache.put(self.name, query, results)
        return results


__all__ = ["TavilySource"]
