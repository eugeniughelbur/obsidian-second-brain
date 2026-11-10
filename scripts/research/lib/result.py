# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""Typed result returned by every source client. Pure data, no behavior."""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Result:
    """A single search result. Sources fill the fields they have; rest stay None."""

    source: str
    title: str
    url: str
    snippet: str | None = None  # web/discourse one-line preview
    abstract: str | None = None  # academic full abstract
    authors: list[str] | None = None  # academic
    year: int | None = None  # academic
    points: int | None = None  # HN score / Reddit upvotes
    comments: int | None = None  # discourse comment count
    posted_at: str | None = None  # ISO 8601 date if known
    extra: dict[str, Any] = field(default_factory=dict)  # per-source extras (doi, etc.)


def encode_results(obj: Any) -> Any:
    """`json.dumps` default= callable. Serializes Result to plain dict."""
    if isinstance(obj, Result):
        return asdict(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
