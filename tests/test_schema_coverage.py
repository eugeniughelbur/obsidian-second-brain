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
# The folder map's entity rows ("Person (entity)", "Company (entity)", ...) list the
# kinds that live in an entities folder.
ENTITY_ROW_RE = re.compile(r"^\|\s*([^|(]+?)\s*\(entity\)\s*\|", re.MULTILINE)
# A command naming kinds in prose, e.g. "for each person/company/tool mentioned".
KIND_LIST_RE = re.compile(r"\bfor each ([a-z]+(?:/[a-z]+)+)")


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


def _entity_kinds() -> set[str]:
    folder_map = (REPO_ROOT / "references" / "folder-map.md").read_text(encoding="utf-8")
    rows = ENTITY_ROW_RE.findall(folder_map)
    assert rows, "references/folder-map.md has no `(entity)` row; update this test if it was renamed"
    return {k.strip().lower() for row in rows for k in row.split("/") if k.strip()}


def test_every_entity_kind_has_a_schema():
    """#274: the fence above only sees types spelled `type: x`. /obsidian-ingest creates
    a page "for each person/company/tool mentioned", naming the kinds in prose, so
    company and tool pages were written with no schema and nothing failed. Every kind
    the folder map files as an entity, and every entity kind a command lists, needs one."""
    rules = (REPO_ROOT / "references" / "ai-first-rules.md").read_text(encoding="utf-8")
    kinds = _entity_kinds()
    missing = [
        f"references/folder-map.md: entity kind `{k}` has no schema in ai-first-rules.md"
        for k in sorted(kinds)
        if f"### `type: {k}`" not in rules
    ]
    for md in sorted((REPO_ROOT / "commands").glob("*.md")):
        for listed in KIND_LIST_RE.findall(md.read_text(encoding="utf-8")):
            named = set(listed.split("/"))
            if not named & kinds:
                continue  # a list of something else, e.g. idea/framework/methodology
            for k in sorted(named):
                if f"### `type: {k}`" not in rules:
                    missing.append(f"{md.name}: entity kind `{k}` has no schema in ai-first-rules.md")
    assert missing == [], "\n".join(missing)
