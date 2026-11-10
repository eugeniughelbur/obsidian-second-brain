#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""Verify that quoted claims exist, word for word, in vault notes.

/obsidian-reconcile acts on a contradiction only when both sides are proven:
each side names a note, a line and a quote, and this script checks the quote
is really in that note. A contradiction a model reports but cannot quote is
dropped, never acted on. A wrong claim that gets "reconciled" into a rewrite
spreads to every note that copies it (#258).

Input, on stdin, a JSON array with one object per claim:
  [{"path": "<note path, relative to the vault>", "line": 12, "quote": "..."}]

Output, on stdout, the same array with three keys added to each object:
  ok          true when the quote is in the note
  found_line  the 1-based line holding the quote, or null
  reason      why a claim failed, or a note when the line number was off

Exit 0 when every claim is proven, 1 when any is not, 2 on bad input.

Rules:
  - The path must name a file inside the vault. ".." and symlinks that lead
    outside it fail.
  - The quote must be one line and at least MIN_QUOTE characters. A short
    quote such as "the" matches almost any note and proves nothing.
  - Matching is exact, except that Unicode is NFC-normalized and runs of
    spaces or tabs count as one space. One changed word fails the match.
  - The line number is a hint. A quote found on another line still counts,
    and found_line gives the real line.

Usage:
  python scripts/verify_quotes.py --path /path/to/vault < claims.json

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

MIN_QUOTE = 12
_SPACES = re.compile(r"[ \t]+")


def _norm(text: str) -> str:
    return _SPACES.sub(" ", unicodedata.normalize("NFC", text)).strip()


def check(vault: Path, claim: object) -> dict:
    """Check one claim and return it with ok, found_line and reason added."""
    result = dict(claim) if isinstance(claim, dict) else {"claim": claim}
    result.update(ok=False, found_line=None, reason=None)

    def fail(reason: str) -> dict:
        result["reason"] = reason
        return result

    if not isinstance(claim, dict):
        return fail("claim is not an object")
    path, line, quote = claim.get("path"), claim.get("line"), claim.get("quote")
    if not isinstance(path, str) or not path.strip():
        return fail("missing path")
    if not isinstance(quote, str):
        return fail("missing quote")
    if "\n" in quote.strip("\r\n") or "\r" in quote.strip("\r\n"):
        return fail("quote spans more than one line")
    wanted = _norm(quote)
    if len(wanted) < MIN_QUOTE:
        return fail(f"quote shorter than {MIN_QUOTE} characters proves nothing")

    root = vault.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        return fail("path is outside the vault")
    if not target.is_file():
        return fail("no such note")
    try:
        text = target.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return fail(f"cannot read note: {exc}")

    hits = [n for n, text_line in enumerate(text.splitlines(), 1) if wanted in _norm(text_line)]
    if not hits:
        return fail("quote not found in the note")
    result["ok"] = True
    if isinstance(line, int) and not isinstance(line, bool) and line in hits:
        result["found_line"] = line
    else:
        result["found_line"] = hits[0]
        if line is not None:
            result["reason"] = f"quote is on line {hits[0]}, not line {line}"
    return result


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Verify quoted claims against vault notes.")
    ap.add_argument("--path", required=True, help="vault root")
    args = ap.parse_args(argv)
    vault = Path(args.path).expanduser()
    if not vault.is_dir():
        print(f"verify_quotes: not a folder: {vault}", file=sys.stderr)
        return 2
    # Bytes, not text: a Windows console code page would garble non-ASCII quotes.
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    try:
        claims = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"verify_quotes: stdin is not JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(claims, list):
        print("verify_quotes: stdin must be a JSON array of claims", file=sys.stderr)
        return 2
    results = [check(vault, claim) for claim in claims]
    print(json.dumps(results, indent=2))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
