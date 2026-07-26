#!/usr/bin/env python3
"""Freshness lint - enforce references/freshness-policy.md on any markdown folder.

Part of OKM (Open Knowledge Metabolism), an open standard for keeping
AI-maintained knowledge folders true. Copyright (c) 2026 Eugeniu Ghelbur.
MIT-licensed. https://theaioperator.io

Every stored fact must be timeless, dated, or a pointer. This lint finds the
one illegal form: a present-tense claim about a fast fact, with no stamp,
outside a dated container.

Rules (see the spec for prose):
  FRESH-1 (error):   volatile quantitative claim without an "as of" stamp
  FRESH-2 (warning): stamp on a volatile claim older than the freshness window
  FRESH-3 (error):   typed pointer id with no mapping in .freshness.json
  FRESH-4 (exempt):  dated containers (dated filenames, dated headings,
                     freshness: snapshot frontmatter) are immutable history

Usage:
  python scripts/freshness_lint.py --path /path/to/folder [--json] [--strict]

Storage-agnostic and stdlib-only: works on an Obsidian vault, a team's
GitHub knowledge repo, or any folder of markdown. Configure per folder with
an optional .freshness.json at the root:
  { "window-days": 7, "volatile-nouns": ["gmv"], "pointer-types": {"linear": "https://linear.app/..."} }
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

from vault_scan import BASE_EXCLUDE_DIRS  # noqa: E402

DEFAULT_WINDOW_DAYS = 7

# Nouns whose counts/values change fast enough to rot (extend via config).
DEFAULT_VOLATILE = {
    "deal", "deals", "ticket", "tickets", "issue", "issues", "pr", "prs",
    "task", "tasks", "subscriber", "subscribers", "follower", "followers",
    "star", "stars", "user", "users", "member", "members", "customer",
    "customers", "lead", "leads", "download", "downloads", "install",
    "installs", "clone", "clones", "view", "views", "session", "sessions",
    "balance", "revenue", "mrr", "arr", "pipeline", "backlog", "queue",
    "vacancy", "vacancies", "opening", "openings", "contributor", "contributors",
}

# Words that mark a line as history rather than a current-state claim.
PAST_MARKERS = re.compile(
    r"\b(was|were|had|reached|hit|closed|shipped|merged|finished|completed|"
    r"grew|dropped|ended|launched|became)\b", re.IGNORECASE)

# A volatile count is only a CURRENT-STATE claim when the line says so.
# Without one of these, number+noun lines are usually timeless specs,
# history, or quotes - flagging them made v0 ~80% noise on a real vault.
CURRENT_MARKERS = re.compile(
    r"\b(currently|now|today|right now|at the moment|so far|to date|"
    r"has|have|open|active|pending|in[- ]flight|outstanding|unresolved|"
    r"remaining|this (week|month|quarter))\b|\bat \d", re.IGNORECASE)

# Line-initial Has/Have is imperative or a question, not a state claim.
IMPERATIVE_START = re.compile(r"^\s*(?:[-*>]\s*)?(?:\*\*)?(have|has)\b", re.IGNORECASE)

# Modal verbs mark rules, predictions, and hypotheticals - not observations.
MODAL = re.compile(r"\b(can|could|may|might|would|should|must|will)\b", re.IGNORECASE)

# Inline code spans are quotation, not claims (same principle as code fences).
CODE_SPAN = re.compile(r"`[^`]*`")

# HTML comments are invisible in rendered markdown - never content.
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})(?:-(\d{2}))?\b")
AS_OF = re.compile(r"\bas of\s+(\d{4})-(\d{2})(?:-(\d{2}))?", re.IGNORECASE)
NUMBER = re.compile(r"(?<![\w./-])\d[\d,.]*(?![\w-])")
ORDERED_LIST = re.compile(r"^\s*(?:>\s*)?\d+[.)]\s")
TYPED_POINTER = re.compile(r"\b([a-z][a-z0-9]+):([A-Za-z0-9][A-Za-z0-9/_-]+)\b")
URL = re.compile(r"https?://\S+")
HEADING = re.compile(r"^(#{1,6})\s")
# Typed-pointer prefixes that are just URI schemes or common false positives.
POINTER_IGNORE = {"http", "https", "mailto", "file", "obsidian", "tel", "ftp",
                  "note", "example", "type", "status", "date", "source"}


def parse_frontmatter(lines: list[str]) -> tuple[dict, int]:
    """Return (frontmatter dict-ish, index of first body line)."""
    if not lines or lines[0].strip() != "---":
        return {}, 0
    fm = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return fm, i + 1
        m = re.match(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$", line)
        if m:
            fm[m.group(1).strip().lower()] = m.group(2).strip().strip('"')
    return {}, 0


def stamp_date(m: re.Match) -> date:
    y, mo, d = int(m.group(1)), int(m.group(2)), m.group(3)
    return date(y, mo, int(d) if d else 28)  # month-only stamps get end-of-month grace


def load_config(root: Path) -> dict:
    cfg = root / ".freshness.json"
    if cfg.is_file():
        try:
            return json.loads(cfg.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"warning: could not read {cfg}: {exc}", file=sys.stderr)
    return {}


def parse_window(value, default: int) -> int:
    if value is None:
        return default
    s = str(value).strip().lower().rstrip("d")
    try:
        return int(s)
    except ValueError:
        return default


def lint_file(path: Path, rel: str, cfg: dict, today: date) -> list[dict]:
    try:
        # utf-8-sig: a BOM otherwise survives into lines[0], the "---" fence
        # check fails, and every freshness directive in the note is ignored -
        # so `freshness: snapshot` stops exempting and CI fails on exempt files.
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return []
    lines = text.splitlines()
    fm, body_start = parse_frontmatter(lines)

    # FRESH-4: whole-file exemptions - declared snapshots and dated filenames.
    if fm.get("freshness") == "snapshot":
        return []
    if ISO_DATE.search(path.stem):
        return []

    window = parse_window(fm.get("freshness-window"),
                          parse_window(cfg.get("window-days"), DEFAULT_WINDOW_DAYS))
    volatile = set(DEFAULT_VOLATILE) | {n.lower() for n in cfg.get("volatile-nouns", [])}
    pointer_types = {k.lower() for k in cfg.get("pointer-types", {})}

    findings = []
    in_fence = False
    dated_heading_level = None  # exempt region under a dated heading (FRESH-4)

    for lineno, line in enumerate(lines[body_start:], start=body_start + 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not stripped:
            continue

        h = HEADING.match(stripped)
        if h:
            level = len(h.group(1))
            if dated_heading_level is not None and level <= dated_heading_level:
                dated_heading_level = None
            if ISO_DATE.search(stripped):
                dated_heading_level = level
            continue
        if dated_heading_level is not None:
            continue  # FRESH-4: inside a dated section

        # Quoted code is never a claim: strip inline spans before any check.
        stripped = CODE_SPAN.sub("", stripped)
        stripped = HTML_COMMENT.sub("", stripped)

        # FRESH-3: typed pointers must be mapped (URLs are always fine).
        for pm in TYPED_POINTER.finditer(stripped):
            prefix = pm.group(1).lower()
            if prefix in POINTER_IGNORE or URL.search(pm.group(0)):
                continue
            if pm.group(2).isdigit():
                continue  # host:port (localhost:8080), not a typed pointer
            if ISO_DATE.fullmatch(pm.group(0)):
                continue
            if prefix not in pointer_types:
                findings.append({
                    "rule": "FRESH-3", "severity": "error", "file": rel,
                    "line": lineno,
                    "text": f"typed pointer '{pm.group(0)}' has no mapping in .freshness.json",
                })

        # Volatile-claim detection (FRESH-1 / FRESH-2 candidates).
        # Ordered-list step markers are structure, not quantities.
        claim_text = ORDERED_LIST.sub("", stripped)
        words = {w.strip(".,;:!?()[]*_`'\"").lower() for w in claim_text.split()}
        if stripped.lstrip().startswith(">"):
            continue  # blockquote: quoted speech or captured output, a snapshot by nature
        if not (words & volatile) or not NUMBER.search(claim_text):
            continue
        if not CURRENT_MARKERS.search(claim_text):
            continue  # timeless spec, history, or quote - not a current-state claim
        if MODAL.search(claim_text):
            continue  # "can change...", "must carry..." - a rule, not an observation
        if IMPERATIVE_START.match(claim_text) and not CURRENT_MARKERS.search(
                IMPERATIVE_START.sub("", claim_text, count=1)):
            continue  # "Have the server return..." - an instruction, not a fact
        if PAST_MARKERS.search(stripped):
            continue  # reads as history, not current state

        as_of = AS_OF.search(stripped)
        if as_of:
            age = (today - stamp_date(as_of)).days
            if age > window:
                findings.append({
                    "rule": "FRESH-2", "severity": "warning", "file": rel,
                    "line": lineno,
                    "text": f"stamp is {age}d old (window {window}d): refresh or convert to pointer: {stripped[:120]}",
                })
            continue
        if ISO_DATE.search(stripped):
            continue  # a bare date on the line scopes the claim (lenient snapshot)
        if URL.search(stripped):
            continue  # links out to where truth lives: pointer enough for v1

        findings.append({
            "rule": "FRESH-1", "severity": "error", "file": rel, "line": lineno,
            "text": f"undated present-tense claim about a fast fact: {stripped[:120]}",
        })
    return findings


SKIP_DIRS = frozenset(d.lower() for d in BASE_EXCLUDE_DIRS)  # see scripts/vault_scan.py


def lint_folder(root: Path, today: date | None = None) -> dict:
    today = today or datetime.now().date()
    cfg = load_config(root)
    exempt = {d.strip("/") for d in cfg.get("exempt-dirs", [])}
    findings: list[dict] = []
    for path in sorted(root.rglob("*.md")):
        parts = path.relative_to(root).parts
        if any(part.lower() in SKIP_DIRS for part in parts):
            continue
        if exempt and any("/".join(parts[:i + 1]) in exempt for i in range(len(parts) - 1)):
            continue
        findings.extend(lint_file(path, str(path.relative_to(root)), cfg, today))
    errors = sum(1 for f in findings if f["severity"] == "error")
    warnings = sum(1 for f in findings if f["severity"] == "warning")
    return {"errors": errors, "warnings": warnings, "findings": findings}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Freshness lint (see references/freshness-policy.md)")
    ap.add_argument("--path", required=True, help="folder of markdown to lint")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--strict", action="store_true", help="warnings also fail the run")
    args = ap.parse_args(argv[1:])

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    report = lint_folder(root)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for f in report["findings"]:
            print(f"[{f['rule']}] {f['severity']}: {f['file']}:{f['line']}  {f['text']}")
        print(f"\n{report['errors']} error(s), {report['warnings']} warning(s) "
              f"across {root}")
        if not report["findings"]:
            print("Folder is freshness-clean: every fact is timeless, dated, or a pointer.")
    if report["errors"] or (args.strict and report["warnings"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
