#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""checkin.py - ask the owner whether old people and project notes still hold.

A fact check can only compare notes with other notes. News that never reached
the vault (a bill settled, a move, a new job) leaves a note stale forever, and
no lint can see it. The only source is the owner, so this asks them: a few
notes at a time, each shown with what it says and when that was last checked.

The deterministic half lives here so every host renders the same cards and
keeps the same memory; the agent only condenses each note into up to three
facts and applies the owner's answers.

    pick     notes worth asking about now (JSON, with an excerpt to condense)
    ask      put one note's card on the open list
    message  render the open cards as one short message and count the send
    done     close a card: same | updated | skipped (stamps last-checked)
    status   the open list as JSON

The open list lives in <vault>/.checkin.json, not in the chat, so a question
the host drops after an hour is re-sent by the next `message` until answered.

Which date counts: `last-checked` when present (only a check moves it), else
`updated` (the spec's "last meaningful update"), else `date`. A link-only edit
must not touch `updated`, or the note hides from the check-in for a cycle.
"""
import argparse
import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from note_io import NoteChangedError, read_exact, write_exact, write_exact_if_unchanged
from vault_health import _fm_field, load_vault, load_vault_config

STATE_FILE = ".checkin.json"
DEFAULT_TYPES = ("person", "project", "company", "entity")
DEFAULT_BOOST_TAGS = ("family",)
# Statuses that mean the note no longer describes a live thing - nothing to update.
CLOSED_STATUSES = {
    "superseded", "declined", "rejected", "archived", "obsolete", "cancelled",
    "closed", "parked", "inactive", "done", "completed", "on-hold",
}
OUTCOMES = ("same", "updated", "skipped")
HISTORY_CAP = 500
MAX_FACTS = 3
MAX_FACT_LEN = 140

ISO_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
PREAMBLE = re.compile(r"^#{1,6} For future \w+\s*$", re.MULTILINE | re.IGNORECASE)
HEADING = re.compile(r"^#{1,6} ", re.MULTILINE)
FRONTMATTER = re.compile(r"\A(﻿?---\r?\n)(.*?)(\r?\n---[ \t]*(?:\r?\n|\Z))", re.DOTALL)


def _date(value: str):
    m = ISO_DATE.search(value or "")
    try:
        return dt.date.fromisoformat(m.group(1)) if m else None
    except ValueError:
        return None


def facts_date(frontmatter: str):
    for field in ("last-checked", "updated", "date"):
        d = _date(_fm_field(frontmatter, field))
        if d:
            return d
    return None


def _target(link: str) -> str:
    return link.split("|")[0].split("#")[0].strip().rsplit("/", 1)[-1].lower()


def _excerpt(content: str, limit: int = 600) -> dict:
    """The preamble text and the first bullets: raw material for three facts."""
    body = FRONTMATTER.sub("", content, count=1)
    preamble = ""
    m = PREAMBLE.search(body)
    if m:
        rest = body[m.end():]
        nxt = HEADING.search(rest)
        preamble = " ".join((rest[: nxt.start()] if nxt else rest).split())[:limit]
    bullets = [
        ln.strip()[2:].strip()[:160]
        for ln in body.splitlines()
        if ln.strip().startswith(("- ", "* ")) and len(ln.strip()) > 4
    ][:10]
    return {"preamble": preamble, "bullets": bullets}


def load_state(vault: Path) -> dict:
    path = vault / STATE_FILE
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        state = {}
    except ValueError as exc:
        # A corrupt state file must stop the run, not reset it: resetting loses
        # every open question, which is the one thing this tool promises not to do.
        raise SystemExit(f"{path} is not valid JSON ({exc}); fix or move it, then re-run")
    state.setdefault("version", 1)
    state.setdefault("open", [])
    state.setdefault("closed", [])
    state.setdefault("last_message", {})
    return state


def save_state(vault: Path, state: dict) -> None:
    state["closed"] = state["closed"][-HISTORY_CAP:]
    write_exact(vault / STATE_FILE, json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def pick(vault: Path, today: dt.date, days: int, max_open: int,
         types: set, boost_tags: set) -> list:
    state = load_state(vault)
    room = max_open - len(state["open"])
    if room <= 0:
        return []
    open_notes = {c["note"] for c in state["open"]}
    cutoff = today - dt.timedelta(days=days)
    recently_skipped = {
        c["note"] for c in state["closed"]
        if c.get("outcome") == "skipped" and (_date(c.get("date", "")) or dt.date.min) > cutoff
    }

    notes = load_vault(vault, load_vault_config(vault))
    inbound = defaultdict(set)
    for rel, note in notes.items():
        for link in note["links"]:
            target = _target(link)
            if target and target != note["stem"].lower():
                inbound[target].add(rel)

    candidates = []
    for rel, note in notes.items():
        fm = note["frontmatter"]
        tags = {t.lower() for t in note["tags"]}
        note_type = _fm_field(fm, "type")
        if note_type not in types and "person" not in tags:
            continue
        if _fm_field(fm, "status") in CLOSED_STATUSES or _fm_field(fm, "checkin") == "never":
            continue
        if rel in open_notes or rel in recently_skipped:
            continue
        when = facts_date(fm)
        if when and when > cutoff:
            continue
        if tags & boost_tags or _fm_field(fm, "relationship") == "strong" \
                or _fm_field(fm, "checkin") == "priority":
            tier = 0
        elif _fm_field(fm, "status") in ("active", "planning") \
                or _fm_field(fm, "relationship") == "medium":
            tier = 1
        else:
            tier = 2
        links_in = len(inbound.get(note["stem"].lower(), ()))
        candidates.append((tier, -links_in, when or dt.date.min, rel, note, when))

    candidates.sort(key=lambda c: c[:4])
    return [
        {
            "note": rel,
            "title": note["stem"],
            "type": _fm_field(note["frontmatter"], "type"),
            "facts_date": when.isoformat() if when else None,
            "days_old": (today - when).days if when else None,
            "inbound_links": -neg_links,
            "excerpt": _excerpt(note["content"]),
        }
        for tier, neg_links, _, rel, note, when in candidates[:room]
    ]


def ask(vault: Path, today: dt.date, rel: str, facts: list) -> dict:
    note = vault / rel
    if not note.is_file():
        raise SystemExit(f"no such note: {rel}")
    facts = [" ".join(f.split())[:MAX_FACT_LEN] for f in facts if f.strip()]
    if not 1 <= len(facts) <= MAX_FACTS:
        raise SystemExit(f"give 1 to {MAX_FACTS} facts, got {len(facts)}")
    state = load_state(vault)
    if any(c["note"] == rel for c in state["open"]):
        return {"note": rel, "status": "already open"}
    text = read_exact(note) or ""
    m = FRONTMATTER.match(text)
    when = facts_date(m.group(2) if m else "")
    state["open"].append({
        "note": rel,
        "title": note.stem,
        "facts_date": when.isoformat() if when else None,
        "facts": facts,
        "asked": today.isoformat(),
        "sent": 0,
        "last_sent": None,
    })
    save_state(vault, state)
    return {"note": rel, "status": "opened"}


def _show_date(iso, today: dt.date) -> str:
    d = _date(iso or "")
    if d is None:
        return "undated"
    shown = f"{d.day} {d.strftime('%b')}"  # %-d is glibc-only, Windows rejects it
    return shown if d.year == today.year else f"{shown} {d.year}"


def message(vault: Path, today: dt.date, limit: int, peek: bool) -> str:
    state = load_state(vault)
    cards = state["open"][:limit]
    if not cards:
        return ""
    total = len(state["open"])
    reminder = max(c["sent"] for c in cards)
    noun = "note" if total == 1 else "notes"
    if reminder:
        head = f"Reminder {reminder}: still waiting on {total} {noun}"
    else:
        head = f"Vault check-in: {total} {noun} to confirm"
    lines = [head, ""]
    for i, card in enumerate(cards, 1):
        lines.append(f"**{i}. {card['title']}** (facts from {_show_date(card['facts_date'], today)})")
        lines += [f"- {fact}" for fact in card["facts"]]
        lines.append("")
    if total > len(cards):
        lines += [f"+{total - len(cards)} more waiting.", ""]
    lines.append('Reply like "1 same", "1 <what changed>", or "skip 1".')
    if not peek:
        for card in cards:
            card["sent"] += 1
            card["last_sent"] = today.isoformat()
        state["last_message"] = {str(i): c["note"] for i, c in enumerate(cards, 1)}
        save_state(vault, state)
    return "\n".join(lines)


def stamp_checked(note: Path, today: dt.date) -> None:
    """Set `last-checked: <today>` in the note's frontmatter, byte-exact elsewhere."""
    text = read_exact(note)
    if text is None:
        raise SystemExit(f"{note} is not valid UTF-8; not rewriting it")
    m = FRONTMATTER.match(text)
    if not m:
        raise SystemExit(f"{note} has no frontmatter to stamp")
    nl = "\r\n" if "\r\n" in m.group(1) else "\n"
    fm = m.group(2)
    line = f"last-checked: {today.isoformat()}"
    # [^\r\n]* rather than .*: in a CRLF note `.` eats the \r and the insert
    # would land between \r and \n.
    if re.search(r"^last-checked:[^\r\n]*", fm, re.MULTILINE):
        fm = re.sub(r"^last-checked:[^\r\n]*", line, fm, count=1, flags=re.MULTILINE)
    else:
        anchor = None
        for field in ("updated", "date"):
            anchor = re.search(rf"^{field}:[^\r\n]*", fm, re.MULTILINE)
            if anchor:
                break
        if anchor:
            fm = fm[: anchor.end()] + nl + line + fm[anchor.end():]
        else:
            fm = fm + nl + line
    write_exact_if_unchanged(note, m.group(1) + fm + m.group(3) + text[m.end():], text)


def done(vault: Path, today: dt.date, rel, number, outcome: str) -> dict:
    state = load_state(vault)
    if rel is None:
        rel = state["last_message"].get(str(number))
        if rel is None:
            raise SystemExit(f"number {number} is not in the last message sent")
    card = next((c for c in state["open"] if c["note"] == rel), None)
    if card is None:
        raise SystemExit(f"not open: {rel}")
    note = vault / rel
    if not note.is_file():
        outcome = "missing"  # moved or deleted since it was asked; close, do not stamp
    elif outcome in ("same", "updated"):
        try:
            stamp_checked(note, today)
        except NoteChangedError:
            raise SystemExit(f"{rel} changed on disk while stamping; re-run done")
    state["open"] = [c for c in state["open"] if c["note"] != rel]
    state["closed"].append({"note": rel, "outcome": outcome, "date": today.isoformat()})
    state["last_message"] = {k: v for k, v in state["last_message"].items() if v != rel}
    save_state(vault, state)
    return {"note": rel, "outcome": outcome, "open_left": len(state["open"])}


def _csv(value: str) -> set:
    return {x.strip().lower() for x in value.split(",") if x.strip()}


def main() -> int:
    ap = argparse.ArgumentParser(description="Ask the owner whether old notes still hold")
    ap.add_argument("--path", required=True, help="vault root")
    ap.add_argument("--today", help="YYYY-MM-DD (tests); default: local date")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pick", help="notes worth asking about now")
    p.add_argument("--days", type=int, default=14, help="facts older than this are due")
    p.add_argument("--max-open", type=int, default=3, help="never hold more open cards")
    p.add_argument("--types", default=",".join(DEFAULT_TYPES))
    p.add_argument("--boost-tags", default=",".join(DEFAULT_BOOST_TAGS))

    a = sub.add_parser("ask", help="open a card for one note")
    a.add_argument("--note", required=True, help="vault-relative path")
    a.add_argument("--fact", action="append", default=[], help="one short fact (1 to 3)")

    m = sub.add_parser("message", help="render open cards and count the send")
    m.add_argument("--limit", type=int, default=3)
    m.add_argument("--peek", action="store_true", help="render without counting a send")

    d = sub.add_parser("done", help="close a card")
    target = d.add_mutually_exclusive_group(required=True)
    target.add_argument("--note", help="vault-relative path")
    target.add_argument("--number", type=int, help="its number in the last message")
    d.add_argument("--outcome", required=True, choices=OUTCOMES)

    sub.add_parser("status", help="open cards as JSON")
    args = ap.parse_args()

    vault = Path(args.path).expanduser().resolve()
    if not vault.is_dir():
        raise SystemExit(f"vault not found: {vault}")
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()

    if args.cmd == "pick":
        out = pick(vault, today, args.days, args.max_open,
                   _csv(args.types), _csv(args.boost_tags))
    elif args.cmd == "ask":
        out = ask(vault, today, args.note, args.fact)
    elif args.cmd == "message":
        print(message(vault, today, args.limit, args.peek))
        return 0
    elif args.cmd == "done":
        out = done(vault, today, args.note, args.number, args.outcome)
    else:
        out = load_state(vault)["open"]
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
