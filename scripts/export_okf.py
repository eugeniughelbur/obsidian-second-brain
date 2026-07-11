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
import html
import os
import re
import sys
import datetime
import pathlib

import yaml

FM_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)
WIKILINK_RE = re.compile(r"(!?)\[\[([^\]]+)\]\]")
# Compared lowercased; any folder ENDING in "templates" is also skipped (matching
# vault_health.load_vault), so the canonical capital Templates/ stays out too.
SKIP_DIRS = {".obsidian", "_export", ".git", ".trash", ".claude", "excalidraw"}
# frontmatter fields that point at a real external asset -> OKF `resource`
RESOURCE_KEYS = ("resource", "url", "source_url", "post-url", "post_url", "repo", "linkedin")


def _skipped(parts) -> bool:
    return any(p.lower() in SKIP_DIRS or p.lower().endswith("templates") for p in parts)


def parse_note(text):
    """Return (fm, body, malformed).

    malformed=True means the note HAS a frontmatter block we failed to parse
    (YAML error, or YAML that is not a mapping). The caller must warn and must
    not guess: the whole text rides along as body so no prose is dropped, and
    the type falls back to plain "note", never the folder name. A note with no
    frontmatter at all is NOT malformed - folder inference stays fair game."""
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
    s = html.unescape(s)  # decode &gt; &amp; &quot; etc. so markup-strip below catches them
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


# YAML indicator characters that are unsafe as the FIRST char of a plain scalar
_YAML_LEAD = set("&*@`!|>%?:#-[]{},\"'")


def yaml_val(v):
    """Render a value for OKF frontmatter (lists inline, strings quoted if needed).

    Quotes (and fully escapes) any scalar that YAML would otherwise misparse:
    values containing `: # "`, leading/trailing whitespace, an empty string, or a
    leading YAML indicator char (e.g. `@sentropic/...`, `&gt; ...`). In the quoted
    branch backslashes are escaped BEFORE quotes, so source `\\(` / `\\"` from
    markdown-escaped links stay valid inside a double-quoted YAML scalar.
    """
    if isinstance(v, list):
        return "[" + ", ".join(str(x) for x in v) + "]"
    s = str(v)
    if s == "" or s != s.strip() or (s[0] in _YAML_LEAD) or any(c in s for c in ':#"'):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
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

    # 1) collect notes (relative path -> (src_file, fm, body, malformed))
    notes = {}
    for f in vault.rglob("*.md"):
        rel = f.relative_to(vault)
        if _skipped(rel.parts):
            continue
        if str(rel).startswith(args.out):
            continue
        # The vault's own root index.md is navigation, not knowledge, and the
        # generated bundle index would overwrite its export anyway.
        if str(rel) == "index.md":
            continue
        # rglob matches names, not files: skip dangling symlinks and directories
        # named *.md instead of crashing the whole export (stress-test fix 2/24).
        if not f.is_file():
            continue
        try:
            fm, body, malformed = parse_note(f.read_text(encoding="utf-8-sig", errors="replace"))
        except OSError:
            continue
        if malformed:
            print(f"WARNING: malformed frontmatter in {rel} - exporting as type: note, "
                  f"body kept verbatim", file=sys.stderr)
        notes[str(rel)] = (f, fm, body, malformed)

    # 2) index note name -> output relative path (for wikilink resolution)
    name_to_rel = {}
    for rel in notes:
        stem = pathlib.PurePath(rel).stem
        name_to_rel.setdefault(stem.lower(), rel)
        fm = notes[rel][1]
        for a in (fm.get("aliases") or []):
            name_to_rel.setdefault(str(a).lower(), rel)

    # 2b) index real non-note vault files (pdf, png, canvas, ...) so links to
    # them export as links, exactly like embeds already do, instead of silently
    # degrading to plain text.
    asset_to_rel = {}
    for f in vault.rglob("*"):
        if not f.is_file() or f.suffix.lower() == ".md":
            continue
        arel = f.relative_to(vault)
        if _skipped(arel.parts) or str(arel).startswith(args.out):
            continue
        posix = str(arel).replace(os.sep, "/")
        asset_to_rel.setdefault(posix.lower(), posix)
        asset_to_rel.setdefault(arel.name.lower(), posix)

    def _link_name(target: str) -> str:
        """Basename with only a literal trailing .md stripped. Titles are not
        paths: PurePath.stem would truncate 'release v2.4 notes' to 'release v2'
        (the #93 regression, alive here until stress-test fix 5/24)."""
        base = target.rsplit("/", 1)[-1]
        return base[:-3] if base.lower().endswith(".md") else base

    def convert_links(body, from_rel):
        from_dir = pathlib.PurePath(from_rel).parent

        def repl(m):
            embed, inner = m.group(1), m.group(2)
            target = inner.split("|", 1)[0].split("#", 1)[0].strip()
            display = inner.split("|", 1)[1].strip() if "|" in inner else target
            tgt_rel = name_to_rel.get(_link_name(target).lower())
            if tgt_rel:
                relpath = os.path.relpath(tgt_rel, from_dir) if str(from_dir) != "." else tgt_rel
                relpath = relpath.replace(os.sep, "/")
                href = f"<{relpath}>" if " " in relpath else relpath
                return f"![{display}]({href})" if embed else f"[{display}]({href})"
            # a real vault file (asset) that just isn't a note: keep the link
            asset_rel = asset_to_rel.get(target.lower())
            if asset_rel:
                href = f"<{asset_rel}>" if " " in asset_rel else asset_rel
                return f"![{display}]({href})" if embed else f"[{display}]({href})"
            # truly unresolved: embed keeps the raw name, plain link degrades to text
            href = f"<{target}>" if " " in target else target
            return f"![{display}]({href})" if embed else display

        return WIKILINK_RE.sub(repl, body)

    # 3) write the bundle
    out.mkdir(parents=True, exist_ok=True)
    written = 0
    for rel, (src, fm, body, malformed) in sorted(notes.items()):
        title = (fm.get("title") or first_heading(body) or pathlib.PurePath(rel).stem)
        desc = clean_desc(str(fm.get("description") or first_paragraph(body)))
        # A failed parse means the note HAS a type we could not read - inferring
        # one from the folder would be a silent guess, so plain "note" it is.
        ntype = "note" if malformed else infer_type(fm, rel)
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
    for rel in notes:
        top = pathlib.PurePath(rel).parts[0] if len(pathlib.PurePath(rel).parts) > 1 else "."
        groups.setdefault(top, []).append(rel)
    # §6: index.md carries no frontmatter; §11: the bundle-root index MAY declare okf_version
    # (the only frontmatter key permitted in any index.md).
    idx = ['---', 'okf_version: "0.1"', "---", "",
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
        (out / "log.md").write_text(vlog.read_text(encoding="utf-8-sig", errors="replace"),
                                    encoding="utf-8")

    print(f"OKF bundle written: {out}")
    print(f"  {written} concept docs + index.md" + (" + log.md" if vlog.exists() else ""))


if __name__ == "__main__":
    main()
