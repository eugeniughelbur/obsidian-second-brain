"""Deterministic vault link-graph extractor for /obsidian-visualize.

Builds the note graph - nodes (notes), edges (resolved `[[wikilinks]]`), degree,
hubs, and orphans - in one pass, so the command does not have to read every note
into the model just to know what links to what. Claude then does the layout, the
canvas, and the interpretation; the counting is done here, fast and exactly.

Pure stdlib. Mirrors vault_health.py's link handling BY SHARING ITS PARTS (the
full-file index) and matching its rules exactly: code fences/inline code are
stripped before scanning, em/en dashes are normalized so `[[A - B]]` resolves to
a file named with an em/en dash, spaces vs hyphens are NOT flattened together
(Obsidian does not resolve `[[Foo Bar Baz]]` to `foo-bar-baz.md`, so neither do
we), links to real assets/folders are not dangling, and _CLAUDE.md's example
links are skipped. Two implementations of one rule always drift; a test pins
this one's counts to vault_health's (stress-test fix 7/24).

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

# Shared with the health check so the two tools cannot drift apart again.
from vault_health import index_vault_files

SKIP_DIRS = {".obsidian", ".git", ".trash", "_trash", ".claude", "_export", "templates", "node_modules"}


def _skipped(parts) -> bool:
    return any(p.lower() in SKIP_DIRS or p.lower().endswith("templates") for p in parts)

LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]*`")
TYPE_RE = re.compile(r"(?m)^type:\s*[\"']?([A-Za-z0-9_-]+)")
ALIAS_BLOCK_RE = re.compile(r"(?ms)^aliases:\s*\n((?:\s*-\s*.+\n?)+)")
ALIAS_INLINE_RE = re.compile(r"(?m)^aliases:\s*\[(.+)\]")
EM_DASH, EN_DASH = "\u2014", "\u2013"


def _norm(s: str) -> str:
    """Lowercase with em/en dashes unified to '-' - the matching key for a title.

    Spaces, hyphens and underscores are deliberately NOT flattened together:
    Obsidian does not resolve [[Foo Bar Baz]] to foo-bar-baz.md, and flattening
    them created phantom edges while hiding real broken links (341 of them on
    the audit's 3,000-note fixture)."""
    s = s.replace(EM_DASH, "-").replace(EN_DASH, "-")
    return re.sub(r"\s+", " ", s.strip().lower())


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
    relpath_to_rel: dict[str, str] = {}

    for md in sorted(vault.rglob("*.md")):
        parts = md.relative_to(vault).parts
        if _skipped(parts):
            continue
        if not md.is_file():
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
        relpath_to_rel[_norm(rel[:-3])] = rel
        for a in note["aliases"]:
            key_to_rel.setdefault(_norm(a), rel)

    # Shared with vault_health: lowercased rel paths + bare names of every real
    # vault file, so a link to Attachments/file.pdf is never "dangling".
    vault_files = index_vault_files(vault)
    vault_dirs: set[str] = set()
    for d in vault.rglob("*/"):
        dparts = d.relative_to(vault).parts
        if _skipped(dparts):
            continue
        vault_dirs.add(d.relative_to(vault).as_posix().lower())
        vault_dirs.add(d.name.lower())

    def _resolve(raw: str) -> str | None:
        body = raw.split("|", 1)[0].split("#", 1)[0].strip().rstrip("\\")
        if "/" in body:
            # [[Projects/ProjectX]] disambiguates twins by path: match the full
            # relative path first, basename only as a fallback.
            p = body[:-3] if body.lower().endswith(".md") else body
            hit = relpath_to_rel.get(_norm(p))
            if hit:
                return hit
        return key_to_rel.get(_norm(_link_target(raw)))

    edges: list[dict] = []
    dangling = 0
    indeg = {rel: 0 for rel in notes}
    outdeg = {rel: 0 for rel in notes}

    for rel, note in notes.items():
        # The operating manual's [[wikilinks]] are syntax demos, not references
        # (vault_health skips it the same way).
        if rel.rsplit("/", 1)[-1] == "_CLAUDE.md":
            continue
        seen: set[str] = set()
        for raw in LINK_RE.findall(note["content"]):
            target = _resolve(raw)
            if target is None:
                body = raw.split("|", 1)[0].split("#", 1)[0].strip().rstrip("\\")
                key = body.lower().rstrip("/")
                if key in vault_files or key in vault_dirs:
                    continue  # a real asset or folder-nav link, not a broken note link
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
