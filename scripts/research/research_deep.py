#!/usr/bin/env python3
"""/research-deep [topic] [--free] [--academic] - vault-first deep research.

Paid flow (default when PERPLEXITY_API_KEY is set):
1. Vault scan: find existing notes on this topic (baseline knowledge).
2. Identify gaps via Perplexity.
3. Targeted research: Perplexity (web) + Grok (X discourse) to fill gaps.
4. Synthesize the delta vs baseline (Perplexity), write the note, emit a
   propagation payload for the calling Claude to run /obsidian-save.

Free flow (no key, or --free): vault scan + free key-less source aggregation,
then emit JSON. The calling Claude does the gap analysis + delta synthesis
itself, writes the AI-first note to Research/Deep/, and propagates via
/obsidian-save (see commands/research-deep.md). The vault scan is identical in
both modes - /research-deep is vault-first by definition, so OBSIDIAN_VAULT_PATH
is required either way.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from .lib.config import VAULT_PATH

VAULT_SCAN_DIRS = ["wiki", "Research", "Knowledge", "Projects", "Ideas"]
MAX_BASELINE_NOTES = 8
MAX_BASELINE_CHARS_PER_NOTE = 1500


def vault_scan(topic: str) -> list[dict]:
    """Find vault notes whose path or content references the topic. Returns sorted hits."""
    keywords = [w for w in re.split(r"\s+", topic.lower()) if len(w) > 2]
    if not keywords:
        return []
    hits: list[dict] = []
    for sub in VAULT_SCAN_DIRS:
        root = VAULT_PATH / sub
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            try:
                text = path.read_text(errors="ignore").lower()
            except OSError:
                continue
            score = sum(text.count(k) for k in keywords)
            path_score = sum(k in str(path).lower() for k in keywords) * 5
            total = score + path_score
            if total > 0:
                hits.append({
                    "path": str(path.relative_to(VAULT_PATH)),
                    "abs_path": str(path),
                    "score": total,
                })
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits[:MAX_BASELINE_NOTES]


def load_baseline(hits: list[dict]) -> str:
    chunks = []
    for h in hits:
        try:
            text = Path(h["abs_path"]).read_text(errors="ignore")[:MAX_BASELINE_CHARS_PER_NOTE]
            chunks.append(f"### [[{h['path']}]] (score={h['score']})\n\n{text.strip()}\n")
        except OSError:
            continue
    return "\n---\n".join(chunks) if chunks else "(vault has no existing notes referencing this topic)"


GAP_PROMPT = """You are analyzing a knowledge vault to identify research gaps before doing external research.

TOPIC: "{topic}"
TODAY: {today}

EXISTING VAULT NOTES ON THIS TOPIC:
{baseline}

Output EXACTLY this structure (markdown), nothing else:

## Vault Baseline Summary
[3-5 sentences summarizing what the vault currently knows about this topic. Be specific. If the vault is empty on this topic, say so directly.]

## Gaps to Fill
- [Specific question or sub-topic the vault doesn't cover]
- [Specific claim in the vault that may now be stale (cite the file)]
- [...]

## What Looks Current and Reliable
- [Specific claim from the vault that still seems trustworthy, with the source note]
- [...]

## Targeted Research Queries
List 3-5 SPECIFIC search queries that would fill the gaps above. Format each on its own line as: `query | source`
where source is one of `web` (for Perplexity) or `x` (for Grok+X). Examples:
- "Anthropic Claude memory tool 2026 features" | web
- "developers reaction to Mem0 Series A" | x

End with one final line: "READY".
"""


def parse_queries(gap_text: str) -> list[tuple[str, str]]:
    queries = []
    for line in gap_text.splitlines():
        line = line.strip().lstrip("-").strip()
        if "|" in line and not line.startswith("#") and "READY" not in line:
            parts = [p.strip().strip('"').strip("'") for p in line.split("|")]
            if len(parts) >= 2 and parts[1].lower() in ("web", "x"):
                queries.append((parts[0], parts[1].lower()))
    return queries[:5]


SYNTHESIS_PROMPT = """You are synthesizing a vault-first research delta for a personal knowledge vault. Future-Claude will read this note years from now to answer the user's questions, so be specific, structured, and cite everything.

TOPIC: "{topic}"
TODAY: {today}

VAULT BASELINE (what the vault already knew):
{baseline_summary}

NEW EXTERNAL FINDINGS:
{findings}

CRITICAL FORMAT RULES - DO NOT DEVIATE:
- Output ONLY the six sections below, in this exact order, with these exact headers.
- Use markdown bullets (- ...) inside each section. NO long narrative paragraphs.
- Do NOT add an introduction, preamble, conclusion, or "report" framing.
- Do NOT exceed ~1200 words total.
- Every external claim has a recency marker (date) AND source domain.
- Every vault reference uses [[wikilinks]] with the exact path.
- Be ruthless about contradictions - flagging them is the most valuable output.

## What's New Since Vault Baseline
- [Specific new fact from external sources, with recency marker and source domain]
- [...]

## What's Confirmed
- [Specific vault claim that external sources still agree with]
- [...]

## Contradictions / Updates Needed
- [Specific claim where new external info contradicts a vault note - name the [[vault file path]] and the specific contradiction]
- [...]

## Synthesis
- [3-6 short bullets, NOT paragraphs. Each bullet captures one synthesized insight that combines baseline + new findings, with [[wikilink]] or URL citations inline]

## Recommended Vault Updates
- [Specific instruction for /obsidian-save: e.g. "Update [[Knowledge/AI memory]] with the Anthropic memory tool launch (2026-02)"]
- [Each instruction must reference a specific vault file path or clearly describe a new note to create]

## Open Questions
- [What's still unclear after this round of research]
- [...]
"""


def run_free_deep(topic: str, academic: bool) -> int:
    """Vault scan + free key-less source aggregation, emitted as JSON. The
    calling Claude performs the gap analysis, delta synthesis, note write, and
    /obsidian-save propagation (it is the LLM in free mode)."""
    from .lib.aggregator import aggregate
    from .lib.result import encode_results
    from .research import _free_sources

    today = datetime.now().strftime("%Y-%m-%d")

    print(f"[/research-deep] Phase 1: scanning vault for '{topic}'...", file=sys.stderr)
    hits = vault_scan(topic)
    print(f"[/research-deep] Found {len(hits)} relevant vault notes.", file=sys.stderr)

    baseline_notes = []
    for h in hits:
        try:
            excerpt = Path(h["abs_path"]).read_text(errors="ignore")[:MAX_BASELINE_CHARS_PER_NOTE].strip()
        except OSError:
            excerpt = ""
        baseline_notes.append({"path": h["path"], "score": h["score"], "excerpt": excerpt})

    sources = _free_sources(academic)
    label = "academic" if academic else "default"
    print(
        f"[/research-deep] No Perplexity key (or --free): aggregating {len(sources)} free "
        f"{label} sources for '{topic}'...",
        file=sys.stderr,
    )
    agg = aggregate(topic, sources, n_per_source=10)
    stats = agg["stats"]
    print(
        f"[/research-deep] {stats['results_total']} results from "
        f"{stats['sources_succeeded']}/{stats['sources_attempted']} sources.",
        file=sys.stderr,
    )

    payload = {
        "mode": "free-sources-deep",
        "topic": topic,
        "today": today,
        "vault_baseline_notes": baseline_notes,
        "sources": agg["results"],
        "stats": stats,
        "warnings": agg["warnings"],
        "instruction": (
            "You are the synthesizer in free mode. Using the vault_baseline_notes (what the vault "
            "already knew) and the sources (fresh external findings), produce a vault-first delta note "
            "with exactly these sections: What's New Since Vault Baseline, What's Confirmed, "
            "Contradictions / Updates Needed (name the [[vault path]]), Synthesis, Recommended Vault "
            "Updates, Open Questions. Every external claim carries a recency marker and source domain; "
            "every vault reference uses [[wikilinks]]. Never invent facts - if coverage is thin "
            "(stats.success is false), say so in Open Questions. Save the note to "
            "Research/Deep/YYYY-MM-DD - <slug>.md as AI-first (type: research-deep, ai-first: true, "
            "vault-baseline-notes and sources in frontmatter), then run /obsidian-save propagation on "
            "the synthesis and honor the Recommended Vault Updates bullets."
        ),
    }
    print(json.dumps(payload, indent=2, default=encode_results))
    return 0


def run_paid_deep(topic: str) -> int:
    from .lib import perplexity, grok, vault

    today = datetime.now().strftime("%Y-%m-%d")

    print(f"[/research-deep] Phase 1: scanning vault for '{topic}'...", file=sys.stderr)
    hits = vault_scan(topic)
    baseline = load_baseline(hits)
    print(f"[/research-deep] Found {len(hits)} relevant vault notes.", file=sys.stderr)

    print(f"[/research-deep] Phase 2: identifying gaps via Perplexity (sonar-pro, fast)...", file=sys.stderr)
    gap_prompt = GAP_PROMPT.format(topic=topic, today=today, baseline=baseline)
    try:
        gap_result = perplexity.call(gap_prompt, deep=False, max_tokens=2000)
    except Exception as e:
        print(f"Phase 2 (gap analysis) failed: {e}", file=sys.stderr)
        return 1

    queries = parse_queries(gap_result["text"])
    print(f"[/research-deep] Identified {len(queries)} targeted queries.", file=sys.stderr)

    print(f"[/research-deep] Phase 3: filling gaps...", file=sys.stderr)
    findings_chunks: list[str] = []
    sources_collected: list[str] = []

    for q, src in queries:
        try:
            if src == "web":
                print(f"  [web] {q}", file=sys.stderr)
                r = perplexity.call(f"Research this question: {q}\n\nReturn 3-5 specific facts with recency markers (date) and source domain. Be concise.", deep=False, max_tokens=1200)
                findings_chunks.append(f"### Web - {q}\n\n{r['text']}")
                for c in r.get("citations", []):
                    if isinstance(c, dict):
                        url = c.get("url") or c.get("link") or ""
                        if url:
                            sources_collected.append(url)
                    elif isinstance(c, str):
                        sources_collected.append(c)
            else:
                print(f"  [x]   {q}", file=sys.stderr)
                r = grok.call(
                    f"On X right now, what are people saying about: {q}\n\nReturn 3-5 specific posts/voices with @ handles and post URLs. No commentary outside that.",
                    command="research-deep",
                    tools=[{"type": "x_search"}],
                    max_output_tokens=1200,
                )
                findings_chunks.append(f"### X - {q}\n\n{r['text']}")
        except Exception as e:
            findings_chunks.append(f"### {src} - {q}\n\n[FAILED: {e}]")
            print(f"  {src} query failed: {e}", file=sys.stderr)

    findings = "\n\n".join(findings_chunks) if findings_chunks else "(no findings - all targeted queries failed)"

    print(f"[/research-deep] Phase 4: synthesizing delta vs vault baseline...", file=sys.stderr)
    synth_prompt = SYNTHESIS_PROMPT.format(
        topic=topic,
        today=today,
        baseline_summary=gap_result["text"],
        findings=findings,
    )
    try:
        # Use sonar-reasoning-pro for synthesis (follows instructions, supports markdown structure).
        # sonar-deep-research has a hardcoded "10k-word academic narrative" that overrides our prompt.
        synth = perplexity.call(synth_prompt, model="sonar-reasoning-pro", max_tokens=3500)
    except Exception as e:
        print(f"Phase 4 (synthesis) failed: {e}", file=sys.stderr)
        return 1

    body = synth["text"]
    print(body)

    # AI-first note save (Phase 5)
    now = datetime.now()
    preamble = (
        f"For future Claude: This is a vault-first deep research delta on \"{topic}\" "
        f"performed on {now.strftime('%Y-%m-%d %H:%M')}. The vault was scanned first ({len(hits)} relevant notes), "
        f"gaps were identified, and {len(queries)} targeted queries filled them via Perplexity (web) + Grok (X). "
        f"This note focuses on WHAT'S NEW vs the vault's prior knowledge, contradictions to resolve, and recommended updates. "
        f"Cross-vault propagation should follow via /obsidian-save."
    )
    fm = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "type": "research-deep",
        "topic": topic,
        "tags": ["research", "research-deep", _slug_tag(topic)],
        "vault-baseline-notes": [h["path"] for h in hits],
        "queries-run": [f"[{s}] {q}" for q, s in queries],
        "sources": sources_collected,
        "ai-first": True,
    }
    note_body = (
        f"## For future Claude\n\n{preamble}\n\n"
        f"## Topic\n\n{topic}\n\n"
        f"## Vault Baseline Found\n\n"
        + ("\n".join(f"- [[{h['path']}]] (score={h['score']})" for h in hits) if hits else "(none)")
        + f"\n\n## Synthesis\n\n{body}\n"
    )
    path = vault.write_note("research-deep", topic, fm, note_body)
    vault.print_save_links(path)

    # Emit JSON instruction block for the calling Claude to handle propagation
    propagation_payload = {
        "command": "obsidian-save-context",
        "research_note_path": str(path.relative_to(VAULT_PATH)),
        "topic": topic,
        "vault_baseline_notes": [h["path"] for h in hits],
        "synthesis_body": body,
        "instruction": (
            "Read the research note at the path above. Then run /obsidian-save logic on the synthesis body: "
            "spawn parallel subagents for People, Projects, Ideas, Decisions; create or update notes per the AI-first vault rule; "
            "honor 'Recommended Vault Updates' bullets in the synthesis as explicit propagation instructions; "
            "link this research note from today's daily note."
        ),
    }
    print("\n<<<RESEARCH_DEEP_PROPAGATION_PAYLOAD>>>")
    print(json.dumps(propagation_payload, indent=2))
    print("<<<END_PAYLOAD>>>")

    vault.append_to_log(f"research-deep on \"{topic}\" - saved to {path.name}, propagation payload emitted")
    return 0


def main(argv: list[str]) -> int:
    args = argv[1:]
    force_free = "--free" in args
    academic = "--academic" in args
    topic = " ".join(a for a in args if not a.startswith("--")).strip()
    if not topic:
        print("Usage: /research-deep <topic> [--free] [--academic]", file=sys.stderr)
        return 2

    use_free = force_free or not os.environ.get("PERPLEXITY_API_KEY", "").strip()
    if use_free:
        return run_free_deep(topic, academic)
    return run_paid_deep(topic)


def _slug_tag(s: str) -> str:
    s = s.lower().strip()
    return "-".join(w for w in s.split() if w.isalnum() or "-" in w)[:40] or "topic"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
