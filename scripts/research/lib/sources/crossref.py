"""CrossRef REST API. Free; polite pool when User-Agent has mailto."""

from __future__ import annotations

from .. import cache, http
from ..source_config import load
from ..result import Result

ENDPOINT = "https://api.crossref.org/works"


class CrossRefSource:
    name = "crossref"

    def __init__(self, retries: int = 2) -> None:
        self._session = http.get_session(retries=retries, backoff=1.0)
        self._ttl = load().cache_ttl_hours

    def search(self, query: str, n: int = 10) -> list[Result]:
        cached = cache.get(self.name, query, ttl_hours=self._ttl)
        if cached is not None:
            return [Result(**r) for r in cached]

        params = {"query": query, "rows": min(n, 50)}
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
    for w in payload.get("message", {}).get("items", []):
        titles = w.get("title") or []
        title = titles[0] if titles else ""
        doi = w.get("DOI")
        url = w.get("URL") or (f"https://doi.org/{doi}" if doi else "")
        abstract = w.get("abstract")
        authors = [
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in w.get("author", [])
        ]
        year = None
        date_parts = (w.get("issued") or {}).get("date-parts") or []
        if date_parts and date_parts[0]:
            year = date_parts[0][0]
        out.append(Result(
            source="crossref",
            title=title,
            url=url,
            abstract=abstract,
            authors=[a for a in authors if a],
            year=year,
            extra={"doi": doi},
        ))
    return out


__all__ = ["CrossRefSource"]
