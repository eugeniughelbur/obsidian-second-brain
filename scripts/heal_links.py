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
  2. faithful slug match - casefold both sides, fold diacritics (every alphabet
     survives, so "Привет Мир" matches "привет-мир"), and collapse separator runs
     to a single space, so "Title Case", "kebab-case", punctuation and stray
     slashes all compare equal (this is what resolves the Title<->kebab case).
     A slug that deleted meaning (C++ -> c) or folded to nothing is NOT certain
     and goes to triage instead; rewrites never touch code fences or inline code.
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
from vault_health import load_vault, check_wanted_notes, replace_outside_code

DECORATION = re.compile(r"[#|].*$")          # a #heading anchor or |display alias
LINK_IN_MSG = re.compile(r"\[\[(.+?)\]\] - wanted by ")
NON_WORD = re.compile(r"[\W_]+")              # any run of non-word chars, Unicode-aware
PLACEHOLDER = set("*{}<>[]")                  # template/glob/bracket junk, never auto-fix
# Characters slugify may silently fold away: separators per the Title<->kebab
# contract (plus en-dash U+2013 / em-dash U+2014, common in vault filenames).
# Folding anything ELSE away (+, #, &, emoji, ...) deletes meaning, so the match
# is a guess, not a certainty - see slug_is_faithful.
SAFE_FOLDED = set(" \t\r\n-_/\\.,:;()'\"!?|") | {"\u2013", "\u2014"}


def _fold(text: str) -> str:
    """NFKD-decompose and drop combining marks: accents fold, alphabets survive."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def slugify(text: str) -> str:
    """Casefold, fold diacritics, and collapse every non-word run to one space.

    "Host iptables rules", "host-iptables-rules" and "Flat /24 LAN" all normalize to a
    space-joined token stream, so a Title-cased wikilink matches its kebab-cased file.
    Only decorations fold: accents drop ("Ivan" == "Ivan" with diacritics) but every
    alphabet survives ("Привет Мир" == "привет-мир"). The old ASCII-only fold erased
    whole alphabets, so [[Ελλάδα]], [[مرحبا]] and [[🚀🚀]] all slugged to "" and
    "matched" whichever single note also folded to nothing (stress-test fix 3/24).
    """
    return NON_WORD.sub(" ", _fold(text).casefold()).strip()


def slug_is_faithful(text: str) -> bool:
    """True when slugify lost nothing meaningful: every folded character was a
    separator. "C++" slugs to "c", deleting the ++ that distinguishes it from C -
    an unfaithful slug match is a guess and belongs in triage, not auto-fix."""
    return all(c.isalnum() or c in SAFE_FOLDED for c in _fold(text))


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
        # An empty slug (emoji-only or symbol-only title) must never be a match
        # key: "" == "" would pair unrelated names (stress-test fix 3/24).
        if s := slugify(stem):
            slug_to_rels[s].add(rel)
        for a in note["aliases"]:
            name_to_rel.setdefault(a.lower(), rel)
            if s := slugify(a):
                slug_to_rels[s].add(rel)
    stems = list({note["stem"].lower() for note in notes.values()})
    return name_to_rel, stems, slug_to_rels


def classify(link, name_to_rel, stems, slug_to_rels):
    base = base_target(link)
    if not base:
        return "skip", None
    low = base.lower()
    if low in name_to_rel:
        return "already_real", name_to_rel[low]
    # deterministic slug match on the FULL link (base_target mangles slashes like "/24"),
    # and only when slugging the link deleted nothing meaningful - otherwise the
    # "match" was manufactured by the fold (C++ -> c) and belongs in triage.
    slug = slugify(link)
    rels = slug_to_rels.get(slug) if slug and slug_is_faithful(link) else None
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
    Occurrences inside code fences and inline code are left alone - the wanted-link
    counter never saw them, so editing them would corrupt example code and make
    apply exceed what dry-run promised.
    """
    return replace_outside_code(text, f"[[{link}]]", f"[[{new_stem}|{link}]]")


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
