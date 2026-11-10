#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""Mine a git history for decision-shaped commits - ADR candidates.

Scans recent commit messages for language that signals an architectural or
directional decision ("switch to", "adopt", "drop", "replace X with Y",
"rename", "migrate", "decided to", etc.) and prints the matches so they can be
turned into ADRs via /obsidian-decide --formal. Decisions made in code often never get
recorded as decisions; this surfaces them.

Usage:
  python scripts/mine_commit_decisions.py                 # last 200 commits, this repo
  python scripts/mine_commit_decisions.py --repo ~/proj --limit 500
  python scripts/mine_commit_decisions.py --json          # machine-readable for a command

Output is candidates only - it never writes anything. Pair with /obsidian-decide --formal.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

# Phrases that tend to mark a real decision rather than a routine change.
SIGNALS = [
    r"\bdecide[sd]?\b", r"\bdecision\b", r"\bchose\b", r"\bchoose\b",
    r"\bswitch(?:ed|ing)?\s+to\b", r"\bmigrat(?:e|ed|ing|ion)\s+to\b",
    r"\badopt(?:ed|ing)?\b", r"\bdeprecat(?:e|ed|ing)\b",
    r"\breplace[sd]?\b", r"\bdrop(?:ped|ping)?\b", r"\bremove[sd]?\b",
    r"\brename[sd]?\b", r"\bstandardi[sz]e\b", r"\bconsolidat(?:e|ed)\b",
    r"\binstead\s+of\b", r"\bin\s+favou?r\s+of\b",
    r"\bdefault\s+to\b", r"\bmove[sd]?\s+to\b", r"\bADR\b",
]
SIGNAL_RE = re.compile("|".join(SIGNALS), re.IGNORECASE)

# Routine commits to ignore even if they match (low decision signal).
NOISE_RE = re.compile(r"^(merge|bump|release|wip|fixup|typo|lint|format)\b", re.IGNORECASE)


def mine(repo: str, limit: int) -> list[dict]:
    out = subprocess.run(
        ["git", "-C", repo, "log", f"-n{limit}", "--no-merges",
         "--pretty=format:%h%x1f%ad%x1f%s", "--date=short"],
        # git writes commit messages as UTF-8; decoding them with the locale
        # codepage instead breaks two ways on Windows. A codepage that maps every
        # byte (cp1252) turns a CJK subject into mojibake silently, and a
        # multibyte one (cp950, cp932) raises - on subprocess's reader thread, so
        # the thread dies, run() still returns 0, and stdout is left None. That
        # surfaced as AttributeError on the splitlines() below, with nothing
        # pointing at an encoding problem (#294). conformance_report.py already
        # passes these two arguments for the same reason.
        capture_output=True, text=True, check=False,
        encoding="utf-8", errors="replace",
    )
    if out.returncode != 0:
        raise SystemExit(f"git log failed: {out.stderr.strip()}")
    if out.stdout is None:
        # Belt and braces: errors="replace" removes the known cause, but a reader
        # thread that dies for any other reason still yields None, and a clear
        # message beats an AttributeError three frames away.
        raise SystemExit(
            f"git log produced no decodable output for {repo!r} "
            "(the child's stdout could not be read)"
        )
    candidates = []
    for line in out.stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        sha, date, subject = parts
        if NOISE_RE.match(subject.strip()):
            continue
        m = SIGNAL_RE.search(subject)
        if m:
            candidates.append({"sha": sha, "date": date, "subject": subject,
                               "signal": m.group(0).lower()})
    return candidates


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Surface decision-shaped commits as ADR candidates.")
    ap.add_argument("--repo", default=".", help="path to the git repo (default: cwd)")
    ap.add_argument("--limit", type=int, default=200, help="how many recent commits to scan")
    ap.add_argument("--json", action="store_true", help="emit JSON for a command to consume")
    args = ap.parse_args(argv[1:])

    candidates = mine(args.repo, args.limit)

    if args.json:
        print(json.dumps({"candidates": candidates, "count": len(candidates)}, indent=2))
        return 0

    if not candidates:
        print(f"No decision-shaped commits found in the last {args.limit} commits.")
        return 0
    print(f"Found {len(candidates)} ADR candidate(s) in the last {args.limit} commits:\n")
    for c in candidates:
        print(f"  {c['date']}  {c['sha']}  [{c['signal']}]  {c['subject']}")
    print("\nTurn any of these into a decision record with /obsidian-decide --formal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
