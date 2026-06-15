# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""
export_okf.py - export an Obsidian vault as an OKF (Open Knowledge Format) bundle.

OKF (Google Cloud's Open Knowledge Format, v0.1) is "folders of markdown with minimal
YAML frontmatter" - a vendor-neutral way to hand a knowledge corpus to any AI agent.
An obsidian-second-brain vault is already ~90% OKF; this emits a compliant bundle so the
vault "speaks the standard" without changing how it works natively.

What it does, per note:
  - frontmatter -> OKF fields: `type` (required), `title`, `description`, `resource`
    (only if the note actually has a source/url), `tags`, `timestamp` (ISO-8601)
  - `[[wikilinks]]` -> relative-path markdown links (OKF's cross-link convention);
    unresolved links degrade to plain text, embeds (`![[x]]`) keep a relative path
  - the full AI-first body (incl. the `## For future Claude` preamble) is preserved -
    OKF is minimally opinionated, so the richer content rides along
Plus a generated `index.md` (progressive disclosure) and a copied `log.md` if present.

Usage:
  uv run scripts/export_okf.py --path "/path/to/Vault" [--out _export/okf]
"""
import argparse
import os
import re
import sys
import datetime
import pathlib

import yaml

FM_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)
WIKILINK_RE = re.compile(r"(!?)\[\[([^\]]+)\]\]")
SKIP_DIRS = {".obsidian", "_export", ".git", ".trash", "templates", "Excalidraw"}
# frontmatter fields that point at a real external asset -> OKF `resource`
RESOURCE_KEYS = ("resource", "url", "source_url", "post-url", "post_url", "repo", "linkedin")


def parse_note(text):
    m = FM_RE.match(text)
    if m:
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except Exception:
            fm = {}
        body = m.group(2)
    else:
        fm, body = {}, text
    return (fm if isinstance(fm, dict) else {}), body


def first_heading(body):
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return None


def first_paragraph(body):
    para = []
    for line in body.splitlines():
        s = line.strip()
        if not s:
            if para:
                break
            continue
        if s.startswith(("#", ">", "-", "*", "|", "```")):
            if para:
                break
            continue
        para.append(s)
    return " ".join(para)


def clean_desc(s):
    """Plain-text, link-free, word-boundary-trimmed description for OKF frontmatter."""
    def _wl(m):
        inner = m.group(2)
        disp = inner.split("|", 1)[1] if "|" in inner else inner
        return disp.split("#", 1)[0].strip()
    s = WIKILINK_RE.sub(_wl, s)
    s = re.sub(r"[*_`>#]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > 200:
        s = s[:200].rsplit(" ", 1)[0].rstrip(",.;:") + "..."
    return s


def to_iso(fm, src_file):
    d = fm.get("date")
    t = fm.get("time")
    if d:
        ds = str(d)
        if t:
            ts = str(t)
            return f"{ds}T{ts}:00Z" if len(ts) <= 5 else f"{ds}T{ts}Z"
        return f"{ds}T00:00:00Z"
    mtime = datetime.datetime.fromtimestamp(src_file.stat().st_mtime, datetime.timezone.utc)
    return mtime.strftime("%Y-%m-%dT%H:%M:%SZ")


def infer_type(fm, rel):
    t = fm.get("type")
    if t:
        return str(t)
    parts = pathlib.PurePath(rel).parts
    if len(parts) >= 2:
        folder = parts[-2].lower()
        singular = {"entities": "entity", "projects": "project", "concepts": "concept",
                    "daily": "daily", "meetings": "meeting", "decisions": "decision",
                    "tasks": "task", "logs": "log"}.get(folder, folder.rstrip("s") or "note")
        return singular
    return "note"


def yaml_val(v):
    """Render a value for OKF frontmatter (lists inline, strings quoted if needed)."""
    if isinstance(v, list):
        return "[" + ", ".join(str(x) for x in v) + "]"
    s = str(v)
    if any(c in s for c in ':#"') or s != s.strip():
        return '"' + s.replace('"', '\\"') + '"'
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--out", default="_export/okf")
    args = ap.parse_args()
    vault = pathlib.Path(args.path).expanduser()
    if not vault.is_dir():
        print(f"vault not found: {vault}", file=sys.stderr)
        sys.exit(1)
    out = (vault / args.out) if not os.path.isabs(args.out) else pathlib.Path(args.out)

    # 1) collect notes (relative path -> (src_file, fm, body))
    notes = {}
    for f in vault.rglob("*.md"):
        rel = f.relative_to(vault)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if str(rel).startswith(args.out):
            continue
        fm, body = parse_note(f.read_text(encoding="utf-8", errors="replace"))
        notes[str(rel)] = (f, fm, body)

    # 2) index note name -> output relative path (for wikilink resolution)
    name_to_rel = {}
    for rel in notes:
        stem = pathlib.PurePath(rel).stem
        name_to_rel.setdefault(stem.lower(), rel)
        fm = notes[rel][1]
        for a in (fm.get("aliases") or []):
            name_to_rel.setdefault(str(a).lower(), rel)

    def convert_links(body, from_rel):
        from_dir = pathlib.PurePath(from_rel).parent

        def repl(m):
            embed, inner = m.group(1), m.group(2)
            target = inner.split("|", 1)[0].split("#", 1)[0].strip()
            display = inner.split("|", 1)[1].strip() if "|" in inner else target
            tgt_rel = name_to_rel.get(pathlib.PurePath(target).stem.lower())
            if tgt_rel:
                relpath = os.path.relpath(tgt_rel, from_dir) if str(from_dir) != "." else tgt_rel
                relpath = relpath.replace(os.sep, "/")
                href = f"<{relpath}>" if " " in relpath else relpath
                return f"![{display}]({href})" if embed else f"[{display}]({href})"
            # unresolved: embed keeps the raw name, plain link degrades to text
            href = f"<{target}>" if " " in target else target
            return f"![{display}]({href})" if embed else display

        return WIKILINK_RE.sub(repl, body)

    # 3) write the bundle
    out.mkdir(parents=True, exist_ok=True)
    written = 0
    for rel, (src, fm, body) in sorted(notes.items()):
        title = (fm.get("title") or first_heading(body) or pathlib.PurePath(rel).stem)
        desc = clean_desc(str(fm.get("description") or first_paragraph(body)))
        ntype = infer_type(fm, rel)
        tags = fm.get("tags") or []
        resource = next((str(fm[k]) for k in RESOURCE_KEYS if fm.get(k)), None)

        lines = ["---", f"type: {yaml_val(ntype)}", f"title: {yaml_val(title)}"]
        if desc:
            lines.append(f"description: {yaml_val(desc)}")
        if resource:
            lines.append(f"resource: {yaml_val(resource)}")
        if tags:
            lines.append(f"tags: {yaml_val(tags)}")
        lines.append(f"timestamp: {to_iso(fm, src)}")
        lines.append("---\n")
        fmblock = "\n".join(lines)

        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(fmblock + convert_links(body, rel).lstrip("\n"), encoding="utf-8")
        written += 1

    # 4) index.md (progressive disclosure) grouped by top-level folder
    groups = {}
    for rel, (src, fm, body) in notes.items():
        top = pathlib.PurePath(rel).parts[0] if len(pathlib.PurePath(rel).parts) > 1 else "."
        groups.setdefault(top, []).append(rel)
    idx = ["---", "type: index", f"title: {yaml_val(vault.name + ' (OKF bundle)')}",
           f"timestamp: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}", "---", "",
           f"# {vault.name} - OKF bundle", "",
           f"{written} concepts. Exported by obsidian-second-brain (OKF v0.1 compatible).", ""]
    for top in sorted(groups):
        idx.append(f"## {top}")
        idx.append("")
        for rel in sorted(groups[top]):
            title = pathlib.PurePath(rel).stem
            idx.append(f"- [{title}]({rel.replace(os.sep, '/')})")
        idx.append("")
    (out / "index.md").write_text("\n".join(idx), encoding="utf-8")

    # 5) copy log.md if the vault has one
    vlog = vault / "log.md"
    if vlog.exists():
        (out / "log.md").write_text(vlog.read_text(encoding="utf-8", errors="replace"),
                                    encoding="utf-8")

    print(f"OKF bundle written: {out}")
    print(f"  {written} concept docs + index.md" + (" + log.md" if vlog.exists() else ""))


if __name__ == "__main__":
    main()
