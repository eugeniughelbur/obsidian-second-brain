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
    ollama pull mxbai-embed-large
Configure via env: OLLAMA_URL (default http://localhost:11434),
OBSIDIAN_EMBED_MODEL (default mxbai-embed-large),
OBSIDIAN_EMBED_EXCLUDE (default empty; e.g. "wiki/private/,Faith,Masha").
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
EMBED_MODEL = os.environ.get("OBSIDIAN_EMBED_MODEL", "mxbai-embed-large")
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
# Embedding models have a token limit (mxbai-embed-large ~512 tokens). Long notes
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


def _embed_request(text: str) -> tuple[str, bytes, dict]:
    """Build the (url, body, headers) for the configured backend."""
    if EMBED_BACKEND == "openai":
        headers = {"Content-Type": "application/json"}
        if EMBED_KEY:
            headers["Authorization"] = f"Bearer {EMBED_KEY}"
        body = json.dumps({"model": EMBED_MODEL, "input": text[:_CHUNK_CHARS]}).encode()
        return f"{EMBED_URL}/v1/embeddings", body, headers
    # ollama (default): keep_alive holds the model in memory between calls
    body = json.dumps({"model": EMBED_MODEL, "prompt": text[:_CHUNK_CHARS], "keep_alive": "15m"}).encode()
    return f"{EMBED_URL}/api/embeddings", body, {"Content-Type": "application/json"}


def _parse_embedding(data: dict) -> list[float] | None:
    """Pull the vector out of either response shape."""
    if data.get("embedding"):                       # ollama
        return data["embedding"]
    items = data.get("data")                         # openai-compatible
    if items and isinstance(items, list) and items[0].get("embedding"):
        return items[0]["embedding"]
    return None


def embed(text: str) -> list[float]:
    """Return the embedding vector for one text via the configured backend.

    Retries transient errors (HTTP 5xx, connection resets): a local model on a
    laptop can buckle under rapid sequential calls, then recover a second later.
    The last failure is raised so the caller can skip the note.
    """
    url, body, headers = _embed_request(text)
    last_err: Exception | None = None
    for attempt in range(len(_RETRY_WAITS) + 1):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as r:
                vec = _parse_embedding(json.loads(r.read()))
            if vec:
                return vec
            last_err = RuntimeError(f"backend returned no embedding (model '{EMBED_MODEL}')")
        except (urllib.error.HTTPError, urllib.error.URLError, ConnectionError, TimeoutError) as e:
            last_err = e
        if attempt < len(_RETRY_WAITS):
            time.sleep(_RETRY_WAITS[attempt])
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


def embed_note(text: str) -> list[float]:
    """Embed a whole note: split into safe-sized chunks, embed each, average them.

    A note longer than the model's token limit cannot be embedded in one call, so
    we chunk it and mean-pool - representing the entire note, not just its opening.
    Chunk count is capped so a giant transcript stays fast (the cap still covers
    ~9600 chars, far more than any preamble + first sections)."""
    text = text.strip()
    if not text:
        return []
    chunks = [text[i:i + _CHUNK_CHARS] for i in range(0, len(text), _CHUNK_CHARS)][:_MAX_CHUNKS]
    return _mean_pool([embed(c) for c in chunks])


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
        if SKIP_DIRS & set(parts):
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
    old = cache.get("notes", {})
    new: dict = {}
    embedded = reused = skipped = failed = 0

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
        embed_text = text if text.strip() else md.stem
        if not embed_text.strip():
            continue
        try:
            vec = embed_note(embed_text)
        except Exception as e:  # one bad note must not abort a 1000-note run
            failed += 1
            if verbose:
                print(f"  [skip] {rel}: {e}", file=sys.stderr)
            continue
        new[rel] = {"hash": h, "title": md.stem, "vec": vec}
        embedded += 1
        if verbose and embedded % 50 == 0:
            print(f"  embedded {embedded} notes...", file=sys.stderr)

    out = {"model": EMBED_MODEL, "notes": new}
    index_path.write_text(json.dumps(out), encoding="utf-8")
    if verbose:
        print(
            f"[semantic] indexed {len(new)} notes ({embedded} new, {reused} cached, "
            f"{skipped} excluded, {failed} failed) -> {index_path}",
            file=sys.stderr,
        )
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
    qvec = embed(query)
    scored = [
        {"path": rel, "title": n["title"], "score": cosine(qvec, n["vec"])}
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
