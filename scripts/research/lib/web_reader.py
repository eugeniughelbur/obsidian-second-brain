"""Full-page reader via the Tavily Extract API. Optional deep-research upgrade.

/research-deep's synthesis normally sees only citation snippets. When
TAVILY_API_KEY is set, the top sources are fetched as full page text and
injected into the synthesis prompt, so the synthesizer reads what the pages
actually say instead of guessing from snippets. Pattern from fork-insights
round 2 (the web-reader fork).

Contract: never raises. Any failure returns what was extracted so far (or {});
deep research must proceed snippet-only when extraction is unavailable. Paid:
Tavily Extract bills credits per URL batch - hence the hard URL cap.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import requests

from . import usage

API_URL = "https://api.tavily.com/extract"
MAX_EXTRACT_URLS = 3      # hard cap: extraction is paid, synthesis has finite context
MAX_EXTRACT_CHARS = 8000  # per page; enough substance, bounded prompt growth
TIMEOUT = 60


def available() -> bool:
    return bool(os.environ.get("TAVILY_API_KEY", "").strip())


def read(urls: list[str]) -> dict[str, str]:
    """Extract full text for up to MAX_EXTRACT_URLS unique URLs.
    Returns {url: text}; empty dict when unavailable or on total failure."""
    if not available() or not urls:
        return {}
    unique: list[str] = []
    for u in urls:
        if u and u.startswith("http") and u not in unique:
            unique.append(u)
        if len(unique) >= MAX_EXTRACT_URLS:
            break
    if not unique:
        return {}

    try:
        resp = requests.post(
            API_URL,
            json={"urls": unique},
            headers={"Authorization": f"Bearer {os.environ['TAVILY_API_KEY'].strip()}"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
    except Exception as e:  # noqa: BLE001 - extraction is additive, never fatal
        print(f"[web_reader] extract failed ({e}); synthesis proceeds snippet-only", file=sys.stderr)
        return {}

    out: dict[str, str] = {}
    for item in data.get("results", []):
        url = item.get("url") or ""
        text = (item.get("raw_content") or "").strip()
        if url and text:
            out[url] = text[:MAX_EXTRACT_CHARS]
    # Ledger: extract has no token accounting; record the batch (fail-soft).
    usage.log_call("research-deep", "tavily-extract", 0, 0, 0.0,
                   extra={"provider": "tavily", "urls_extracted": len(out)})
    return out
