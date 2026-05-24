#!/usr/bin/env python3
"""
vault_health.py — Obsidian Second Brain Health Check

Audits an Obsidian vault for structural issues:
- Duplicate notes (same concept, multiple files)
- Orphaned notes (no incoming links)
- Stale tasks (overdue, no recent activity)
- Notes missing frontmatter
- Empty folders
- Broken internal links
- Templates left in notes (unfilled Templater syntax)

Usage:
    python vault_health.py --path ~/my-vault
    python vault_health.py --path ~/my-vault --json     # JSON output (for Claude)
"""

import argparse
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

TODAY = date.today()
EXCLUDE_DIRS = {".obsidian", ".trash", "_trash", ".git", "Templates"}
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
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


def load_vault(vault: Path) -> dict:
    notes = {}
    for md in vault.rglob("*.md"):
        parts = md.relative_to(vault).parts
        if any(p in EXCLUDE_DIRS for p in parts):
            continue
        rel = str(md.relative_to(vault))
        content = md.read_text(encoding="utf-8", errors="replace")
        fm_match = FRONTMATTER_RE.match(content)
        frontmatter = fm_match.group(1) if fm_match else ""
        links = [l.strip().rstrip("\\") for l in LINK_RE.findall(content)]
        due_match = DATE_RE.search(frontmatter)
        notes[rel] = {
            "path": md,
            "rel": rel,
            "stem": md.stem,
            "content": content,
            "frontmatter": frontmatter,
            "has_frontmatter": bool(fm_match),
            "links": links,
            "aliases": parse_aliases(frontmatter),
            "due": due_match.group(1) if due_match else None,
            "size": len(content),
        }
    return notes


def check_duplicates(notes: dict) -> list:
    issues = []
    stems = defaultdict(list)
    for rel, note in notes.items():
        norm = re.sub(r"\d{4}-\d{2}-\d{2}", "", note["stem"]).lower()
        norm = re.sub(r"[^a-z0-9 ]", " ", norm).strip()
        norm = re.sub(r"\s+", " ", norm)
        stems[norm].append(rel)
    for norm, files in stems.items():
        if len(files) > 1 and norm.strip():
            issues.append({
                "type": "duplicate",
                "severity": "warning",
                "message": f"Possible duplicates: {norm!r}",
                "files": files,
            })
    return issues


def check_orphans(notes: dict) -> list:
    all_links = set()
    for note in notes.values():
        for link in note["links"]:
            all_links.add(link.lower())
            all_links.add(link.lower().replace(" ", "-"))

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
        if not note["has_frontmatter"] and note["size"] > 50:
            issues.append({
                "type": "no_frontmatter",
                "severity": "warning",
                "message": f"Missing frontmatter: {rel}",
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


def check_broken_links(notes: dict, vault: Path) -> list:
    all_stems = {note["stem"].lower(): rel for rel, note in notes.items()}
    # build alias → rel lookup so [[Full Name]] resolves if the note has that alias
    all_aliases: dict[str, str] = {}
    for rel, note in notes.items():
        for alias in note["aliases"]:
            all_aliases[alias.lower()] = rel

    # Operating manuals contain example wikilinks like [[wikilinks]], [[Related Project]],
    # [[Links]] as syntax demonstrations, not as real references. Skip them from the
    # broken-link scan so they don't generate dozens of false positives per scan.
    SKIP_FROM_LINK_SCAN = {"_CLAUDE.md"}

    issues = []
    for rel, note in notes.items():
        if Path(rel).name in SKIP_FROM_LINK_SCAN:
            continue
        for link in note["links"]:
            link_stem = Path(link).stem.lower() if "/" in link else link.lower()
            link_norm = link_stem.replace("-", " ").replace("_", " ")
            resolved = (
                link_stem in all_stems
                or link_norm in all_stems
                or link_stem in all_aliases
                or link_norm in all_aliases
            )
            if not resolved:
                potential_folder = vault / link
                if not potential_folder.is_dir():
                    issues.append({
                        "type": "broken_link",
                        "severity": "warning",
                        "message": f"Broken link [[{link}]] in {rel}",
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
    print(f"🔍 Scanning vault: {vault}\n")
    notes = load_vault(vault)
    print(f"   Found {len(notes)} notes\n")

    checks = [
        ("Duplicates", check_duplicates(notes)),
        ("Orphans", check_orphans(notes)),
        ("Stale tasks", check_stale_tasks(notes)),
        ("Missing frontmatter", check_missing_frontmatter(notes)),
        ("Empty folders", check_empty_folders(vault)),
        ("Broken links", check_broken_links(notes, vault)),
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
    print(f"  VAULT HEALTH REPORT — {result['scanned']}")
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
