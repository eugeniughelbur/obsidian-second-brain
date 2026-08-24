#!/usr/bin/env python3
"""/notebooklm [topic]: vault-first source-grounded research via Gemini File Search.

Same shape as /research-deep: one command, one HTTP call, no browser. Uses Google's
Gemini File Search API (generally available, $0.15/M tokens indexed, storage free).

Flow:
  1. Scan the vault for notes related to the topic (Research/NotebookLM/ excluded).
  2. Upload the top 12 most relevant notes to an ephemeral Gemini File Search store.
  3. Ask Gemini (default gemini-2.5-pro) for a synthesis grounded against that store.
  4. Write the AI-first synthesis to Research/NotebookLM/YYYY-MM-DD - <slug>.md.
  5. Delete the File Search store.
  6. Emit a propagation payload for /obsidian-save.

Cost per run: roughly $0.01 to $0.05 for a 12-note bundle.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types

from .lib.config import NOTEBOOKLM_MODEL, VAULT_PATH, get_required
from .lib.gemini import GEMINI_DEFAULT_MODEL, MODEL_LADDER
from .lib.vault import slugify
from .lib.vault_terms import topic_terms

MAX_BUNDLE_NOTES = 12
NOTEBOOKLM_DIR = VAULT_PATH / "Research" / "NotebookLM"


def _vault_scan_dirs() -> list[str]:
    """Top-level vault folders that actually exist - never a hardcoded name (folder-map.md)."""
    if not VAULT_PATH.exists():
        return []
    return [p.name for p in VAULT_PATH.iterdir() if p.is_dir() and not p.name.startswith(".")]


def vault_scan(topic: str) -> list[dict]:
    # Tokenize via the search tokenizer, never a private copy: the old
    # whitespace split + len(w) > 2 here returned nothing for CJK topics and
    # survived #159/#188/#192 because each fix landed elsewhere (issue #212).
    keywords = topic_terms(topic)
    if not keywords:
        return []
    hits: list[dict] = []
    for sub in _vault_scan_dirs():
        root = VAULT_PATH / sub
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            if "Research/NotebookLM/" in str(path):
                continue
            try:
                text = path.read_text(errors="ignore").lower()
            except OSError:
                continue
            score = sum(text.count(k) for k in keywords)
            path_score = sum(k in str(path).lower() for k in keywords) * 5
            total = score + path_score
            if total > 0:
                hits.append(
                    {
                        "path": str(path.relative_to(VAULT_PATH)),
                        "abs_path": str(path),
                        "score": total,
                    }
                )
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits[:MAX_BUNDLE_NOTES]


PROMPT_TEMPLATE = """\
You are answering from the sources I have given you. Topic: "{topic}".

Produce a synthesis with EXACTLY these sections:

## Source summary (3 to 5 sentences)
What do the sources collectively say about this topic? Be specific. Cite source titles in [brackets].

## Confirmed claims
- [claim] (which source(s) state it)

## Contradictions or tensions across sources
- [claim A in source X] vs [claim B in source Y]

## Gaps in the sources
- [question]

## Recommended next reads or angles
- [angle / source / query]

## Confidence on the synthesis
high | medium | low. One sentence on why.

Cite source titles in brackets wherever a claim originates. Do not invent facts beyond the sources.
Do not use em-dashes in your response. Use periods, commas, parentheses, or " - " (hyphen with spaces) instead.
"""


NOTEBOOKLM_NOTE_TEMPLATE = """---
date: {date}
type: research-notebooklm
tags:
  - research
  - research-notebooklm
  - notebooklm
  - source-grounded
ai-first: true
confidence: stated
model: {model}
---

# {topic}: NotebookLM synthesis ({date})

## For future agent

Source-grounded synthesis on "{topic}" via Gemini File Search (model: {model}). Vault baseline: {baseline_count} notes from the vault scan, uploaded as grounded sources. Output cites source titles where the model included them. This is the parallel research track to `/research-deep` (Perplexity-based, open-web); this one is grounded in the user's own sources, not the open web. Confidence: stated (grounded retrieval is reliable on the sources you give it; less reliable on synthesis breadth).

## Vault baseline that fed this notebook

{baseline_links}

## Synthesis ({model}, grounded)

{response}

## Related

- [[Research/Deep/]] (the parallel Perplexity-based research track)
"""


def safe_display_name(path: str) -> str:
    """Strip non-ASCII so display_name survives HTTP header encoding."""
    # \u2014/\u2013 escapes keep this sweep-proof (see #63): em-dash -> " - ", en-dash -> "-"
    s = path.replace("\u2014", " - ").replace("\u2013", "-")
    s = s.encode("ascii", "replace").decode("ascii")
    return s[:200]


def upload_and_wait(client: genai.Client, store_name: str, hit: dict) -> None:
    """Upload one file, then poll the operation until it finishes.

    Copies the source file to a temp path with an ASCII-safe name first. The Gemini
    SDK puts the basename into a Content-Disposition header, and httpx rejects
    non-ASCII headers (vault filenames often have em-dashes from /research-deep).
    """
    with tempfile.NamedTemporaryFile(prefix="nblm-", suffix=".md", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        shutil.copyfile(hit["abs_path"], tmp_path)
        operation = client.file_search_stores.upload_to_file_search_store(
            file=tmp_path,
            file_search_store_name=store_name,
            config={"display_name": safe_display_name(hit["path"])},
        )
        deadline = time.time() + 300
        while not operation.done:
            if time.time() > deadline:
                raise TimeoutError(f"upload timed out after 300s: {hit['path']}")
            time.sleep(5)
            operation = client.operations.get(operation)
    finally:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass


def run(topic: str) -> int:
    api_key = get_required("GEMINI_API_KEY")
    hits = vault_scan(topic)
    if not hits:
        print(f"ERROR: no vault notes match topic '{topic}'.", file=sys.stderr)
        return 1

    today = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(topic) or "untitled"

    print(f"=== /notebooklm: {topic} ===", file=sys.stderr)
    print(f"Vault baseline: {len(hits)} notes", file=sys.stderr)
    print(f"Model: {NOTEBOOKLM_MODEL}", file=sys.stderr)

    client = genai.Client(api_key=api_key)

    print("Creating Gemini File Search store...", file=sys.stderr)
    store = client.file_search_stores.create(
        config={
            "display_name": f"vault-{slug}-{today}",
        },
    )

    response_text = ""
    try:
        for i, h in enumerate(hits, 1):
            print(f"  [{i}/{len(hits)}] uploading {h['path']}", file=sys.stderr)
            upload_and_wait(client, store.name, h)

        print("Asking Gemini, grounded against the uploaded sources...", file=sys.stderr)
        # Same per-key-cohort 404 problem as lib/gemini.py (issue #211): the
        # default walks the shared ladder; an explicit NOTEBOOKLM_MODEL is
        # never laddered and fails loud with the fix named.
        candidates = ([NOTEBOOKLM_MODEL] if NOTEBOOKLM_MODEL != GEMINI_DEFAULT_MODEL
                      else list(MODEL_LADDER))
        resp = None
        used_model = candidates[0]
        last_404: Exception | None = None
        for m in candidates:
            try:
                resp = client.models.generate_content(
                    model=m,
                    contents=PROMPT_TEMPLATE.format(topic=topic),
                    config=types.GenerateContentConfig(
                        tools=[
                            types.Tool(
                                file_search=types.FileSearch(
                                    file_search_store_names=[store.name],
                                ),
                            )
                        ],
                    ),
                )
                used_model = m
                break
            except Exception as e:
                if "NOT_FOUND" in str(e) or "404" in str(e):
                    last_404 = e
                    print(f"NOTE: model {m} not available to this key (404); "
                          f"trying the next fallback...", file=sys.stderr)
                    continue
                raise
        if resp is None:
            print(f"ERROR: no Gemini model available to this key "
                  f"(tried: {', '.join(candidates)}). Set NOTEBOOKLM_MODEL in "
                  f"~/.config/obsidian-second-brain/.env to a model your key can "
                  f"generate with. Last error: {last_404}", file=sys.stderr)
            return 1
        response_text = resp.text or ""
        if not response_text.strip():
            print("ERROR: Gemini returned an empty response.", file=sys.stderr)
            return 1
    finally:
        print("Deleting File Search store...", file=sys.stderr)
        try:
            client.file_search_stores.delete(name=store.name, config={"force": True})
        except Exception as e:
            print(f"WARNING: failed to delete store {store.name}: {e}", file=sys.stderr)

    NOTEBOOKLM_DIR.mkdir(parents=True, exist_ok=True)
    note_path = NOTEBOOKLM_DIR / f"{today} - {slug}.md"
    body = NOTEBOOKLM_NOTE_TEMPLATE.format(
        date=today,
        topic=topic,
        slug=slug,
        model=used_model,
        baseline_count=len(hits),
        baseline_links="\n".join(f"- [[{h['path']}]]" for h in hits),
        response=response_text,
    )
    note_path.write_text(body)

    payload = {
        "topic": topic,
        "today": today,
        "slug": slug,
        "saved_note": str(note_path.relative_to(VAULT_PATH)),
        "vault_baseline_notes": [h["path"] for h in hits],
        "model": used_model,
    }

    print(f"\n=== SAVED ===\n{note_path}\n")
    print("<<<NOTEBOOKLM_PROPAGATION_PAYLOAD>>>")
    print(json.dumps(payload, indent=2))
    print("<<<NOTEBOOKLM_PROPAGATION_PAYLOAD>>>")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True, help="topic to research")
    args = parser.parse_args()
    return run(args.topic)


if __name__ == "__main__":
    sys.exit(main())
