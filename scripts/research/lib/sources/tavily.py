"""Tavily search source. Requires TAVILY_API_KEY."""

from __future__ import annotations

import os

from ..result import Result


class TavilySource:
    name = "tavily"

    def __init__(self) -> None:
        from tavily import TavilyClient

        self._client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

    def search(self, query: str, n: int = 10) -> list[Result]:
        response = self._client.search(query=query, max_results=min(n, 20))
        results: list[Result] = []
        for item in response.get("results", []):
            results.append(
                Result(
                    source="tavily",
                    title=item.get("title") or "",
                    url=item.get("url") or "",
                    snippet=item.get("content"),
                )
            )
        return results


__all__ = ["TavilySource"]
