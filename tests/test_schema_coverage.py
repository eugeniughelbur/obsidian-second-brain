"""Every note type a command mandates must have a schema (fix 20/24).

The audit found five note types that commands create with no schema in
ai-first-rules.md, so every writer improvised its own shape. This fence
cross-references the types commanded against the constitution.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

TYPE_RE = re.compile(r"`type: ([a-z][a-z0-9-]*)`")
# Frontmatter *values* that look like types but are field values, not note types.
NOT_TYPES = {"board"}


def test_every_commanded_type_has_a_schema():
    rules = (REPO_ROOT / "references" / "ai-first-rules.md").read_text(encoding="utf-8")
    missing: list[str] = []
    for md in sorted((REPO_ROOT / "commands").glob("*.md")):
        for t in set(TYPE_RE.findall(md.read_text(encoding="utf-8"))):
            if t in NOT_TYPES:
                continue
            if f"type: {t}" not in rules:
                missing.append(f"{md.name}: `type: {t}` has no schema in ai-first-rules.md")
    assert missing == [], "\n".join(missing)
