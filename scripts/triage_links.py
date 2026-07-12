#!/usr/bin/env python3
"""
triage_links.py - the loop that sorts dangling wikilinks into keep / create / delete.

It reads each broken link and the sentence it sits in, asks Claude what it is, and
tallies the verdict. Report-only by default: it decides, it does not edit.

    uv run scripts/triage_links.py --path "/vault" --limit 20

Needs ANTHROPIC_API_KEY in the environment.
"""
import argparse
import json
import os
import re
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

from note_io import read_exact, write_exact
from vault_health import load_vault, check_wanted_notes, replace_outside_code

LINK_IN_MSG = re.compile(r"\[\[(.+?)\]\]")
MODEL = "claude-haiku-4-5"

PROMPT = """You triage a broken wikilink in a personal Obsidian vault written with AI help.
The link points to a note that does not exist yet.

Note: {note}
The link appears in this line:
{line}
Link: [[{link}]]

Pick ONE:
KEEP - a deliberate placeholder the author will likely turn into a real note later
CREATE - the topic is substantial and clearly deserves its own note now
DELETE - a typo, a one-off, or junk; the link should just be removed

Reply as: WORD - up to 6 word reason"""


def ask_claude(note, line, link, key):
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 40,
        "messages": [{"role": "user",
                      "content": PROMPT.format(note=note, line=line[:300], link=link)}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.load(r)
    text = out["content"][0]["text"].strip()
    verdict = text.split()[0].upper().strip(":-")
    if verdict not in {"KEEP", "CREATE", "DELETE"}:
        verdict = "KEEP"
    return verdict, text


def line_for(vault, rel, link):
    for ln in (vault / rel).read_text(encoding="utf-8", errors="replace").splitlines():
        if f"[[{link}]]" in ln:
            return ln.strip()
    return ""


VERDICT_LINE = re.compile(r"^\s*(KEEP|CREATE|DELETE)\s+\[\[(.+?)\]\]")


def load_verdicts(path):
    """Parse {link_text: verdict} from a prior triage run's output."""
    verdicts = {}
    for ln in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        m = VERDICT_LINE.match(ln)
        if m:
            verdicts[m.group(2)] = m.group(1)
    return verdicts


def apply_verdicts(vault, verdicts, create_cap):
    broken = check_wanted_notes(load_vault(vault), vault)
    deleted, created, skipped = 0, 0, 0
    seen_create = set()
    for iss in broken:
        m = LINK_IN_MSG.search(iss["message"])
        if not m:
            continue
        link, rel = m.group(1), iss["files"][0]
        v = verdicts.get(link)
        if v == "DELETE":
            path = vault / rel
            text = read_exact(path)
            if text is None:
                print(f"  SKIPPED (not valid UTF-8, left untouched): {rel}")
                skipped += 1
                continue
            # Delete only prose occurrences: a [[link]] inside a code fence or
            # inline code is example text the counter never reported.
            new_text, n = replace_outside_code(text, f"[[{link}]]", link)
            if n:
                write_exact(path, new_text)
                deleted += 1
        elif v == "CREATE" and link not in seen_create and created < create_cap:
            seen_create.add(link)
            # Triage cannot reliably know the note's type, so it does NOT assert one.
            # Stubs land in a single holding folder marked `type: stub`; a human or a
            # later Claude pass classifies and moves them. Link resolution is by
            # filename, so the stub heals the broken link from here just the same.
            stubs_root = (vault / "wiki" / "stubs").resolve()
            stub = stubs_root / f"{link}.md"
            # Containment guard: the link text is vault content shaped by an LLM verdict,
            # so a crafted or hallucinated [[../../x]] or [[/abs/x]] must never write
            # outside the stubs folder. Resolve and confirm the target stays inside it;
            # skip (never crash the batch) if it escapes.
            try:
                safe_stub = stub.resolve()
                safe_stub.relative_to(stubs_root)
            except (ValueError, OSError):
                print(f"  SKIPPED (unsafe link path, not created): [[{link}]]")
                skipped += 1
                continue
            if not safe_stub.exists():
                safe_stub.parent.mkdir(parents=True, exist_ok=True)
                today = date.today().isoformat()
                safe_stub.write_text(
                    f"---\ntype: stub\ndate: {today}\ntags: [stub]\nai-first: true\n---\n\n"
                    f"## For future Claude\n\nStub created by link triage on {today}. "
                    f"`{link}` was referenced across the vault but had no note. "
                    f"Classify it (person, project, concept, decision, etc.), fill it from "
                    f"context, set the real `type:`, and move it to the matching folder when "
                    f"you next encounter it.\n",
                    encoding="utf-8")
                created += 1
    return deleted, created, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--from", dest="src", help="prior triage output to act on")
    ap.add_argument("--create-cap", type=int, default=5)
    args = ap.parse_args()
    vault = Path(args.path).expanduser()

    if args.apply:
        if not args.src:
            ap.error("--from <prior triage output> is required with --apply")
        verdicts = load_verdicts(args.src)
        d, c, s = apply_verdicts(vault, verdicts, args.create_cap)
        after = len(check_wanted_notes(load_vault(vault), vault))
        print(f"\nDeleted {d} junk links, created {c} stub notes.")
        if s:
            print(f"Skipped {s} (non-UTF-8 file or unsafe link path, left untouched).")
        print(f"Wanted notes now: {after}\n")
        return

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("set ANTHROPIC_API_KEY")
    broken = check_wanted_notes(load_vault(vault), vault)

    # One verdict per DISTINCT link text. apply_verdicts keys by link text and acts on
    # every occurrence, so triaging each unique dangling link once (instead of re-asking
    # for all N occurrences of the same link) is both consistent and cheaper.
    seen, unique = set(), []
    for iss in broken:
        m = LINK_IN_MSG.search(iss["message"])
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        unique.append((m.group(1), iss["files"][0]))

    print(f"\nTriaging {min(args.limit, len(unique))} of {len(unique)} distinct dangling links "
          f"({len(broken)} occurrences).\n")
    tally, n = Counter(), 0
    for link, rel in unique:
        if n >= args.limit:
            break
        verdict, text = ask_claude(Path(rel).stem, line_for(vault, rel, link), link, key)
        tally[verdict] += 1
        n += 1
        print(f"  {verdict:<7} [[{link}]]  ({text.split('-',1)[-1].strip()[:40]})")
    print("\nVerdicts: " + ", ".join(f"{k} {v}" for k, v in tally.most_common()))
    print("Report only. Nothing changed.\n")


if __name__ == "__main__":
    main()
