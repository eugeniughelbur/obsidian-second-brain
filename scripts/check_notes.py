#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""check_notes.py - run the AI-first write check on notes an agent just wrote.

Claude Code checks every vault write through the PostToolUse hook
(hooks/validate-ai-first.sh). Hosts with no hook runtime - Grok Bot, a cron
agent, a script that patches files directly - wrote notes nothing ever checked.
This runs the SAME hook over a list of files, so every writer is held to one
rule set instead of a second copy that drifts.

    python scripts/check_notes.py --path "/vault" "wiki/entities/Ada.md" ...
    python scripts/check_notes.py --path "/vault" --changed          # git-dirty notes
    python scripts/check_notes.py --path "/vault" --changed --fix    # fix safe chars first

--fix rewrites only the banned substitution characters (em/en-dashes, curly
quotes, ellipsis, Unicode math, NBSP) to ASCII, the same table as
scripts/sweep_non_ascii.py. It leaves code fences, inline code, wikilink
targets, and any line with CJK text alone - there those characters are the
language's own punctuation (#271). Everything else the hook reports (missing
frontmatter, missing preamble, bad tags, secrets) needs judgment, so it is
reported, never auto-fixed.

Prints JSON {checked, fixed, failed: [{path, issues}]}. Exit 1 when any note
still fails, so an agent can gate its commit on it.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from note_io import NoteChangedError, read_exact, write_exact_if_unchanged
from sweep_non_ascii import FENCE_RE, SUBSTITUTIONS, process_line

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "hooks" / "validate-ai-first.sh"
# By path, not a bare name: on Windows a bare "bash" resolves to WSL's launcher
# in System32, which cannot read a Windows script path (#308).
BASH = shutil.which("bash") or "bash"

# Same Han/kana/Hangul/fullwidth ranges as the hook's CJK_RE, so --fix skips
# exactly the lines the hook exempts.
CJK_RANGES = (
    (0x1100, 0x11FF), (0x3000, 0x303F), (0x3040, 0x30FF), (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF), (0xA960, 0xA97F), (0xAC00, 0xD7AF), (0xF900, 0xFAFF),
    (0xFF00, 0xFFEF), (0x20000, 0x2FA1F),
)


def _has_cjk(line: str) -> bool:
    return any(lo <= ord(ch) <= hi for ch in line for lo, hi in CJK_RANGES)


def fix_chars(path: Path) -> int:
    """Rewrite banned substitution characters in place. Returns lines changed."""
    original = read_exact(path)
    if original is None:
        return 0
    out, changed, fence = [], 0, ""
    for line in original.splitlines(keepends=True):
        m = FENCE_RE.match(line)
        if m:
            marker = m.group(1)[0]
            fence = "" if fence == marker else (fence or marker)
            out.append(line)
            continue
        if fence or _has_cjk(line) or not any(ch in line for ch, _ in SUBSTITUTIONS):
            out.append(line)
            continue
        new = process_line(line, True)
        changed += new != line
        out.append(new)
    if changed:
        write_exact_if_unchanged(path, "".join(out), original)
    return changed


def hook_issues(vault: Path, note: Path) -> list:
    """The hook's warning lines for one note, or [] when it passes."""
    result = subprocess.run(
        [BASH, str(HOOK)],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(note)}}),
        env=dict(os.environ, OBSIDIAN_VAULT_PATH=str(vault)),
        capture_output=True, text=True,
    )
    if not result.stdout.strip():
        return []
    try:
        msg = json.loads(result.stdout)["systemMessage"]
    except (ValueError, KeyError):
        return [result.stdout.strip()]
    lines = [ln.strip() for ln in msg.splitlines()]
    return [ln.lstrip("- ").strip() for ln in lines if ln.startswith("-")] or [msg]


def changed_notes(vault: Path) -> list:
    """Markdown files git reports as modified, added, or untracked in the vault."""
    out = subprocess.run(
        ["git", "-C", str(vault), "-c", "core.quotepath=false",
         "status", "--porcelain", "-z", "--untracked-files=all"],
        capture_output=True, text=True,
    ).stdout
    entries = iter(out.split("\0"))
    paths = []
    for entry in entries:
        code, rel = entry[:2], entry[3:]
        if "R" in code or "C" in code:
            next(entries, None)  # -z puts a rename's old path in its own entry
        if "D" not in code and code.strip() and rel.endswith(".md"):
            paths.append(rel)
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description="AI-first write check for hook-less agents")
    ap.add_argument("--path", required=True, help="vault root")
    ap.add_argument("files", nargs="*", help="notes to check, vault-relative or absolute")
    ap.add_argument("--changed", action="store_true", help="also check git-dirty notes")
    ap.add_argument("--fix", action="store_true", help="fix banned characters first")
    args = ap.parse_args()

    vault = Path(args.path).expanduser().resolve()
    rels = list(args.files) + (changed_notes(vault) if args.changed else [])
    notes = []
    for rel in dict.fromkeys(rels):
        p = Path(rel) if Path(rel).is_absolute() else vault / rel
        if p.suffix == ".md" and p.is_file():
            notes.append(p.resolve())

    fixed, failed = [], []
    for note in notes:
        shown = note.relative_to(vault).as_posix() if note.is_relative_to(vault) else str(note)
        if args.fix:
            try:
                if fix_chars(note):
                    fixed.append(shown)
            except NoteChangedError:
                failed.append({"path": shown, "issues": ["changed on disk during fix, re-run"]})
                continue
        issues = hook_issues(vault, note)
        if issues:
            failed.append({"path": shown, "issues": issues})

    print(json.dumps({"checked": len(notes), "fixed": fixed, "failed": failed}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
