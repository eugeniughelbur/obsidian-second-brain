#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""Migrate a monolithic vault log.md into per-day files under Logs/.

Splits the original log.md by `## [YYYY-MM-DD]` headers (brackets optional,
trailing text on the header line is ignored) into individual files named
`Logs/YYYY-MM-DD.md`, each with proper AI-first frontmatter. Replaces the
root log.md with a thin pointer file that documents the new structure and
ships the entry template.

Idempotent: skips dates whose target file already exists. Prints a summary.

Safety: log.md is only replaced with the pointer when EVERY dated section was
carried over. If any date was skipped because its target already existed, that
section still lives only in log.md, so overwriting it would destroy the sole
copy. In that case the original is left untouched and the run exits non-zero.

Usage:
    python scripts/migrate_log.py --vault /path/to/vault [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from note_io import write_exact  # noqa: E402

DATE_HEADER = re.compile(r"^##\s+\[?(\d{4}-\d{2}-\d{2})\]?[^\n]*", re.MULTILINE)
TEMPLATE_HEADER = re.compile(r"^##\s+Template\s*$", re.MULTILINE)

PER_DAY_FRONTMATTER = """---
type: log
date: {date}
ai-first: true
---

# Vault Operations - {date}

> For future agent: timestamped audit log of vault writes on this day. Append-only.

"""

ROOT_POINTER = """---
type: log-index
description: "Pointer to per-day vault operation logs under Logs/"
ai-first: true
---

# Vault Operation Log

> For future agent: vault operation history is split per-day under `Logs/YYYY-MM-DD.md`.
> Append today's entries to `Logs/{today}.md` (create the file if missing using the template below).
> Do not write entries into this file.

## Where to look

- **Today's writes** - `Logs/YYYY-MM-DD.md`
- **History** - `ls Logs/` then read the day(s) you need
- **Cross-day queries** - search `Logs/` directly, do not scan this file

## Per-day file template

When creating a new `Logs/YYYY-MM-DD.md`:

```markdown
---
type: log
date: YYYY-MM-DD
ai-first: true
---

# Vault Operations - YYYY-MM-DD

> For future agent: timestamped audit log of vault writes on this day. Append-only.

**HH:MM** - [Operation type]
- [What changed]
- [Files created/updated]
- [Linked items]
- [Notes]
```

Example entry:

```
**09:30** - Dev log for Project X
- Created Dev Logs/2026-05-06 - Project X.md
- Updated Projects/Project X.md with link to log
- Linked: [[Project X]]
```
"""


def split_log(text: str) -> dict[str, str]:
    """Return {date: body} for each `## [YYYY-MM-DD]` section in text.

    Handles both bare `## YYYY-MM-DD` and bracketed `## [YYYY-MM-DD] ...`
    formats; trailing content on the header line is excluded from the body.
    Stops a section at the next date header or at `## Template` (template
    section is dropped - it moves to the new root pointer file).
    """
    sections: dict[str, list[str]] = {}
    headers = list(DATE_HEADER.finditer(text))
    template_match = TEMPLATE_HEADER.search(text)
    template_pos = template_match.start() if template_match else len(text)

    for i, m in enumerate(headers):
        date = m.group(1)
        body_start = m.end()
        # Section ends at next date header or at the template marker
        next_header_pos = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body_end = min(next_header_pos, template_pos) if body_start < template_pos else next_header_pos
        body = text[body_start:body_end].strip()
        if body:
            sections.setdefault(date, []).append(body)

    # Concatenate duplicate-date sections (defensive - log.md may have repeats)
    return {date: "\n\n".join(parts) for date, parts in sections.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    # --path is the convention across every other script; accept both so a
    # wrapper passing --path does not break silently on this one.
    ap.add_argument("--vault", "--path", dest="vault", required=True, type=Path,
                    help="Path to vault root")
    ap.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    args = ap.parse_args()

    vault: Path = args.vault.resolve()
    log_path = vault / "log.md"
    logs_dir = vault / "Logs"

    if not log_path.is_file():
        print(f"error: {log_path} not found", file=sys.stderr)
        return 1

    text = log_path.read_text(encoding="utf-8-sig")
    sections = split_log(text)

    if not sections:
        print("error: no `## [YYYY-MM-DD]` sections found in log.md - nothing to migrate", file=sys.stderr)
        return 1

    newest = max(sections.keys())
    # The pointer tells future agent where TODAY's entries go, so it must carry
    # the current date, not the last date found in the legacy log. Using `newest`
    # here silently directed every future write into a stale day's file.
    today = _date.today().isoformat()
    print(f"Found {len(sections)} dated section(s): {min(sections)} ... {newest}")

    if not args.dry_run:
        logs_dir.mkdir(exist_ok=True)

    written = skipped = 0
    for date, body in sorted(sections.items()):
        target = logs_dir / f"{date}.md"
        if target.exists():
            print(f"  skip   Logs/{date}.md (exists)")
            skipped += 1
            continue
        content = PER_DAY_FRONTMATTER.format(date=date) + body + "\n"
        if args.dry_run:
            print(f"  would write Logs/{date}.md ({len(body)} chars)")
        else:
            write_exact(target, content)
            print(f"  wrote  Logs/{date}.md")
        written += 1

    # A skipped date was never carried over anywhere, so log.md still holds the
    # only copy of that section. Replacing it with the pointer would delete it.
    if skipped:
        print(
            f"\n{skipped} date(s) already existed under Logs/ and were NOT migrated.\n"
            "log.md is unchanged - it still holds the only copy of those sections.\n"
            "Resolve the collisions (merge or rename the existing files), then re-run.",
            file=sys.stderr,
        )
        print(f"Done. {written} file(s) written, {skipped} skipped. log.md left intact.")
        return 1

    pointer = ROOT_POINTER.format(today=today)
    if args.dry_run:
        print(f"  would replace log.md with pointer ({len(pointer)} chars)")
    else:
        write_exact(log_path, pointer)
        print("  wrote  log.md (pointer)")

    print(f"\nDone. {written} file(s) written, {skipped} skipped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
