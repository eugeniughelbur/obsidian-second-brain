#!/usr/bin/env python3
"""Ranked keyword search over the vault, Korean-aware and stdlib-only.

Usage:
    python3 vault_search.py "query" [--vault PATH] [--limit N] [--json]

Design:
- Text is NFC-normalized on both sides. macOS can hand back filenames and
  pasted text in decomposed (NFD) Hangul, which otherwise never matches.
- Hangul / CJK runs are indexed as overlapping character bigrams, so Korean
  particles and endings do not break a match: "프로젝트를" still shares
  three of four bigrams with "프로젝트".
- Latin tokens keep a length > 2 rule minus English stopwords.
- Title hits weigh more than body hits; body hits are length-normalized so a
  long transcript does not win on volume. raw/ captures and Logs/ fade.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import osb_env  # noqa: E402

_CJK_RE = re.compile(
    r"[ᄀ-ᇿ㄰-㆏぀-ヿ㐀-䶿一-鿿"
    r"가-힯豈-﫿]+"
)
_STOPWORDS = frozenset(
    "the a an and or but of to for in on at by with from as is are was were be been "
    "do does did have has had this that these those it its there here what when where "
    "who which why how will would can could should may might you we they my your our "
    "about into over than then so if not no all any some more most other".split()
)
_SKIP_DIRS = {".obsidian", ".git", ".trash", ".claude", ".codex", "node_modules"}
_FADE_PREFIXES = ("raw/", "Logs/")
_FADE_FILES = {"log.md", "index.md"}


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def query_terms(query: str, drop_stopwords: bool = True) -> list[str]:
    q = nfc(query).lower()
    terms: list[str] = []
    for run in _CJK_RE.findall(q):
        if len(run) == 1:
            terms.append(run)
        else:
            terms.extend(run[i:i + 2] for i in range(len(run) - 1))
    for tok in re.split(r"\W+", _CJK_RE.sub(" ", q)):
        if len(tok) > 2 and (not drop_stopwords or tok not in _STOPWORDS):
            terms.append(tok)
    seen: set[str] = set()
    return [t for t in terms if t and not (t in seen or seen.add(t))]


def iter_notes(vault: Path):
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
        for name in files:
            if name.endswith(".md"):
                yield Path(root) / name


def snippet(text: str, terms: list[str], width: int = 160) -> str:
    low = text.lower()
    pos = min((p for p in (low.find(t) for t in terms) if p >= 0), default=0)
    start = max(0, pos - width // 3)
    return re.sub(r"\s+", " ", text[start:start + width]).strip()


def search(vault: Path, query: str, limit: int = 10) -> list[dict]:
    terms = query_terms(query) or query_terms(query, drop_stopwords=False)
    if not terms:
        return []
    results = []
    for md in iter_notes(vault):
        try:
            text = nfc(md.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        rel = nfc(md.relative_to(vault).as_posix())
        title = nfc(md.stem).lower()
        low = text.lower()
        title_score = sum(5.0 * (1 + math.log1p(title.count(t))) for t in terms if t in title)
        body_score = sum(1 + math.log1p(low.count(t)) for t in terms if t in low)
        if not (title_score or body_score):
            continue
        matched = sum(1 for t in terms if t in low or t in title)
        coverage = matched / len(terms)
        length_norm = 1 + math.log1p(len(text) / 2000)
        score = (title_score + body_score / length_norm) * (0.5 + coverage)
        if rel.startswith(_FADE_PREFIXES) or md.name in _FADE_FILES:
            score *= 0.3
        type_match = re.search(r"(?m)^type:\s*['\"]?([\w-]+)", text[:1500])
        results.append({
            "path": rel,
            "title": nfc(md.stem),
            "type": type_match.group(1) if type_match else None,
            "score": round(score, 3),
            "snippet": snippet(text, terms),
        })
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("query")
    ap.add_argument("--vault", default="")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    vault = Path(args.vault or osb_env.vault_path() or "").expanduser()
    if not str(vault) or not vault.is_dir():
        print("error: vault path not configured. Run the installer or set "
              "OBSIDIAN_VAULT_PATH.", file=sys.stderr)
        return 2
    hits = search(vault, args.query, max(1, min(args.limit, 50)))
    if args.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
    else:
        for h in hits:
            print(f"{h['score']:>8}  {h['path']}  [{h['type'] or '-'}]\n          {h['snippet']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
