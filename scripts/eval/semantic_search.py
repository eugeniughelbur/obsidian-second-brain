"""Local semantic search for the vault - meaning-based retrieval, nothing leaves the machine.

This is the "map of meaning" layer: it asks a LOCAL embedding model (via Ollama,
running on your own computer) for each note's coordinates, caches them, and finds
the notes whose meaning is nearest a query - even when they share no words with it.
It is the answer to the ~17% ceiling the lexical eval exposed on paraphrased queries.

Design choices that matter:
- **Local only.** Embeddings come from Ollama on localhost. Note text never leaves
  the machine, so it is safe for private notes (the firewall in _CLAUDE.md).
- **Privacy carve-out.** Folders listed in OBSIDIAN_EMBED_EXCLUDE (comma-separated
  path prefixes) are never embedded at all - belt and braces even though it is local.
- **Pure stdlib.** Cosine similarity is hand-rolled; no numpy/torch dependency in the
  repo. The model lives in Ollama, not in Python.
- **Cached.** The index is a JSON file keyed by note path + content hash, so only
  changed notes are re-embedded on the next run.
- **Default off.** Nothing calls this unless explicitly run; vault_ops.search stays
  the shipped default until the eval proves hybrid beats lexical.

Requires Ollama (https://ollama.com) with an embedding model pulled:
    ollama pull bge-m3
Configure via env: OLLAMA_URL (default http://localhost:11434),
OBSIDIAN_EMBED_MODEL (default bge-m3, multilingual),
OBSIDIAN_EMBED_EXCLUDE (default empty; e.g. "wiki/private/,Journal,Private").
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
EMBED_MODEL = os.environ.get("OBSIDIAN_EMBED_MODEL", "bge-m3")
# Backend selects how embeddings are produced:
#   "ollama" (default) - local Ollama at OLLAMA_URL, fully private/offline.
#   "openai" - ANY OpenAI-compatible /v1/embeddings endpoint, so users without
#              Ollama can point at another local runtime (LM Studio, llama.cpp)
#              or a cloud API (OpenAI, a gateway). Set OBSIDIAN_EMBED_URL (base) and
#              OBSIDIAN_EMBED_KEY (if the endpoint needs auth). Cloud = text leaves
#              the machine, so keep the OBSIDIAN_EMBED_EXCLUDE carve-out in mind.
EMBED_BACKEND = os.environ.get("OBSIDIAN_EMBED_BACKEND", "ollama").lower()
EMBED_URL = os.environ.get("OBSIDIAN_EMBED_URL", OLLAMA_URL).rstrip("/")
EMBED_KEY = os.environ.get("OBSIDIAN_EMBED_KEY", "")
EXCLUDE_PREFIXES = tuple(
    p.strip() for p in os.environ.get("OBSIDIAN_EMBED_EXCLUDE", "").split(",") if p.strip()
)
# Single source of truth: the MCP server owns the skip set, so the semantic
# index and the lexical scan can never drift into different universes
# (stress-test fix 10/24).
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "integrations" / "obsidian-mcp-server"))
from vault_ops import _SKIP_DIRS as SKIP_DIRS  # noqa: E402
INDEX_FILE = ".obsidian-semantic-index.json"  # written at vault root
# Embedding models have a token limit (typically ~512 tokens). Long notes
# must be split into safe chunks and averaged, or the model 500s. ~1200 chars sits
# well under the limit; capping the chunk count bounds time on huge notes.
_CHUNK_CHARS = 1200
_MAX_CHUNKS = 8


# --------------------------------------------------------------------------- #
# Ollama (local) embedding calls
# --------------------------------------------------------------------------- #
def ollama_available() -> bool:
    """Is the embedding backend reachable? (Name kept for callers.)"""
    if EMBED_BACKEND == "openai":
        return bool(EMBED_URL)  # assume configured endpoint is up; embed() falls back on error
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


_RETRY_WAITS = (1, 3, 8, 15)  # a local model on a laptop can briefly 500 under rapid load


def _embed_request(text: str, model: str | None = None) -> tuple[str, bytes, dict]:
    """Build the (url, body, headers) for the configured backend."""
    if EMBED_BACKEND == "openai":
        headers = {"Content-Type": "application/json"}
        if EMBED_KEY:
            headers["Authorization"] = f"Bearer {EMBED_KEY}"
        body = json.dumps({"model": (model or EMBED_MODEL), "input": text[:_CHUNK_CHARS]}).encode()
        return f"{EMBED_URL}/v1/embeddings", body, headers
    # ollama (default): keep_alive holds the model in memory between calls
    body = json.dumps({"model": (model or EMBED_MODEL), "prompt": text[:_CHUNK_CHARS], "keep_alive": "15m"}).encode()
    return f"{EMBED_URL}/api/embeddings", body, {"Content-Type": "application/json"}


def _parse_embedding(data: dict) -> list[float] | None:
    """Pull the vector out of either response shape."""
    if data.get("embedding"):                       # ollama
        return data["embedding"]
    items = data.get("data")                         # openai-compatible
    if items and isinstance(items, list) and items[0].get("embedding"):
        return items[0]["embedding"]
    return None


def embed(text: str, retries: int | None = None, model: str | None = None) -> list[float]:
    """Return the embedding vector for one text via the configured backend.

    Retries transient errors (HTTP 5xx, connection resets): a local model on a
    laptop can buckle under rapid sequential calls, then recover a second later.
    The last failure is raised so the caller can skip the note. retries caps the
    ladder: the adaptive splitter passes 1, because a deterministic too-many-
    tokens failure repays every retry with the same 500 and the full ladder at
    every split level turned an 11-note repair into a 10-minute stall.
    """
    url, body, headers = _embed_request(text, model)
    last_err: Exception | None = None
    waits = _RETRY_WAITS if retries is None else _RETRY_WAITS[:retries]
    for attempt in range(len(waits) + 1):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as r:
                vec = _parse_embedding(json.loads(r.read()))
            if vec:
                return vec
            last_err = RuntimeError(f"backend returned no embedding (model '{EMBED_MODEL}')")
        except (urllib.error.HTTPError, urllib.error.URLError, ConnectionError, TimeoutError) as e:
            last_err = e
        if attempt < len(waits):
            time.sleep(waits[attempt])
    raise RuntimeError(
        f"Embedding backend '{EMBED_BACKEND}' at {EMBED_URL} failed after retries ({last_err})."
    )


def _mean_pool(vectors: list[list[float]]) -> list[float]:
    """Average several chunk vectors into one note vector (component-wise)."""
    if not vectors:
        return []
    if len(vectors) == 1:
        return vectors[0]
    dim = len(vectors[0])
    n = len(vectors)
    return [sum(v[i] for v in vectors) / n for i in range(dim)]


_FM_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
_FM_LIST_RE = re.compile(r"^(aliases|related-people|related-projects|tags):\s*\[(.+?)\]\s*$", re.MULTILINE)
_FM_TYPE_RE = re.compile(r"^type:\s*[\"\']?([A-Za-z0-9_-]+)", re.MULTILINE)


def prepare_note_text(stem: str, text: str) -> tuple[str, str]:
    """Return (identity_header, cleaned_body) for embedding.

    The header names the note (title, type, aliases, related people/projects) so
    every chunk stays reachable by described role, not just by title words. The
    body drops frontmatter and empty template sections - a daily note that is
    mostly unfilled scaffolding must not have its one real paragraph diluted by
    boilerplate headings (stress-test fix 13/24)."""
    fm = ""
    m = _FM_RE.match(text)
    if m:
        fm = m.group(1)
        text = text[m.end():]
    bits = [stem]
    tm = _FM_TYPE_RE.search(fm)
    if tm:
        bits.append(tm.group(1))
    for _, items in _FM_LIST_RE.findall(fm):
        bits.extend(i.strip().strip("\"\'[]") for i in items.split(",") if i.strip())
    header = " | ".join(dict.fromkeys(b for b in bits if b)) + "\n"
    # Drop sections that contain no prose: a heading directly followed by another
    # heading (or EOF) is template scaffolding, not content.
    lines = text.splitlines()
    kept: list[str] = []
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            nxt = next((l for l in lines[i + 1:] if l.strip()), "")
            if not nxt or nxt.lstrip().startswith("#"):
                continue
        kept.append(line)
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return header, body


def embed_note(text: str) -> list[float]:
    """Embed a whole note into ONE mean-pooled vector (legacy shape; kept for
    compatibility - build_index stores per-chunk vectors via embed_note_chunks)."""
    vecs = embed_note_chunks(text)
    return _mean_pool(vecs) if vecs else []


def embed_note_chunks(text: str, header: str = "") -> list[list[float]]:
    """Embed a note as per-chunk vectors (stress-test fix 13/24).

    Mean-pooling a long note produced one averaged mumble: a 10-section dossier
    answering a query in section 7 has one strong vector and nine unrelated ones,
    and the average drowns the signal 9-to-1. Chunks are scored independently at
    query time (best chunk wins), so each chunk carries the note's identity
    header (title/type/aliases/related) - a mid-dossier section must still know
    who it is about."""
    text = text.strip()
    if not text:
        return []
    body_room = max(200, _CHUNK_CHARS - len(header))
    chunks = [text[i:i + body_room] for i in range(0, len(text), body_room)][:_MAX_CHUNKS]
    vecs: list[list[float]] = []
    for c in chunks:
        vecs.extend(_embed_adaptive(c, header))
    return vecs


def _embed_adaptive(text: str, header: str) -> list[list[float]]:
    """Embed one chunk, halving it on failure (stress-test fix 14/24).

    Retry cures transient failures; these were deterministic: token-dense
    content (a 1,066-char table of euro-rows) blows past the model's 512-token
    window at char counts where prose fits fine, and failed on every build.
    Char count is a bad proxy for tokens (even 'x'*1200 fails), so no fixed
    chunk size is safe - halve until it fits, floor at 300 chars. 6-decimal
    rounding is far beyond cosine's needs and halves the on-disk index."""
    try:
        return [[round(x, 6) for x in embed(header + text, retries=1)]]
    except Exception:
        if len(text) <= 300:
            raise
        mid = len(text) // 2
        return _embed_adaptive(text[:mid], header) + _embed_adaptive(text[mid:], header)


# --------------------------------------------------------------------------- #
# Pure-stdlib vector math
# --------------------------------------------------------------------------- #
def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [-1, 1]; how close two meaning-coordinates point."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _content_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:16]


def _excluded(rel: str) -> bool:
    return any(rel == p or rel.startswith(p) for p in EXCLUDE_PREFIXES)


# --------------------------------------------------------------------------- #
# Index build / load (cached, incremental)
# --------------------------------------------------------------------------- #
def _iter_notes(vault: Path):
    for md in sorted(vault.rglob("*.md")):
        parts = md.relative_to(vault).parts
        if any(pt.lower() in SKIP_DIRS or pt.lower().endswith("templates") for pt in parts):
            continue
        if md.name.endswith(".excalidraw.md"):
            continue  # drawings are raw JSON, not prose - they bloat and fail embedding
        yield md


def build_index(vault: Path, verbose: bool = True) -> dict:
    """Embed every (non-excluded) note, reusing cached vectors for unchanged notes."""
    index_path = vault / INDEX_FILE
    cache: dict = {}
    if index_path.exists():
        try:
            cache = json.loads(index_path.read_text())
        except Exception:
            cache = {}
    # Format 2 = per-chunk vectors with identity headers (fix 13/24). A cache in
    # the old shape must not be reused: the note text is unchanged but what we
    # embed for it is not. Same rule for a MODEL switch (fix 16/24): vectors
    # from different embedding models live in different spaces - mixing them
    # silently would make every similarity meaningless.
    cache_ok = cache.get("format") == 2 and cache.get("model") == EMBED_MODEL
    old = cache.get("notes", {}) if cache_ok else {}
    new: dict = {}
    embedded = reused = skipped = failed = degraded = 0
    degraded_paths: list[str] = []
    dropped_paths: list[str] = []

    for md in _iter_notes(vault):
        rel = md.relative_to(vault).as_posix()
        if _excluded(rel):
            skipped += 1
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        h = _content_hash(text)
        prev = old.get(rel)
        if prev and prev.get("hash") == h:
            new[rel] = prev
            reused += 1
            continue
        # An empty/whitespace-only note has no body to embed; fall back to its title
        # (which still carries meaning) so it stays findable. Skip only if even that is empty.
        header, body = prepare_note_text(md.stem, text)
        # A note that is all scaffolding still embeds its identity header, so it
        # stays findable by name/aliases. Skip only if even that is empty.
        embed_text = body if body else header.strip()
        if not embed_text.strip():
            continue
        degraded_note = False
        try:
            vecs = embed_note_chunks(embed_text, header=header)
        except Exception:
            # The body will not embed even split down - keep the note findable
            # by NAME at least: an identity-only vector beats silent absence.
            try:
                vecs = [[round(x, 6) for x in embed(header.strip() or md.stem)]]
                degraded_note = True
            except Exception as e:  # one bad note must not abort a 1000-note run
                failed += 1
                dropped_paths.append(rel)
                if verbose:
                    print(f"  [skip] {rel}: {e}", file=sys.stderr)
                continue
        tm = _FM_TYPE_RE.search(text[:400])
        entry = {"hash": h, "title": md.stem, "vecs": vecs}
        if tm:
            entry["type"] = tm.group(1).lower()
        if degraded_note:
            entry["degraded"] = True
            degraded += 1
            degraded_paths.append(rel)
        new[rel] = entry
        embedded += 1
        if verbose and embedded % 50 == 0:
            print(f"  embedded {embedded} notes...", file=sys.stderr)

    out = {"model": EMBED_MODEL, "format": 2, "notes": new}
    index_path.write_text(json.dumps(out), encoding="utf-8")
    if verbose:
        total_eligible = len(new) + failed
        pct = (100.0 * len(new) / total_eligible) if total_eligible else 100.0
        print(
            f"[semantic] indexed {len(new)} notes ({embedded} new, {reused} cached, "
            f"{skipped} excluded, {degraded} degraded, {failed} dropped) -> {index_path}",
            file=sys.stderr,
        )
        print(f"[semantic] coverage: {len(new)}/{total_eligible} ({pct:.1f}%)", file=sys.stderr)
        # Gaps must be a report, not a surprise: name every degraded/dropped note.
        for rel in degraded_paths:
            print(f"  [degraded to identity-only] {rel}", file=sys.stderr)
        for rel in dropped_paths:
            print(f"  [DROPPED - not findable semantically] {rel}", file=sys.stderr)
    return out


def load_index(vault: Path) -> dict:
    index_path = vault / INDEX_FILE
    if not index_path.exists():
        raise RuntimeError(f"No semantic index at {index_path}. Build it first: --build")
    return json.loads(index_path.read_text())


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
def semantic_search(query: str, index: dict, limit: int = 10) -> list[dict]:
    """Rank notes by meaning-distance from the query."""
    # The query must live in the same vector space as the index (fix 16/24).
    qvec = embed(query, model=index.get("model"))

    def _score(n: dict) -> float:
        vecs = n.get("vecs") or ([n["vec"]] if n.get("vec") else [])
        return max((cosine(qvec, v) for v in vecs), default=0.0)

    scored = [
        {"path": rel, "title": n["title"], "score": _score(n)}
        for rel, n in index["notes"].items()
    ]
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:limit]


def _rank_map(results: list[dict]) -> dict[str, int]:
    return {r["path"]: i for i, r in enumerate(results)}


def hybrid_search(query: str, index: dict, lexical_results: list[dict], limit: int = 10) -> list[dict]:
    """Combine lexical and semantic rankings with Reciprocal Rank Fusion.

    RRF score = sum over each ranking of 1/(k + rank). It needs no score calibration
    between the two systems (lexical counts vs cosine values are not comparable), just
    their rank orders - which is exactly why it is the standard way to fuse them.
    """
    K = 60
    sem = semantic_search(query, index, limit=max(limit, 20))
    sem_rank = _rank_map(sem)
    lex_rank = _rank_map(lexical_results)
    paths = set(sem_rank) | set(lex_rank)
    fused = []
    for p in paths:
        score = 0.0
        if p in lex_rank:
            score += 1.0 / (K + lex_rank[p])
        if p in sem_rank:
            score += 1.0 / (K + sem_rank[p])
        title = next((r["title"] for r in (sem + lexical_results) if r["path"] == p), p)
        fused.append({"path": p, "title": title, "score": score})
    fused.sort(key=lambda r: r["score"], reverse=True)
    return fused[:limit]


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Local semantic search over the vault (via Ollama)")
    ap.add_argument("--path", required=True, help="Vault root")
    ap.add_argument("--build", action="store_true", help="Build/refresh the embedding index")
    ap.add_argument("--query", help="Run a semantic search and print the top matches")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args(argv[1:])

    vault = Path(args.path).expanduser().resolve()
    if not vault.is_dir():
        print(f"vault path does not exist: {vault}", file=sys.stderr)
        return 2
    if not ollama_available():
        print(
            f"Local model runtime not found at {OLLAMA_URL}.\n"
            f"Install Ollama (https://ollama.com), open it, then: ollama pull {EMBED_MODEL}",
            file=sys.stderr,
        )
        return 3

    if args.build:
        build_index(vault)
    if args.query:
        index = load_index(vault)
        for i, r in enumerate(semantic_search(args.query, index, args.limit), 1):
            print(f"{i:2}. {r['score']:.3f}  {r['path']}")
    if not args.build and not args.query:
        print("Nothing to do. Pass --build and/or --query.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
