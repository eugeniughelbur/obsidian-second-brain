# scripts/research/lib/aggregator.py
"""Run multiple source clients in parallel, aggregate, never crash on per-source failure."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout, as_completed
from dataclasses import asdict
from typing import Any, Protocol

from .result import Result

OVERALL_TIMEOUT_SECONDS = 30


class SourceClient(Protocol):
    name: str

    def search(self, query: str, n: int = 10) -> list[Result]: ...


def aggregate(
    query: str,
    sources: list[SourceClient],
    n_per_source: int = 10,
    timeout: float = OVERALL_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run all sources in parallel. Return JSON-serializable dict."""

    results: list[Result] = []
    warnings: list[str] = []
    succeeded: set[str] = set()

    with ThreadPoolExecutor(max_workers=len(sources)) as ex:
        future_to_source = {
            ex.submit(_safe_search, s, query, n_per_source): s for s in sources
        }
        try:
            for future in as_completed(future_to_source, timeout=timeout):
                src = future_to_source[future]
                got, err = future.result()
                if err:
                    warnings.append(f"{src.name}: {err}")
                if got:
                    results.extend(got)
                    succeeded.add(src.name)
        except FuturesTimeout:
            for f, s in future_to_source.items():
                if not f.done():
                    warnings.append(f"{s.name}: timeout")

    return {
        "topic": query,
        "results": [asdict(r) for r in results],
        "stats": {
            "sources_attempted": len(sources),
            "sources_succeeded": len(succeeded),
            "results_total": len(results),
            "success": len(succeeded) >= 3,
        },
        "warnings": warnings,
    }


def _safe_search(source: SourceClient, query: str, n: int) -> tuple[list[Result], str | None]:
    try:
        return source.search(query, n=n), None
    except Exception as e:
        print(f"[{source.name}] {type(e).__name__}: {e}", file=sys.stderr)
        return [], str(e)


__all__ = ["aggregate", "SourceClient", "OVERALL_TIMEOUT_SECONDS"]
