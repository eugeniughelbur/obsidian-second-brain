"""OpenAlex Works API. Free; polite pool when User-Agent has mailto."""

from __future__ import annotations

from .. import cache, http
from ..source_config import load
from ..result import Result

ENDPOINT = "https://api.openalex.org/works"


class OpenAlexSource:
    name = "openalex"

    def __init__(self, retries: int = 2) -> None:
        self._session = http.get_session(retries=retries, backoff=1.0)
        self._ttl = load().cache_ttl_hours

    def search(self, query: str, n: int = 10) -> list[Result]:
        cached = cache.get(self.name, query, ttl_hours=self._ttl)
        if cached is not None:
            return [Result(**r) for r in cached]

        params = {"search": query, "per-page": min(n, 25)}
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
    for w in payload.get("results", []):
        title = w.get("display_name") or w.get("title") or ""
        doi = w.get("doi")
        url = doi or w.get("id") or ""
        abstract = _reconstruct_abstract(w.get("abstract_inverted_index"))
        authors = [
            a.get("author", {}).get("display_name", "")
            for a in w.get("authorships", [])
        ]
        out.append(Result(
            source="openalex",
            title=title,
            url=url,
            abstract=abstract,
            authors=[a for a in authors if a],
            year=w.get("publication_year"),
            extra={"doi": doi, "cited_by_count": w.get("cited_by_count")},
        ))
    return out


def _reconstruct_abstract(inv: dict | None) -> str | None:
    """OpenAlex stores abstracts as inverted index {word: [positions]}. Reconstruct."""
    if not inv:
        return None
    pairs = []
    for word, positions in inv.items():
        for p in positions:
            pairs.append((p, word))
    pairs.sort()
    return " ".join(w for _, w in pairs) or None


__all__ = ["OpenAlexSource"]
