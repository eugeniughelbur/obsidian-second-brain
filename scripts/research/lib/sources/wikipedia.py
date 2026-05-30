"""Wikipedia search + summary. Free; 200 req/s soft cap."""

from __future__ import annotations

import urllib.parse

from .. import cache, http
from ..source_config import load
from ..result import Result

SEARCH = "https://en.wikipedia.org/w/api.php"
SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"


class WikipediaSource:
    name = "wikipedia"

    def __init__(self, retries: int = 2) -> None:
        self._session = http.get_session(retries=retries, backoff=1.0)
        self._ttl = load().cache_ttl_hours

    def search(self, query: str, n: int = 5) -> list[Result]:
        cached = cache.get(self.name, query, ttl_hours=self._ttl)
        if cached is not None:
            return [Result(**r) for r in cached]

        try:
            r = self._session.get(
                SEARCH,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": n,
                    "format": "json",
                },
                timeout=http.DEFAULT_TIMEOUT,
            )
            if r.status_code != 200:
                return []
            titles = [h["title"] for h in r.json().get("query", {}).get("search", [])]
            results = []
            for t in titles[:n]:
                summ = self._summary(t)
                if summ:
                    results.append(summ)
            cache.put(self.name, query, results)
            return results
        except Exception:
            return []

    def _summary(self, title: str) -> Result | None:
        try:
            r = self._session.get(
                SUMMARY + urllib.parse.quote(title.replace(" ", "_"), safe=""),
                timeout=http.DEFAULT_TIMEOUT,
            )
            if r.status_code != 200:
                return None
            j = r.json()
            return Result(
                source="wikipedia",
                title=j.get("title") or title,
                url=j.get("content_urls", {}).get("desktop", {}).get("page", ""),
                snippet=j.get("extract"),
            )
        except Exception:
            return None


__all__ = ["WikipediaSource"]
