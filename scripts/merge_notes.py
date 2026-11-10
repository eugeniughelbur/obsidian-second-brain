#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""
merge_notes.py - merges two near-duplicate vault notes into one, per #220.

`/obsidian-health` finds duplicate pairs and stops (it is read-only by contract).
This script does the mechanical half of the merge: frontmatter union (canonical
wins on conflict, the loser is recorded under `merged_from:`), folding the
retired note's title into the canonical note's `aliases:`, and replacing the
retired note with a short `type: redirect` stub so wikilinks keep resolving and
the file is never deleted (references/write-rules.md - the vault is a permanent
record).

The merged BODY is deliberately NOT composed here. Deciding what is actually a
contradiction between two notes' prose is judgment, not mechanics - the same
split heal_links.py (mechanical) draws against triage_links.py (AI judgment).
commands/obsidian-merge.md composes the body (following references/ai-first-
rules.md: one `## For future agent` preamble, both provenance trails kept,
contradictions listed) and hands it to this script via --merged-body-file.

Dry-run and --apply run the exact same compute_merge() and differ only in
whether write_exact is called - the preview promise ("shows the diff and the
proposed merged note") is worthless if apply could write something dry-run
never showed.

Look-only, preview everything:
    python scripts/merge_notes.py --path "/vault" --canonical "A.md" --retire "B.md" \
        --merged-body-file /tmp/merged-body.md
List the duplicate pairs vault_health would report, without merging anything:
    python scripts/merge_notes.py --path "/vault" --from-health
Resolve the other side of a pair from the health scan and write it:
    python scripts/merge_notes.py --path "/vault" --from-health --canonical "A.md" \
        --merged-body-file /tmp/merged-body.md --apply
"""
import argparse
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_okf import parse_note  # noqa: E402 - reuse the one dict-frontmatter parser in the repo
from note_io import NoteChangedError, read_exact, write_exact_if_unchanged  # noqa: E402
from vault_health import check_duplicates, load_vault, load_vault_config  # noqa: E402

# Bare tokens (idea, active, 2026-08-26, research-notebooklm) are left unquoted,
# matching the actual generated notes in this repo (bootstrap_vault.py's
# templates, notebooklm.py's NOTEBOOKLM_NOTE_TEMPLATE both leave type/status/
# date bare) rather than CLAUDE.md's "quote when in doubt" prose, which the
# real templates don't follow either. Wikilinks ("[[X]]") MUST be quoted: a
# leading "[" is YAML flow-sequence syntax, so an unquoted wikilink is not a
# style choice, it is invalid/misparsed YAML.
_YAML_RESERVED = {"true", "false", "null", "~", "yes", "no", "on", "off", ""}
_UNSAFE_LEAD = set("[]{}#&*!|>'\"%@`-?:,")


def _bare_safe(s: str) -> bool:
    if not s or s != s.strip():
        return False
    if s.lower() in _YAML_RESERVED:
        return False
    if s[0] in _UNSAFE_LEAD:
        return False
    return ": " not in s and not s.endswith(":") and " #" not in s


def _scalar(v) -> str:
    if v is None:
        return '""'
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if _bare_safe(s):
        return s
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _dump_entry(key: str, v, indent: int = 0) -> str:
    """Render one `key: value` frontmatter entry, block style.

    Handles the three shapes a merge ever produces: a plain scalar, a flat list
    (tags, aliases, related-projects, ...), and one-or-more levels of dict
    (merged_from, and any relations:-style block a source note already carried).
    List items are assumed scalar - no schema in ai-first-rules.md uses a list
    of objects. Extend here if one ever does.
    """
    pad = "  " * indent
    if isinstance(v, list):
        if not v:
            return f"{pad}{key}: []"
        items = "\n".join(f"{pad}  - {_scalar(i)}" for i in v)
        return f"{pad}{key}:\n{items}"
    if isinstance(v, dict):
        if not v:
            return f"{pad}{key}: {{}}"
        sub = "\n".join(_dump_entry(k, sv, indent + 1) for k, sv in v.items())
        return f"{pad}{key}:\n{sub}"
    return f"{pad}{key}: {_scalar(v)}"


def dump_frontmatter(fm: dict) -> str:
    """The inverse of export_okf.parse_note's yaml.safe_load - there is no
    existing serializer in this repo (yaml.dump's default style does not match
    the hand-tuned conventions in CLAUDE.md), so this writes clean text
    directly instead of reformatting through PyYAML."""
    body = "\n".join(_dump_entry(k, v) for k, v in fm.items())
    return f"---\n{body}\n---\n"


@dataclass
class MergeResult:
    canonical_rel: str
    retire_rel: str
    canonical_text: str
    redirect_text: str
    merged_fm: dict
    # The exact bytes each note held when the merge was computed (#217). --apply
    # can run long after the dry run the user read, and a merge rewrites one note
    # whole and replaces the other with a stub, so a concurrent edit to either is
    # the most expensive one in the project to lose.
    canonical_before: str = ""
    retire_before: str = ""
    conflicts: dict = field(default_factory=dict)
    alias_added: str | None = None


def merge_frontmatter(canonical_fm: dict, retired_fm: dict, retired_title: str, canonical_title: str) -> tuple:
    """Union of fields; canonical wins on conflict, loser goes under merged_from.

    Per #220: "on conflict, the canonical note's value wins and the other is
    recorded under a merged_from: block." A field present in only one note is
    not a conflict - it just joins the union. Equal values are not a conflict
    either, so a merged_from block only appears when something was actually
    overwritten (empty conflicts -> no merged_from key at all).
    """
    merged = dict(canonical_fm)
    conflicts = {}
    for k, v in retired_fm.items():
        if k not in canonical_fm:
            merged[k] = v
        elif isinstance(canonical_fm[k], list) and isinstance(v, list):
            # Two lists (tags, aliases, related-*) are a union, not a conflict:
            # "canonical wins" would silently drop every tag only the retired
            # note carried. Order: canonical's items first, then new ones.
            seen = {str(x).lower() for x in canonical_fm[k]}
            merged[k] = list(canonical_fm[k]) + [
                x for x in v if str(x).lower() not in seen and not seen.add(str(x).lower())
            ]
        elif canonical_fm[k] != v:
            conflicts[k] = v
    if conflicts:
        merged["merged_from"] = {"path": None, **conflicts}  # path filled in by caller

    # Fold the retired title into aliases (#220) - unless it IS the canonical
    # title (same-name notes in different folders, e.g. two "Project Alpha.md"),
    # where an alias identical to the note's own filename is dead weight.
    aliases = list(merged.get("aliases") or [])
    alias_added = None
    if retired_title.lower() != canonical_title.lower() and not any(
        str(a).lower() == retired_title.lower() for a in aliases
    ):
        aliases.append(retired_title)
        alias_added = retired_title
    if aliases:
        merged["aliases"] = aliases
    return merged, conflicts, alias_added


def _load_note(vault: Path, rel: str) -> tuple:
    path = vault / rel
    if not path.is_file():
        raise SystemExit(f"not a file in the vault: {rel}")
    text = read_exact(path)
    if text is None:
        raise SystemExit(f"not valid UTF-8, refusing to merge: {rel}")
    fm, body, malformed = parse_note(text)
    if malformed:
        raise SystemExit(f"frontmatter is malformed YAML, fix it before merging: {rel}")
    return fm, body, text.startswith("\ufeff"), text


def compute_merge(vault: Path, canonical_rel: str, retire_rel: str, merged_body: str) -> MergeResult:
    canonical_fm, _, canonical_bom, canonical_before = _load_note(vault, canonical_rel)
    retired_fm, _, retired_bom, retire_before = _load_note(vault, retire_rel)
    retired_title = Path(retire_rel).stem
    canonical_title = Path(canonical_rel).stem

    merged_fm, conflicts, alias_added = merge_frontmatter(
        canonical_fm, retired_fm, retired_title, canonical_title
    )
    if conflicts:
        merged_fm["merged_from"]["path"] = retire_rel
    # A note that carried a UTF-8 BOM keeps it (the redirect stub below likewise):
    # the file is rewritten whole, but a byte an editor put there stays there.
    bom = "\ufeff" if canonical_bom else ""
    canonical_text = bom + dump_frontmatter(merged_fm) + "\n" + merged_body.lstrip("\n")
    if not canonical_text.endswith("\n"):
        canonical_text += "\n"

    # Link target for the redirect. A bare `[[stem]]` is what every existing
    # wikilink to the canonical note uses, so it is the right default - except
    # when both notes share a stem (the most common duplicate: "Ideas/Project
    # Alpha.md" vs "Archive/Project Alpha.md"). Then `[[Project Alpha]]` is
    # ambiguous and Obsidian may resolve it to the redirect note itself, so the
    # link is path-qualified instead.
    if retired_title.lower() == canonical_title.lower():
        link_target = canonical_rel[:-3] if canonical_rel.endswith(".md") else canonical_rel
    else:
        link_target = canonical_title

    today = date.today().isoformat()
    redirect_fm = {
        "date": today,
        "type": "redirect",
        "tags": ["redirect"],
        "redirects_to": f"[[{link_target}]]",
        "ai-first": True,
    }
    redirect_text = (
        ("\ufeff" if retired_bom else "")
        + dump_frontmatter(redirect_fm)
        + f"\nThis note was merged into [[{link_target}]] on {today}. "
        "See the canonical note for current content.\n"
    )

    return MergeResult(
        canonical_rel=canonical_rel,
        retire_rel=retire_rel,
        canonical_text=canonical_text,
        redirect_text=redirect_text,
        merged_fm=merged_fm,
        canonical_before=canonical_before,
        retire_before=retire_before,
        conflicts=conflicts,
        alias_added=alias_added,
    )


def preview(result: MergeResult) -> None:
    print(f"\nCanonical (survives, path unchanged): {result.canonical_rel}")
    print(f"Retired (becomes a redirect stub):     {result.retire_rel}\n")
    if result.conflicts:
        print(f"Frontmatter conflicts (canonical wins, loser -> merged_from): {sorted(result.conflicts)}")
    else:
        print("Frontmatter conflicts: none")
    if result.alias_added:
        print(f"Alias added to canonical: {result.alias_added!r}\n")
    else:
        print()
    print(f"--- proposed {result.canonical_rel} ---")
    print(result.canonical_text)
    print(f"--- proposed {result.retire_rel} (replaces its current content) ---")
    print(result.redirect_text)
    print("DRY RUN: nothing changed. Re-run with --apply to write.\n")


def apply_merge(vault: Path, result: MergeResult) -> None:
    """Write both halves, or neither (#217).

    Both notes are checked against the bytes the merge was computed from before
    either is written, so a concurrent edit cannot leave the vault half-merged -
    a canonical note holding the merged body while the note it was supposed to
    retire still stands as a second copy is worse than no merge at all.
    """
    canonical = vault / result.canonical_rel
    retire = vault / result.retire_rel
    for path, before in ((canonical, result.canonical_before), (retire, result.retire_before)):
        if read_exact(path) != before:
            raise NoteChangedError(path)
    write_exact_if_unchanged(canonical, result.canonical_text, result.canonical_before)
    write_exact_if_unchanged(retire, result.redirect_text, result.retire_before)
    print(f"\nMerged. {result.retire_rel} is now a redirect stub pointing at {result.canonical_rel}.\n")


def list_health_pairs(vault: Path) -> None:
    """--from-health with no --canonical: report what vault_health.check_duplicates
    found, without merging anything. Groups of exactly 2 files can be resolved
    automatically by find_health_pair(); larger groups need explicit
    --canonical/--retire because nothing in the health check says which file
    should survive."""
    excludes = load_vault_config(vault)
    notes = load_vault(vault, excludes)
    issues = check_duplicates(notes)
    pairs = [iss for iss in issues if len(iss["files"]) == 2]
    others = [iss for iss in issues if len(iss["files"]) != 2]
    print(f"\nDuplicate groups from the health scan: {len(issues)}")
    print(f"  auto-pairable (exactly 2 files): {len(pairs)}")
    for iss in pairs:
        a, b = iss["files"]
        print(f"    [{iss['severity']}] {a}  <->  {b}   ({iss['message']})")
    if others:
        print(f"  needs explicit --canonical/--retire (group size != 2): {len(others)}")
        for iss in others:
            print(f"    [{iss['severity']}] {iss['files']}   ({iss['message']})")
    print(
        "\nRe-run with --from-health --canonical <path> --merged-body-file <file> "
        "to merge one pair (add --apply to write).\n"
    )


def find_health_pair(vault: Path, canonical_rel: str) -> str:
    """Resolve --retire from the health scan: the other file in the one 2-file
    duplicate group that contains canonical_rel. Anything ambiguous (not found,
    in >1 group, or a group bigger than 2) is a hard error - guessing which
    note survives is exactly what this script must never do."""
    excludes = load_vault_config(vault)
    notes = load_vault(vault, excludes)
    groups = [iss["files"] for iss in check_duplicates(notes) if canonical_rel in iss["files"]]
    if not groups:
        raise SystemExit(
            f"--from-health: {canonical_rel!r} is not in any duplicate group from the current health scan."
        )
    if len(groups) > 1:
        raise SystemExit(f"--from-health: {canonical_rel!r} appears in multiple duplicate groups; "
                          "pass --retire explicitly.")
    files = groups[0]
    if len(files) != 2:
        raise SystemExit(
            f"--from-health: the group containing {canonical_rel!r} has {len(files)} notes {files} - "
            "only 2-file groups auto-pair. Pick the pair yourself with --canonical/--retire."
        )
    return next(f for f in files if f != canonical_rel)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--canonical", help="vault-relative path of the note that survives")
    ap.add_argument("--retire", help="vault-relative path of the note that becomes a redirect")
    ap.add_argument("--from-health", action="store_true",
                     help="resolve --retire from vault_health's current duplicate scan; "
                          "with no --canonical, lists the candidate pairs instead of merging")
    ap.add_argument("--merged-body-file",
                     help="file holding the composed merged body (required to merge; "
                          "dry-run previews the same text --apply would write)")
    ap.add_argument("--apply", action="store_true", help="write the merge (default: dry run)")
    args = ap.parse_args()
    vault = Path(args.path).expanduser()

    if args.from_health and not args.canonical:
        list_health_pairs(vault)
        return

    if not args.canonical:
        ap.error("--canonical is required (with --retire, or with --from-health to resolve the pair)")

    if args.from_health:
        retire_rel = find_health_pair(vault, args.canonical)
    elif args.retire:
        retire_rel = args.retire
    else:
        ap.error("need --retire <path>, or --from-health to resolve it from the current duplicate scan")

    if args.canonical == retire_rel:
        ap.error("--canonical and --retire must be different notes")

    if not args.merged_body_file:
        ap.error(
            "--merged-body-file is required: dry-run previews the exact text --apply would "
            "write, so compose the merged body first (see commands/obsidian-merge.md)"
        )
    merged_body = read_exact(Path(args.merged_body_file).expanduser())
    if merged_body is None:
        ap.error(f"--merged-body-file is not valid UTF-8: {args.merged_body_file}")

    result = compute_merge(vault, args.canonical, retire_rel, merged_body)
    if args.apply:
        apply_merge(vault, result)
    else:
        preview(result)


if __name__ == "__main__":
    main()
