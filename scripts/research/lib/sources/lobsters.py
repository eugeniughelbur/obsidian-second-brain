"""Lobsters search. Free, no key."""

from __future__ import annotations

from .. import cache, http
from ..source_config import load
from ..result import Result

ENDPOINT = "https://lobste.rs/search.json"


class LobstersSource:
    name = "lobsters"

    def __init__(self, retries: int = 1) -> None:
        self._session = http.get_session(retries=retries, backoff=1.0)
        self._ttl = load().cache_ttl_hours

    def search(self, query: str, n: int = 10) -> list[Result]:
        cached = cache.get(self.name, query, ttl_hours=self._ttl)
        if cached is not None:
            return [Result(**r) for r in cached]

        params = {"q": query, "what": "stories", "order": "relevance"}
        try:
            r = self._session.get(ENDPOINT, params=params, timeout=http.DEFAULT_TIMEOUT)
            if r.status_code != 200:
                return []
            data = r.json()
            if isinstance(data, list):
                items = data[: min(n, 25)]
            elif isinstance(data, dict) and isinstance(data.get("stories"), list):
                items = data["stories"][: min(n, 25)]
            else:
                items = []
            results = [
                Result(
                    source="lobsters",
                    title=s.get("title") or "",
                    url=s.get("url") or s.get("short_id_url") or "",
                    points=s.get("score"),
                    comments=s.get("comment_count"),
                    posted_at=s.get("created_at"),
                    extra={"tags": s.get("tags")},
                )
                for s in items
            ]
            cache.put(self.name, query, results)
            return results
        except Exception:
            return []


__all__ = ["LobstersSource"]
