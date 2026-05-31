#!/usr/bin/env python3
"""
Sweep banned non-ASCII substitution characters from tracked repo files.
Dry-run by default; pass --apply to write changes.

Skips:
  - hooks/validate-ai-first.sh (detection dict contains intentional banned chars)
  - Lines inside Markdown code fences (``` / ~~~)
  - Inline backtick code spans within lines

Usage:
  python scripts/sweep_non_ascii.py                    # dry-run, show what would change
  python scripts/sweep_non_ascii.py --apply            # write changes
  python scripts/sweep_non_ascii.py --apply file.md    # single file
  python scripts/sweep_non_ascii.py --check            # CI gate: exit 1 if any prose violations

In --check mode the script exits non-zero when a banned substitution character
appears in prose (anything the sweep would rewrite). Characters inside code
fences and inline backtick spans are intentionally preserved and never fail the
check.
"""
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


def substitute(text: str) -> str:
    for ch, rep in SUBSTITUTIONS:
        text = text.replace(ch, rep)
    return text


def process_line(line: str, is_md: bool) -> str:
    if not is_md:
        return substitute(line)
    # Markdown: preserve inline code spans verbatim
    result = []
    last = 0
    for m in CODE_SPAN_RE.finditer(line):
        result.append(substitute(line[last:m.start()]))
        result.append(m.group(0))
        last = m.end()
    result.append(substitute(line[last:]))
    return ''.join(result)


def process_file(path: Path, apply: bool) -> tuple[int, int]:
    """Returns (lines_changed, lines_skipped_inside_fence)."""
    is_md = path.suffix == '.md'
    try:
        original = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return 0, 0

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
    apply = '--apply' in sys.argv
    check = '--check' in sys.argv
    extra_args = [a for a in sys.argv[1:] if not a.startswith('--')]

    if extra_args:
        files = [Path(f) for f in extra_args]
    else:
        result = subprocess.run(
            ['git', 'ls-files', '*.md', '*.py', '*.sh'],
            capture_output=True, text=True,
        )
        files = [Path(f) for f in result.stdout.splitlines() if f.strip()]

    total_changed = 0
    total_skipped = 0
    touched_files = 0

    for path in files:
        norm = str(path).replace('\\', '/')
        if any(norm == s or norm.endswith('/' + s) for s in SKIP_FILES):
            print(f'  skip   {path}  (exempted)')
            continue

        changed, skipped = process_file(path, apply)
        if changed or skipped:
            action = 'fixed ' if apply else 'would '
            print(f'  {action}  {path}  ({changed} line(s) changed, {skipped} skipped inside fence)')
            touched_files += 1
            total_changed += changed
            total_skipped += skipped

    if check:
        if total_changed > 0:
            print(
                f'\nCHECK FAILED: {total_changed} banned substitution character(s) in prose '
                f'across {touched_files} file(s).\n'
                f'Fix with: python scripts/sweep_non_ascii.py --apply'
            )
            return 1
        print(
            f'\nCHECK PASSED: no banned substitution characters in prose. '
            f'({total_skipped} preserved inside code fences/spans.)'
        )
        return 0

    mode = 'Applied' if apply else 'Dry-run'
    print(
        f'\n{mode}: {total_changed} line(s) across {touched_files} file(s). '
        f'{total_skipped} line(s) left untouched inside code fences -- review manually.'
    )
    if not apply:
        print('Run with --apply to write changes.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
