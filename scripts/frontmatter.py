"""Frontmatter parsing shared by the vault scripts.

Moved out of the former export_okf.py so merge_notes.py keeps one parser after
the export command was removed.
"""

import re

import yaml

FM_RE = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n)?(.*)$", re.DOTALL)


def parse_note(text):
    """Return (fm, body, malformed).

    malformed=True means the note HAS a frontmatter block we failed to parse
    (YAML error, or YAML that is not a mapping). The caller must warn and must
    not guess: the whole text rides along as body so no prose is dropped.
    A note with no frontmatter at all is NOT malformed.
    """
    if text.startswith("﻿"):
        text = text[1:]
    m = FM_RE.match(text)
    if not m:
        return {}, text, False
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception:
        return {}, text, True
    if not isinstance(fm, dict):
        return {}, text, True
    return fm, m.group(2), False
