"""Vault operations for the Obsidian Second Brain MCP server.

Pure stdlib, no MCP dependency, so the logic is unit-testable on its own. The
MCP wiring in `server.py` is a thin layer over these functions.

Every write follows the AI-first rule (references/ai-first-rules.md): frontmatter
with type/date/tags/ai-first, a `## For future Claude` preamble, and a
`source: mcp` marker so notes added through the connector are distinguishable.
"""

from __future__ import annotations

import json
from collections import OrderedDict
import math
import os
import re
import sys
import unicodedata
import urllib.request
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

_VAULT_ENV = "OBSIDIAN_VAULT_PATH"

# Notes added via the connector land here, separate from hand-authored notes.
_NOTES_DIR = "Inbox"

# Never scanned during search (config, vcs, immutable sources, exports). `.claude`
# is a vault-local agent config dir (CLAUDE.md, commands, settings) - its markdown
# is not vault content and would inflate every result (see issue #80).
# Canonical skip set for the WHOLE search stack: semantic_search.py imports it
# and retrieval_eval.py consults it, so lexical scan, semantic index, and eval
# all search the same universe (stress-test fix 10/24).
# Mirrors scripts/vault_scan.BASE_EXCLUDE_DIRS. Kept as a literal because this
# module ships standalone in the MCP server and must not import from scripts/.
# tests/test_exclude_policy.py pins the two together so they cannot drift again.
_SKIP_DIRS = {".obsidian", ".git", ".trash", "_trash", ".claude", "_export",
              "templates", "node_modules", ".agents", ".codex", ".gemini",
              ".opencode", "__pycache__"}

# Directories no write tool may touch. `raw/` holds original sources the skill
# treats as immutable, and `templates` needs to match the conventional capital-T
# `Templates/` a bootstrapped vault actually creates - the old guard compared a
# lowercase set against un-lowercased path parts, so it never matched.
_PROTECTED_WRITE_DIRS = _SKIP_DIRS | {"raw"}

# Operational logs and immutable raw sources are rarely the *answer* to a query:
# they are long and term-dense, so without a penalty they dominate term-frequency
# ranking and bury short canonical notes (measured: 0% recall@10 before this - see
# scripts/eval/retrieval_eval.py). De-weight them so they stay findable but cannot
# outrank a real wiki note on equal terms.
# Common function words carry no retrieval signal but recur thousands of times in
# long notes, so without filtering they let any long note outscore the right one on
# "the/what/status" alone (measured: a query like "what is the status of X" returned
# 10 meeting notes, none the target). Drop them from query terms before scoring.
_STOPWORDS = frozenset(
    "the a an and or but of to for in on at by with from as is are was were be been "
    "being do does did doing have has had this that these those it its their there here "
    "what when where who whom which why how whose will would can could should may might "
    "i you he she we they me him her us them my your his our about into over under than "
    "then so if not no yes all any some more most other into out up down off again".split()
)

# CJK ideographs and kana/hangul are all Python `\w`, so `\W+` never splits a
# Chinese/Japanese/Korean phrase and the English `len > 2` noise filter then
# discards the result - a 2-char CJK word is a full word, not noise (issue #159).
# Match CJK runs explicitly so they can be indexed as overlapping character
# bigrams (unigram when the run is a single char) instead of being dropped.
_CJK_RE = re.compile(
    r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af\uff66-\uff9d]+"
)


def _query_terms(query: str, *, drop_stopwords: bool = True) -> List[str]:
    """Split a query into search terms, CJK-aware.

    Latin/ASCII tokens keep the English rule (len > 2, minus stopwords) - two
    letters there is noise. CJK runs are indexed as overlapping character bigrams
    (`知識管理` -> 知識, 識管, 管理), with a lone character kept as a unigram, so a
    2-char word like 系統 survives and a reordered phrase still overlaps. Order is
    preserved and duplicates removed so scoring is stable."""
    q = query.lower()
    terms: List[str] = []
    for run in _CJK_RE.findall(q):
        if len(run) == 1:
            terms.append(run)
        else:
            terms.extend(run[i:i + 2] for i in range(len(run) - 1))
    non_cjk = _CJK_RE.sub(" ", q)
    for t in re.split(r"\W+", non_cjk):
        if len(t) > 2 and (not drop_stopwords or t not in _STOPWORDS):
            terms.append(t)
    seen: set = set()
    out: List[str] = []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out

_SEARCH_DEWEIGHT_PREFIXES = ("raw/",)
_SEARCH_DEWEIGHT_FILES = {"log.md"}
# Tunable so retrieval changes can be A/B-measured (set to 1.0 to disable the penalty).
_SEARCH_DEWEIGHT_FACTOR = float(os.environ.get("OBSIDIAN_SEARCH_DEWEIGHT") or "0.15")
# Type-aware volume (stress-test fix 13/24): term-dense operational logs took #1
# on 7 of 12 audit queries, burying canonical notes. Log-ish notes fade to 0.5 -
# a moderator, not a mute: they lose ties against canon but still win when they
# are genuinely the best match. Person/entity dossiers get a modest boost.
_SEARCH_LOG_WEIGHT = float(os.environ.get("OBSIDIAN_SEARCH_LOG_WEIGHT") or "0.5")
_SEARCH_ENTITY_BOOST = float(os.environ.get("OBSIDIAN_SEARCH_ENTITY_BOOST") or "1.5")
_LOG_TYPES = {"log", "dev-log", "daily", "worklog"}
_ENTITY_TYPES = {"person", "entity"}
_LOG_FOLDERS = {"logs", "daily", "dev logs"}
# Freshness (stress-test fix 15/24): a "what is CURRENT" query ranked a
# superseded/declined note above the one that still holds. Two levers, lexical arm only (the
# semantic arm rejected additive nudges by measurement in fix 13):
# - a recency band: old notes lose near-ties, gently always, strongly when the
#   query itself asks about the present (current/now/still/today/latest)
# - a status fade: notes whose OWN metadata says they no longer hold
#   (superseded/declined/archived/parked/on-hold...) step back
_STALE_STATUSES = {"superseded", "declined", "rejected", "archived", "obsolete",
                   "cancelled", "closed", "parked", "inactive", "done"}
_STATUS_RE = re.compile(r"(?m)^status:\s*['\"]?([A-Za-z0-9_-]+)")
# The supersedes REVERSE edge (fork-insights round 2, the local-first memory
# fork): when ADR A declares `supersedes: "[[B]]"`, B should fade even if B's
# own status was never updated - the exact "vault forgot to update the old
# note" failure the freshness policy warns about. Checked within the candidate
# set only (both notes compete on the same query), so it stays O(results).
_SUPERSEDES_RE = re.compile(r"(?m)^supersedes:\s*(.+)$")
_WIKILINK_TARGET_RE = re.compile(r"\[\[([^\]|#]+)")
_DATE_RE_FM = re.compile(r"(?m)^(?:updated|date):\s*['\"]?(\d{4})-(\d{2})-(\d{2})")
_CURRENT_INTENT = {"current", "currently", "now", "today", "still", "latest", "actual"}
_STATUS_FADE = float(os.environ.get("OBSIDIAN_SEARCH_STATUS_FADE") or "0.6")


def _note_age_days(text: str, md: Path) -> float:
    """Days since the note last held true: updated: > date: > file mtime."""
    dates = _DATE_RE_FM.findall(text[:400])
    if dates:
        y, mo, d = max(dates)
        try:
            then = datetime(int(y), int(mo), int(d))
            return max(0.0, (datetime.now() - then).days)
        except ValueError:
            pass
    try:
        return max(0.0, (datetime.now().timestamp() - md.stat().st_mtime) / 86400)
    except OSError:
        return 0.0


def _freshness_rerank(results, vault: Path, current_intent: bool):
    """Post-fusion re-rank: the semantic arm knows nothing about time or status,
    so fusion happily served a superseded note above the one that still holds for
    a "what is current now" query. Reads only the top results' frontmatter heads
    (cheap): stale-status notes step back always (their own metadata says they
    no longer hold); recency reorders only when the query asks about the
    present. Rank-derived base scores keep this a reorder, never a rewrite."""
    # Pass 1: read heads once; collect every note some OTHER candidate claims
    # to supersede (by wikilink target stem, lowercased).
    heads: list[str] = []
    superseded_targets: set = set()
    for r in results:
        try:
            head = (vault / r["path"]).read_text(encoding="utf-8-sig", errors="ignore")[:400]
        except OSError:
            head = ""
        heads.append(head)
        for line in _SUPERSEDES_RE.findall(head):
            for target in _WIKILINK_TARGET_RE.findall(line):
                superseded_targets.add(PurePosixPath(target.strip()).stem.lower())

    rescored = []
    for i, (r, head) in enumerate(zip(results, heads, strict=True)):
        weight = 1.0
        sm = _STATUS_RE.search(head)
        if sm and sm.group(1).lower() in _STALE_STATUSES:
            weight *= _STATUS_FADE
        # Reverse edge: a candidate that another candidate supersedes steps
        # back even when its own status was never updated.
        if superseded_targets and PurePosixPath(r["path"]).stem.lower() in superseded_targets:
            weight *= _STATUS_FADE
        if current_intent and head:
            weight *= _freshness_weight(_note_age_days(head, vault / r["path"]), True)
        rescored.append((weight / (_RRF_K + i), r))
    rescored.sort(key=lambda t: t[0], reverse=True)
    return [r for _, r in rescored]


def _freshness_weight(age_days: float, current_intent: bool) -> float:
    """Multiplicative band on lexical scores. Default band [0.92, 1.0] only
    breaks near-ties (evergreen notes unharmed); current-intent queries widen
    it to [0.6, 1.0] with a ~90-day half-life - the question said "now"."""
    if current_intent:
        return 0.6 + 0.4 * math.exp(-age_days / 130.0)
    return 0.92 + 0.08 * math.exp(-age_days / 270.0)
_TYPE_RE = re.compile(r"(?m)^type:\s*[\"\']?([A-Za-z0-9_-]+)")


def _type_weight(rel: str, text: str) -> float:
    """Volume knob for a note based on its declared type (folder as fallback)."""
    m = _TYPE_RE.search(text[:400])
    ntype = m.group(1).lower() if m else ""
    if ntype in _ENTITY_TYPES:
        return _SEARCH_ENTITY_BOOST
    if ntype in _LOG_TYPES:
        return _SEARCH_LOG_WEIGHT
    if not ntype and any(part.lower() in _LOG_FOLDERS for part in rel.split("/")[:-1]):
        return _SEARCH_LOG_WEIGHT
    return 1.0

# BM25-style sublinear-TF + length normalization. Env-toggle for A/B (0 = old raw counts).
_SEARCH_LENGTH_NORM = os.environ.get("OBSIDIAN_SEARCH_LENGTHNORM", "1") != "0"

# Optional semantic (meaning-based) layer. Activates ONLY when a local embedding
# index exists at the vault root AND a local Ollama model is reachable - so it is
# opt-in by setup (build the index with scripts/eval/semantic_search.py --build).
# When present, query results are the Reciprocal-Rank-Fusion of lexical + semantic
# (measured best all-rounder). Any failure (no index, Ollama down, bad response)
# silently falls back to pure lexical, so search never breaks or hangs.
_SEMANTIC_INDEX_FILE = ".obsidian-semantic-index.json"
_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
_EMBED_MODEL = os.environ.get("OBSIDIAN_EMBED_MODEL", "bge-m3")
# Backend mirrors scripts/eval/semantic_search.py: "ollama" (default, local) or
# "openai" (any OpenAI-compatible /v1/embeddings - other local runtimes or a cloud API).
_EMBED_BACKEND = os.environ.get("OBSIDIAN_EMBED_BACKEND", "ollama").lower()
_EMBED_URL = os.environ.get("OBSIDIAN_EMBED_URL", _OLLAMA_URL).rstrip("/")
_EMBED_KEY = os.environ.get("OBSIDIAN_EMBED_KEY", "")
_SEMANTIC_ENABLED = os.environ.get("OBSIDIAN_SEARCH_SEMANTIC", "1") != "0"
_RRF_K = 60
_FUSE_DEPTH = 25  # how many from each ranking feed the fusion
# Semantic votes count more than lexical ones in the fusion. Measured on the
# straightened ruler (fix 11/24): flat 1:1 fusion let noisy term-dense log
# notes demote answers pure semantic had ranked #1 (paraphrase recall@1
# 8% fused vs 50% semantic on the audit cases). Re-tuned per model on the
# measured sweep (w=3 for mxbai; w=5/10/20 each strictly better on bge-m3):
# at 20 the lexical arm is a tiebreak plus coverage for notes written since
# the last index build, and the default converges to pure-semantic quality.
_RRF_SEMANTIC_WEIGHT = float(os.environ.get("OBSIDIAN_RRF_SEMANTIC_WEIGHT") or "20.0")
# Lexical rank carries signal only near the top: on paraphrase queries the
# tail of the lexical ranking is term-frequency noise, and letting 25 noisy
# entries vote demoted semantic answers. Lexical votes are capped to its
# strongest few; semantic keeps the full fusion depth.
_FUSE_LEX_DEPTH = int(os.environ.get("OBSIDIAN_RRF_LEX_DEPTH") or "25")
# The semantic index is built on demand and never invalidates itself, so a note
# written after the last build is invisible to the semantic arm. On English
# queries the lexical arm covers for that; on a query in another language it
# contributes nothing (measured: on the RU/ES case set every hit came from the
# semantic arm, lexical rank was absent or in the hundreds), so an unindexed
# note is simply unfindable. Found at 29% uncovered on a real vault, silently.
# Warned, never auto-rebuilt: rebuilding mid-search would stall the query for
# minutes, and the user may not want an embedding pass running unprompted.
_INDEX_STALE_WARN_PCT = float(os.environ.get("OBSIDIAN_INDEX_STALE_WARN_PCT") or "5.0")
_STALE_WARNED_FOR: Optional[str] = None

# Bounds keep search fast and reads safe. The scan cap exists to stop a runaway
# walk on pathological trees, NOT to slice a real vault: 10k covers personal
# vaults several times over, it is env-tunable, notes iterate newest-first so a
# bite drops the oldest notes (never an arbitrary filesystem-order slice), and
# search warns when it truncates (stress-test fix 12/24 - the old silent 2000
# cap made ~342 of the maintainer's 2342 notes randomly unsearchable).
_MAX_FILES_SCANNED = int(os.environ.get("OBSIDIAN_SEARCH_MAX_FILES") or "10000")
_MAX_FILE_BYTES = 200_000
_SNIPPET_CHARS = 320
_READ_CAP = 20_000


# Documented config home (architecture.md, .env.example, CONTRIBUTING.md). The
# research toolkit loads it via python-dotenv, but this module is pure stdlib and
# the MCP server runs under `uv run --with mcp` (no python-dotenv installed), so
# we parse the one key we need by hand. Override the path in tests via
# OBSIDIAN_ENV_FILE. (Fixes #160 - same root cause as #124, different code path.)
_ENV_FILE = Path.home() / ".config" / "obsidian-second-brain" / ".env"


def _env_from_file(name: str) -> str:
    """Read a single `KEY=value` from the config .env. Environment always wins;
    this is only consulted as a fallback. A missing or malformed file yields ""."""
    path = Path(os.environ.get("OBSIDIAN_ENV_FILE") or _ENV_FILE).expanduser()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            if key.strip() == name:
                return val.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def resolve_vault() -> Path:
    """Return the configured vault dir, or raise with a clear message.

    Reads OBSIDIAN_VAULT_PATH from the environment first, then falls back to
    ~/.config/obsidian-second-brain/.env - the location architecture.md documents.
    Before #160 only the environment was checked, so plugin-marketplace installs
    that configured the vault in .env got a non-functional MCP server."""
    raw = os.environ.get(_VAULT_ENV, "").strip() or _env_from_file(_VAULT_ENV)
    if not raw:
        raise RuntimeError(
            f"{_VAULT_ENV} is not set (checked the environment and {_ENV_FILE})"
        )
    vault = Path(raw).expanduser().resolve()
    if not vault.is_dir():
        raise RuntimeError(f"vault path does not exist: {vault}")
    return vault


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    # strict=True: a and b are already verified equal-length above, so this
    # never raises. It documents that invariant instead of letting a future
    # edit that removes the length check silently reintroduce a truncated,
    # wrong-but-plausible-looking dot product (see #164).
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _unit(v: List[float]) -> Optional[List[float]]:
    """Return v scaled to length 1, or None when it has no length."""
    n = math.sqrt(sum(x * x for x in v))
    if not n:
        return None
    return [x / n for x in v]


def _dot(a: List[float], b: List[float]) -> float:
    """Cosine for two already-normalized vectors: just the dot product.

    _cosine recomputed BOTH norms on every call. Profiled on a ~2,900-note vault
    it was called 6,455 times for a single query and recomputed the query's own
    norm - invariant across the entire loop - every one of those times. Chunk
    norms were also recomputed per query although they only change when the
    index is rebuilt. Normalizing the query once and caching normalized chunk
    vectors alongside the loaded index removes both.
    """
    if len(a) != len(b):
        return 0.0
    # strict=True: see _cosine above - this is defence in depth, not a live
    # bug fix, since the length check just above already guarantees a and b
    # match. It's called in a tight loop over every chunk in the vault, so
    # keep it a documented invariant rather than a silent truncation risk.
    return sum(x * y for x, y in zip(a, b, strict=True))


def _embed_query(text: str, model: Optional[str] = None) -> Optional[List[float]]:
    """One fast embedding call for the query via the configured backend. Short
    timeout, no retries - search must stay snappy; on any failure the caller falls
    back to lexical. Supports Ollama (default) and OpenAI-compatible endpoints.
    model: pass the INDEX's model so query and note vectors share one space."""
    model = model or _EMBED_MODEL
    if _EMBED_BACKEND == "openai":
        headers = {"Content-Type": "application/json"}
        if _EMBED_KEY:
            headers["Authorization"] = f"Bearer {_EMBED_KEY}"
        body = json.dumps({"model": model, "input": text[:1200]}).encode()
        url = f"{_EMBED_URL}/v1/embeddings"
    else:
        body = json.dumps({"model": model, "prompt": text[:1200], "keep_alive": "15m"}).encode()
        url = f"{_EMBED_URL}/api/embeddings"
    req = urllib.request.Request(url, data=body, headers=headers if _EMBED_BACKEND == "openai"
                                else {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
    if data.get("embedding"):
        return data["embedding"]
    items = data.get("data")
    if items and isinstance(items, list) and items[0].get("embedding"):
        return items[0]["embedding"]
    return None


# The MCP server is long-running and the per-chunk index is tens of MB: parsing
# it on every search call would dominate latency. Cache by (path, mtime, size)
# so an index rebuild is picked up on the next call (stress-test fix 13/24).
_INDEX_CACHE: Dict[str, Any] = {}

# ── Lexical scan cache ──────────────────────────────────────────────────────
# Every search re-read, re-decoded and re-lowercased every note, then recomputed
# the per-note values that do not depend on the query at all: length norm, type
# weight, stale-status fade and age. Measured on a ~2,900-note vault, a lexical
# search is 0.62s of which roughly 0.2s is file I/O - so this is a useful win
# rather than a transformational one, and worth saying plainly. It matters most
# where searches run back to back: the eval harness does one per case, and
# /obsidian-find is interactive.
#
# Deliberately NOT an inverted term index. Scoring uses `low.count(term)`, which
# is substring matching - "run" matches "running" - so tokenizing would change
# results, and the retrieval numbers in scripts/eval/BASELINE.md are the contract.
# This caches the inputs to the existing scorer and changes no ranking.
#
# Keyed on (mtime_ns, size) so an edited note is re-read on the next search.
# Bounded by total cached characters, evicting oldest-first, so a very large
# vault degrades to the previous behaviour instead of growing without limit.
_SCAN_CACHE: "OrderedDict[str, Any]" = OrderedDict()
_SCAN_CACHE_MAX_CHARS = int(os.environ.get("OBSIDIAN_SCAN_CACHE_CHARS") or "40000000")
_scan_cache_chars = 0


def _scan_entry(md: Path, vault: Path):
    """Per-note scan inputs, cached until the file changes.

    Returns (lowercased_text, title_low, length_norm, static_weight) or None when
    the file is unreadable. `static_weight` folds together every query-independent
    multiplier: de-weight prefix, type weight and stale-status fade.
    """
    global _scan_cache_chars
    key = str(md)
    try:
        st = md.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        return None

    hit = _SCAN_CACHE.get(key)
    if hit is not None and hit[0] == stamp:
        _SCAN_CACHE.move_to_end(key)
        return hit[1]

    text = _read_safe(md, limit=_MAX_FILE_BYTES)
    if not text:
        return None
    low = text.lower()
    rel = md.relative_to(vault).as_posix()
    weight = 1.0
    if rel in _SEARCH_DEWEIGHT_FILES or rel.startswith(_SEARCH_DEWEIGHT_PREFIXES):
        weight *= _SEARCH_DEWEIGHT_FACTOR
    else:
        weight *= _type_weight(rel, text)
    sm = _STATUS_RE.search(text[:400])
    if sm and sm.group(1).lower() in _STALE_STATUSES:
        weight *= _STATUS_FADE
    entry = (low, md.stem.lower(), 1.0 + math.log1p(len(low) / 1000.0), weight,
             _note_age_days(text, md), text)

    if hit is not None:
        _scan_cache_chars -= len(hit[1][0])
    _SCAN_CACHE[key] = (stamp, entry)
    _SCAN_CACHE.move_to_end(key)
    _scan_cache_chars += len(low)
    while _scan_cache_chars > _SCAN_CACHE_MAX_CHARS and len(_SCAN_CACHE) > 1:
        _, old = _SCAN_CACHE.popitem(last=False)
        _scan_cache_chars -= len(old[1][0])
    return entry


def _load_index_cached(index_path: Path) -> dict:
    st = index_path.stat()
    key = (str(index_path), st.st_mtime_ns, st.st_size)
    if _INDEX_CACHE.get("key") != key:
        _INDEX_CACHE["key"] = key
        index = json.loads(index_path.read_text(encoding="utf-8"))
        # Pre-normalize every chunk vector once per index load instead of once
        # per query. Stored under a private key so a rebuilt index cannot serve
        # stale norms - the cache key already covers mtime and size.
        for n in (index.get("notes") or {}).values():
            vecs = n.get("vecs") or ([n["vec"]] if n.get("vec") else [])
            n["_unit"] = [u for u in (_unit(v) for v in vecs) if u]
        _INDEX_CACHE["index"] = index
    return _INDEX_CACHE["index"]


def index_coverage(vault: Path) -> Dict[str, Any]:
    """How much of the vault the semantic index actually covers.

    Shared by search (which warns) and vault_health (which reports), so the two
    can never disagree about whether an index is current.
    """
    index_path = vault / _SEMANTIC_INDEX_FILE
    if not index_path.exists():
        return {"index": False, "scanned": 0, "indexed": 0, "missing": 0, "pct_missing": 0.0}
    try:
        notes = (_load_index_cached(index_path).get("notes") or {})
    except Exception:
        return {"index": False, "scanned": 0, "indexed": 0, "missing": 0, "pct_missing": 0.0}
    scanned = {md.relative_to(vault).as_posix() for md in _iter_notes(vault)}
    missing = len(scanned - set(notes))
    return {
        "index": True,
        "scanned": len(scanned),
        "indexed": len(notes),
        "missing": missing,
        "pct_missing": (100.0 * missing / len(scanned)) if scanned else 0.0,
    }


def _warn_if_index_stale(vault: Path, scanned: List[str], notes: Dict[str, Any]) -> None:
    """Warn once per index version, using the paths search already walked.

    Reuses the search loop's own scan rather than re-walking the vault, so the
    check costs a set difference and cannot slow a query down.
    """
    global _STALE_WARNED_FOR
    key = str(_INDEX_CACHE.get("key"))
    if _STALE_WARNED_FOR == key or not scanned:
        return
    _STALE_WARNED_FOR = key
    missing = len(set(scanned) - set(notes))
    pct = 100.0 * missing / len(scanned)
    if pct < _INDEX_STALE_WARN_PCT:
        return
    print(
        f"warning: the semantic index covers {len(notes)} of {len(scanned)} notes; "
        f"{missing} ({pct:.0f}%) are missing and will not be found by meaning, only "
        f"by literal word match. Rebuild: uv run python scripts/eval/semantic_search.py "
        f"--path \"<vault>\" --build (incremental - only new and changed notes re-embed).",
        file=sys.stderr,
    )


def _semantic_fuse(
    query: str, lexical: List[Dict[str, Any]], vault: Path, limit: int,
    enabled: Optional[bool] = None, scanned: Optional[List[str]] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Fuse lexical results with local semantic ranking via RRF. Returns None (so the
    caller uses pure lexical) whenever semantic is unavailable or anything fails.
    enabled overrides the env toggle for this call (None = follow the env)."""
    if not (_SEMANTIC_ENABLED if enabled is None else enabled):
        return None
    index_path = vault / _SEMANTIC_INDEX_FILE
    if not index_path.exists():
        return None
    try:
        index = _load_index_cached(index_path)
        notes = index.get("notes") or {}
        if not notes:
            return None
        _warn_if_index_stale(vault, scanned or [], notes)
        # The query MUST be embedded with the model the index was built with -
        # vectors from different models live in different spaces (fix 16/24).
        qvec = _embed_query(query, model=index.get("model") or _EMBED_MODEL)
        if not qvec:
            return None
        # Normalize the query ONCE. It is invariant across the whole scoring
        # loop, and recomputing its norm per comparison was a third of the work.
        qunit = _unit(qvec)
        if not qunit:
            return None
        # Best-chunk scoring (fix 13/24): a note is as relevant as its most
        # relevant section, not the average of everything it contains.
        def _note_score(rel, n):
            """A note is as relevant as its most relevant section. Pure max won
            the measured sweep (vs multiplicative type weights on cosine - which
            deleted log notes outright, recall halved - vs additive nudges, vs a
            70/30 max+mean blend): fix 13/24, all variants scored on both case
            sets before shipping."""
            units = n.get("_unit") or []
            return max((_dot(qunit, v) for v in units), default=0.0)

        sem = sorted(
            ({"path": rel, "title": n.get("title", rel), "score": _note_score(rel, n)}
             for rel, n in notes.items() if n.get("_unit")),
            key=lambda r: r["score"], reverse=True,
        )[:_FUSE_DEPTH]
        lex_rank = {r["path"]: i for i, r in enumerate(lexical[:min(_FUSE_DEPTH, _FUSE_LEX_DEPTH)])}
        sem_rank = {r["path"]: i for i, r in enumerate(sem)}
        snippet = {r["path"]: r.get("snippet", "") for r in lexical}
        title = {r["path"]: r["title"] for r in lexical}
        for r in sem:
            title.setdefault(r["path"], r["title"])
        fused = []
        for p in set(lex_rank) | set(sem_rank):
            s = (1.0 / (_RRF_K + lex_rank[p]) if p in lex_rank else 0.0) \
                + (_RRF_SEMANTIC_WEIGHT / (_RRF_K + sem_rank[p]) if p in sem_rank else 0.0)
            fused.append({"path": p, "title": title.get(p, p), "snippet": snippet.get(p, ""), "score": s})
        fused.sort(key=lambda r: r["score"], reverse=True)
        out = fused[:limit]
        for r in out:
            r.pop("score", None)
        return out
    except Exception:
        return None  # any failure -> pure lexical, never break search


def search(query: str, *, limit: int = 6, semantic: Optional[bool] = None) -> List[Dict[str, Any]]:
    """Bounded keyword search over vault markdown, fused with local semantic search
    when an embedding index + Ollama are available (else pure lexical).

    semantic: force fusion on/off for this call. None (the default, what the MCP
    serves) follows OBSIDIAN_SEARCH_SEMANTIC. The eval harness passes False to get
    a genuinely pure lexical ranking - before this switch existed, "--mode lexical"
    silently measured the fused blend under a false label (stress-test fix 10/24)."""
    vault = resolve_vault()
    terms = _query_terms(query)
    if not terms:
        # Query was all stopwords/short tokens - fall back to the raw terms so a
        # search like "the who" still returns something rather than nothing. (CJK
        # is already fully captured above, so this only relaxes the English side.)
        terms = _query_terms(query, drop_stopwords=False)
    if not terms:
        return []
    current_intent = bool(_CURRENT_INTENT & {t.lower() for t in re.split(r"\W+", query)})
    # Query-aware dispatch (fix 11/24): a single exact token ("OKF", "docker") is
    # a lookup, not a question - bare tokens embed near-meaninglessly, and fusing
    # semantic noise into an exact hit demoted it (OKF: lexical rank 2 -> fused
    # rank 5 in the audit). Multi-word queries keep the semantic-weighted fusion.
    if semantic is None and len(terms) == 1:
        semantic = False
    limit = max(1, min(int(limit), 20))
    scored: List[Dict[str, Any]] = []
    # Every note the scan reached, scoring or not. The staleness check diffs
    # this against the index for free rather than walking the vault a second time.
    seen: List[str] = []
    truncated = False
    for i, md in enumerate(_iter_notes(vault)):
        if i >= _MAX_FILES_SCANNED:
            truncated = True
            break
        seen.append(md.relative_to(vault).as_posix())
        entry = _scan_entry(md, vault)
        if entry is None:
            continue
        low, title_low, length_norm, static_weight, age_days, text = entry
        # Sublinear term frequency + length normalization (BM25-style): a note that
        # repeats a term 50 times in passing should not outrank a short note that has
        # the term in its title. log1p saturates repeated mentions; dividing the body
        # contribution by a length factor stops long notes winning on sheer volume.
        # Title matches stay a strong, length-independent signal.
        title_score = 0.0
        body_score = 0.0
        for t in terms:
            tc = title_low.count(t)
            if tc:
                title_score += 5.0 * (1.0 + math.log1p(tc))
            bc = low.count(t)
            if bc:
                body_score += 1.0 + math.log1p(bc)
        score = title_score + (body_score / length_norm) if _SEARCH_LENGTH_NORM else float(
            sum(low.count(t) + 5 * title_low.count(t) for t in terms)
        )
        if score:
            rel = md.relative_to(vault).as_posix()
            # static_weight folds the de-weight prefix, type weight and stale
            # status; all three are query-independent and cached with the note.
            score *= static_weight
            score *= _freshness_weight(age_days, current_intent)
            scored.append(
                {
                    "path": rel,
                    "title": md.stem,
                    "score": score,
                    "snippet": _snippet(text, terms),
                }
            )
    if truncated:
        print(
            f"warning: search scanned only the newest {_MAX_FILES_SCANNED} notes; "
            f"raise OBSIDIAN_SEARCH_MAX_FILES to cover the whole vault",
            file=sys.stderr,
        )
    scored.sort(key=lambda r: r["score"], reverse=True)
    fused = _semantic_fuse(query, scored, vault, limit, enabled=semantic, scanned=seen)
    if fused is not None:
        return _freshness_rerank(fused, vault, current_intent)
    for r in scored:
        r.pop("score", None)
    # The pure-lexical fallback gets the same freshness/supersession rerank -
    # it used to skip it entirely, so keyless installs never got the status
    # fade the comment above promises for the lexical arm.
    return _freshness_rerank(scored[:limit], vault, current_intent)


def read_note(rel: str) -> Dict[str, Any]:
    """Read a note by vault-relative path. Guards against escaping the vault."""
    vault = resolve_vault()
    rel = (rel or "").strip()
    if not rel:
        return {"error": "path is required"}
    target = _resolve_in_vault(vault, rel)
    if target is None:
        return {"error": "path is outside the vault"}
    text = _read_safe(target)
    if text is None:
        return {"error": f"not found: {rel}"}
    return {"path": rel, "content": text[:_READ_CAP]}


def save_note(
    title: str,
    content: str,
    *,
    note_type: str = "note",
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Write an AI-first note to the vault's Inbox folder."""
    vault = resolve_vault()
    title = (title or "").strip()
    content = (content or "").strip()
    if not title or not content:
        return {"error": "title and content are required"}
    note_type = (note_type or "note").strip() or "note"
    tags = [str(t) for t in (tags or [note_type])]

    inbox = vault / _NOTES_DIR
    inbox.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    path = inbox / f"{date} - {_slug(title)}.md"
    tag_block = "\n".join(f"  - {t}" for t in tags)
    preamble = content.split("\n", 1)[0][:280]
    body = (
        f"---\n"
        f"type: {note_type}\n"
        f"date: {date}\n"
        f"tags:\n{tag_block}\n"
        f"ai-first: true\n"
        f"source: mcp\n"
        f"---\n\n"
        f"## For future Claude\n"
        f"{preamble}\n\n"
        f"{content}\n"
    )
    # B7: the filename is date + slug, so a second save with the same title on
    # the same day used to overwrite the first with no error and no backup.
    # Refuse and point at the tool that can actually edit an existing note.
    if path.exists():
        return {
            "error": (
                f"a note already exists at {path.relative_to(vault).as_posix()}; "
                "use obsidian_update_note to append to it, or save under a different title"
            )
        }
    _write_atomic(path, body)
    return {"saved": path.relative_to(vault).as_posix()}


def capture_idea(text: str, *, tags: Optional[List[str]] = None) -> Dict[str, Any]:
    """Quick idea capture: a lightweight idea note (type: idea) to the Inbox."""
    text = (text or "").strip()
    if not text:
        return {"error": "text is required"}
    title = text.split("\n", 1)[0][:60]
    return save_note(title, text, note_type="idea", tags=tags or ["idea", "capture"])


def update_note(
    rel: str,
    *,
    append: Optional[str] = None,
    heading: Optional[str] = None,
    set_fields: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Guarded edit of an EXISTING vault note.

    Deliberately conservative: it appends a section and/or merges scalar
    frontmatter fields, preserving the rest of the note verbatim. It never
    creates a note (use save_note), never rewrites the body, never touches list
    frontmatter (e.g. `tags:` blocks), and refuses paths outside the vault or in
    protected dirs. Every update stamps `updated: <today>` for provenance.
    """
    vault = resolve_vault()
    rel = (rel or "").strip()
    if not rel:
        return {"error": "path is required"}
    target = _resolve_in_vault(vault, rel)
    if target is None:
        return {"error": "path is outside the vault"}
    if {p.lower() for p in target.relative_to(vault).parts} & _PROTECTED_WRITE_DIRS:
        return {"error": "path is in a protected directory"}
    text = _read_safe(target)
    if text is None:
        return {"error": f"not found: {rel} (update_note only edits existing notes)"}
    if not append and not set_fields:
        return {"error": "nothing to update: provide append and/or set_fields"}

    fm_lines, body, _ = _split_frontmatter(text)
    fields = {str(k): str(v) for k, v in (set_fields or {}).items()}
    fields.setdefault("updated", datetime.now().strftime("%Y-%m-%d"))
    fm_lines = _apply_fields(fm_lines, fields)

    new_body = body
    if append:
        section = append.strip()
        if heading:
            new_body = new_body.rstrip() + f"\n\n## {heading.strip()}\n\n{section}\n"
        else:
            new_body = new_body.rstrip() + f"\n\n{section}\n"

    out = "---\n" + "\n".join(fm_lines).strip("\n") + "\n---\n\n" + new_body.lstrip("\n")
    _write_atomic(target, out)
    out: Dict[str, Any] = {"updated": rel, "set": sorted(fields.keys()), "appended": bool(append)}
    # Surface a retrieval-affecting change instead of making it silent: a status
    # in _STALE_STATUSES multiplies this note's score in every future search.
    new_status = str(fields.get("status", "")).strip().lower()
    if new_status in _STALE_STATUSES:
        out["faded"] = (
            f"status '{new_status}' de-ranks this note in all future vault search "
            f"(score x{_STATUS_FADE}). Set it only if the note no longer holds."
        )
    return out


def validate_note(rel: str) -> Dict[str, Any]:
    """Check a note against the AI-first rule and for unresolved wikilinks.

    Returns {path, ok, issues}. Issues cover missing frontmatter, missing
    required keys (type/date/tags/ai-first), a missing `## For future Claude`
    preamble, and `[[wikilinks]]` whose target note does not exist in the vault.
    """
    vault = resolve_vault()
    rel = (rel or "").strip()
    if not rel:
        return {"error": "path is required"}
    target = _resolve_in_vault(vault, rel)
    if target is None:
        return {"error": "path is outside the vault"}
    text = _read_safe(target)
    if text is None:
        return {"error": f"not found: {rel}"}

    issues: List[str] = []
    fm_lines, _, had_fm = _split_frontmatter(text)
    fmtext = "\n".join(fm_lines)
    if not had_fm:
        issues.append("missing frontmatter block")
    for key in ("type", "date", "tags", "ai-first"):
        if not re.search(rf"(?mi)^{key}:", fmtext):
            issues.append(f"missing frontmatter key: {key}")
    if "## For future Claude" not in text:
        issues.append("missing '## For future Claude' preamble")
    index = _stem_index(vault)
    seen = set()
    for link in _wikilinks(text):
        norm = _norm_link(link)
        if norm and norm not in index and norm not in seen:
            seen.add(norm)
            issues.append(f"unresolved wikilink: [[{link}]]")
    return {"path": rel, "ok": not issues, "issues": issues}


def backlinks(target: str) -> Dict[str, Any]:
    """Find every note that links to `target` via [[wikilink]].

    `target` may be a note title/stem or a vault-relative path; both resolve to
    the note's stem for matching (aliases `[[Note|alias]]` and folder-qualified
    links `[[folder/Note]]` are handled).
    """
    vault = resolve_vault()
    key = (target or "").strip()
    if not key:
        return {"error": "target is required"}
    stem = _norm_link(Path(key).name if "/" in key or key.endswith(".md") else key)
    refs: List[str] = []
    for i, md in enumerate(_iter_notes(vault)):
        if i >= _MAX_FILES_SCANNED:
            break
        text = _read_safe(md, limit=_MAX_FILE_BYTES) or ""
        if any(_norm_link(link) == stem for link in _wikilinks(text)):
            rel = str(md.relative_to(vault))
            if md.stem.lower() != stem:  # don't list the note itself
                refs.append(rel)
    return {"target": stem, "count": len(refs), "backlinks": sorted(refs)}


def vault_health() -> Dict[str, Any]:
    """Bounded structural health summary of the vault.

    Reports counts plus capped samples of orphan notes (no inbound or outbound
    links), wanted notes (a link exists but the target note does not - a
    wishlist, not an error), and notes with no frontmatter. Bounded by the same
    file cap as search so it stays fast.
    """
    vault = resolve_vault()
    index = _stem_index(vault)
    note_paths: Dict[str, str] = {}
    missing_fm: List[str] = []
    wanted: List[Dict[str, str]] = []
    linked_to: set = set()
    has_outbound: set = set()
    count = 0
    for i, md in enumerate(_iter_notes(vault)):
        if i >= _MAX_FILES_SCANNED:
            break
        count += 1
        rel = str(md.relative_to(vault))
        note_paths[md.stem.lower()] = rel
        text = _read_safe(md, limit=_MAX_FILE_BYTES) or ""
        if not text.lstrip().startswith("---"):
            if len(missing_fm) < 10:
                missing_fm.append(rel)
        links = _wikilinks(text)
        if links:
            has_outbound.add(md.stem.lower())
        for link in links:
            norm = _norm_link(link)
            linked_to.add(norm)
            if norm and norm not in index and len(wanted) < 10:
                wanted.append({"in": rel, "link": link})
    orphans = [p for s, p in note_paths.items() if s not in linked_to and s not in has_outbound]
    return {
        "notes_scanned": count,
        "capped": count >= _MAX_FILES_SCANNED,
        "orphans": {"count": len(orphans), "sample": sorted(orphans)[:10]},
        "wanted_notes": {"count": len(wanted), "sample": wanted},
        "missing_frontmatter": {"count": len(missing_fm), "sample": missing_fm},
    }


# Commands not worth exposing over MCP: meta/setup, Claude-only Google Calendar
# connector commands, and the niche ones flagged on Issue #60 (challenge, health).
_EXCLUDED_SKILLS = {
    "create-command",
    "obsidian-init",
    "obsidian-export",
    "obsidian-visualize",
    "obsidian-challenge",
    "obsidian-health",
    "obsidian-calendar",
    "obsidian-agenda",
    "obsidian-meeting",
    "obsidian-schedule",
}


def list_skills() -> List[Dict[str, Any]]:
    """List the obsidian-second-brain commands exposable as skills (name + description)."""
    cmds = _commands_dir()
    if cmds is None or not cmds.is_dir():
        return []
    out: List[Dict[str, Any]] = []
    for md in sorted(cmds.glob("*.md")):
        name = md.stem
        if name in _EXCLUDED_SKILLS:
            continue
        meta, _ = _parse_command(md)
        out.append(
            {
                "name": name,
                "description": meta.get("description", ""),
                "category": meta.get("category", ""),
            }
        )
    return out


def get_skill(name: str) -> Dict[str, Any]:
    """Return a command's playbook (instructions) so the agent can run the skill."""
    name = (name or "").strip().lstrip("/")
    if not name:
        return {"error": "name is required"}
    # Path-traversal guard: skill names are flat slugs (alphanumerics, '-' and '_').
    # Rejecting separators and dots stops a crafted name like "../../etc/passwd" from
    # escaping the commands/ dir, since lstrip("/") alone does not remove ".." segments.
    if not all(c.isalnum() or c in "-_" for c in name):
        return {"error": f"unknown skill: {name}"}
    if name in _EXCLUDED_SKILLS:
        return {"error": f"skill '{name}' is not exposed over MCP"}
    cmds = _commands_dir()
    md = (cmds / f"{name}.md") if cmds else None
    if md is None or not md.is_file():
        return {"error": f"unknown skill: {name}"}
    meta, body = _parse_command(md)
    note = (
        "Run this skill using the MCP tools on this server for vault I/O: "
        "obsidian_search (find/recall), obsidian_read_note (read), "
        "obsidian_backlinks (graph), "
        "obsidian_update_note (append to, or set frontmatter on, an EXISTING note - "
        "use this whenever a step says update, rewrite, or integrate), "
        "obsidian_save_note / obsidian_capture (create a NEW note), "
        "obsidian_validate_note (check a note before or after a write). "
        "A step calling for a full rewrite of an existing note cannot be done with "
        "these tools: report that to the user rather than approximating it with a "
        "new note, which produces exactly the duplicates these playbooks forbid. "
        "Follow the steps below."
    )
    return {
        "name": name,
        "description": meta.get("description", ""),
        "instructions": f"{note}\n\n{body.strip()}",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iter_notes(vault: Path):
    """Yield vault notes newest-first (modified time). Deterministic on purpose:
    every consumer of this iterator caps its scan, and a cap that bites must
    drop the oldest notes, never a random filesystem-order slice."""
    found = []
    for md in vault.rglob("*.md"):
        parts = md.relative_to(vault).parts
        if any(p.lower() in _SKIP_DIRS or p.lower().endswith("templates") for p in parts):
            continue
        # Drawings are JSON blobs in .md clothing; the semantic index skips them,
        # so the lexical scan does too - one universe for every mode.
        if md.name.endswith(".excalidraw.md"):
            continue
        try:
            found.append((md.stat().st_mtime, md))
        except OSError:
            continue  # dangling symlink or race: a ghost must not kill the scan
    found.sort(key=lambda t: t[0], reverse=True)
    for _, md in found:
        yield md


def _commands_dir() -> Optional[Path]:
    """Locate the skill's commands/ dir: env override, else repo root relative to this file."""
    env = os.environ.get("OBSIDIAN_COMMANDS_DIR", "").strip()
    if env:
        p = Path(env).expanduser()
        return p if p.is_dir() else None
    # this file: <repo>/integrations/obsidian-mcp-server/vault_ops.py
    candidate = Path(__file__).resolve().parents[2] / "commands"
    return candidate if candidate.is_dir() else None


def _parse_command(md: Path):
    """Split a command file into (frontmatter dict, body). Minimal YAML, no deps."""
    text = _read_safe(md) or ""
    meta: Dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end]
            body = text[end + 4 :]
            for line in fm.splitlines():
                if ":" in line and not line.lstrip().startswith(("-", "#", "[")):
                    key, _, val = line.partition(":")
                    meta[key.strip()] = val.strip().strip('"').strip("'")
    return meta, body


def _snippet(text: str, terms: List[str]) -> str:
    low = text.lower()
    pos = min((low.find(t) for t in terms if low.find(t) >= 0), default=-1)
    if pos < 0:
        return text.strip()[:_SNIPPET_CHARS]
    start = max(0, pos - _SNIPPET_CHARS // 2)
    return text[start : start + _SNIPPET_CHARS].replace("\n", " ").strip()


def _write_atomic(path: Path, text: str) -> None:
    """Write via temp file + os.replace, preserving the target's mode.

    Both write paths here run over a live MCP connection, so a client timeout or
    a crash mid-write would otherwise leave a half-written note with no backup.
    Mirrors scripts/note_io.write_exact, which the vault scripts already use.
    """
    import os as _os
    import tempfile
    keep_mode = None
    try:
        keep_mode = path.stat().st_mode
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".{}.".format(path.name), suffix=".tmp")
    try:
        with _os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        if keep_mode is not None:
            _os.chmod(tmp, keep_mode)
        _os.replace(tmp, path)
    except BaseException:
        try:
            _os.unlink(tmp)
        except OSError:
            pass
        raise


def _resolve_in_vault(vault: Path, rel: str) -> Optional[Path]:
    """Resolve a vault-relative path, refusing anything that escapes the vault.

    A security boundary, so it lives in exactly one place. It was previously
    inlined identically in read_note, update_note, and validate_note; the next
    tool to forget a line would have reintroduced traversal silently.
    """
    target = (vault / rel).resolve()
    if vault != target and vault not in target.parents:
        return None
    return target


def _read_safe(path: Path, *, limit: int = 4_000_000) -> Optional[str]:
    # utf-8-sig, matching every sibling reader (vault_health, vault_stats,
    # link_graph, export_okf). Plain utf-8 leaves a BOM glued to the first line,
    # which breaks frontmatter detection and shows up in every snippet this
    # server surfaces. Windows editors and several sync tools emit BOMs.
    try:
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8-sig", errors="replace")[:limit]
    except OSError:
        return None


def _slug(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:80] or "untitled"


_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


def _wikilinks(text: str) -> List[str]:
    """Return the raw target of each [[wikilink]] (before any | alias or # anchor)."""
    return [m.group(1).strip() for m in _WIKILINK_RE.finditer(text)]


def _nfc(s: str) -> str:
    """Canonical Unicode form, matching vault_health._nfc.

    macOS stores filenames decomposed (NFD) while a typed wikilink is usually
    composed (NFC), so an accented title compares unequal without this and the
    note is reported as a false orphan. Fixed in vault_health and link_graph by
    PR #161; this server had the same gap.
    """
    return unicodedata.normalize("NFC", s)


def _norm_link(link: str) -> str:
    """Normalize a wikilink target to a comparable note stem (basename, lowercased)."""
    return _nfc(link.split("/")[-1].strip()).lower()


def _stem_index(vault: Path) -> Dict[str, str]:
    """Map every note's lowercased stem to its vault-relative path (bounded)."""
    idx: Dict[str, str] = {}
    for i, md in enumerate(_iter_notes(vault)):
        if i >= _MAX_FILES_SCANNED:
            break
        idx[_nfc(md.stem).lower()] = str(md.relative_to(vault))
    return idx


def _split_frontmatter(text: str):
    """Split into (frontmatter_lines, body, had_frontmatter).

    frontmatter_lines excludes the --- fences; body is everything after them.
    Preserves raw lines so unknown/list keys survive a round-trip untouched.
    """
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end].strip("\n")
            body = text[end + 4 :]
            return fm.splitlines(), body, True
    return [], text, False


def _apply_fields(fm_lines: List[str], fields: Dict[str, str]) -> List[str]:
    """Set/replace scalar frontmatter keys, preserving every other line as-is."""
    lines = list(fm_lines)
    remaining = dict(fields)
    for i, line in enumerate(lines):
        m = re.match(r"^([A-Za-z0-9_-]+):", line)
        if m and m.group(1) in remaining:
            key = m.group(1)
            lines[i] = f"{key}: {remaining.pop(key)}"
    for k, v in remaining.items():
        lines.append(f"{k}: {v}")
    return lines
