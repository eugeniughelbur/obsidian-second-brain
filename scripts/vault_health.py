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

Optional per-vault config at `<vault>/.vault-config.json` extends the built-in
exclude list (additive, never overrides the hardcoded EXCLUDE_DIRS):
    {
      "exclude-dirs":  ["_card-pool", "_candidates"],  # dir names anywhere in the tree
      "exclude-paths": ["Archive/Backup"]              # vault-relative path prefixes
    }
A missing or malformed file is ignored silently. See VaultExcludes.
"""

import argparse
import difflib
import fnmatch
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
ALIAS_INLINE_RE = re.compile(r"^aliases:\s*\[(.+)\]\s*$", re.MULTILINE)


def parse_aliases(frontmatter: str) -> list:
    """Extract aliases from frontmatter text - block style AND inline style.

    Inline `aliases: [X, Y]` is at least as common in Obsidian vaults as the
    block form; reading only the block style silently lost aliases, so links to
    them rang as broken (gap found during stress-test fix 4, closed in 8/24)."""
    m = ALIAS_INLINE_RE.search(frontmatter)
    if m:
        return [a.strip().strip('"\'').lower() for a in m.group(1).split(",") if a.strip()]
    block = ALIAS_RE.search(frontmatter)
    if not block:
        return []
    return [m.strip().strip('"\'').lower() for m in ALIAS_ITEM_RE.findall(block.group(1))]


class VaultExcludes:
    """Additive, user-configured exclusions loaded from `<vault>/.vault-config.json`.

    Large or academic vaults carry directories that are pure noise to a health
    scan (atomic-card pools, backup snapshots, imported transcription dumps).
    Hardcoding every one into EXCLUDE_DIRS does not scale, and on a 10k+ note
    vault the false positives drown the real findings. A vault can extend the
    skip list per-vault instead; the hardcoded EXCLUDE_DIRS always applies on top.

        {
          "exclude-dirs":  ["_card-pool", "_candidates"],  # dir names, matched as path components
          "exclude-paths": ["Archive/Backup"],             # vault-relative path prefixes (POSIX)
          "exclude-link-scan": ["Meetings/2024-*"]         # globs: notes whose OUTGOING links are not audited
        }

    `exclude-link-scan` exists because some notes echo every link they mention
    without owning them - activity logs and prior health reports quote broken
    links verbatim, so auditing them re-reports each finding once per echo
    (fork-insights round 2). Built-in defaults: `_CLAUDE.md`, `log.md`, and
    `Vault Health*` report notes. Globs match the bare filename and the
    vault-relative path.
    """

    __slots__ = ("dirs", "paths", "link_scan")

    #: Notes whose outgoing links are never audited (see class docstring).
    DEFAULT_LINK_SCAN_EXCLUDES = ("_CLAUDE.md", "log.md", "Vault Health*")

    def __init__(self, dirs=None, paths=None, link_scan=None):
        self.dirs = dirs or set()
        self.paths = paths or []
        self.link_scan = list(self.DEFAULT_LINK_SCAN_EXCLUDES) + list(link_scan or [])

    def skip(self, parts, rel_posix) -> bool:
        """True if a vault path is excluded from the scan (hardcoded + user rules)."""
        if any(p in EXCLUDE_DIRS for p in parts):
            return True
        if self.dirs and any(p in self.dirs for p in parts):
            return True
        return any(rel_posix == pre or rel_posix.startswith(pre + "/") for pre in self.paths)

    def skip_link_scan(self, rel_posix: str) -> bool:
        """True if this note's OUTGOING links are excluded from the audit.
        The note itself still resolves as a link target and is scanned by
        every other check - only its outgoing-link report is suppressed."""
        name = rel_posix.rsplit("/", 1)[-1]
        return any(
            fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel_posix, pat)
            for pat in self.link_scan
        )

    def skip_file_index(self, parts) -> bool:
        """True if a path is excluded from the file index used for link resolution.

        Only the hardcoded FILE_INDEX_EXCLUDE_DIRS (Templates stay indexed so
        template assets still resolve) and the user's noisy `exclude-dirs` are
        pruned here. User `exclude-paths` are deliberately NOT applied, so a live
        link into an excluded path still resolves instead of ringing as broken."""
        if any(p in FILE_INDEX_EXCLUDE_DIRS for p in parts):
            return True
        return bool(self.dirs) and any(p in self.dirs for p in parts)


# Shared "nothing extra excluded" instance for callers that pass no config.
_NO_EXCLUDES = VaultExcludes()


def load_vault_config(vault: Path) -> VaultExcludes:
    """Read `<vault>/.vault-config.json` if present. A missing or malformed file
    is silently ignored (returns empty excludes): a health check must never fail
    because of its own optional config file."""
    cfg_path = vault / ".vault-config.json"
    if not cfg_path.is_file():
        return VaultExcludes()
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return VaultExcludes()
    if not isinstance(data, dict):
        return VaultExcludes()
    raw_dirs = data.get("exclude-dirs", [])
    raw_paths = data.get("exclude-paths", [])
    raw_link = data.get("exclude-link-scan", [])
    dirs = set()
    if isinstance(raw_dirs, list):
        dirs = {d for d in raw_dirs if isinstance(d, str) and d}
    paths = []
    if isinstance(raw_paths, list):
        paths = [p.strip("/") for p in raw_paths if isinstance(p, str) and p.strip("/")]
    link_scan = []
    if isinstance(raw_link, list):
        link_scan = [g for g in raw_link if isinstance(g, str) and g]
    return VaultExcludes(dirs, paths, link_scan)


def index_vault_files(vault: Path, excludes=None) -> set:
    """Lowercased relative paths and bare filenames of every non-excluded vault file.

    Wikilinks can target non-markdown assets ([[Bases/Tasks.base]], [[map.canvas]],
    [[control-center.html]]) or carry an explicit extension ([[_CLAUDE.md]]). The
    .md-note stem index alone cannot resolve those, so broken-link checks also
    consult this full-file index.
    """
    excludes = excludes or _NO_EXCLUDES
    files = set()
    for f in vault.rglob("*"):
        parts = f.relative_to(vault).parts
        if excludes.skip_file_index(parts):
            continue
        if len(parts) == 1 and parts[0] in EXCLUDE_ROOT_FILES:
            continue
        if not f.is_file():
            continue
        files.add(f.relative_to(vault).as_posix().lower())
        files.add(f.name.lower())
    return files


def load_vault(vault: Path, excludes=None) -> dict:
    excludes = excludes or _NO_EXCLUDES
    notes = {}
    for md in vault.rglob("*.md"):
        parts = md.relative_to(vault).parts
        # Also skip any template folder (Templates, 20_Templates, ...): its
        # <%...%> Templater syntax is intentional, not a "template leftover" bug.
        if len(parts) == 1 and parts[0] in EXCLUDE_ROOT_FILES:
            continue
        if any(p.lower().endswith("templates") for p in parts):
            continue
        if excludes.skip(parts, md.relative_to(vault).as_posix()):
            continue
        # rglob matches names, not files: a dangling symlink or a directory named
        # *.md would crash the read and abort the whole scan (stress-test fix 2/24).
        if not md.is_file():
            continue
        rel = str(md.relative_to(vault))
        try:
            content = md.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
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
    # Compare prose, not skeleton: every AI-first note shares frontmatter keys
    # and the "## For future Claude" preamble heading, and that shared
    # boilerplate alone pushed two unrelated notes to 0.80 similarity
    # (stress-test fix 8/24). Strip what all notes share, compare what's unique.
    def _prose(rel: str) -> str:
        text = FRONTMATTER_RE.sub("", notes[rel]["content"], count=1)
        text = text.replace("## For future Claude", "")
        return re.sub(r"\s+", " ", text).strip()[:1000]

    bodies = [_prose(f) for f in files]
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
    # key -> set of source notes that link to it. Tracking the SOURCE matters:
    # a note's own links must not count as incoming (a self-link is the note
    # vouching for itself), and exact keys replace the old substring test that
    # let a short stem like "ai" hide inside "detail" and never ring the alarm
    # (stress-test fix 8/24). Path-qualified links count via their basename.
    link_sources: dict[str, set] = defaultdict(set)
    for src_rel, note in notes.items():
        for link in note["links"]:
            lk = link.lower()
            # An incoming link may carry the .md extension ([[note.md]]); it still
            # targets the same note, so strip it before matching against stems.
            if lk.endswith(".md"):
                lk = lk[:-3]
            for key in {lk, lk.replace(" ", "-"), lk.rsplit("/", 1)[-1]}:
                link_sources[key].add(src_rel)

    def _has_incoming(rel: str, keys) -> bool:
        return any(link_sources.get(k, set()) - {rel} for k in keys)

    issues = []
    skip_folders = {"Daily", "Dev Logs", "Boards", "Templates", "Life Chapters",
                    "Private", "Journal", "Faith", "Reviews", "Partner", "Family"}

    for rel, note in notes.items():
        top_folder = rel.split("/")[0] if "/" in rel else ""
        if top_folder in skip_folders:
            continue
        if rel in ("Home.md", "_CLAUDE.md"):
            continue
        stem_lower = note["stem"].lower()
        stem_norm = stem_lower.replace("-", " ").replace("_", " ")
        linked = _has_incoming(rel, {stem_lower, stem_norm, *note["aliases"]})
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


def check_empty_folders(vault: Path, excludes=None) -> list:
    excludes = excludes or _NO_EXCLUDES
    issues = []
    for folder in vault.rglob("*/"):
        if excludes.skip(folder.parts, folder.relative_to(vault).as_posix()):
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


def _replace_between(pattern, text: str, old: str, new: str) -> tuple[str, int]:
    out, last, n = [], 0, 0
    for m in pattern.finditer(text):
        seg = text[last:m.start()]
        n += seg.count(old)
        out.append(seg.replace(old, new))
        out.append(m.group(0))
        last = m.end()
    seg = text[last:]
    n += seg.count(old)
    out.append(seg.replace(old, new))
    return "".join(out), n


def replace_outside_code(text: str, old: str, new: str) -> tuple[str, int]:
    """Replace old -> new everywhere EXCEPT inside fenced blocks and inline code.

    The link counters ignore code (_strip_code), so anything that EDITS links must
    ignore it too - otherwise dry-run promises N changes and apply makes more,
    corrupting example code (stress-test fix 3/24). Returns (new_text, count)."""
    out, last, total = [], 0, 0
    for m in CODE_FENCE_BLOCK_RE.finditer(text):
        seg, n = _replace_between(INLINE_CODE_RE, text[last:m.start()], old, new)
        total += n
        out.append(seg)
        out.append(m.group(0))
        last = m.end()
    seg, n = _replace_between(INLINE_CODE_RE, text[last:], old, new)
    total += n
    out.append(seg)
    return "".join(out), total


def _normalize_dashes(s: str) -> str:
    """Convert em-dash (U+2014) and en-dash (U+2013) to a regular hyphen.

    Vault naming conventions often use em-dashes in filenames (e.g.
    `2026-05-22 - Learnings Review.md`). Wikilinks that reference the same
    note with a regular hyphen (`[[2026-05-22 - Learnings Review]]`) should
    still resolve. Normalize both sides before comparison.
    """
    return s.replace(_EM_DASH, "-").replace(_EN_DASH, "-")


def check_wanted_notes(notes: dict, vault: Path, excludes=None) -> list:
    """Find links whose target note does not exist yet. These are NOT errors -
    in a wiki-style vault you link a thing the moment you mention it, long before
    (or instead of) writing its note. They are a demand-ranked wishlist of notes
    worth writing, so they are reported as info, not warnings. Named after
    MediaWiki's "Wanted pages"."""
    all_stems = {note["stem"].lower(): rel for rel, note in notes.items()}
    # Full-file index so links to non-markdown assets and links written with an
    # explicit extension resolve instead of being flagged broken.
    all_files = index_vault_files(vault, excludes)
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

    # Some notes echo links without owning them: operating manuals show example
    # wikilinks as syntax demonstrations, and activity logs / prior health
    # reports quote every audited link verbatim - scanning them re-reports each
    # finding once per echo. Defaults (_CLAUDE.md, log.md, Vault Health*) live
    # on VaultExcludes; users extend via .vault-config.json "exclude-link-scan".
    excludes = excludes or _NO_EXCLUDES

    issues = []
    for rel, note in notes.items():
        if excludes.skip_link_scan(Path(rel).as_posix()):
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
                        # A '[' inside the captured name means the real filename
                        # contains brackets and the regex capture stopped early -
                        # never present a possibly-mangled name as authoritative.
                        "message": f"[[{link}]] - wanted by {rel}" + (
                            " (name contains brackets; capture may be truncated)"
                            if "[" in link else ""
                        ),
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
    excludes = load_vault_config(vault)
    notes = load_vault(vault, excludes)
    print(f"   Found {len(notes)} notes\n", file=sys.stderr)

    checks = [
        ("Duplicates", check_duplicates(notes)),
        ("Orphans", check_orphans(notes)),
        ("Stale tasks", check_stale_tasks(notes)),
        ("Code-fence-wrapped notes", check_code_fence_wrapped(notes)),
        ("Missing frontmatter", check_missing_frontmatter(notes)),
        ("Empty folders", check_empty_folders(vault, excludes)),
        ("Wanted notes", check_wanted_notes(notes, vault, excludes)),
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
