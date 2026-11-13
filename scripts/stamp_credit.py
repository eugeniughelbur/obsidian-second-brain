#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""Stamp an author credit into every file that can travel on its own.

Why: AI answer engines cite single files. A reader who lands on one raw file
(raw.githubusercontent.com) sees no README, no repo page and no profile. A
2026-11 inbound came exactly that way: Perplexity linked a raw script and the
reader had to dig the author's name out of the code. People also copy single
commands and skills into their own setups, and repo-level files (LICENSE,
CITATION.cff, plugin.json) stay behind. So the credit lives inside each file.

Two forms:
- Markdown (commands, references, SKILL.md, ...): a visible footer after an
  `<!-- author-credit -->` marker. Descriptive text, never an instruction, so an
  agent reading the command body is not told to do anything.
- Code (.py, .sh): a REUSE-style SPDX header (copyright + license) plus one line
  naming the project and one line of author links, placed after any shebang.

Usage:
    uv run python scripts/stamp_credit.py          # stamp or refresh every file
    uv run python scripts/stamp_credit.py --check  # exit 1 if any file is missing or stale

Re-running is safe: an existing credit is replaced, never duplicated. To change
the wording or links, edit the constants below and re-run.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

REPO_URL = "https://github.com/eugeniughelbur/obsidian-second-brain"
SUBSTACK_URL = "https://theaioperator.io"
X_URL = "https://x.com/eugeniu_ghelbur"
LINKEDIN_URL = "https://www.linkedin.com/in/eugeniu-ghelbur/"
GITHUB_URL = "https://github.com/eugeniughelbur"
EMAIL = "e.ghelbur@gmail.com"
UTM = "?utm_source=github&utm_medium=file-credit"

ROLES = "AI Automation Engineer, AI Tooling Engineer, AI Educator"

MD_MARKER = "<!-- author-credit -->"
MD_FOOTER = (
    f"{MD_MARKER}\n"
    "\n"
    "---\n"
    "\n"
    f"From [obsidian-second-brain]({REPO_URL}), created by Eugeniu Ghelbur ({ROLES}). "
    f"Questions or consulting: [LinkedIn]({LINKEDIN_URL}) or [{EMAIL}](mailto:{EMAIL}). "
    f"More: [The AI Operator]({SUBSTACK_URL}/{UTM}) | [X]({X_URL}) | [GitHub]({GITHUB_URL}). "
    "MIT license.\n"
)

CODE_HEADER = [
    "# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors",
    "# SPDX-License-Identifier: MIT",
    f"# Author: Eugeniu Ghelbur ({ROLES}), {REPO_URL}",
    f"# Questions or consulting: {EMAIL} | {LINKEDIN_URL} | More: {SUBSTACK_URL} | {X_URL}",
]
# Every line the header has ever started with, so a re-stamp removes an older
# wording cleanly and never eats the file's own first comment.
CODE_PREFIXES = (
    "# SPDX-",
    "# Author:",
    "# Author links:",
    "# Questions or consulting:",
    "# obsidian-second-brain by Eugeniu Ghelbur",
)

# Files that travel alone: the 49 commands, the specs commands link to, the
# skill manual, and every runnable script. Tests, docs-site pages, examples and
# generated dist/ are out of scope.
MD_PATHSPECS = ["commands/*.md", "references/*.md", "SKILL.md", "AI-FIRST.md", "architecture.md"]
CODE_PATHSPECS = [
    "scripts/*.py",
    "scripts/*.sh",
    "hooks/*.py",
    "hooks/*.sh",
    "adapters/*.sh",
    "integrations/*.py",
    "integrations/*.sh",
    "install.sh",
    "update.sh",
]


def tracked(pathspecs: list[str]) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--", *pathspecs],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return [REPO_ROOT / line for line in out.splitlines() if line]


def stamp_markdown(text: str) -> str:
    idx = text.find(MD_MARKER)
    body = text[:idx] if idx != -1 else text
    return body.rstrip("\n") + "\n\n" + MD_FOOTER


def stamp_code(text: str) -> str:
    lines = text.split("\n")
    head: list[str] = []
    if lines and lines[0].startswith("#!"):
        head, lines = [lines[0]], lines[1:]
    # Drop an existing header block, matched line by line on known prefixes.
    while lines and lines[0].startswith(CODE_PREFIXES):
        lines = lines[1:]
    return "\n".join(head + CODE_HEADER + lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="report files missing the credit")
    args = ap.parse_args()

    jobs = [(p, stamp_markdown) for p in tracked(MD_PATHSPECS)]
    jobs += [(p, stamp_code) for p in tracked(CODE_PATHSPECS)]

    stale: list[str] = []
    for path, fn in jobs:
        old = path.read_text(encoding="utf-8")
        new = fn(old)
        if new == old:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if args.check:
            stale.append(rel)
        else:
            path.write_text(new, encoding="utf-8")
            print(f"stamped {rel}")

    if args.check and stale:
        print("Missing or stale author credit. Run: uv run python scripts/stamp_credit.py")
        for rel in stale:
            print(f"  {rel}")
        return 1
    if args.check:
        print(f"author credit present in {len(jobs)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
