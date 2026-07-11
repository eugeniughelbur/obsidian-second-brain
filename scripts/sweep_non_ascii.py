#!/usr/bin/env python3
"""
Sweep banned non-ASCII substitution characters from tracked repo files.
Dry-run by default; pass --apply to write changes.

Skips:
  - hooks/validate-ai-first.sh (detection dict contains intentional banned chars)
  - Lines inside Markdown code fences (``` / ~~~)
  - Inline backtick code spans within lines
  - [[wikilink]] interiors: a dash inside a link is part of a FILENAME, not
    typography - substituting it breaks the link

Usage:
  python scripts/sweep_non_ascii.py                    # dry-run, show what would change
  python scripts/sweep_non_ascii.py --apply            # write changes
  python scripts/sweep_non_ascii.py --apply file.md    # single file
  python scripts/sweep_non_ascii.py --check            # CI gate: exit 1 if any prose violations

In --check mode the script exits non-zero when a banned substitution character
appears in prose (anything the sweep would rewrite). Characters inside code
fences, inline backtick spans, and wikilinks are intentionally preserved and
never fail the check. Files that cannot be decoded are WARNED about and counted
- an unchecked file must never silently read as a passed one.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

SUBSTITUTIONS = [
    ('—', '-'),  # — em-dash
    ('–', '-'),  # – en-dash
    ('“', '"'),    # " left double quote
    ('”', '"'),    # " right double quote
    ('‘', "'"),    # ' left single quote
    ('’', "'"),    # ' right single quote
    ('≥', '>='),   # ≥
    ('≤', '<='),   # ≤
    ('≠', '!='),   # ≠
    ('…', '...'),  # … ellipsis
    (' ', ' '),    # non-breaking space
]

# Files with intentional banned chars (e.g. detection dict keys)
SKIP_FILES = {'hooks/validate-ai-first.sh', 'scripts/sweep_non_ascii.py', 'README.md'}

CODE_SPAN_RE = re.compile(r'(`+)(.+?)\1', re.DOTALL)
FENCE_RE = re.compile(r'^[ \t]*(`{3,}|~{3,})')
WIKILINK_RE = re.compile(r'\[\[[^\]]*\]\]')


def substitute(text: str) -> str:
    for ch, rep in SUBSTITUTIONS:
        text = text.replace(ch, rep)
    return text


def _substitute_outside_wikilinks(text: str) -> str:
    """Substitute everywhere except inside [[...]]: the characters in a link
    target are part of a filename, and rewriting them breaks the link."""
    result = []
    last = 0
    for m in WIKILINK_RE.finditer(text):
        result.append(substitute(text[last:m.start()]))
        result.append(m.group(0))
        last = m.end()
    result.append(substitute(text[last:]))
    return ''.join(result)


def process_line(line: str, is_md: bool) -> str:
    if not is_md:
        return substitute(line)
    # Markdown: preserve inline code spans and wikilink interiors verbatim
    result = []
    last = 0
    for m in CODE_SPAN_RE.finditer(line):
        result.append(_substitute_outside_wikilinks(line[last:m.start()]))
        result.append(m.group(0))
        last = m.end()
    result.append(_substitute_outside_wikilinks(line[last:]))
    return ''.join(result)


def process_file(path: Path, apply: bool) -> tuple[int, int]:
    """Returns (lines_changed, lines_skipped_inside_fence).

    Raises OSError/UnicodeDecodeError to the caller: an unreadable file must be
    reported, never silently counted as clean (a banned char in it would pass
    the --check CI gate unseen)."""
    is_md = path.suffix == '.md'
    original = path.read_text(encoding='utf-8')

    out_lines = []
    in_fence = False
    fence_char = ''
    changed = 0
    skipped = 0

    for line in original.splitlines(keepends=True):
        if is_md:
            m = FENCE_RE.match(line)
            if m:
                marker = m.group(1)
                if not in_fence:
                    in_fence = True
                    fence_char = marker[0]
                elif marker[0] == fence_char:
                    in_fence = False
                out_lines.append(line)
                continue
            if in_fence:
                skipped += any(ch in line for ch, _ in SUBSTITUTIONS)
                out_lines.append(line)
                continue

        new_line = process_line(line, is_md)
        if new_line != line:
            changed += 1
        out_lines.append(new_line)

    new_content = ''.join(out_lines)
    if apply and new_content != original:
        path.write_text(new_content, encoding='utf-8')

    return changed, skipped


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Sweep banned non-ASCII substitution characters from tracked repo files."
    )
    ap.add_argument('files', nargs='*', help='specific files (default: all tracked md/py/sh)')
    ap.add_argument('--apply', action='store_true', help='write changes (default: dry-run)')
    ap.add_argument('--check', action='store_true',
                    help='CI gate: exit 1 if any prose violations')
    args = ap.parse_args()

    if args.files:
        files = [Path(f) for f in args.files]
    else:
        # core.quotepath=false: git otherwise octal-escapes and quotes non-ASCII
        # filenames, and the quoted string is not a real path - the sweep then
        # warns 'unreadable' on files that exist (seen on CI with the sample
        # vault's em-dash filenames).
        result = subprocess.run(
            ['git', '-c', 'core.quotepath=false', 'ls-files', '*.md', '*.py', '*.sh'],
            capture_output=True, text=True,
        )
        files = [Path(f) for f in result.stdout.splitlines() if f.strip()]

    total_changed = 0
    total_skipped = 0
    touched_files = 0
    unreadable = 0

    for path in files:
        norm = str(path).replace('\\', '/')
        if any(norm == s or norm.endswith('/' + s) for s in SKIP_FILES):
            print(f'  skip   {path}  (exempted)')
            continue

        try:
            changed, skipped = process_file(path, args.apply)
        except (OSError, UnicodeDecodeError) as exc:
            print(f'  WARN   {path}  (unreadable, NOT checked: {exc.__class__.__name__})',
                  file=sys.stderr)
            unreadable += 1
            continue
        if changed or skipped:
            action = 'fixed ' if args.apply else 'would '
            print(f'  {action}  {path}  ({changed} line(s) changed, {skipped} skipped inside fence)')
            touched_files += 1
            total_changed += changed
            total_skipped += skipped

    unreadable_note = (
        f' WARNING: {unreadable} file(s) unreadable and NOT checked.' if unreadable else ''
    )
    if args.check:
        if total_changed > 0:
            print(
                f'\nCHECK FAILED: {total_changed} banned substitution character(s) in prose '
                f'across {touched_files} file(s).\n'
                f'Fix with: python scripts/sweep_non_ascii.py --apply'
            )
            return 1
        print(
            f'\nCHECK PASSED: no banned substitution characters in prose. '
            f'({total_skipped} preserved inside code fences/spans.)' + unreadable_note
        )
        return 0

    mode = 'Applied' if args.apply else 'Dry-run'
    print(
        f'\n{mode}: {total_changed} line(s) across {touched_files} file(s). '
        f'{total_skipped} line(s) left untouched inside code fences -- review manually.'
        + unreadable_note
    )
    if not args.apply:
        print('Run with --apply to write changes.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
