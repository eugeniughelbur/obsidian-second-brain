"""Semantic Scholar Graph API. Free; 100 req/5min unauth, polite to throttle."""

from __future__ import annotations

import json

from .. import cache, http
from ..source_config import load
from ..result import Result

ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,abstract,authors,year,url,externalIds"


class SemanticScholarSource:
    name = "semantic_scholar"

    def __init__(self, retries: int = 2) -> None:
        self._session = http.get_session(retries=retries, backoff=2.0)
        self._ttl = load().cache_ttl_hours

    def search(self, query: str, n: int = 10) -> list[Result]:
        cached = cache.get(self.name, query, ttl_hours=self._ttl)
        if cached is not None:
            return [Result(**r) for r in cached]

        params = {"query": query, "limit": min(n, 100), "fields": FIELDS}
        try:
            r = self._session.get(ENDPOINT, params=params, timeout=http.DEFAULT_TIMEOUT)
            if r.status_code != 200:
                return []
            results = _parse(r.json())
            cache.put(self.name, query, results)
            return results
        except (json.JSONDecodeError, Exception):
            return []


def _parse(payload: dict) -> list[Result]:
    out: list[Result] = []
    for paper in payload.get("data", []):
        authors = [a.get("name", "") for a in paper.get("authors") or []]
        doi = (paper.get("externalIds") or {}).get("DOI")
        url = paper.get("url") or (f"https://doi.org/{doi}" if doi else "")
        out.append(
            Result(
                source="semantic_scholar",
                title=paper.get("title") or "",
                url=url,
                abstract=paper.get("abstract"),
                authors=[a for a in authors if a],
                year=paper.get("year"),
                extra={"doi": doi} if doi else {},
            )
        )
    return out


__all__ = ["SemanticScholarSource"]
