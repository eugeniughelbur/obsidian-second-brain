"""HackerNews via Algolia search. Free, no key, no rate limit."""

from __future__ import annotations

from .. import cache, http
from ..source_config import load
from ..result import Result

ENDPOINT = "https://hn.algolia.com/api/v1/search"


class HackerNewsSource:
    name = "hackernews"

    def __init__(self, retries: int = 1) -> None:
        self._session = http.get_session(retries=retries, backoff=0.5)
        self._ttl = load().cache_ttl_hours

    def search(self, query: str, n: int = 10) -> list[Result]:
        cached = cache.get(self.name, query, ttl_hours=self._ttl)
        if cached is not None:
            return [Result(**r) for r in cached]

        params = {"query": query, "hitsPerPage": min(n, 50), "tags": "story"}
        try:
            r = self._session.get(ENDPOINT, params=params, timeout=http.DEFAULT_TIMEOUT)
            if r.status_code != 200:
                return []
            results = _parse(r.json())
            cache.put(self.name, query, results)
            return results
        except Exception:
            return []


def _parse(payload: dict) -> list[Result]:
    out: list[Result] = []
    for h in payload.get("hits", []):
        out.append(Result(
            source="hackernews",
            title=h.get("title") or "",
            url=h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
            snippet=(h.get("story_text") or "")[:280] or None,
            points=h.get("points"),
            comments=h.get("num_comments"),
            posted_at=h.get("created_at"),
        ))
    return out


__all__ = ["HackerNewsSource"]
