"""Vault operations for the Obsidian Second Brain MCP server.

Pure stdlib, no MCP dependency, so the logic is unit-testable on its own. The
MCP wiring in `server.py` is a thin layer over these functions.

Every write follows the AI-first rule (references/ai-first-rules.md): frontmatter
with type/date/tags/ai-first, a `## For future Claude` preamble, and a
`source: mcp` marker so notes added through the connector are distinguishable.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
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
_SKIP_DIRS = {".obsidian", ".git", ".trash", "_trash", ".claude", "_export",
              "templates", "node_modules"}

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
# Freshness (stress-test fix 15/24): "who is my CURRENT employer" ranked a
# declined offer above the real employer. Two levers, lexical arm only (the
# semantic arm rejected additive nudges by measurement in fix 13):
# - a recency band: old notes lose near-ties, gently always, strongly when the
#   query itself asks about the present (current/now/still/today/latest)
# - a status fade: notes whose OWN metadata says they no longer hold
#   (superseded/declined/archived/parked/on-hold...) step back
_STALE_STATUSES = {"superseded", "declined", "rejected", "archived", "obsolete",
                   "cancelled", "closed", "parked", "inactive", "done"}
_STATUS_RE = re.compile(r"(?m)^status:\s*['\"]?([A-Za-z0-9_-]+)")
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
    so fusion happily served a declined April offer above the real employer for
    "who is my CURRENT employer". Reads only the top results' frontmatter heads
    (cheap): stale-status notes step back always (their own metadata says they
    no longer hold); recency reorders only when the query asks about the
    present. Rank-derived base scores keep this a reorder, never a rewrite."""
    rescored = []
    for i, r in enumerate(results):
        weight = 1.0
        try:
            head = (vault / r["path"]).read_text(encoding="utf-8-sig", errors="ignore")[:400]
            sm = _STATUS_RE.search(head)
            if sm and sm.group(1).lower() in _STALE_STATUSES:
                weight *= _STATUS_FADE
            if current_intent:
                weight *= _freshness_weight(_note_age_days(head, vault / r["path"]), True)
        except OSError:
            pass
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
_EMBED_MODEL = os.environ.get("OBSIDIAN_EMBED_MODEL", "mxbai-embed-large")
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
# 8% fused vs 50% semantic on the audit cases). w=3.0 won the measured
# sweep: best average MRR across paraphrase + keyword case sets.
_RRF_SEMANTIC_WEIGHT = float(os.environ.get("OBSIDIAN_RRF_SEMANTIC_WEIGHT") or "3.0")
# Lexical rank carries signal only near the top: on paraphrase queries the
# tail of the lexical ranking is term-frequency noise, and letting 25 noisy
# entries vote demoted semantic answers. Lexical votes are capped to its
# strongest few; semantic keeps the full fusion depth.
_FUSE_LEX_DEPTH = int(os.environ.get("OBSIDIAN_RRF_LEX_DEPTH") or "25")

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


def resolve_vault() -> Path:
    """Return the configured vault dir, or raise with a clear message."""
    raw = os.environ.get(_VAULT_ENV, "").strip()
    if not raw:
        raise RuntimeError(f"{_VAULT_ENV} is not set")
    vault = Path(raw).expanduser().resolve()
    if not vault.is_dir():
        raise RuntimeError(f"vault path does not exist: {vault}")
    return vault


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _embed_query(text: str) -> Optional[List[float]]:
    """One fast embedding call for the query via the configured backend. Short
    timeout, no retries - search must stay snappy; on any failure the caller falls
    back to lexical. Supports Ollama (default) and OpenAI-compatible endpoints."""
    if _EMBED_BACKEND == "openai":
        headers = {"Content-Type": "application/json"}
        if _EMBED_KEY:
            headers["Authorization"] = f"Bearer {_EMBED_KEY}"
        body = json.dumps({"model": _EMBED_MODEL, "input": text[:1200]}).encode()
        url = f"{_EMBED_URL}/v1/embeddings"
    else:
        body = json.dumps({"model": _EMBED_MODEL, "prompt": text[:1200], "keep_alive": "15m"}).encode()
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


def _load_index_cached(index_path: Path) -> dict:
    st = index_path.stat()
    key = (str(index_path), st.st_mtime_ns, st.st_size)
    if _INDEX_CACHE.get("key") != key:
        _INDEX_CACHE["key"] = key
        _INDEX_CACHE["index"] = json.loads(index_path.read_text(encoding="utf-8"))
    return _INDEX_CACHE["index"]


def _semantic_fuse(
    query: str, lexical: List[Dict[str, Any]], vault: Path, limit: int,
    enabled: Optional[bool] = None,
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
        qvec = _embed_query(query)
        if not qvec:
            return None
        # Best-chunk scoring (fix 13/24): a note is as relevant as its most
        # relevant section, not the average of everything it contains.
        def _note_score(rel, n):
            """A note is as relevant as its most relevant section. Pure max won
            the measured sweep (vs multiplicative type weights on cosine - which
            deleted log notes outright, recall halved - vs additive nudges, vs a
            70/30 max+mean blend): fix 13/24, all variants scored on both case
            sets before shipping."""
            vecs = n.get("vecs") or ([n["vec"]] if n.get("vec") else [])
            return max((_cosine(qvec, v) for v in vecs), default=0.0)

        sem = sorted(
            ({"path": rel, "title": n.get("title", rel), "score": _note_score(rel, n)}
             for rel, n in notes.items() if n.get("vecs") or n.get("vec")),
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
    terms = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2 and t not in _STOPWORDS]
    if not terms:
        # Query was all stopwords/short tokens - fall back to the raw terms so a
        # search like "the who" still returns something rather than nothing.
        terms = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]
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
    truncated = False
    for i, md in enumerate(_iter_notes(vault)):
        if i >= _MAX_FILES_SCANNED:
            truncated = True
            break
        text = _read_safe(md, limit=_MAX_FILE_BYTES)
        if not text:
            continue
        low = text.lower()
        title_low = md.stem.lower()
        # Sublinear term frequency + length normalization (BM25-style): a note that
        # repeats a term 50 times in passing should not outrank a short note that has
        # the term in its title. log1p saturates repeated mentions; dividing the body
        # contribution by a length factor stops long notes winning on sheer volume.
        # Title matches stay a strong, length-independent signal.
        length_norm = 1.0 + math.log1p(len(low) / 1000.0)
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
            if rel in _SEARCH_DEWEIGHT_FILES or rel.startswith(_SEARCH_DEWEIGHT_PREFIXES):
                score *= _SEARCH_DEWEIGHT_FACTOR
            else:
                score *= _type_weight(rel, text)
            sm = _STATUS_RE.search(text[:400])
            if sm and sm.group(1).lower() in _STALE_STATUSES:
                score *= _STATUS_FADE
            score *= _freshness_weight(_note_age_days(text, md), current_intent)
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
    fused = _semantic_fuse(query, scored, vault, limit, enabled=semantic)
    if fused is not None:
        return _freshness_rerank(fused, vault, current_intent)
    for r in scored:
        r.pop("score", None)
    return scored[:limit]


def read_note(rel: str) -> Dict[str, Any]:
    """Read a note by vault-relative path. Guards against escaping the vault."""
    vault = resolve_vault()
    rel = (rel or "").strip()
    if not rel:
        return {"error": "path is required"}
    target = (vault / rel).resolve()
    if vault != target and vault not in target.parents:
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
    path.write_text(body, encoding="utf-8")
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
    target = (vault / rel).resolve()
    if vault != target and vault not in target.parents:
        return {"error": "path is outside the vault"}
    if set(target.relative_to(vault).parts) & _SKIP_DIRS:
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
    target.write_text(out, encoding="utf-8")
    return {"updated": rel, "set": sorted(fields.keys()), "appended": bool(append)}


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
    target = (vault / rel).resolve()
    if vault != target and vault not in target.parents:
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
        "obsidian_save_note / obsidian_capture (write). Follow the steps below."
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


def _read_safe(path: Path, *, limit: int = 4_000_000) -> Optional[str]:
    try:
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
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


def _norm_link(link: str) -> str:
    """Normalize a wikilink target to a comparable note stem (basename, lowercased)."""
    return link.split("/")[-1].strip().lower()


def _stem_index(vault: Path) -> Dict[str, str]:
    """Map every note's lowercased stem to its vault-relative path (bounded)."""
    idx: Dict[str, str] = {}
    for i, md in enumerate(_iter_notes(vault)):
        if i >= _MAX_FILES_SCANNED:
            break
        idx[md.stem.lower()] = str(md.relative_to(vault))
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
