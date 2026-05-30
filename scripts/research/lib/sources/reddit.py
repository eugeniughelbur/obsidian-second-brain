"""Reddit search.json. Free, no key; needs realistic User-Agent."""

from __future__ import annotations

import time

from .. import cache, http
from ..source_config import load
from ..result import Result

ENDPOINT = "https://www.reddit.com/search.json"


class RedditSource:
    name = "reddit"

    def __init__(self, retries: int = 1) -> None:
        self._session = http.get_session(retries=retries, backoff=2.0)
        self._ttl = load().cache_ttl_hours
        self._throttle = load().reddit_seconds

    def search(self, query: str, n: int = 10) -> list[Result]:
        cached = cache.get(self.name, query, ttl_hours=self._ttl)
        if cached is not None:
            return [Result(**r) for r in cached]

        params = {"q": query, "limit": min(n, 25)}
        try:
            time.sleep(self._throttle)
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
    for child in payload.get("data", {}).get("children", []):
        d = child.get("data", {})
        out.append(Result(
            source="reddit",
            title=d.get("title") or "",
            url=f"https://www.reddit.com{d.get('permalink', '')}",
            snippet=(d.get("selftext") or "")[:280] or None,
            points=d.get("score"),
            comments=d.get("num_comments"),
            posted_at=str(d.get("created_utc")) if d.get("created_utc") else None,
            extra={"subreddit": d.get("subreddit")},
        ))
    return out


__all__ = ["RedditSource"]
