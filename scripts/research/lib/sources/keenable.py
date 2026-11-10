# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""Keenable search source. Opt-in extra for the free-mode pool, off by default.

Joins the aggregation pool only when RESEARCH_KEENABLE=1 is set (the caller
checks; see research._free_sources, and the constructor refuses otherwise).
Unset means it never runs and makes no request. KEENABLE_API_KEY alone never
switches it on: Keenable needs no key, so the opt-in is the env var, and the
optional key only lifts the anonymous limit (1,000 requests an hour and 10 a
second per IP, as of 2026-11; docs.keenable.ai). Keenable runs the API; the
query text is what gets sent. Plain requests against the REST API, no SDK, so
the dependency list stays unchanged and the test suite never needs a vendor
package.
"""

from __future__ import annotations

import os
import re

from .. import cache, http
from ..result import Result
from ..source_config import load

PUBLIC_URL = "https://api.keenable.ai/v1/search/public"
KEYED_URL = "https://api.keenable.ai/v1/search"
# The app-identifier header names the toolkit only, nothing about the user or
# their machine.
APP_TITLE = "obsidian-second-brain"
# Keenable returns the page text in `snippet` (a few thousand chars with
# newlines). The Result contract treats snippet as a one-line preview, and the
# other sources emit short previews, so collapse whitespace and cap to keep the
# aggregated JSON the same size it is for every other source. The heavy
# full-page path is web_reader, not this one.
MAX_SNIPPET_CHARS = 500


def _preview(text: object) -> str | None:
    if not isinstance(text, str):
        return None
    collapsed = re.sub(r"\s+", " ", text).strip()
    if not collapsed:
        return None
    if len(collapsed) > MAX_SNIPPET_CHARS:
        return collapsed[:MAX_SNIPPET_CHARS].rstrip()
    return collapsed


class KeenableSource:
    name = "keenable"

    def __init__(self, retries: int = 1) -> None:
        if os.environ.get("RESEARCH_KEENABLE", "").strip() != "1":
            raise RuntimeError("KeenableSource requires RESEARCH_KEENABLE=1")
        # Optional; it only lifts the rate limit and never enables the source.
        self._key = os.environ.get("KEENABLE_API_KEY", "").strip()
        self._session = http.get_session(retries=retries, backoff=1.0)
        self._ttl = load().cache_ttl_hours

    def search(self, query: str, n: int = 10) -> list[Result]:
        cached = cache.get(self.name, query, ttl_hours=self._ttl)
        if cached is not None:
            return [Result(**r) for r in cached]

        # The shared session's User-Agent carries RESEARCH_CONTACT_EMAIL for the
        # arXiv/CrossRef/OpenAlex polite pools. Keenable gets the bare toolkit
        # name instead, so nothing about the user goes out with the query.
        headers = {"X-Keenable-Title": APP_TITLE, "User-Agent": http.USER_AGENT_BASE}
        url = PUBLIC_URL
        if self._key:
            # The key travels in a header (never the body) and switches to the
            # keyed endpoint for the higher limit.
            url = KEYED_URL
            headers["X-API-Key"] = self._key

        resp = self._session.post(
            url,
            json={"query": query, "max_results": min(n, 50)},
            headers=headers,
            timeout=http.DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        results = [
            Result(
                source=self.name,
                title=item.get("title") or "",
                url=item.get("url") or "",
                # `description` is always empty; the text is in `snippet`.
                snippet=_preview(item.get("snippet")),
            )
            for item in data.get("results", [])
            if item.get("url")
        ]
        if results:
            cache.put(self.name, query, results)
        return results


__all__ = ["KeenableSource"]
