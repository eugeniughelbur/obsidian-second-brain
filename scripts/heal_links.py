#!/usr/bin/env python3
"""
heal_links.py - heals broken/"wanted" wikilinks in an Obsidian vault.

A wiki-style vault often links a note by its human Title ([[Host iptables rules ...]])
while the file on disk is kebab-cased (host-iptables-rules-....md). Those links do not
resolve, so vault_health counts them as "wanted notes". This script repoints each such
link to the real note when exactly one note is an unambiguous match, preserving the
original text as a display alias: [[kebab-basename|Host iptables rules ...]].

Only certain matches are ever auto-applied:
  1. exact stem/alias match,
  2. slug match - fold diacritics, lowercase both sides, and collapse every run of
     non-alphanumeric characters to a single space, so "Title Case", "kebab-case",
     "Ivan"/"Ivan", punctuation and stray slashes all compare equal (this is what
     resolves the Title<->kebab case).
A fuzzy match (difflib) is only a GUESS - at any workable cutoff it will confuse
"Google Ads" with "Google Docs" and "ADR-2026-05-17" with "ADR-2026-05-11". So fuzzy
hits, ambiguous slugs (2+ candidates), and no-match links are never auto-fixed: they
are counted and handed to the AI triage loop (triage_links.py), which decides.

The score is vault_health.check_wanted_notes, so this count == the health check's count.

Look-only (changes nothing):
    python scripts/heal_links.py --path "/vault" --dry-run
Heal everything safe in one fast pass (recount once at the end):
    python scripts/heal_links.py --path "/vault" --batch
Incremental loop, bounded to N fixes, recounting each pass so you can watch:
    python scripts/heal_links.py --path "/vault" --apply --max 15
"""
import argparse
import re
import unicodedata
from collections import Counter, defaultdict
from difflib import get_close_matches
from pathlib import Path

# reuse the EXACT detection the health check uses, so our count == its count
from note_io import read_exact, write_exact
from vault_health import load_vault, check_wanted_notes

DECORATION = re.compile(r"[#|].*$")          # a #heading anchor or |display alias
LINK_IN_MSG = re.compile(r"\[\[(.+?)\]\] - wanted by ")
NON_ALNUM = re.compile(r"[^a-z0-9]+")         # any run of non-alphanumerics
PLACEHOLDER = set("*{}<>")                    # template/glob junk, never auto-fix


def slugify(text: str) -> str:
    """Fold diacritics, lowercase, and collapse every non-alphanumeric run to one space.

    "Host iptables rules", "host-iptables-rules" and "Flat /24 LAN" all normalize to a
    space-joined token stream, so a Title-cased wikilink matches its kebab-cased file.
    Diacritics are folded first (NFKD + ASCII), so "Ivan Rusakoff" == "Ivan Rusakoff"
    resolves as a certain slug match instead of falling to the fuzzy guesser.
    """
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return NON_ALNUM.sub(" ", folded.lower()).strip()


def base_target(link: str) -> str:
    link = DECORATION.sub("", link).strip()
    if "/" in link:
        link = Path(link).stem
    return link


def index_notes(notes):
    """Return (name_to_rel, stems, slug_to_rels).

    name_to_rel: exact lowercased stem/alias -> rel (first wins).
    stems:       lowercased stems, for the fuzzy fallback.
    slug_to_rels: slug -> set of rels (a set so collisions read as ambiguous).
    """
    name_to_rel = {}
    slug_to_rels = defaultdict(set)
    for rel, note in notes.items():
        stem = note["stem"]
        name_to_rel.setdefault(stem.lower(), rel)
        slug_to_rels[slugify(stem)].add(rel)
        for a in note["aliases"]:
            name_to_rel.setdefault(a.lower(), rel)
            slug_to_rels[slugify(a)].add(rel)
    stems = list({note["stem"].lower() for note in notes.values()})
    return name_to_rel, stems, slug_to_rels


def classify(link, name_to_rel, stems, slug_to_rels):
    base = base_target(link)
    if not base:
        return "skip", None
    low = base.lower()
    if low in name_to_rel:
        return "already_real", name_to_rel[low]
    # deterministic slug match on the FULL link (base_target mangles slashes like "/24")
    rels = slug_to_rels.get(slugify(link))
    if rels:
        if len(rels) == 1:
            return "easy_fix", next(iter(rels))
        return "ask_claude", sorted(rels)
    # A fuzzy hit is a GUESS, never a certainty: at cutoff 0.84 difflib matches
    # "Google Ads" -> "Google Docs" and "ADR-2026-05-17" -> "ADR-2026-05-11". Never
    # auto-apply it; hand any close names to triage so a human/AI makes the call.
    near = get_close_matches(low, stems, n=2, cutoff=0.84)
    if near:
        return "ask_claude", [name_to_rel[n] for n in near]
    return "no_target", None


def is_safe(link, target_rel):
    """Only auto-fix things we are sure about. Skip placeholders and templates."""
    if any(c in link for c in PLACEHOLDER):
        return False
    if any(p.lower() == "templates" for p in target_rel.split("/")):
        return False
    return True


def _rewrite(text, link, new_stem):
    """Repoint a bare [[link]] to [[new_stem|link]], keeping the readable title.

    Returns (new_text, count_replaced). Only bare links are touched; an already-aliased
    [[x|y]] is never matched here because check_wanted_notes reports the target only.
    """
    literal = f"[[{link}]]"
    n = text.count(literal)
    if n:
        text = text.replace(literal, f"[[{new_stem}|{link}]]")
    return text, n


def _collect_safe(wanted, name_to_rel, stems, slug_to_rels):
    """Bucket every wanted link and return per-file safe fixes: rel -> [(link, new_stem)]."""
    buckets = Counter()
    per_file = defaultdict(list)
    seen = set()
    for iss in wanted:
        m = LINK_IN_MSG.search(iss["message"])
        if not m:
            continue
        link, rel = m.group(1), iss["files"][0]
        kind, target = classify(link, name_to_rel, stems, slug_to_rels)
        buckets[kind] += 1
        if kind != "easy_fix" or not is_safe(link, target):
            continue
        if (rel, link) in seen:
            continue
        seen.add((rel, link))
        per_file[rel].append((link, Path(target).stem))
    return per_file, buckets


def dry_run(vault):
    notes = load_vault(vault)
    wanted = check_wanted_notes(notes, vault)
    per_file, buckets = _collect_safe(wanted, *index_notes(notes))
    safe = sum(len(v) for v in per_file.values())
    print(f"\nWanted links: {sum(buckets.values())}")
    print(f"  safe to auto-fix right now (no AI): {safe} across {len(per_file)} files")
    print(f"  already real (alias/path):          {buckets['already_real']}")
    print(f"  left for AI triage (ambiguous):     {buckets['ask_claude']}")
    print(f"  no match at all:                    {buckets['no_target']}")
    print("\nDRY RUN: nothing changed.\n")


def apply_batch(vault):
    print("\nBatch heal: one pass, all unambiguous fixes, single recount.\n")
    notes = load_vault(vault)
    wanted = check_wanted_notes(notes, vault)
    before = len(wanted)
    per_file, buckets = _collect_safe(wanted, *index_notes(notes))

    applied = files_touched = skipped = 0
    for rel, fixes in per_file.items():
        path = vault / rel
        text = read_exact(path)
        if text is None:
            print(f"  SKIPPED (not valid UTF-8, left untouched): {rel}")
            skipped += 1
            continue
        changed = 0
        for link, new_stem in fixes:
            text, n = _rewrite(text, link, new_stem)
            changed += n
        if changed:
            write_exact(path, text)
            applied += changed
            files_touched += 1

    after = len(check_wanted_notes(load_vault(vault), vault))
    print(f"  wanted links before:        {before}")
    print(f"  safe auto-fixes applied:    {applied} (across {files_touched} files)")
    if skipped:
        print(f"  skipped non-UTF-8 files:    {skipped}")
    print(f"  left for AI triage:         {buckets['ask_claude']}")
    print(f"  no match at all:            {buckets['no_target']}")
    print(f"  wanted links after:         {after}\n")


def find_next_safe_fix(per_file, skip_rels=frozenset()):
    for rel, fixes in per_file.items():
        if rel in skip_rels:
            continue
        if fixes:
            link, new_stem = fixes[0]
            return rel, link, new_stem
    return None


def apply_loop(vault, max_fixes):
    print(f"\nStarting the loop. Bounded to {max_fixes} safe fixes. Watch the count.\n")
    fixed = 0
    skip_rels = set()
    while fixed < max_fixes:
        notes = load_vault(vault)
        wanted = check_wanted_notes(notes, vault)
        before = len(wanted)
        per_file, _ = _collect_safe(wanted, *index_notes(notes))

        nxt = find_next_safe_fix(per_file, skip_rels)
        if nxt is None:
            print("  no more safe fixes left. stopping.")
            break

        rel, link, new_stem = nxt
        path = vault / rel
        text = read_exact(path)
        if text is None:
            print(f"  SKIPPED (not valid UTF-8, left untouched): {rel}")
            skip_rels.add(rel)
            continue
        text, _ = _rewrite(text, link, new_stem)
        write_exact(path, text)

        after = len(check_wanted_notes(load_vault(vault), vault))
        fixed += 1
        print(f"  fix {fixed:>2}: [[{link}]]")
        print(f"           -> [[{new_stem}|{link}]]   in {rel}")
        print(f"           wanted links: {before} -> {after}")

        if after >= before:
            print("  count did not drop - no-progress guard tripped, stopping.")
            break

    print(f"\nLoop stopped. {fixed} links healed. You pressed start once.\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--batch", action="store_true", help="heal all safe fixes in one fast pass")
    ap.add_argument("--max", type=int, default=15)
    args = ap.parse_args()
    vault = Path(args.path).expanduser()
    if args.batch:
        apply_batch(vault)
    elif args.apply:
        apply_loop(vault, args.max)
    else:
        dry_run(vault)


if __name__ == "__main__":
    main()
