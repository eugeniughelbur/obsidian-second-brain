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

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

# Shared with the health check so the two tools cannot drift apart again.
from vault_health import index_vault_files
from vault_scan import BASE_EXCLUDE_DIRS  # noqa: E402

SKIP_DIRS = frozenset(d.lower() for d in BASE_EXCLUDE_DIRS)  # see scripts/vault_scan.py


def _skipped(parts) -> bool:
    return any(p.lower() in SKIP_DIRS or p.lower().endswith("templates") for p in parts)

LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
# Newline-bounded, matching vault_health.py:441. Without the \n exclusion one
# stray backtick in prose swallows every line up to the next one, so real
# [[links]] disappear from the graph and their targets look like orphans.
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
TYPE_RE = re.compile(r"(?m)^type:\s*[\"']?([A-Za-z0-9_-]+)")
ALIAS_BLOCK_RE = re.compile(r"(?ms)^aliases:\s*\n((?:\s*-\s*.+\n?)+)")
ALIAS_INLINE_RE = re.compile(r"(?m)^aliases:\s*\[(.+)\]")
EM_DASH, EN_DASH = "\u2014", "\u2013"

# Typed edges (graph engineering): the vault stores relationships as a named
# `relations:` frontmatter block, so a link stops being a generic "related" and
# becomes a traversable, interpretable edge (supersedes, depends_on, caused...).
# Each type maps to its inverse so linting can flag a missing reciprocal edge;
# a type whose inverse is itself is symmetric (relates_to, contradicts). The
# legacy top-level `supersedes:` scalar (already read by the search rerank and
# the ADR schema) is treated as an alias for `relations.supersedes`, so nothing
# that already writes it has to change.
EDGE_INVERSE = {
    "supersedes": "superseded_by",
    "superseded_by": "supersedes",
    "depends_on": "required_by",
    "required_by": "depends_on",
    "caused": "caused_by",
    "caused_by": "caused",
    "decided_by": "decides",
    "decides": "decided_by",
    "relates_to": "relates_to",
    "contradicts": "contradicts",
}
# Asymmetric ordering types: A->B and B->A of the SAME type is a logical
# contradiction (A supersedes B while B supersedes A), not just a missing inverse.
# Derived, not hand-maintained. This is exactly the set of types whose inverse
# is not itself, so listing it separately meant a contributor adding a new pair
# to EDGE_INVERSE and forgetting this line would make lint_graph silently stop
# detecting missing reciprocals for that type - no error, just a class of
# finding quietly gone.
ASYMMETRIC_TYPES = frozenset(t for t, inv in EDGE_INVERSE.items() if inv != t)
LEGACY_EDGE_KEYS = {"supersedes", "superseded_by"}
_REL_KEY_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*):(.*)$")
_WIKILINK_IN_RE = re.compile(r"\[\[([^\]|#]+)")


def _nfc(s: str) -> str:
    """Canonical (NFC) Unicode form - the comparison-boundary normalization that
    keeps an NFD filename (macOS stores decomposed) and an NFC wikilink (composed,
    as typed) from being read as two different titles. Mirrors vault_health._nfc so
    the graph resolves links exactly as the health check does (PR #161)."""
    return unicodedata.normalize("NFC", s)


def _norm(s: str) -> str:
    """Lowercase with em/en dashes unified to '-' - the matching key for a title.

    Normalized to NFC first so accented titles resolve regardless of composition
    (see _nfc). Spaces, hyphens and underscores are deliberately NOT flattened
    together: Obsidian does not resolve [[Foo Bar Baz]] to foo-bar-baz.md, and
    flattening them created phantom edges while hiding real broken links (341 of
    them on the audit's 3,000-note fixture)."""
    s = _nfc(s).replace(EM_DASH, "-").replace(EN_DASH, "-")
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


def _parse_relations(fm: str) -> list[tuple[str, str]]:
    """Pull (edge_type, target_title) pairs from a note's frontmatter.

    Reads two shapes so authors are not boxed in, without a YAML dependency:
      relations:
        supersedes: ["[[ADR-006]]"]
        depends_on:
          - "[[Projects/Tide Gateway]]"
    plus the legacy top-level scalar `supersedes: "[[...]]"` (equivalent to
    relations.supersedes). We only harvest the type name and the `[[targets]]`;
    quoting and list style are irrelevant. Types are NOT validated here - an
    unknown type is still returned so the linter can flag it by name."""
    pairs: list[tuple[str, str]] = []
    in_block = False
    current_type: str | None = None
    for line in fm.splitlines():
        if not line.strip():
            continue
        m = _REL_KEY_RE.match(line)
        if not in_block:
            if m and not m.group(1) and m.group(2) in LEGACY_EDGE_KEYS:
                pairs += [(m.group(2), t.strip()) for t in _WIKILINK_IN_RE.findall(m.group(3))]
            elif m and not m.group(1) and m.group(2) == "relations" and not m.group(3).strip():
                in_block, current_type = True, None
            continue
        # inside the relations block; a return to column 0 ends it
        if line[:1] not in (" ", "\t"):
            in_block = False
            if m and m.group(2) in LEGACY_EDGE_KEYS:
                pairs += [(m.group(2), t.strip()) for t in _WIKILINK_IN_RE.findall(m.group(3))]
            continue
        if line.lstrip().startswith("-"):
            if current_type:
                pairs += [(current_type, t.strip()) for t in _WIKILINK_IN_RE.findall(line)]
        elif m:
            current_type = m.group(2)
            pairs += [(current_type, t.strip()) for t in _WIKILINK_IN_RE.findall(m.group(3))]
    return pairs


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
            "relations": _parse_relations(fm),
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
        vault_dirs.add(_nfc(d.relative_to(vault).as_posix()).lower())
        vault_dirs.add(_nfc(d.name).lower())

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
                key = _nfc(body).lower().rstrip("/")
                if key in vault_files or key in vault_dirs:
                    continue  # a real asset or folder-nav link, not a broken note link
                dangling += 1
                continue
            if target == rel or target in seen:
                continue
            seen.add(target)
            edges.append({"from": rel, "to": target, "type": "link"})
            outdeg[rel] += 1
            indeg[target] += 1

    # Typed edges from `relations:` frontmatter: a semantic OVERLAY on the link
    # graph, not new connectivity. The underlying `[[target]]` already lives in
    # the frontmatter (which is part of content), so the body-link scan above
    # has already counted it toward degree - re-counting here would double it.
    # We only attach the edge's *type* and keep unhonored edges (unknown type,
    # unresolved target) for the linter instead of dropping them silently.
    typed_edges: list[dict] = []
    typed_problems: list[dict] = []
    for rel, note in notes.items():
        if rel.rsplit("/", 1)[-1] == "_CLAUDE.md":
            continue
        seen_typed: set[tuple[str, str]] = set()
        for etype, raw_target in note["relations"]:
            if etype not in EDGE_INVERSE:
                typed_problems.append({"note": rel, "type": etype, "target": raw_target,
                                       "problem": "unknown_type"})
                continue
            target = _resolve(raw_target)
            if target is None:
                typed_problems.append({"note": rel, "type": etype, "target": raw_target,
                                       "problem": "dangling_target"})
                continue
            if target == rel:
                typed_problems.append({"note": rel, "type": etype, "target": raw_target,
                                       "problem": "self_edge"})
                continue
            key = (etype, target)
            if key in seen_typed:
                continue
            seen_typed.add(key)
            typed_edges.append({"from": rel, "to": target, "type": etype})

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
        typed_edges = [e for e in typed_edges if e["from"] in keep and e["to"] in keep]
        typed_problems = [p for p in typed_problems if p["note"] in keep]

    ranked = sorted(nodes, key=lambda n: n["degree"], reverse=True)
    orphans = [n["path"] for n in nodes if n["degree"] == 0]
    return {
        "nodes": nodes,
        "edges": edges,
        "typed_edges": typed_edges,
        "typed_edge_problems": typed_problems,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "typed_edge_count": len(typed_edges),
            "orphan_count": len(orphans),
            "dangling_link_count": dangling,
            "top_hubs": [{"path": n["path"], "title": n["title"], "degree": n["degree"]} for n in ranked[:10]],
            "orphans": orphans[:50],
            "scope": scope or "full",
        },
    }


def lint_graph(graph: dict) -> dict:
    """Validate the typed-edge layer - the graph-linting step your notes graph
    otherwise never gets. Findings, most severe first:
      - contradiction (critical): A and B assert the SAME asymmetric type about
        each other (A supersedes B and B supersedes A).
      - unknown_type / dangling_target / self_edge (warning): a `relations:` edge
        the graph could not honor. Carried through from build_graph.
      - missing_inverse (info): A->B of a type whose reciprocal edge B->A is
        absent. Not wrong, but a one-directional edge is invisible from B."""
    findings: list[dict] = []
    typed = graph.get("typed_edges", [])
    present = {(e["from"], e["to"], e["type"]) for e in typed}

    for f, t, etype in sorted(present):
        inv = EDGE_INVERSE.get(etype)
        if etype in ASYMMETRIC_TYPES and (t, f, etype) in present:
            if f < t:  # report each contradicting pair once
                findings.append({
                    "severity": "critical", "kind": "contradiction",
                    "note": f, "target": t, "type": etype,
                    "detail": f"{f} and {t} both claim `{etype}` about each other",
                })
        if inv and (t, f, inv) not in present:
            findings.append({
                "severity": "info", "kind": "missing_inverse",
                "note": f, "target": t, "type": etype,
                "detail": f"{t} has no `{inv}` edge back to {f}",
            })

    for p in graph.get("typed_edge_problems", []):
        findings.append({
            "severity": "warning", "kind": p["problem"],
            "note": p["note"], "target": p["target"], "type": p["type"],
            "detail": {
                "unknown_type": f"`{p['type']}` is not a known relation type",
                "dangling_target": f"`{p['type']}` points at `{p['target']}` which does not resolve",
                "self_edge": f"`{p['type']}` points at the note itself",
            }.get(p["problem"], p["problem"]),
        })

    order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda x: order.get(x["severity"], 9))
    summary = {"critical": 0, "warning": 0, "info": 0}
    for f in findings:
        summary[f["severity"]] = summary.get(f["severity"], 0) + 1
    return {"findings": findings, "summary": summary,
            "typed_edge_count": len(typed), "known_types": sorted(EDGE_INVERSE)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Extract the vault link graph as JSON")
    ap.add_argument("--path", required=True, help="Vault root")
    ap.add_argument("--scope", default=None, help="Center on one note title (2 hops); omit for full vault")
    ap.add_argument("--json", action="store_true", help="(default) emit JSON")
    ap.add_argument("--lint", action="store_true",
                    help="Emit typed-edge lint findings instead of the full graph")
    args = ap.parse_args(argv[1:])

    vault = Path(args.path).expanduser().resolve()
    if not vault.is_dir():
        print(f"vault path does not exist: {vault}", file=sys.stderr)
        return 2
    graph = build_graph(vault, args.scope)
    out = lint_graph(graph) if args.lint else graph
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
