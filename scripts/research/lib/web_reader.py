# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""Bounded page reader for /research-deep Phase 3.5. Optional deep-research upgrade.

/research-deep's synthesis normally sees only citation snippets. When a reader
key is set, the top sources are fetched as page text and injected into the
synthesis prompt, so the synthesizer reads what the pages actually say instead
of guessing from snippets. Pattern from fork-insights round 2 (the web-reader
fork).

Two readers, never both, picked by key (#387):
- TAVILY_API_KEY set: Tavily Extract, one request for the whole URL batch. This
  is the default and wins whenever its key is set, with no fallback to Firecrawl.
- Only FIRECRAWL_API_KEY set: Firecrawl scrape, one request per URL. Run by
  Firecrawl; the cited page URLs are what gets sent. The request names the
  toolkit only (origin "obsidian-second-brain").
- Neither key: Phase 3.5 is skipped and synthesis stays snippet-only.

Bounded, not complete: each page is cut at MAX_EXTRACT_CHARS and the cut is
marked inline. Do not describe the output as "full text" - a long page arrives
as its opening section, and a reader told otherwise will treat what is missing
as absent from the source rather than absent from the excerpt (#194).

Contract: never raises. Any failure returns what was extracted so far (or {});
deep research must proceed snippet-only when extraction is unavailable. Paid:
both readers bill per page or per URL batch - hence the hard URL cap.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import requests

from . import config, usage

API_URL = "https://api.tavily.com/extract"
FIRECRAWL_URL = "https://api.firecrawl.dev/v2/scrape"
# Names the toolkit only, nothing about the user or their machine.
FIRECRAWL_ORIGIN = "obsidian-second-brain"
# Firecrawl answers these for the key or the account, not the page, so every
# remaining URL would fail the same way.
FIRECRAWL_STOP_STATUSES = {401, 402, 429}
MAX_EXTRACT_URLS = 3      # hard cap: extraction is paid, synthesis has finite context
MAX_EXTRACT_CHARS = 8000  # per page; enough substance, bounded prompt growth
TIMEOUT = 60


def provider() -> str | None:
    """Which reader runs: "tavily", "firecrawl", or None when neither is keyed."""
    if os.environ.get("TAVILY_API_KEY", "").strip():
        return "tavily"
    if config.FIRECRAWL_API_KEY():
        return "firecrawl"
    return None


def available() -> bool:
    return provider() is not None


def _bounded(text: str) -> str:
    if len(text) <= MAX_EXTRACT_CHARS:
        return text
    # Mark the cut. The truncation was silent and the caller labelled the result
    # "full-page text", so the synthesizer had no way to know it was reading the
    # opening of a long page and could state conclusions about sections that
    # were never sent (#194).
    return (
        text[:MAX_EXTRACT_CHARS]
        + f"\n\n[TRUNCATED: this is the first {MAX_EXTRACT_CHARS} characters "
        f"of {len(text)}. The rest of the page was not read - do not treat "
        f"absence of a topic below as evidence the page does not cover it.]"
    )


def read(urls: list[str]) -> dict[str, str]:
    """Extract full text for up to MAX_EXTRACT_URLS unique URLs.
    Returns {url: text}; empty dict when unavailable or on total failure."""
    reader = provider()
    if reader is None or not urls:
        return {}
    unique: list[str] = []
    for u in urls:
        if u and u.startswith("http") and u not in unique:
            unique.append(u)
        if len(unique) >= MAX_EXTRACT_URLS:
            break
    if not unique:
        return {}
    if reader == "firecrawl":
        return _read_firecrawl(unique)

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
            out[url] = _bounded(text)
    # Ledger: extract has no token accounting; record the batch (fail-soft).
    usage.log_call("research-deep", "tavily-extract", 0, 0, 0.0,
                   extra={"provider": "tavily", "urls_extracted": len(out)})
    return out


def _read_firecrawl(urls: list[str]) -> dict[str, str]:
    """One scrape per URL, no retry loop. A failed page is skipped and the rest
    still come back; a key or account error stops the remaining requests."""
    headers = {"Authorization": f"Bearer {config.FIRECRAWL_API_KEY()}"}
    out: dict[str, str] = {}
    for url in urls:
        try:
            resp = requests.post(
                FIRECRAWL_URL,
                json={
                    "url": url,
                    "formats": ["markdown"],
                    "onlyMainContent": True,
                    "origin": FIRECRAWL_ORIGIN,
                },
                headers=headers,
                timeout=TIMEOUT,
            )
            if resp.status_code in FIRECRAWL_STOP_STATUSES:
                print(f"[web_reader] Firecrawl returned {resp.status_code}; "
                      f"skipping the remaining pages", file=sys.stderr)
                break
            resp.raise_for_status()
            page: dict[str, Any] = resp.json().get("data") or {}
            # The page's own status: a 404 or error page is not source content.
            status = (page.get("metadata") or {}).get("statusCode") or 200
            text = (page.get("markdown") or "").strip()
            if text and status < 400:
                out[url] = _bounded(text)
        except Exception as e:  # noqa: BLE001 - extraction is additive, never fatal
            print(f"[web_reader] scrape failed for {url} ({e}); skipping it", file=sys.stderr)
    # Ledger: scrape has no token accounting; record the batch (fail-soft).
    usage.log_call("research-deep", "firecrawl-scrape", 0, 0, 0.0,
                   extra={"provider": "firecrawl", "urls_extracted": len(out)})
    return out
