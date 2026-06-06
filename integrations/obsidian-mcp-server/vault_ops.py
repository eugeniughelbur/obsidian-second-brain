"""Vault operations for the Obsidian Second Brain MCP server.

Pure stdlib, no MCP dependency, so the logic is unit-testable on its own. The
MCP wiring in `server.py` is a thin layer over these functions.

Every write follows the AI-first rule (references/ai-first-rules.md): frontmatter
with type/date/tags/ai-first, a `## For future Claude` preamble, and a
`source: mcp` marker so notes added through the connector are distinguishable.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_VAULT_ENV = "OBSIDIAN_VAULT_PATH"

# Notes added via the connector land here, separate from hand-authored notes.
_NOTES_DIR = "Inbox"

# Never scanned during search (config, vcs, immutable sources, exports).
_SKIP_DIRS = {".obsidian", ".git", ".trash", "_export", "templates"}

# Bounds keep search fast and reads safe.
_MAX_FILES_SCANNED = 2000
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


def search(query: str, *, limit: int = 6) -> List[Dict[str, Any]]:
    """Bounded case-insensitive term-frequency search over vault markdown."""
    vault = resolve_vault()
    terms = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]
    if not terms:
        return []
    limit = max(1, min(int(limit), 20))
    scored: List[Dict[str, Any]] = []
    for i, md in enumerate(_iter_notes(vault)):
        if i >= _MAX_FILES_SCANNED:
            break
        text = _read_safe(md, limit=_MAX_FILE_BYTES)
        if not text:
            continue
        low = text.lower()
        title_low = md.stem.lower()
        score = 0
        for t in terms:
            score += low.count(t)
            score += 5 * title_low.count(t)  # title matches weighted
        if score:
            scored.append(
                {
                    "path": str(md.relative_to(vault)),
                    "title": md.stem,
                    "score": score,
                    "snippet": _snippet(text, terms),
                }
            )
    scored.sort(key=lambda r: r["score"], reverse=True)
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
    return {"saved": str(path.relative_to(vault))}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iter_notes(vault: Path):
    for md in vault.rglob("*.md"):
        if set(md.relative_to(vault).parts) & _SKIP_DIRS:
            continue
        yield md


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
