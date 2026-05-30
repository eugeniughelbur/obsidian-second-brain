#!/usr/bin/env python3
"""/research [topic] [--free] [--academic] - web research with citations.

Two modes, chosen automatically:

- Paid (default when PERPLEXITY_API_KEY is set): Perplexity Sonar produces a
  finished deep dossier, and this script saves the AI-first note itself.
- Free (no key set, or --free passed): fetch raw results from free, key-less
  sources in parallel and emit them as JSON. The calling Claude then synthesizes
  the dossier from that JSON and writes the AI-first note (see commands/research.md).

--academic restricts the free sources to scholarly ones (arXiv, Semantic
Scholar, OpenAlex, CrossRef). It has no effect in paid mode.
"""

import json
import os
import sys
from datetime import datetime

PROMPT_TEMPLATE = """You are a research analyst. Topic: "{topic}"

Produce a DEEP DOSSIER on this topic with the following structure (markdown). Be specific, cite sources, and attach a recency marker (date or "as of YYYY-MM") to every concrete factual claim so it can be re-verified later.

# Research - {topic}

## Summary
[3-5 sentence executive summary capturing the current state of the topic.]

## Key Facts
- [Specific factual claim] (as of YYYY-MM, [domain.com])
- [Specific factual claim] (as of YYYY-MM, [domain.com])
- ...

## Timeline
- [YYYY-MM] [Event]
- [YYYY-MM] [Event]
- ...

## Key Players
- **[Name / company]** - [role, why they matter]
- ...

## Contrarian Views
- [Counter-argument or skeptical position] - held by [who], summary of their case.
- ...

## Recommended Further Reading
- [Title or topic] - [why it's worth reading]
- ...

## Open Questions
- [What's not well-documented or where the data is thin]
- ...

Rules:
- Every concrete factual claim has a recency marker AND a source domain.
- Be honest about gaps in your knowledge ("Open Questions" section is mandatory, not decoration).
- Do NOT add framing, commentary, or filler outside this structure.
"""


def _free_sources(academic: bool):
    """Build the free key-less source clients. Imported lazily so paid mode and
    the test suite never pay for them."""
    from .lib.sources.arxiv import ArxivSource
    from .lib.sources.crossref import CrossRefSource
    from .lib.sources.openalex import OpenAlexSource
    from .lib.sources.semantic_scholar import SemanticScholarSource

    if academic:
        return [ArxivSource(), SemanticScholarSource(), OpenAlexSource(), CrossRefSource()]

    from .lib.sources.duckduckgo import DuckDuckGoSource
    from .lib.sources.hackernews import HackerNewsSource
    from .lib.sources.reddit import RedditSource
    from .lib.sources.wikipedia import WikipediaSource

    return [
        DuckDuckGoSource(),
        WikipediaSource(),
        HackerNewsSource(),
        RedditSource(),
        ArxivSource(),
        SemanticScholarSource(),
    ]


def run_free(topic: str, academic: bool) -> int:
    """Fetch from free sources and emit JSON for the calling Claude to synthesize.
    Does not touch the vault or any API key."""
    from .lib.aggregator import aggregate
    from .lib.result import encode_results

    sources = _free_sources(academic)
    label = "academic" if academic else "default"
    print(
        f"[/research] No Perplexity key (or --free): aggregating {len(sources)} free "
        f"{label} sources for '{topic}'...",
        file=sys.stderr,
    )
    payload = aggregate(topic, sources, n_per_source=10)
    payload["mode"] = "free-sources"
    stats = payload["stats"]
    print(
        f"[/research] {stats['results_total']} results from "
        f"{stats['sources_succeeded']}/{stats['sources_attempted']} sources.",
        file=sys.stderr,
    )
    print(json.dumps(payload, indent=2, default=encode_results))
    return 0


def run_paid(topic: str) -> int:
    """Perplexity Sonar deep dossier, synthesized and saved by this script."""
    from .lib import perplexity, vault

    prompt = PROMPT_TEMPLATE.format(topic=topic)
    print(f"[/research] Researching '{topic}' via Perplexity Sonar...\n", file=sys.stderr)

    try:
        result = perplexity.call(prompt, deep=False, max_tokens=4500)
    except SystemExit:
        raise
    except Exception as e:
        print(f"\n/research failed: {e}", file=sys.stderr)
        return 1

    body = result["text"]
    citations = result.get("citations", [])
    print(body)

    if citations:
        print("\n## Sources (citations)\n")
        for i, c in enumerate(citations, 1):
            if isinstance(c, dict):
                url = c.get("url") or c.get("link") or ""
                title = c.get("title", "")
                print(f"[{i}] {title} - {url}".strip())
            else:
                print(f"[{i}] {c}")

    now = datetime.now()
    preamble = (
        f"For future Claude: This note is a Perplexity Sonar deep dossier on \"{topic}\" "
        f"performed on {now.strftime('%Y-%m-%d %H:%M')}. It captures key facts with recency markers, "
        f"timeline, key players, contrarian views, and open questions. "
        f"Every claim was sourced at the time of research - verify recency markers before relying on individual facts."
    )
    sources_list = []
    for c in citations:
        if isinstance(c, dict):
            url = c.get("url") or c.get("link") or ""
            if url:
                sources_list.append(url)
        elif isinstance(c, str):
            sources_list.append(c)

    fm = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "type": "research",
        "topic": topic,
        "tags": ["research", "perplexity", _slug_tag(topic)],
        "model": result["model"],
        "sources": sources_list,
        "ai-first": True,
    }
    sources_md = ""
    if sources_list:
        sources_md = "\n## Sources\n\n" + "\n".join(f"- {s}" for s in sources_list) + "\n"
    note_body = (
        f"## For future Claude\n\n{preamble}\n\n"
        f"## Topic\n\n{topic}\n\n"
        f"## Dossier\n\n{body}\n"
        f"{sources_md}"
    )
    path = vault.write_note("research", topic, fm, note_body)
    vault.print_save_links(path)
    vault.append_to_log(f"research on \"{topic}\" - saved to {path.name}")
    return 0


def main(argv: list[str]) -> int:
    args = argv[1:]
    force_free = "--free" in args
    academic = "--academic" in args
    topic = " ".join(a for a in args if not a.startswith("--")).strip()
    if not topic:
        print("Usage: /research <topic> [--free] [--academic]", file=sys.stderr)
        return 2

    use_free = force_free or not os.environ.get("PERPLEXITY_API_KEY", "").strip()
    if use_free:
        return run_free(topic, academic)
    return run_paid(topic)


def _slug_tag(s: str) -> str:
    s = s.lower().strip()
    return "-".join(w for w in s.split() if w.isalnum() or "-" in w)[:40] or "topic"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
