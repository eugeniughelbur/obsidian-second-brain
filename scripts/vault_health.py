#!/usr/bin/env python3
"""
vault_health.py - Obsidian Second Brain Health Check

Audits an Obsidian vault for structural issues:
- Duplicate notes (same concept, multiple files)
- Orphaned notes (no incoming links)
- Stale tasks (overdue, no recent activity)
- Notes missing frontmatter
- Notes with frontmatter trapped in a leading ```markdown code fence (unwrap, do not add)
- Empty folders
- Wanted notes (links to notes not written yet - a wishlist, not errors)
- Templates left in notes (unfilled Templater syntax)

Usage:
    python vault_health.py --path ~/my-vault
    python vault_health.py --path ~/my-vault --json     # JSON output (for Claude)
"""

import argparse
import difflib
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

TODAY = date.today()
EXCLUDE_DIRS = {
    ".obsidian",
    ".trash",
    "_trash",
    ".git",
    ".claude",
    ".agents",
    ".codex",
    "_export",
    "Templates",
}
FILE_INDEX_EXCLUDE_DIRS = EXCLUDE_DIRS - {"Templates"}
EXCLUDE_ROOT_FILES = {"AGENTS.md", "INSTALL.md"}
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
# A note whose entire body was accidentally saved inside a ```markdown code fence:
# the first non-blank line opens a fence and the real frontmatter (---) lives INSIDE it.
# This must be detected separately from genuinely-missing frontmatter, because the naive
# "add frontmatter" fix prepends a SECOND frontmatter block and leaves the body trapped
# in the fence (double corruption). The correct fix is to UNWRAP, not to add.
CODE_FENCE_WRAP_RE = re.compile(r"\A\s*```[^\n]*\n\s*---\s*\n")
LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
DATE_RE = re.compile(r"due:\s*(\d{4}-\d{2}-\d{2})")
TEMPLATE_RE = re.compile(r"<%.*?%>")
ALIAS_RE = re.compile(r"^aliases:\s*\n((?:\s+-\s+.+\n?)+)", re.MULTILINE)
ALIAS_ITEM_RE = re.compile(r"^\s+-\s+(.+)$", re.MULTILINE)


def parse_aliases(frontmatter: str) -> list:
    """Extract aliases list from frontmatter text."""
    block = ALIAS_RE.search(frontmatter)
    if not block:
        return []
    return [m.strip().strip('"\'').lower() for m in ALIAS_ITEM_RE.findall(block.group(1))]


def index_vault_files(vault: Path) -> set:
    """Lowercased relative paths and bare filenames of every non-excluded vault file.

    Wikilinks can target non-markdown assets ([[Bases/Tasks.base]], [[map.canvas]],
    [[control-center.html]]) or carry an explicit extension ([[_CLAUDE.md]]). The
    .md-note stem index alone cannot resolve those, so broken-link checks also
    consult this full-file index.
    """
    files = set()
    for f in vault.rglob("*"):
        parts = f.relative_to(vault).parts
        if any(p in FILE_INDEX_EXCLUDE_DIRS for p in parts):
            continue
        if len(parts) == 1 and parts[0] in EXCLUDE_ROOT_FILES:
            continue
        if not f.is_file():
            continue
        files.add(f.relative_to(vault).as_posix().lower())
        files.add(f.name.lower())
    return files


def load_vault(vault: Path) -> dict:
    notes = {}
    for md in vault.rglob("*.md"):
        parts = md.relative_to(vault).parts
        # Also skip any template folder (Templates, 20_Templates, ...): its
        # <%...%> Templater syntax is intentional, not a "template leftover" bug.
        if len(parts) == 1 and parts[0] in EXCLUDE_ROOT_FILES:
            continue
        if any(p in EXCLUDE_DIRS or p.lower().endswith("templates") for p in parts):
            continue
        rel = str(md.relative_to(vault))
        content = md.read_text(encoding="utf-8", errors="replace")
        fm_match = FRONTMATTER_RE.match(content)
        frontmatter = fm_match.group(1) if fm_match else ""
        # Strip fenced/inline code before extracting links so shell snippets like
        # `[[ -z "$VAR" ]]` are not stored as wikilinks. These links feed the orphan
        # check (all_links); leaving code noise in masks real orphans (issue #93).
        links = [l.strip().rstrip("\\") for l in LINK_RE.findall(_strip_code(content))]
        due_match = DATE_RE.search(frontmatter)
        notes[rel] = {
            "path": md,
            "rel": rel,
            "stem": md.stem,
            "content": content,
            "frontmatter": frontmatter,
            "has_frontmatter": bool(fm_match),
            "code_fence_wrapped": bool(not fm_match and CODE_FENCE_WRAP_RE.match(content)),
            "links": links,
            "aliases": parse_aliases(frontmatter),
            "due": due_match.group(1) if due_match else None,
            "size": len(content),
        }
    return notes


# Folders whose notes recur by date with a shared descriptive title (e.g. a
# "Weekly Review" every Friday). Same title across dates is expected here, not a
# duplicate, so they are exempt from duplicate detection (issue #82).
DATED_SERIES_FOLDERS = {"daily", "logs", "dev logs", "reviews"}


def _norm_title(stem: str) -> str:
    """Normalize a filename stem to a comparable title. Keeps digits and dates -
    the old version stripped ISO dates, which collapsed every dated note in a
    series onto one bucket and flagged them all as duplicates (issue #82)."""
    norm = re.sub(r"[^a-z0-9 ]", " ", stem.lower())
    return re.sub(r"\s+", " ", norm).strip()


def _max_pairwise_similarity(notes: dict, files: list) -> float:
    """Largest body-text similarity ratio among a set of notes (first 1000 chars).
    Used as the content signal that separates real duplicates from notes that
    merely share a title."""
    bodies = [notes[f]["content"][:1000] for f in files]
    best = 0.0
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            best = max(best, difflib.SequenceMatcher(None, bodies[i], bodies[j]).ratio())
    return best


def check_duplicates(notes: dict) -> list:
    issues = []
    groups = defaultdict(list)
    for rel, note in notes.items():
        parts = [p.lower() for p in rel.split("/")[:-1]]
        if any(p in DATED_SERIES_FOLDERS for p in parts):
            continue
        norm = _norm_title(note["stem"])
        if norm:
            groups[norm].append(rel)
    for norm, files in groups.items():
        if len(files) <= 1:
            continue
        # Content signal: high body similarity => likely a real duplicate
        # (warning); low => same title but different content (info, less noise).
        similar = _max_pairwise_similarity(notes, files) >= 0.6
        issues.append({
            "type": "duplicate",
            "severity": "warning" if similar else "info",
            "message": (
                f"{'Likely duplicates' if similar else 'Same title, different content'}: {norm!r}"
            ),
            "files": files,
        })
    return issues


def check_orphans(notes: dict) -> list:
    all_links = set()
    for note in notes.values():
        for link in note["links"]:
            lk = link.lower()
            # An incoming link may carry the .md extension ([[note.md]]); it still
            # targets the same note, so strip it before matching against stems.
            if lk.endswith(".md"):
                lk = lk[:-3]
            all_links.add(lk)
            all_links.add(lk.replace(" ", "-"))

    # also treat aliases as resolvable targets
    alias_set = set()
    for note in notes.values():
        for alias in note["aliases"]:
            alias_set.add(alias.lower())

    issues = []
    skip_folders = {"Daily", "Dev Logs", "Boards", "Templates", "Life Chapters",
                    "Faith", "Reviews", "Partner", "Family"}

    for rel, note in notes.items():
        top_folder = rel.split("/")[0] if "/" in rel else ""
        if top_folder in skip_folders:
            continue
        if rel in ("Home.md", "_CLAUDE.md"):
            continue
        stem_lower = note["stem"].lower()
        stem_norm = stem_lower.replace("-", " ").replace("_", " ")
        linked = (
            stem_lower in all_links
            or stem_norm in all_links
            or any(stem_lower in lk for lk in all_links)
            or any(alias in all_links for alias in note["aliases"])
        )
        if not linked:
            issues.append({
                "type": "orphan",
                "severity": "info",
                "message": f"No incoming links: {rel}",
                "files": [rel],
            })
    return issues


def check_stale_tasks(notes: dict) -> list:
    issues = []
    for rel, note in notes.items():
        if "task" not in note["frontmatter"].lower() and "kanban" not in note["content"][:200].lower():
            continue
        if note["due"]:
            try:
                due_date = date.fromisoformat(note["due"])
                if due_date < TODAY:
                    days_overdue = (TODAY - due_date).days
                    issues.append({
                        "type": "stale_task",
                        "severity": "warning" if days_overdue > 7 else "info",
                        "message": f"Overdue by {days_overdue}d: {rel}",
                        "files": [rel],
                        "due": note["due"],
                    })
            except ValueError:
                pass
    return issues


def check_missing_frontmatter(notes: dict) -> list:
    issues = []
    skip = {"Templates", "_trash", ".obsidian"}
    for rel, note in notes.items():
        if any(s in rel for s in skip):
            continue
        if rel in ("Home.md", "_CLAUDE.md"):
            continue
        if note.get("code_fence_wrapped"):
            # Reported by check_code_fence_wrapped instead. The frontmatter exists but is
            # trapped in a code fence - adding a new block here would duplicate it.
            continue
        if not note["has_frontmatter"] and note["size"] > 50:
            issues.append({
                "type": "no_frontmatter",
                "severity": "warning",
                "message": f"Missing frontmatter: {rel}",
                "files": [rel],
            })
    return issues


def check_code_fence_wrapped(notes: dict) -> list:
    """Notes whose frontmatter + body were accidentally saved inside a leading ```markdown
    code fence. Flagged separately (and as an error) because the fix is to UNWRAP the fence,
    NOT to add frontmatter - the naive add-frontmatter fix produces duplicate frontmatter."""
    issues = []
    skip = {"Templates", "_trash", ".obsidian"}
    for rel, note in notes.items():
        if any(s in rel for s in skip):
            continue
        if note.get("code_fence_wrapped"):
            issues.append({
                "type": "code_fence_wrapped",
                "severity": "error",
                "message": f"Frontmatter trapped in a code fence - unwrap, don't add: {rel}",
                "files": [rel],
            })
    return issues


def check_empty_folders(vault: Path) -> list:
    issues = []
    for folder in vault.rglob("*/"):
        if any(p in EXCLUDE_DIRS for p in folder.parts):
            continue
        if not folder.is_dir():
            continue
        if not list(folder.iterdir()):
            rel = str(folder.relative_to(vault))
            issues.append({
                "type": "empty_folder",
                "severity": "info",
                "message": f"Empty folder: {rel}/",
                "files": [],
            })
    return issues


# Built from code points so the source stays ASCII and the non-ASCII sweep
# (scripts/sweep_non_ascii.py) can never rewrite these operands again (#63).
_EM_DASH, _EN_DASH = "\u2014", "\u2013"


CODE_FENCE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def _strip_code(text: str) -> str:
    """Remove fenced code blocks and inline code so example/placeholder wikilinks
    inside them (`[[wikilinks]]`, `[[Related Project]]`) are not scanned as real
    links (issue #82)."""
    return INLINE_CODE_RE.sub("", CODE_FENCE_BLOCK_RE.sub("", text))


def _normalize_dashes(s: str) -> str:
    """Convert em-dash (U+2014) and en-dash (U+2013) to a regular hyphen.

    Vault naming conventions often use em-dashes in filenames (e.g.
    `2026-05-22 - Learnings Review.md`). Wikilinks that reference the same
    note with a regular hyphen (`[[2026-05-22 - Learnings Review]]`) should
    still resolve. Normalize both sides before comparison.
    """
    return s.replace(_EM_DASH, "-").replace(_EN_DASH, "-")


def check_wanted_notes(notes: dict, vault: Path) -> list:
    """Find links whose target note does not exist yet. These are NOT errors -
    in a wiki-style vault you link a thing the moment you mention it, long before
    (or instead of) writing its note. They are a demand-ranked wishlist of notes
    worth writing, so they are reported as info, not warnings. Named after
    MediaWiki's "Wanted pages"."""
    all_stems = {note["stem"].lower(): rel for rel, note in notes.items()}
    # Full-file index so links to non-markdown assets and links written with an
    # explicit extension resolve instead of being flagged broken.
    all_files = index_vault_files(vault)
    # also index stems with em-dashes normalized to regular hyphens so a
    # wikilink written with `-` still matches a filename written with `-`
    all_stems_dash_norm = {
        _normalize_dashes(note["stem"]).lower(): rel for rel, note in notes.items()
    }
    # build alias → rel lookup so [[Full Name]] resolves if the note has that alias
    all_aliases: dict[str, str] = {}
    for rel, note in notes.items():
        for alias in note["aliases"]:
            all_aliases[alias.lower()] = rel

    # Operating manuals contain example wikilinks like [[wikilinks]], [[Related Project]],
    # [[Links]] as syntax demonstrations, not as real references. Skip them from the
    # scan so they don't generate dozens of false positives per scan.
    SKIP_FROM_LINK_SCAN = {"_CLAUDE.md"}

    issues = []
    for rel, note in notes.items():
        if Path(rel).name in SKIP_FROM_LINK_SCAN:
            continue
        # Re-extract links from code-stripped content so example wikilinks inside
        # code fences / inline code are not counted (issue #82).
        real_links = [
            link.strip().rstrip("\\")
            for link in LINK_RE.findall(_strip_code(note["content"]))
        ]
        for link in real_links:
            # Wikilink targets carry no extension; Path.stem treats everything after
            # the last dot as a suffix and truncates titles like "release v2.4 notes"
            # -> "release v2", so path-form links to dotted titles never resolve
            # (issue #93). Take the last path component verbatim, stripping only a
            # literal .md if present.
            link_name = link.rsplit("/", 1)[-1]
            if link_name.lower().endswith(".md"):
                link_name = link_name[:-3]
            link_stem = link_name.lower()
            link_norm = link_stem.replace("-", " ").replace("_", " ")
            link_dash_norm = _normalize_dashes(link_stem)
            resolved = (
                link_stem in all_stems
                or link_norm in all_stems
                or link_stem in all_aliases
                or link_norm in all_aliases
                or link_dash_norm in all_stems_dash_norm
                or link.lower() in all_files
                or f"{link.lower()}.md" in all_files
            )
            if not resolved:
                potential_folder = vault / link
                if not potential_folder.is_dir():
                    issues.append({
                        "type": "wanted_note",
                        "severity": "info",
                        "message": f"[[{link}]] - wanted by {rel}",
                        "files": [rel],
                    })
    return issues


def check_template_leftovers(notes: dict) -> list:
    issues = []
    for rel, note in notes.items():
        # Skip files in any templates folder regardless of case.
        # Vault conventions vary: Templates/, templates/, etc.
        parts = rel.split("/")
        if any(p.lower() == "templates" for p in parts):
            continue
        if TEMPLATE_RE.search(note["content"]):
            issues.append({
                "type": "template_leftover",
                "severity": "error",
                "message": f"Unfilled template syntax in: {rel}",
                "files": [rel],
            })
    return issues


def run_health_check(vault: Path) -> dict:
    # Progress goes to stderr so `--json` stdout is clean and machine-parseable.
    print(f"🔍 Scanning vault: {vault}\n", file=sys.stderr)
    notes = load_vault(vault)
    print(f"   Found {len(notes)} notes\n", file=sys.stderr)

    checks = [
        ("Duplicates", check_duplicates(notes)),
        ("Orphans", check_orphans(notes)),
        ("Stale tasks", check_stale_tasks(notes)),
        ("Code-fence-wrapped notes", check_code_fence_wrapped(notes)),
        ("Missing frontmatter", check_missing_frontmatter(notes)),
        ("Empty folders", check_empty_folders(vault)),
        ("Wanted notes", check_wanted_notes(notes, vault)),
        ("Template leftovers", check_template_leftovers(notes)),
    ]

    all_issues = []
    counts = {}
    for label, issues in checks:
        counts[label] = len(issues)
        all_issues.extend(issues)

    return {
        "vault": str(vault),
        "scanned": TODAY.isoformat(),
        "total_notes": len(notes),
        "total_issues": len(all_issues),
        "counts": counts,
        "issues": all_issues,
    }


def print_report(result: dict):
    print("=" * 60)
    print(f"  VAULT HEALTH REPORT - {result['scanned']}")
    print("=" * 60)
    print(f"  Notes scanned: {result['total_notes']}")
    print(f"  Issues found:  {result['total_issues']}")
    print()

    if result["total_issues"] == 0:
        print("✅ Vault is clean. No issues found.")
        return

    severity_icon = {"error": "🔴", "warning": "🟡", "info": "⚪"}

    for label, count in result["counts"].items():
        if count > 0:
            print(f"  {label}: {count}")

    print()
    by_type = defaultdict(list)
    for issue in result["issues"]:
        by_type[issue["type"]].append(issue)

    for issue_type, issues in by_type.items():
        icon = severity_icon.get(issues[0]["severity"], "⚪")
        print(f"\n{icon} {issue_type.replace('_', ' ').title()} ({len(issues)})")
        print("-" * 50)
        for issue in issues[:10]:
            print(f"  {issue['message']}")
        if len(issues) > 10:
            print(f"  ... and {len(issues) - 10} more")

    print()
    print("=" * 60)
    print("Tip: run with --json for machine-readable output to pipe into Claude.")


def main():
    # Windows consoles often default to a legacy codepage (cp1252) that cannot
    # encode the report's emoji icons; degrade to replacement characters instead
    # of crashing. The platform encoding is kept so captured output stays decodable.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(description="Obsidian vault health checker")
    parser.add_argument("--path", required=True, help="Path to the vault")
    parser.add_argument("--json", action="store_true", help="Output as JSON (for Claude)")
    args = parser.parse_args()

    vault = Path(args.path).expanduser().resolve()
    if not vault.exists():
        print(f"❌ Vault not found: {vault}")
        return 1

    result = run_health_check(vault)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print_report(result)


if __name__ == "__main__":
    main()
