#!/usr/bin/env python3
"""/research [topic] - Perplexity Sonar-powered web research with citations.

Output (deep dossier): summary, key facts, sources, timeline, key players, contrarian views,
recommended further reading, open questions.
Default behavior: print to chat AND save AI-first note to Research/Web/.
"""

import sys
from datetime import datetime
from .lib import perplexity, vault

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


def main(argv: list[str]) -> int:
    if len(argv) < 2 or not argv[1].strip():
        print("Usage: /research <topic>", file=sys.stderr)
        return 2

    topic = " ".join(argv[1:]).strip()
    prompt = PROMPT_TEMPLATE.format(topic=topic)
    print(f"[/research] Researching '{topic}' via Perplexity Sonar...\n", file=sys.stderr)

    try:
        result = perplexity.call(prompt, deep=False, max_tokens=4500)
    except SystemExit:
        raise
    except Exception as e:
        print(f"\n❌ /research failed: {e}", file=sys.stderr)
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

    # AI-first note save
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


def _slug_tag(s: str) -> str:
    s = s.lower().strip()
    return "-".join(w for w in s.split() if w.isalnum() or "-" in w)[:40] or "topic"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
