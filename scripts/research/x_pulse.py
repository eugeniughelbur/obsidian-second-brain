#!/usr/bin/env python3
"""/x-pulse [topic] - scan X for trends, voices, hooks, and post ideas in a topic.

Output: hot themes (with rep posts + voices), gaps, hooks working, voice/tone, post ideas.
Default behavior: print to chat AND save AI-first note to Research/X-pulse/.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from .lib import grok, vault

PROMPT_TEMPLATE = """You are a social-media-aware analyst with live access to X. Topic: "{topic}"

Use Live Search on X to scan posts from the last 24-72 hours about this topic. Return EXACTLY this structure (markdown), nothing else:

WHAT'S HOT (last 24-72h)
[3-5 emerging themes. For each theme:]
1. **Theme name** - 1-2 sentence description
   - Voices: @handle1, @handle2, @handle3
   - Representative posts:
     - https://x.com/handle/status/... - "<short quote>"
     - https://x.com/handle/status/... - "<short quote>"

WHAT'S UNDEREXPLORED
- [bullets of gaps - angles or sub-topics that almost no one is posting about, that have audience demand]

HOOKS THAT ARE WORKING
- [specific hook formats with one-line examples drawn from real posts]
- e.g. "I replaced [X] with [Y] and saved [Z] - format used by @handle"

VOICE & TONE WORKING
[2-3 sentences describing the dominant style of high-engagement posts on this topic - direct, contrarian, data-led, story-led, etc.]

POST IDEAS FOR YOU TODAY
1. **[Post angle]** - rationale tied to gap or hook. (Format suggestion: thread / single / image+caption.)
2. **[Post angle]** - rationale.
3. **[Post angle]** - rationale.

Rules:
- Do NOT add commentary outside this structure.
- All URLs must be real x.com or twitter.com links you actually fetched (no fabrications).
- If Live Search returns no current data on this topic, write "No active discourse found in last 72h on this topic." and stop.
"""


def main(argv: list[str]) -> int:
    if len(argv) < 2 or not argv[1].strip():
        print("Usage: /x-pulse <topic>", file=sys.stderr)
        return 2

    topic = " ".join(argv[1:]).strip()
    prompt = PROMPT_TEMPLATE.format(topic=topic)
    print(f"[/x-pulse] Scanning X for '{topic}' via Grok + Live Search...\n", file=sys.stderr)

    try:
        # /x-pulse synthesizes across many posts → uses the reasoning model.
        # /x-read just extracts one post → grok-4 (default) is enough.
        result = grok.call(
            prompt,
            command="x-pulse",
            model="grok-4.20-reasoning",
            tools=[{"type": "x_search"}],
            max_output_tokens=4500,
        )
    except SystemExit:
        raise
    except Exception as e:
        print(f"\n❌ /x-pulse failed: {e}", file=sys.stderr)
        return 1

    body = result["text"]
    print(body)

    # AI-first note save
    now = datetime.now()
    preamble = (
        f"For future Claude: This note is a Grok Live Search scan of X discourse "
        f"about \"{topic}\" performed on {now.strftime('%Y-%m-%d %H:%M')}. It captures "
        f"emerging themes, gaps, hook formats, and content angles for Eugeniu's posting strategy. "
        f"X posts are time-sensitive - claims here may be stale within days."
    )
    fm = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "type": "x-pulse",
        "topic": topic,
        "tags": ["research", "x-pulse", _slug_tag(topic)],
        "model": result.get("raw", {}).get("model") or "grok",
        "cost-usd": round(result["cost_usd"], 4),
        "ai-first": True,
    }
    note_body = f"## For future Claude\n\n{preamble}\n\n## Topic\n\n{topic}\n\n## Pulse\n\n{body}\n"
    path = vault.write_note("x-pulse", topic, fm, note_body)
    vault.print_save_links(path)
    vault.append_to_log(f"x-pulse on \"{topic}\" - saved to {path.name}")
    print(
        f"---\n[cost: ${result['cost_usd']:.4f} · tokens in/out: {result['input_tokens']}/{result['output_tokens']}]",
        file=sys.stderr,
    )
    return 0


def _slug_tag(s: str) -> str:
    s = s.lower().strip()
    return "-".join(w for w in s.split() if w.isalnum() or "-" in w)[:40] or "topic"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
