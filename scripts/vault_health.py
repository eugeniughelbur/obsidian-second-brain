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
      "exclude-paths": ["Archive/Backup"],             # vault-relative path prefixes
      "rewrite_policy": "unattended",                  # opt out of the /obsidian-ingest
                                                       # confirm-before-rewrite gate (#250)
      "source_quality_policy": "silent"                # mute the speculation-only-sources
                                                       # warning (#258); default is warn
    }
A missing or malformed file is ignored silently. See VaultExcludes, and
load_rewrite_policy and load_source_quality_policy for the keys that are not about
exclusions.
"""

import argparse
import difflib
import fnmatch
import json
import re
import sys
import sys as _sys
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from vault_scan import BASE_EXCLUDE_DIRS, embed_exclude_prefixes, is_embed_excluded  # noqa: E402

TODAY = date.today()
# Shared base, see scripts/vault_scan.py. This module owns the user-facing
# extension point (.vault-config.json via VaultExcludes); the base is the floor.
EXCLUDE_DIRS = frozenset(d.lower() for d in BASE_EXCLUDE_DIRS)
# The file index deliberately keeps Templates visible: a link pointing AT a
# template should still resolve, even though templates are not scanned as notes.
FILE_INDEX_EXCLUDE_DIRS = EXCLUDE_DIRS - {"templates"}
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
# `\s*-\s*`, not `\s+-\s+`: a list written with the dash at column 0, or with
# no space after it, is valid YAML. Requiring surrounding whitespace made those
# aliases invisible here while link_graph (which uses `\s*`) resolved them, so
# the same note was an orphan to one tool and linked to the other.
ALIAS_RE = re.compile(r"^aliases:\s*\n((?:\s*-\s*.+\n?)+)", re.MULTILINE)
ALIAS_ITEM_RE = re.compile(r"^\s*-\s*(.+)$", re.MULTILINE)
ALIAS_INLINE_RE = re.compile(r"^aliases:\s*\[(.+)\]\s*$", re.MULTILINE)
# Same two shapes as aliases, different key - `tags:` is at least as often a
# block list (see references/vault-schema.md's own frontmatter examples) as
# the inline `tags: [...]` form this project's own notes use (#221).
TAG_RE = re.compile(r"^tags:\s*\n((?:\s*-\s*.+\n?)+)", re.MULTILINE)
TAG_INLINE_RE = re.compile(r"^tags:\s*\[(.*)\]\s*$", re.MULTILINE)


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


def parse_tags(frontmatter: str) -> list:
    """Extract tags from frontmatter text - block style AND inline style, same
    shape as parse_aliases. Feeds check_taxonomy (#221); lowercased to match
    this project's tag convention (see CLAUDE.md Conventions)."""
    m = TAG_INLINE_RE.search(frontmatter)
    if m:
        return [t.strip().strip('"\'').lower() for t in m.group(1).split(",") if t.strip()]
    block = TAG_RE.search(frontmatter)
    if not block:
        return []
    return [t.strip().strip('"\'').lower() for t in ALIAS_ITEM_RE.findall(block.group(1))]


def _is_hidden(parts) -> bool:
    """True for a path with a dot-prefixed component, which is not vault content.

    The case that bit a real vault (#290): on a volume with no native extended
    attributes (exFAT, FAT32, many SMB shares) macOS writes a small binary
    `._<name>` companion beside every file it touches, to carry the xattrs the
    filesystem cannot hold. `rglob("*.md")` matches `._Note.md`, so each
    companion was parsed as a note and reported three times over - as an orphan,
    as missing frontmatter, and as a same-title duplicate of the real note. On an
    exFAT vault those findings outnumbered the real ones, and no
    `.vault-config.json` key could suppress them: `exclude-dirs` matches
    directory names and `exclude-paths` matches prefixes. Deleting them does not
    help either, because macOS writes them again on the next save.

    Dot-prefixed generally, not `._` specifically, because that is the rule
    Obsidian itself applies: it indexes no dot-prefixed file or folder. The
    named dot-directories in BASE_EXCLUDE_DIRS stay listed there; this catches
    the ones nobody thought to name.
    """
    return any(str(p).startswith(".") for p in parts)


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
        # Casefolded: the bootstrapper writes Templates/ while three sibling
        # tools spelled it templates, so the same folder was skipped or scanned
        # depending on which tool ran.
        if _is_hidden(parts):
            return True
        lowered = [str(p).lower() for p in parts]
        if any(p in EXCLUDE_DIRS for p in lowered):
            return True
        if self.dirs and any(p in {d.lower() for d in self.dirs} for p in lowered):
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
        if _is_hidden(parts):
            return True
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


REWRITE_POLICIES = ("confirm", "unattended")


def load_rewrite_policy(vault: Path) -> str:
    """Read `rewrite_policy` from `<vault>/.vault-config.json` (#250).

    `confirm` (the default) keeps /obsidian-ingest's confirm-before-rewrite
    gate; `unattended` lets the command write rewrites of existing notes
    without asking. The opt-out is never inferred: a missing file, a missing
    key, a malformed file, a non-string, or any other value all mean
    `confirm`, the same missing-file contract as load_vault_config."""
    cfg_path = vault / ".vault-config.json"
    if not cfg_path.is_file():
        return "confirm"
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "confirm"
    if not isinstance(data, dict):
        return "confirm"
    value = data.get("rewrite_policy")
    if isinstance(value, str) and value.strip().lower() == "unattended":
        return "unattended"
    return "confirm"


def check_rewrite_policy(vault: Path) -> list:
    """One info line when the vault runs without the rewrite gate, so a reader
    of the health report knows rewrites land unreviewed by a person. Nothing
    is reported for the default; there is nothing to fix either way."""
    if load_rewrite_policy(vault) != "unattended":
        return []
    return [{
        "type": "rewrite_policy",
        "severity": "info",
        "message": ("rewrite_policy: unattended - /obsidian-ingest rewrites existing "
                    "notes without confirmation (#250); this vault reviews rewrites "
                    "through its own layer, not a prompt. Remove the key from "
                    ".vault-config.json to restore the default"),
        "files": [".vault-config.json"],
    }]


# One `##` heading per canonical tag, its synonyms as a `-` list underneath -
# see references/taxonomy-format.md for the full spec and rationale.
TAXONOMY_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def load_taxonomy(vault: Path) -> dict:
    """Read `<vault>/_meta/taxonomy.md` if present: {canonical_tag: [synonym, ...]}.

    Empty dict (not an error) when the file is absent - the taxonomy audit is
    opt-in per #221, so a vault that never created this file must see zero
    findings, same contract as load_vault_config's missing-file case above."""
    path = vault / "_meta" / "taxonomy.md"
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return {}
    taxonomy: dict[str, list] = {}
    headings = list(TAXONOMY_HEADING_RE.finditer(text))
    for i, heading in enumerate(headings):
        canonical = _nfc(heading.group(1)).strip().lower()
        if not canonical:
            continue
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        block = text[heading.end():end]
        taxonomy[canonical] = [
            _nfc(s).strip().lower() for s in ALIAS_ITEM_RE.findall(block) if s.strip()
        ]
    return taxonomy


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
        files.add(_nfc(f.relative_to(vault).as_posix()).lower())
        files.add(_nfc(f.name).lower())
    return files


def load_vault(vault: Path, excludes=None, only: str | None = None) -> dict:
    """Parse every note under `vault` into {rel: note-dict}.

    `only` restricts the walk to a single vault-relative path. heal_links
    rewrites one file per iteration and previously re-read the entire vault to
    learn about it; a full rglob to re-parse one note is the expensive part of
    that loop. Same parsing path either way, so the two cannot drift.
    """
    excludes = excludes or _NO_EXCLUDES
    notes = {}
    source = [vault / only] if only else vault.rglob("*.md")
    for md in source:
        parts = md.relative_to(vault).parts
        # Also skip any template folder (Templates, 20_Templates, ...): its
        # <%...%> Templater syntax is intentional, not a "template leftover" bug.
        if len(parts) == 1 and parts[0] in EXCLUDE_ROOT_FILES:
            continue
        if any(p.lower().endswith("templates") for p in parts):
            continue
        # _meta/ holds tool config (_meta/taxonomy.md, #221), not vault
        # content - scanning it as a note would false-positive it into
        # missing-frontmatter and orphan findings for every vault that adopts
        # a taxonomy. Local to load_vault, not BASE_EXCLUDE_DIRS: the other
        # tools sharing that base (freshness_lint, export_okf, MCP vault_ops)
        # have no reason to know about a vault_health-only convention yet.
        if parts and parts[0].lower() == "_meta":
            continue
        if excludes.skip(parts, md.relative_to(vault).as_posix()):
            continue
        # rglob matches names, not files: a dangling symlink or a directory named
        # *.md would crash the read and abort the whole scan (stress-test fix 2/24).
        if not md.is_file():
            continue
        # POSIX form, not str(): on Windows str(WindowsPath) yields backslashes,
        # so every `rel.split("/")` below saw no separator. Top-folder logic then
        # returned "" for every note, and the whole skip_folders/dated-series
        # exemption collapsed - every note under Daily/, Journal/, Private/ was
        # reported as an orphan. CI is ubuntu-only so nothing caught it.
        # Consumers rebuild paths as `vault / rel`, which accepts forward slashes
        # on Windows, so no downstream change is needed.
        rel = md.relative_to(vault).as_posix()
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
            "tags": parse_tags(frontmatter),
            "due": due_match.group(1) if due_match else None,
            "size": len(content),
        }
    return notes


# Folders whose notes recur by date with a shared descriptive title (e.g. a
# "Weekly Review" every Friday). Same title across dates is expected here, not a
# duplicate, so they are exempt from duplicate detection (issue #82).
DATED_SERIES_FOLDERS = {"daily", "logs", "dev logs", "reviews"}

# Minimum normalized-title length for the truncated-title pass (see
# _truncated_title_groups). Short titles are prefixes of each other by accident
# ("api" prefixes "api keys"); long ones are not.
_TRUNC_TITLE_MIN_LEN = 20


def _norm_title(stem: str) -> str:
    """Normalize a filename stem to a comparable title. Keeps digits and dates -
    the old version stripped ISO dates, which collapsed every dated note in a
    series onto one bucket and flagged them all as duplicates (issue #82).

    Unicode-aware by necessity: the class must NOT be spelled [^a-z0-9 ], which
    deletes every non-Latin letter. Measured on a Ukrainian/Russian vault
    (591 notes, 2026-07): "Зустріч команди 1" and "Огляд кварталу 1"
    both normalized to "1", and any title carrying a Latin fragment collapsed
    onto that fragment ("Огляд ринку та KPI" -> "kpi", "Підсумки за 2024" -> "2024"). 12 of the 14 reported duplicates were unrelated notes grouped this
    way. str.isalnum() is script-agnostic, so Cyrillic, Greek, CJK and Latin
    titles all keep their letters.
    """
    norm = "".join(
        ch if (ch.isalnum() or ch.isspace()) else " " for ch in _nfc(stem).lower()
    )
    return re.sub(r"\s+", " ", norm).strip()


def _max_pairwise_similarity(notes: dict, files: list) -> float:
    """Largest body-text similarity ratio among a set of notes (first 1000 chars).
    Used as the content signal that separates real duplicates from notes that
    merely share a title."""
    # Compare prose, not skeleton: every AI-first note shares frontmatter keys
    # and the "## For future agent" preamble heading, and that shared
    # boilerplate alone pushed two unrelated notes to 0.80 similarity
    # (stress-test fix 8/24). Strip what all notes share, compare what's unique.
    def _prose(rel: str) -> str:
        text = FRONTMATTER_RE.sub("", notes[rel]["content"], count=1)
        # Both spellings rule 2 accepts: the heading and the callout form (#237).
        text = re.sub(
            r"(?:##|>[ \t]*\[![A-Za-z][\w-]*\][-+]?)[ \t]+For future (?:agent|AI|Claude|Codex)",
            "", text,
        )
        return re.sub(r"\s+", " ", text).strip()[:1000]

    bodies = [_prose(f) for f in files]
    best = 0.0
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            best = max(best, difflib.SequenceMatcher(None, bodies[i], bodies[j]).ratio())
    return best


def _truncated_title_groups(candidates: list) -> list:
    """Group notes whose title is a truncation of another note's title.

    Exporters that derive a filename from a title cut it at a fixed length, so
    one source item can land twice under names that differ only in the tail:
    "...про управління компанією.md" and "...про управління компанією та.md" are one
    book stored twice. Exact-title grouping cannot see that.

    Strict prefix, not fuzzy similarity. That distinction was measured, not
    assumed: a 0.90 difflib ratio on normalized titles rated the numbered series
    "Огляд кварталу 1"/"2" at 0.95 and grouped them as duplicates, while a
    genuine truncation pair scored 0.98 - the two are indistinguishable by ratio.
    Body similarity cannot break the tie either: the false pair scored 1.00
    (both are short stubs) and the true pair 0.40. A strict prefix separates them
    cleanly, because a trailing "1" vs "2" is never a prefix of the other.

    `candidates` is a list of (norm_title, rel). Returns lists of rels.
    """
    by_folder = defaultdict(list)
    for norm, rel in candidates:
        by_folder[rel.rsplit("/", 1)[0] if "/" in rel else ""].append((norm, rel))

    groups = []
    for bucket in by_folder.values():
        if len(bucket) < 2:
            continue
        # Shortest first, so a truncated stem is compared as the prefix.
        bucket.sort(key=lambda pair: len(pair[0]))
        used = set()
        for i, (norm_a, rel_a) in enumerate(bucket):
            if rel_a in used:
                continue
            group = [rel_a]
            for norm_b, rel_b in bucket[i + 1:]:
                if rel_b in used or norm_b == norm_a:
                    continue
                if not norm_b.startswith(norm_a):
                    continue
                # "Notes" vs "Notes 2" is a numbered series, not a truncated
                # title: an exporter cutting a title never appends a bare
                # number. Requiring the tail to carry a word keeps parts of a
                # series out of the duplicate report.
                if not norm_b[len(norm_a):].strip().strip("0123456789 ."):
                    continue
                group.append(rel_b)
                used.add(rel_b)
            if len(group) > 1:
                used.add(rel_a)
                groups.append(group)
    return groups


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

    # Second pass: one title is a truncation of another, which exact grouping
    # cannot see. Severity still follows the body signal - a truncated title
    # says the pair came from one source, the bodies say whether it is a copy.
    already = {rel for files in groups.values() if len(files) > 1 for rel in files}
    candidates = [
        (norm, rel)
        for norm, files in groups.items()
        for rel in files
        if rel not in already and len(norm) >= _TRUNC_TITLE_MIN_LEN
    ]
    for files in _truncated_title_groups(candidates):
        similar = _max_pairwise_similarity(notes, files) >= 0.6
        issues.append({
            "type": "duplicate",
            "severity": "warning" if similar else "info",
            "message": (
                "Truncated title of another note"
                f"{' with matching content' if similar else ''}: "
                f"{[Path(f).stem for f in files]}"
            ),
            "files": files,
        })
    return issues


def check_taxonomy(notes: dict, taxonomy: dict) -> list:
    """Notes whose tags disagree with `_meta/taxonomy.md` (#221's opt-in half -
    the digit-only/syntax half of that issue is a write-time check the
    maintainer is adding separately, unrelated to this function).

    No-op when `taxonomy` is empty: an absent (or heading-less) taxonomy file
    must produce zero findings, never flag every tag as unknown - see
    references/taxonomy-format.md.

    Two disjoint findings, matching the maintainer's spec verbatim:
    - `tag_synonym`: the tag IS a known synonym of a canonical tag - the fix
      is unambiguous (rename to the canonical form), so this is a warning.
    - `tag_not_in_taxonomy`: the tag matches neither a canonical tag nor any
      synonym - informational only, since an unlisted tag is not necessarily
      wrong, just not (yet) in the vocabulary.
    """
    if not taxonomy:
        return []
    canonical_tags = set(taxonomy)
    synonym_to_canonical = {syn: canon for canon, syns in taxonomy.items() for syn in syns}

    issues = []
    for rel, note in notes.items():
        for tag in note["tags"]:
            if tag in canonical_tags:
                continue
            canonical = synonym_to_canonical.get(tag)
            if canonical:
                issues.append({
                    "type": "tag_synonym",
                    "severity": "warning",
                    "message": f"#{tag} should be folded to #{canonical}: {rel}",
                    "files": [rel],
                    "tag": tag,
                    "canonical": canonical,
                })
            else:
                issues.append({
                    "type": "tag_not_in_taxonomy",
                    "severity": "info",
                    "message": f"#{tag} is not in the taxonomy: {rel}",
                    "files": [rel],
                    "tag": tag,
                })
    return issues


# Folders whose notes are a dated series or machine-written: nothing is expected
# to link them, so an orphan finding here recurs every day forever in a vault
# behaving exactly as documented.
_ORPHAN_EXEMPT_FOLDERS = frozenset({
    "daily", "dev logs", "logs", "boards", "templates", "reviews",
    "life chapters", "private", "journal", "faith", "partner", "family",
})


def _orphan_exempt_folder(rel: str) -> bool:
    """True when this note lives in a folder the orphan check should skip.

    The old test read the top folder against a set of Obsidian-style names,
    spelled with capitals. It therefore knew one of the two documented layouts
    (#292): wiki-style daily notes sit at `wiki/daily/YYYY-MM-DD.md`, whose top
    folder is `wiki`, so every one of them rang, while `Daily/YYYY-MM-DD.md` in
    a vault next door did not. The same note was noise or not depending only on
    which documented layout its owner picked. `Logs/`, the operations log
    `/obsidian-init` writes and nothing is meant to link, was in neither list.

    Wiki-style nests one level deeper under `wiki/`, per
    `references/folder-map.md`, so the folder that decides this is the second
    component there and the first everywhere else. Matching is casefolded, and
    a slugged name (`wiki/life-chapters/`, which bootstrap writes for a preset
    folder with no explicit mapping) reads as its spaced form.
    """
    parts = rel.lower().split("/")
    if len(parts) < 2:
        return False  # a note at the vault root is never exempt
    head = parts[1] if parts[0] == "wiki" and len(parts) > 2 else parts[0]
    return head.replace("-", " ").replace("_", " ") in _ORPHAN_EXEMPT_FOLDERS


def check_orphans(notes: dict) -> list:
    # key -> set of source notes that link to it. Tracking the SOURCE matters:
    # a note's own links must not count as incoming (a self-link is the note
    # vouching for itself), and exact keys replace the old substring test that
    # let a short stem like "ai" hide inside "detail" and never ring the alarm
    # (stress-test fix 8/24). Path-qualified links count via their basename.
    link_sources: dict[str, set] = defaultdict(set)
    # Path-qualified links are kept apart. Folding them in by basename, which is
    # what this used to do, made one link vouch for every note sharing a
    # filename anywhere in the vault (#290): linking `[[wiki/daily/2026-01-05]]`
    # hid `Logs/2026-01-05.md` from the scan, and one linked
    # `projects/*/README.md` covered all the others.
    path_link_sources: dict[str, set] = defaultdict(set)
    for src_rel, note in notes.items():
        for link in note["links"]:
            lk = _nfc(link).lower()
            # An incoming link may carry a redundant .md extension ([[note.md]]),
            # so register the stripped form. Keep the link as written too: a note
            # titled `... _CLAUDE.md` is saved as `... _CLAUDE.md.md`, and its stem
            # keeps the trailing `.md`.
            keys = {lk}
            if lk.endswith(".md"):
                keys.add(lk[:-3])
            target = path_link_sources if "/" in lk else link_sources
            for key in keys | {k.replace(" ", "-") for k in keys}:
                target[key].add(src_rel)

    def _has_incoming(rel: str, keys) -> bool:
        if any(link_sources.get(k, set()) - {rel} for k in keys):
            return True
        # A path-qualified link resolves to the note it points at, and Obsidian
        # accepts the shortest path that is unique, so `[[alpha/README]]` reaches
        # `projects/alpha/README.md`. Matched as a path suffix on a component
        # boundary for that reason - never as a bare filename, which is the
        # collision this separation exists to prevent.
        rel_key = _nfc(rel[:-3] if rel.endswith(".md") else rel).lower()
        return any(
            (rel_key == pk or rel_key.endswith("/" + pk)) and (srcs - {rel})
            for pk, srcs in path_link_sources.items()
        )

    issues = []

    for rel, note in notes.items():
        if _orphan_exempt_folder(rel):
            continue
        if rel in ("Home.md", "_CLAUDE.md"):
            continue
        stem_lower = _nfc(note["stem"]).lower()
        stem_norm = stem_lower.replace("-", " ").replace("_", " ")
        linked = _has_incoming(
            rel, {stem_lower, stem_norm, *(_nfc(a) for a in note["aliases"])}
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


# System files that carry no frontmatter by design. The same set, matched by
# filename at any depth, that hooks/validate-ai-first.sh exempts at write time, so
# a file the hook lets through is not reported here later.
_FRONTMATTER_EXEMPT_FILES = frozenset({
    "_CLAUDE.md", "Home.md", "index.md", "log.md", "catchup.md",
})


def check_missing_frontmatter(notes: dict) -> list:
    issues = []
    skip = {"Templates", "_trash", ".obsidian"}
    for rel, note in notes.items():
        if any(s in rel for s in skip):
            continue
        if rel.rsplit("/", 1)[-1] in _FRONTMATTER_EXEMPT_FILES:
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


# Obsidian tag syntax (#221). A tag may contain letters in any script, digits,
# `_`, `-` and `/` for nesting, and must contain at least one non-numeric
# character. Anything else renders struck through in the UI with no error
# anywhere, so an agent that wrote `tags: [33]` or `[2.0]` never finds out.
# Mirrors check 7 in hooks/validate-ai-first.sh - keep the two in step.
# Tags come from parse_tags() (#230) so taxonomy and syntax read one parser.
_TAG_ALLOWED_RE = re.compile(r"^[\w/-]+$")
_TAG_HAS_NON_DIGIT_RE = re.compile(r"[^\d/]")
def tag_problem(tag: str):
    """Why Obsidian would render `tag` broken, or None if it is valid."""
    t = tag.lstrip("#")
    if not t:
        return "empty tag"
    if " " in t or "\t" in t:
        return "contains whitespace - use `-` between words"
    if "." in t:
        return "contains `.` - use `-` or spell it out"
    if not _TAG_ALLOWED_RE.match(t):
        return "contains characters outside letters/digits/_/-//"
    if not _TAG_HAS_NON_DIGIT_RE.search(t):
        return f"is digits only - prefix a word, e.g. `store-{t}`"
    return None


def check_tag_syntax(notes: dict) -> list:
    issues = []
    for rel, note in notes.items():
        if not note["has_frontmatter"]:
            continue
        for tag in parse_tags(note["frontmatter"]):
            why = tag_problem(tag)
            if why:
                issues.append({
                    "type": "invalid_tag",
                    "severity": "warning",
                    "message": f"Tag `{tag}` {why} (Obsidian renders it broken, silently): {rel}",
                    "files": [rel],
                    "tag": tag,
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
        # Relative parts, like every other call site. `folder` is absolute here,
        # so folder.parts included every ancestor outside the vault - a vault
        # under any dir named Templates/.git/_export silently skipped every
        # folder and the check reported zero findings with no warning.
        _rel = folder.relative_to(vault)
        if excludes.skip(_rel.parts, _rel.as_posix()):
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


SEMANTIC_INDEX_FILE = ".obsidian-semantic-index.json"
# A note key inside the index. Paths end in .md and every other string in the
# file is a model name or a bare number, so this cannot match a vector element.
_INDEX_KEY_RE = re.compile(r'"((?:[^"\\]|\\.)+?\.md)"\s*:\s*\{')
# Below this share of the vault missing, an index is "current enough" - a couple
# of notes written since the last build is normal, not a problem to report.
INDEX_STALE_PCT = 5.0


def _decode_index_key(raw: str) -> str:
    """One captured index key, as the path it names.

    The capture is the body of a JSON string, so `json.loads` on it quoted is
    the decoder - it is only called when there is an escape to resolve, which
    keeps an all-ASCII index on the same fast path it had before. A malformed
    escape is left alone: an unreadable key should read as one missing note,
    never as a crashed health check.
    """
    if "\\" not in raw:
        return raw
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return raw


def _indexed_paths(index_path: Path, chunk: int = 1 << 20) -> set:
    """Note paths present in the semantic index, read as a stream.

    The index is vectors, so it runs to tens of megabytes on a real vault (66MB
    at 1,300 notes). json.loads would make every health check pay for parsing
    every float to answer a question about keys, so this scans in chunks with an
    overlap wide enough that a key split across a boundary is still matched.

    `chunk` is a parameter only so the seam behaviour can be tested deterministically
    at a small size; at the default a note key cannot span two boundaries.

    Keys are decoded as JSON strings before they are returned (#259). Scanning
    text rather than parsing it means a `\\uXXXX` escape arrives here verbatim,
    and an index written by any build before the writer switched to
    `ensure_ascii=False` stores every non-ASCII path that way - so a Cyrillic or
    CJK note read out of it never matched its own vault path and was reported
    missing from an index that held it.
    """
    found = set()
    tail = ""
    with index_path.open("r", encoding="utf-8", errors="replace") as fh:
        while block := fh.read(chunk):
            buf = tail + block
            found.update(_decode_index_key(m.group(1)) for m in _INDEX_KEY_RE.finditer(buf))
            tail = buf[-4096:]
    return found


def check_semantic_index(vault: Path, notes) -> list:
    """Notes the semantic index does not cover.

    The index is built on demand and never invalidates itself - the README even
    said to "build the index once" - so it silently drifts behind the vault. A
    missing note is still findable by literal word match, but nothing else: on a
    query in a language the note is not written in, the lexical arm contributes
    nothing and the note cannot be retrieved at all. Measured at 29% of a real
    vault uncovered, with no warning anywhere.
    """
    index_path = vault / SEMANTIC_INDEX_FILE
    if not index_path.exists():
        return []  # semantic search is optional; not having it is not a defect
    indexed = _indexed_paths(index_path)
    if not indexed:
        return [{
            "type": "semantic_index",
            "severity": "warning",
            "message": (f"{SEMANTIC_INDEX_FILE} exists but no notes could be read from it; "
                        "semantic search is falling back to literal word match"),
            "files": [],
        }]
    # Notes OBSIDIAN_EMBED_EXCLUDE keeps out of the index are not missing from it:
    # the build skips them on purpose and the rebuild this warning recommends
    # would skip them again, so counting them made the warning permanent (#273).
    prefixes = embed_exclude_prefixes()
    expected = [rel for rel in notes if not is_embed_excluded(rel, prefixes)]
    missing = sorted(rel for rel in expected if rel not in indexed)
    if not missing:
        return []
    pct = 100.0 * len(missing) / len(expected)
    if pct < INDEX_STALE_PCT:
        return []
    return [{
        "type": "semantic_index",
        "severity": "warning",
        "message": (
            f"Semantic index covers {len(expected) - len(missing)} of {len(expected)} notes; "
            f"{len(missing)} ({pct:.0f}%) are missing and can only be found by literal "
            f"word match. Rebuild: uv run python scripts/eval/semantic_search.py "
            f'--path "{vault}" --build'
        ),
        "files": missing[:20],
    }]


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


def _nfc(s: str) -> str:
    """Canonical (NFC) form of a string, for link/stem/alias comparison only.

    Filenames and note content can disagree on Unicode composition: a decomposed
    filename ("Gru" + U+0308 + "ndung.md") and a composed wikilink ("[[Grundung]]"
    with U+00FC) are the same title to a human and to the filesystem, but not to a
    plain string compare. Normalizing both sides at the comparison boundary keeps
    accented titles from being reported as wanted notes or orphans. NFC (not NFKC):
    only canonical equivalence, never compatibility folding.
    """
    return unicodedata.normalize("NFC", s)


def _normalize_dashes(s: str) -> str:
    """Convert em-dash (U+2014) and en-dash (U+2013) to a regular hyphen.

    Vault naming conventions often use em-dashes in filenames (e.g.
    `2026-05-22 - Learnings Review.md`). Wikilinks that reference the same
    note with a regular hyphen (`[[2026-05-22 - Learnings Review]]`) should
    still resolve. Normalize both sides before comparison.
    """
    return s.replace(_EM_DASH, "-").replace(_EN_DASH, "-")


# Suffixes that mean "this link points at an attachment, not at a note yet to be
# written". A missing note is a knowledge gap worth writing; a missing attachment
# is an import-cleanup task. Reporting both under one label hides the first
# inside the second - on the vault this was found on, 43 of 43 "wanted notes"
# were attachment links, so a genuine knowledge gap would have been invisible.
_ASSET_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tiff", ".heic",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".rtf",
    ".zip", ".gz", ".tar", ".7z", ".xmind", ".mp3", ".mp4", ".mov", ".wav",
    ".m4a", ".webm", ".epub", ".mobi",
)


def check_wanted_notes(notes: dict, vault: Path, excludes=None) -> list:
    """Find links whose target note does not exist yet. These are NOT errors -
    in a wiki-style vault you link a thing the moment you mention it, long before
    (or instead of) writing its note. They are a demand-ranked wishlist of notes
    worth writing, so they are reported as info, not warnings. Named after
    MediaWiki's "Wanted pages"."""
    all_stems = {_nfc(note["stem"]).lower(): rel for rel, note in notes.items()}
    # Full-file index so links to non-markdown assets and links written with an
    # explicit extension resolve instead of being flagged broken.
    all_files = index_vault_files(vault, excludes)
    # also index stems with em-dashes normalized to regular hyphens so a
    # wikilink written with `-` still matches a filename written with `-`
    all_stems_dash_norm = {
        _normalize_dashes(_nfc(note["stem"])).lower(): rel
        for rel, note in notes.items()
    }
    # build alias → rel lookup so [[Full Name]] resolves if the note has that alias
    all_aliases: dict[str, str] = {}
    for rel, note in notes.items():
        for alias in note["aliases"]:
            all_aliases[_nfc(alias).lower()] = rel

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
            link_stem = _nfc(link_name).lower()
            link_norm = link_stem.replace("-", " ").replace("_", " ")
            link_dash_norm = _normalize_dashes(link_stem)
            resolved = (
                link_stem in all_stems
                or link_norm in all_stems
                or link_stem in all_aliases
                or link_norm in all_aliases
                or link_dash_norm in all_stems_dash_norm
                or _nfc(link).lower() in all_files
                or f"{_nfc(link).lower()}.md" in all_files
                # Path-form links to assets. Notion exports write
                # [[Attachments Folder/Screenshot_11.png]], where the folder
                # segment is relative to the *note*, not to the vault root - so
                # the full-path lookup above can never match. index_vault_files()
                # already indexes bare filenames (and Obsidian itself resolves a
                # link by name), so the last path component has to be checked
                # too. Without this line every imported attachment link is
                # reported as a wanted note: 43 of 43 on the vault where this
                # was found, with all 43 files present on disk.
                or link_stem in all_files
                or link_dash_norm in all_files
            )
            if not resolved:
                # A "link" longer than the filesystem allows for a name (inline
                # script in a captured page, `[[null,null,...]]`) makes is_dir()
                # raise OSError before Python 3.14, which aborted the scan for the
                # whole vault (#272). A path that cannot exist is not a folder.
                try:
                    is_folder = (vault / link).is_dir()
                except OSError:
                    is_folder = False
                if not is_folder:
                    is_asset = link_name.lower().endswith(_ASSET_SUFFIXES)
                    issues.append({
                        "type": "missing_attachment" if is_asset else "wanted_note",
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


# --- source-payload completeness (#194) --------------------------------------
# A source card can carry a live `source_url`, pass every structural check, and
# still retain no evidence at all. The three checks below are about that gap
# only; none of them judges how long a source ought to be.
_FM_FIELD_RE_CACHE: dict = {}
SOURCE_CAPTURE_SCOPES = ("full-local", "bounded-local", "url-only")
# Deliberately tiny. This is not an opinion about how much text a source should
# hold - a captured tweet is legitimately three lines. It is the floor at which
# "I retained this content locally" is self-evidently untrue.
MIN_RETAINED_PAYLOAD_CHARS = 50


def _fm_field(frontmatter: str, field: str) -> str:
    """One scalar frontmatter value, lowercased and unquoted, or ""."""
    rx = _FM_FIELD_RE_CACHE.get(field)
    if rx is None:
        rx = re.compile(rf"^{re.escape(field)}:\s*(.+?)\s*$", re.MULTILINE)
        _FM_FIELD_RE_CACHE[field] = rx
    m = rx.search(frontmatter)
    return m.group(1).strip().strip("\"'").lower() if m else ""


def load_source_policy(vault: Path) -> str:
    """`source_policy` from `<vault>/.vault-config.json`: "default" or "strict-local".

    Same contract as load_rewrite_policy (#250): a missing file, a missing key,
    a malformed file or any other value all mean "default". Strict mode raises
    the severity of an unretained source, it does not invent new findings.
    """
    cfg_path = vault / ".vault-config.json"
    if not cfg_path.is_file():
        return "default"
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "default"
    if not isinstance(data, dict):
        return "default"
    value = data.get("source_policy")
    if isinstance(value, str) and value.strip().lower() == "strict-local":
        return "strict-local"
    return "default"


def _dependents_of(notes: dict, targets: set, skip: set) -> dict:
    """{target: {notes in `notes` that link it}}, never counting a note in `skip`.

    Same link indexing as check_orphans: match on the stem and its
    path-qualified and hyphenated spellings. Shared by the payload and
    source-quality checks so the two cannot drift apart."""
    by_key: dict = defaultdict(set)
    for rel in targets:
        stem = _nfc(Path(rel).stem).lower()
        for key in {stem, stem.replace(" ", "-"), rel[:-3].lower()}:
            by_key[key].add(rel)
    supported: dict = defaultdict(set)
    for src_rel, note in notes.items():
        if src_rel in skip:
            continue
        for link in note["links"]:
            lk = _nfc(link).lower()
            # Both forms, as in check_orphans: `... _CLAUDE.md.md` keeps its `.md`.
            forms = {lk, lk[:-3]} if lk.endswith(".md") else {lk}
            keys = set()
            for f in forms:
                keys |= {f, f.replace(" ", "-"), f.rsplit("/", 1)[-1]}
            for key in keys:
                for target in by_key.get(key, ()):
                    supported[target].add(src_rel)
    return supported


def check_source_payload(notes: dict, vault: Path) -> list:
    """Sources whose retained evidence does not match what they claim (#194).

    Three distinct problems, deliberately separated because they carry very
    different weight:

    1. A note that declares it retained the content locally and has no body.
       That is a self-contradiction inside one file, so it is an error and needs
       no policy to justify it.
    2. Active knowledge resting on a `url-only` record. The vault kept a
       locator, not evidence: if the page dies or changes, the concept and
       synthesis notes built on it have nothing behind them and nothing says so.
       A warning, because keeping only a URL is a legitimate choice.
    3. Sources with no `capture_scope` at all - every source written before this
       field existed. Reported once, as info, never per note: a research vault
       has thousands and a wall of findings would bury 1 and 2.

    `source_policy: strict-local` raises 2 and 3 by one level for a vault that
    has decided a locator is not a source.
    """
    strict = load_source_policy(vault) == "strict-local"
    sources, unscoped, empty_claims = {}, [], []
    for rel, note in notes.items():
        if _fm_field(note["frontmatter"], "type") != "source":
            continue
        scope = _fm_field(note["frontmatter"], "capture_scope")
        sources[rel] = scope
        body = FRONTMATTER_RE.sub("", note["content"], count=1).strip()
        if not scope:
            unscoped.append(rel)
        elif scope in ("full-local", "bounded-local") and len(body) < MIN_RETAINED_PAYLOAD_CHARS:
            empty_claims.append((rel, scope, len(body)))

    issues = []
    for rel, scope, size in sorted(empty_claims):
        issues.append({
            "type": "source_payload",
            "severity": "error",
            "message": (f"declares capture_scope: {scope} but retains a {size}-character body - "
                        "the note claims evidence it does not hold. Re-capture the source, or "
                        "set capture_scope: url-only to say plainly that only the locator was kept"),
            "files": [rel],
        })

    url_only = {rel for rel, scope in sources.items() if scope == "url-only"}
    if url_only:
        supported = _dependents_of(notes, url_only, skip=set(sources))
        for rel in sorted(supported):
            dependents = sorted(supported[rel])
            shown = ", ".join(dependents[:5]) + ("..." if len(dependents) > 5 else "")
            issues.append({
                "type": "source_payload",
                "severity": "error" if strict else "warning",
                "message": (f"capture_scope: url-only, and {len(dependents)} note(s) rest on it "
                            f"({shown}). The vault kept the locator, not the evidence: if the page "
                            "changes or dies, nothing behind those claims can be re-read"),
                "files": [rel] + dependents,
            })

    if unscoped:
        issues.append({
            "type": "source_payload",
            "severity": "warning" if strict else "info",
            "message": (f"{len(unscoped)} source note(s) have no capture_scope, so how much of each "
                        "source was actually retained is unknown (e.g. "
                        + ", ".join(sorted(unscoped)[:3])
                        + "). Sources written before the field existed read this way; "
                          "set full-local, bounded-local or url-only as you touch them"),
            "files": sorted(unscoped),
        })
    return issues


# --- source quality (#258) ---------------------------------------------------
# `source_quality` says whether a source's provenance was worth building on.
# It is orthogonal to `capture_scope` (how much was kept) and never a verdict on
# truth. Spec: references/source-quality-check.md.
SOURCE_QUALITY_VALUES = ("high", "medium", "speculation")
SOURCE_QUALITY_POLICIES = ("warn", "silent")
# Notes that record activity or navigate, rather than hold claims. A daily note
# that says "captured [[x]] today" is not knowledge resting on x; reporting it
# would be the nag that gets a check policy-toggled to silent within a week.
_ACTIVITY_NOTE_TYPES = frozenset({
    "daily", "log", "devlog", "index", "review", "learnings-review",
    "agenda-snapshot", "task", "recurring-task",
})
_ACTIVITY_NOTE_FILES = frozenset({"index.md", "log.md", "catchup.md", "home.md"})


def load_source_quality_policy(vault: Path) -> str:
    """`source_quality_policy` from `<vault>/.vault-config.json`: "warn" or "silent".

    Same never-inferred contract as load_rewrite_policy (#250): a missing file,
    a missing key, a malformed file, a non-string or any other value all mean
    "warn". There is deliberately no value that blocks a capture."""
    cfg_path = vault / ".vault-config.json"
    if not cfg_path.is_file():
        return "warn"
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "warn"
    if not isinstance(data, dict):
        return "warn"
    value = data.get("source_quality_policy")
    if isinstance(value, str) and value.strip().lower() == "silent":
        return "silent"
    return "warn"


def check_source_quality(notes: dict, vault: Path) -> list:
    """Active knowledge whose every cited source is `speculation` grade (#258).

    A note is reported only when it links at least one source AND every source
    it links carries a recognised `source_quality` of `speculation`. A source
    with no field is unjudged, not speculative, so one unlabelled source in the
    mix keeps the note quiet: this check never turns "not yet labelled" into a
    finding, which is what makes it safe on a vault written before the field.
    Daily, log, index and other activity notes are skipped: they record that a
    source was captured, they do not rest on it.
    A warning, because a speculative source is a legitimate thing to have read.
    """
    if load_source_quality_policy(vault) == "silent":
        return []
    graded = {}
    for rel, note in notes.items():
        if _fm_field(note["frontmatter"], "type") != "source":
            continue
        # A template line copied with its trailing `# high | medium | ...` comment.
        grade = _fm_field(note["frontmatter"], "source_quality").split("#", 1)[0].strip()
        if grade in SOURCE_QUALITY_VALUES:
            graded[rel] = grade
    speculative = {rel for rel, grade in graded.items() if grade == "speculation"}
    if not speculative:
        return []
    all_sources = {rel for rel, n in notes.items() if _fm_field(n["frontmatter"], "type") == "source"}
    by_note: dict = defaultdict(set)
    for source, dependents in _dependents_of(notes, all_sources, skip=all_sources).items():
        for dep in dependents:
            by_note[dep].add(source)
    issues = []
    for dep in sorted(by_note):
        if (_fm_field(notes[dep]["frontmatter"], "type") in _ACTIVITY_NOTE_TYPES
                or Path(dep).name.lower() in _ACTIVITY_NOTE_FILES):
            continue
        cited = by_note[dep]
        if cited and all(src in speculative for src in cited):
            shown = ", ".join(sorted(cited)[:3]) + ("..." if len(cited) > 3 else "")
            issues.append({
                "type": "source_quality",
                "severity": "warning",
                "message": (f"{dep} cites only speculation-grade sources ({shown}). Their "
                            "provenance is unknown, derived or conflicting: corroborate the "
                            "claims with a better source, or say plainly in the note that "
                            "they are unverified"),
                "files": [dep] + sorted(cited),
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

    # Wanted notes and missing attachments come out of one scan but mean
    # different things and get counted separately: a missing note is a gap to
    # write, a missing attachment is import cleanup.
    link_gaps = check_wanted_notes(notes, vault, excludes)
    # Empty dict when _meta/taxonomy.md does not exist - check_taxonomy is a
    # no-op on that input, so this stays wired unconditionally (#221).
    taxonomy = load_taxonomy(vault)

    checks = [
        ("Duplicates", check_duplicates(notes)),
        ("Tag taxonomy", check_taxonomy(notes, taxonomy)),
        ("Orphans", check_orphans(notes)),
        ("Stale tasks", check_stale_tasks(notes)),
        ("Code-fence-wrapped notes", check_code_fence_wrapped(notes)),
        ("Missing frontmatter", check_missing_frontmatter(notes)),
        ("Invalid tags", check_tag_syntax(notes)),
        ("Empty folders", check_empty_folders(vault, excludes)),
        ("Wanted notes", [i for i in link_gaps if i["type"] == "wanted_note"]),
        ("Missing attachments",
         [i for i in link_gaps if i["type"] == "missing_attachment"]),
        ("Template leftovers", check_template_leftovers(notes)),
        ("Source payload", check_source_payload(notes, vault)),
        ("Source quality", check_source_quality(notes, vault)),
        ("Semantic index coverage", check_semantic_index(vault, notes)),
        ("Rewrite policy", check_rewrite_policy(vault)),
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
        # Only on a clean run, and only ever once. A tool asking for a favour
        # right after reporting problems it found in your vault has the tone
        # exactly backwards.
        if result["total_issues"] == 0 and result["total_notes"] > 0:
            try:
                from star_prompt import maybe_ask
                maybe_ask(
                    f"Clean bill of health across {result['total_notes']} notes."
                )
            except Exception:
                pass  # a growth prompt must never be able to fail a health check


if __name__ == "__main__":
    main()
