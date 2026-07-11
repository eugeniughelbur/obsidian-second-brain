"""Deterministic vault link-graph extractor for /obsidian-visualize.

Builds the note graph - nodes (notes), edges (resolved `[[wikilinks]]`), degree,
hubs, and orphans - in one pass, so the command does not have to read every note
into the model just to know what links to what. Claude then does the layout, the
canvas, and the interpretation; the counting is done here, fast and exactly.

Pure stdlib. Mirrors vault_health.py's link handling: code fences/inline code are
stripped before scanning (so example links don't count), and em/en dashes are
normalized so `[[A - B]]` resolves to a file named with an em/en dash too.

Usage:
    python scripts/link_graph.py --path "/path/to/vault" [--json]
    python scripts/link_graph.py --path "/path/to/vault" --scope "Some Note Title"

Output: JSON with nodes, edges, and stats (top hubs, orphans, dangling links).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKIP_DIRS = {".obsidian", ".git", ".trash", "_trash", ".claude", "_export", "templates", "node_modules"}

LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]*`")
TYPE_RE = re.compile(r"(?m)^type:\s*[\"']?([A-Za-z0-9_-]+)")
ALIAS_BLOCK_RE = re.compile(r"(?ms)^aliases:\s*\n((?:\s*-\s*.+\n?)+)")
ALIAS_INLINE_RE = re.compile(r"(?m)^aliases:\s*\[(.+)\]")
EM_DASH, EN_DASH = "\u2014", "\u2013"


def _norm(s: str) -> str:
    """Lowercase, dashes unified, separators flattened - the matching key for a title."""
    s = s.replace(EM_DASH, "-").replace(EN_DASH, "-")
    return re.sub(r"[\s_-]+", " ", s.strip().lower())


def _strip_code(text: str) -> str:
    return INLINE_CODE_RE.sub("", CODE_FENCE_RE.sub("", text))


def _frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[3:end]
    return ""


def _aliases(fm: str) -> list[str]:
    out: list[str] = []
    m = ALIAS_INLINE_RE.search(fm)
    if m:
        out += [a.strip().strip("\"'") for a in m.group(1).split(",")]
    m = ALIAS_BLOCK_RE.search(fm)
    if m:
        out += [ln.strip().lstrip("-").strip().strip("\"'") for ln in m.group(1).splitlines() if ln.strip()]
    return [a for a in out if a]


def _link_target(link: str) -> str:
    """Reduce a raw wikilink body to its target title: drop alias (|), anchor (#), path."""
    link = link.split("|", 1)[0].split("#", 1)[0].strip().rstrip("\\")
    if "/" in link:
        link = link.rsplit("/", 1)[-1]
    if link.endswith(".md"):
        link = link[:-3]
    return link


def build_graph(vault: Path, scope: str | None = None) -> dict:
    notes: dict[str, dict] = {}
    key_to_rel: dict[str, str] = {}

    for md in sorted(vault.rglob("*.md")):
        parts = md.relative_to(vault).parts
        if SKIP_DIRS & set(parts):
            continue
        rel = md.relative_to(vault).as_posix()
        try:
            text = md.read_text(encoding="utf-8-sig", errors="ignore")
        except OSError:
            continue
        fm = _frontmatter(text)
        tmatch = TYPE_RE.search(fm)
        note = {
            "path": rel,
            "title": md.stem,
            "type": tmatch.group(1) if tmatch else "",
            "folder": parts[0] if len(parts) > 1 else "",
            "content": _strip_code(text),
            "aliases": _aliases(fm),
        }
        notes[rel] = note
        key_to_rel.setdefault(_norm(md.stem), rel)
        for a in note["aliases"]:
            key_to_rel.setdefault(_norm(a), rel)

    edges: list[dict] = []
    dangling = 0
    indeg = {rel: 0 for rel in notes}
    outdeg = {rel: 0 for rel in notes}

    for rel, note in notes.items():
        seen: set[str] = set()
        for raw in LINK_RE.findall(note["content"]):
            target = key_to_rel.get(_norm(_link_target(raw)))
            if target is None:
                dangling += 1
                continue
            if target == rel or target in seen:
                continue
            seen.add(target)
            edges.append({"from": rel, "to": target})
            outdeg[rel] += 1
            indeg[target] += 1

    nodes = []
    for rel, note in notes.items():
        deg = indeg[rel] + outdeg[rel]
        nodes.append({
            "id": rel, "path": rel, "title": note["title"], "type": note["type"],
            "folder": note["folder"], "in": indeg[rel], "out": outdeg[rel], "degree": deg,
        })

    if scope:
        skey = _norm(scope)
        root = key_to_rel.get(skey)
        keep = set()
        if root:
            keep.add(root)
            for e in edges:
                if e["from"] == root:
                    keep.add(e["to"])
                if e["to"] == root:
                    keep.add(e["from"])
            second = set()
            for e in edges:
                if e["from"] in keep:
                    second.add(e["to"])
                if e["to"] in keep:
                    second.add(e["from"])
            keep |= second
        nodes = [n for n in nodes if n["id"] in keep]
        edges = [e for e in edges if e["from"] in keep and e["to"] in keep]

    ranked = sorted(nodes, key=lambda n: n["degree"], reverse=True)
    orphans = [n["path"] for n in nodes if n["degree"] == 0]
    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "orphan_count": len(orphans),
            "dangling_link_count": dangling,
            "top_hubs": [{"path": n["path"], "title": n["title"], "degree": n["degree"]} for n in ranked[:10]],
            "orphans": orphans[:50],
            "scope": scope or "full",
        },
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Extract the vault link graph as JSON")
    ap.add_argument("--path", required=True, help="Vault root")
    ap.add_argument("--scope", default=None, help="Center on one note title (2 hops); omit for full vault")
    ap.add_argument("--json", action="store_true", help="(default) emit JSON")
    args = ap.parse_args(argv[1:])

    vault = Path(args.path).expanduser().resolve()
    if not vault.is_dir():
        print(f"vault path does not exist: {vault}", file=sys.stderr)
        return 2
    graph = build_graph(vault, args.scope)
    print(json.dumps(graph, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
