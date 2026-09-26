"""Retrieval-quality eval harness for the vault.

Measures how well the vault's search actually finds the right note for a
natural-language question - BEFORE anyone reaches for a vector index. It reuses
the real `search()` from the MCP connector (`integrations/obsidian-mcp-server/
vault_ops.py`), so it scores the exact term-frequency, title-weighted ranking
the skill ships with, not a reimplementation.

Two modes:

  generate  Bootstrap an eval set FROM the vault. Samples notes, and for each
            asks an LLM to write a natural-language question a user would ask
            whose answer lives in that note - deliberately AVOIDING the note's
            title words, so the question tests semantic retrieval, not string
            match. The note's path is the gold answer. Writes cases as JSONL.
            Falls back to a key-free heuristic generator if no XAI_API_KEY.

  eval      (default) Load the cases, run each question through the real
            search, and report recall@1/3/5/10 and MRR, plus the failures -
            including which note DID rank #1 when the gold note lost, so the
            "noisy high-mention note floats above the canonical note" failure
            mode is visible, not just a number.

Usage:
    uv run python scripts/eval/retrieval_eval.py --generate 30
    uv run python scripts/eval/retrieval_eval.py
    uv run python scripts/eval/retrieval_eval.py --cases scripts/eval/retrieval_cases.jsonl --json

Env (from ~/.config/obsidian-second-brain/.env): OBSIDIAN_VAULT_PATH required;
XAI_API_KEY optional (enables the LLM question generator).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_DIR = REPO_ROOT / "integrations" / "obsidian-mcp-server"
sys.path.insert(0, str(MCP_DIR))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# Load env (OBSIDIAN_VAULT_PATH + optional keys) the same way the research toolkit does.
try:
    from research.lib.config import VAULT_PATH  # noqa: F401  (import triggers dotenv load)
# config.py raises SystemExit (a BaseException) when OBSIDIAN_VAULT_PATH is
# unset, so a bare `except Exception` lets it kill the importing process.
except (Exception, SystemExit):  # pragma: no cover - fall back to a bare dotenv load
    try:
        from dotenv import load_dotenv

        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import osb_env

        load_dotenv(osb_env.env_file())
    except Exception:
        pass

import vault_ops  # noqa: E402  (depends on sys.path insert above)

DEFAULT_CASES = REPO_ROOT / "scripts" / "eval" / "retrieval_cases.jsonl"
RECALL_KS = (1, 3, 5, 10)
SEARCH_LIMIT = 10

# Folders that hold real, answerable knowledge notes (skip raw sources, exports, config).
_KNOWLEDGE_HINTS = ("wiki/", "Knowledge/", "Ideas/", "Projects/", "Research/", "concepts/")
_SKIP_PREFIXES = ("raw/", "_export/", "templates/", ".")
_MIN_BODY_CHARS = 400


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def _vault() -> Path:
    return vault_ops.resolve_vault()


def _candidate_notes(vault: Path) -> list[Path]:
    """Knowledge notes worth asking about - substantial, not raw sources."""
    out: list[Path] = []
    for md in sorted(vault.rglob("*.md")):
        rel = md.relative_to(vault).as_posix()
        if any(rel.startswith(p) for p in _SKIP_PREFIXES):
            continue
        if vault_ops._SKIP_DIRS & set(Path(rel).parts):
            continue
        try:
            body = md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if len(body) < _MIN_BODY_CHARS:
            continue
        out.append(md)
    return out


def _title_tokens(stem: str) -> set[str]:
    return {t for t in re.split(r"\W+", stem.lower()) if len(t) > 2}


# --------------------------------------------------------------------------- #
# Generate mode
# --------------------------------------------------------------------------- #
def _llm_question(body: str, title: str, style: str = "semantic") -> str | None:
    """Ask Grok for a natural-language question this note answers.

    style="semantic": forbid the note's title words (tests meaning-based retrieval -
        the hard case lexical search cannot do).
    style="keyword": allow the topic words a real user would recall (tests whether
        the right note ranks above noisy long notes - where re-ranking helps).
    """
    try:
        from research.lib import grok
    except Exception:
        return None
    import os

    if not os.environ.get("XAI_API_KEY", "").strip():
        return None
    excerpt = body[:2500]
    if style == "keyword":
        rule = (
            "Write it the way a person who half-remembers this note would actually "
            "search - you MAY use the note's topic words. "
        )
    else:
        rule = "Hard rule: do NOT reuse the note's title words verbatim. "
    prompt = (
        "Below is one note from a personal knowledge vault. Write ONE natural-language "
        "question a person would realistically ask whose answer is in this note. "
        f"{rule}Do NOT mention that this is a note, keep it under 20 words, "
        "output ONLY the question.\n\n"
        f"Note title: {title}\n\nNote body:\n{excerpt}"
    )
    try:
        res = grok.call(prompt, command="retrieval-eval", max_output_tokens=120)
        q = (res.get("text") or "").strip().splitlines()[0].strip().strip('"')
        return q or None
    except Exception as e:
        print(f"[generate] LLM call failed ({e}); using heuristic for this note", file=sys.stderr)
        return None


def _heuristic_question(body: str, title: str) -> str | None:
    """Key-free fallback: the longest body sentence that avoids the title words."""
    title_toks = _title_tokens(title)
    # strip frontmatter + preamble headers
    text = re.sub(r"^---.*?---", "", body, count=1, flags=re.DOTALL)
    text = re.sub(r"^#.*$", "", text, flags=re.MULTILINE)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    best = ""
    for s in sentences:
        s = s.strip().replace("\n", " ")
        if len(s) < 30 or len(s) > 160:
            continue
        toks = {t for t in re.split(r"\W+", s.lower()) if len(t) > 2}
        if title_toks & toks:  # avoid sentences that echo the title
            continue
        if len(s) > len(best):
            best = s
    return f"What does the vault say about: {best}" if best else None


def generate(n: int, cases_path: Path, style: str = "semantic") -> int:
    vault = _vault()
    notes = _candidate_notes(vault)
    if not notes:
        print("No candidate knowledge notes found in the vault.", file=sys.stderr)
        return 1
    # Deterministic, well-spread sample (no Date/random; stable across runs).
    step = max(1, len(notes) // n)
    sampled = notes[::step][:n]
    cases: list[dict[str, Any]] = []
    for md in sampled:
        rel = md.relative_to(vault).as_posix()
        body = md.read_text(encoding="utf-8", errors="ignore")
        q = _llm_question(body, md.stem, style) or _heuristic_question(body, md.stem)
        if not q:
            continue
        cases.append({"q": q, "gold": [rel], "title": md.stem})
        print(f"  + {md.stem[:50]:52} <- {q[:60]}")
    cases_path.parent.mkdir(parents=True, exist_ok=True)
    with cases_path.open("w", encoding="utf-8") as fh:
        for c in cases:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(cases)} cases to {cases_path}")
    return 0


# --------------------------------------------------------------------------- #
# Eval mode
# --------------------------------------------------------------------------- #
def _rank_of_gold(results: list[dict[str, Any]], gold: list[str]) -> int:
    """1-based rank of the first result whose path matches any gold path; 0 if absent."""
    gold_set = {g.strip() for g in gold}
    for i, r in enumerate(results, start=1):
        if r.get("path") in gold_set:
            return i
    return 0


def _split_external_cmd(cmd: str) -> list[str]:
    r"""Split RETRIEVAL_EVAL_EXTERNAL_CMD into argv.

    Two forms. A JSON array (the value starts with "[") is the exact form: each
    element is one argument and no shell quoting rules apply, only JSON's own
    (a double quote inside a string is \", a backslash is \\, or write Windows
    paths with forward slashes), so spaces, embedded quotes and empty arguments
    pass through exactly:
        ["bash", "C:/Program Files/x/engine.sh", "--out", "say \"hi\""]
    A plain string is split with shell-like rules: POSIX shlex on macOS and
    Linux; on Windows, where POSIX shlex would treat every backslash as an escape
    and eat the separators of a path, non-POSIX splitting that keeps backslashes
    and removes one layer of matching surrounding quotes per token. The plain
    form covers a command plus simple arguments; anything with escaped quotes or
    quotes inside an argument belongs in the JSON form.
    """
    import json
    import shlex

    stripped = cmd.strip()
    if stripped.startswith("["):
        try:
            parts = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"RETRIEVAL_EVAL_EXTERNAL_CMD looks like a JSON array but does not parse: {exc}")
        if not isinstance(parts, list) or not parts or not all(isinstance(p, str) for p in parts):
            raise SystemExit("RETRIEVAL_EVAL_EXTERNAL_CMD as JSON must be a non-empty array of strings")
        return parts
    if os.name != "nt":
        return shlex.split(cmd)
    parts: list[str] = []
    for token in shlex.split(cmd, posix=False):
        if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
            token = token[1:-1]
        parts.append(token)
    return parts


def _searcher(mode: str):
    """Return a (label, fn(query)->results) for the chosen retrieval mode.

    Four modes, four TRUE labels (stress-test fix 10/24 - before this, "lexical"
    silently measured the fused blend and "hybrid" fused an already-fused input,
    double-counting semantic and flipping the semantic-vs-hybrid conclusion):

      lexical   pure word-match, fusion forced off
      default   exactly what the shipped MCP serves (env-driven fusion)
      semantic  local embeddings only
      hybrid    single RRF of pure lexical + semantic
    """
    if mode == "lexical":
        return "pure lexical: term-frequency, title-weighted (fusion off)", \
            lambda q: vault_ops.search(q, limit=SEARCH_LIMIT, semantic=False)
    if mode == "default":
        return "shipped default: vault_ops.search (lexical + semantic RRF when available)", \
            lambda q: vault_ops.search(q, limit=SEARCH_LIMIT)
    if mode == "external":
        # Benchmark ANY external retrieval engine on the same cases: point
        # RETRIEVAL_EVAL_EXTERNAL_CMD at a command that takes the query as its
        # final argument and prints ranked results - a JSON array of paths (or
        # of {"path": ...} objects), or plain newline-separated paths. This is
        # how a TypeAgent / structured-RAG / vector-DB runner competes against
        # the shipped search without being imported or vendored (pattern from
        # the structured-rag eval fork, fork-insights round 2).
        import os
        import shutil
        import subprocess
        cmd = os.environ.get("RETRIEVAL_EVAL_EXTERNAL_CMD", "").strip()
        if not cmd:
            raise SystemExit(
                "External mode needs RETRIEVAL_EVAL_EXTERNAL_CMD - a command that "
                "takes the query as its final argument and prints ranked note "
                "paths (JSON array or one per line). The value is a plain command "
                "line, or a JSON array of arguments for anything shell quoting "
                "cannot express."
            )

        parts = _split_external_cmd(cmd)
        # An engine command of the form "bash <script>" hits the same collision
        # as every other bare "bash" in this repo (#308): on Windows, CreateProcess
        # checks System32 before PATH, so a bare "bash" resolves to WSL's launcher
        # when WSL is installed, even though shutil.which("bash") still finds Git
        # Bash. WSL then reads the Windows script path's backslashes as escape
        # characters and reports "No such file or directory". Resolved here, not
        # inside _split_external_cmd, which only parses argv and must not assume
        # the first token is bash.
        if parts and parts[0] == "bash":
            parts[0] = shutil.which("bash") or "/bin/bash"

        def _external(q: str) -> list[dict[str, Any]]:
            proc = subprocess.run(
                parts + [q],
                capture_output=True, text=True, timeout=120,
            )
            if proc.returncode != 0:
                print(f"[external] engine failed on {q!r}: {proc.stderr.strip()[:200]}", file=sys.stderr)
                return []
            out = proc.stdout.strip()
            if not out:
                return []
            try:
                parsed = json.loads(out)
                items = parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                items = out.splitlines()
            results = []
            for item in items:
                path = item.get("path") if isinstance(item, dict) else item
                if isinstance(path, str) and path.strip():
                    results.append({"path": path.strip()})
            return results[:SEARCH_LIMIT]

        return f"external engine: {cmd}", _external
    import semantic_search as ss  # local module; needs Ollama running
    vault = vault_ops.resolve_vault()
    if not ss.ollama_available():
        raise SystemExit(
            "Semantic/hybrid mode needs the local model runtime. Install Ollama "
            f"(https://ollama.com), then: ollama pull {ss.EMBED_MODEL}, then "
            "build the index: uv run python scripts/eval/semantic_search.py --path <vault> --build"
        )
    index = ss.load_index(vault)
    if mode == "semantic":
        return f"local embeddings: {index.get('model')} (semantic_search)", \
            lambda q: ss.semantic_search(q, index, limit=SEARCH_LIMIT)
    # hybrid: the lexical arm MUST be pure, or semantic gets fused twice
    return f"hybrid: pure lexical + {index.get('model')} (single RRF)", \
        lambda q: ss.hybrid_search(q, index,
                                   vault_ops.search(q, limit=SEARCH_LIMIT, semantic=False),
                                   limit=SEARCH_LIMIT)


def evaluate(cases_path: Path, as_json: bool, mode: str = "lexical") -> int:
    if not cases_path.exists():
        print(
            f"No cases file at {cases_path}.\n"
            f"Bootstrap one first:  uv run python scripts/eval/retrieval_eval.py --generate 30",
            file=sys.stderr,
        )
        return 1
    cases = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not cases:
        print("Cases file is empty.", file=sys.stderr)
        return 1

    label, search_fn = _searcher(mode)
    per_case: list[dict[str, Any]] = []
    for c in cases:
        try:
            results = search_fn(c["q"])
        except Exception as e:
            # One bad case must not discard every case already scored. In
            # semantic/hybrid mode embed() uses the full (1,3,8,15) retry ladder
            # at 120s per attempt, so a slow backend can burn ~10 minutes here
            # and then take the entire run down with it. Count it as a miss.
            print(f"  case failed, counted as a miss: {c['q'][:60]!r}: {e}", file=sys.stderr)
            results = []
        rank = _rank_of_gold(results, c.get("gold", []))
        top = results[0]["path"] if results else None
        per_case.append({
            "q": c["q"],
            "gold": c.get("gold", []),
            "rank": rank,
            "top_hit": top,
            "title": c.get("title", ""),
        })

    n = len(per_case)
    recall = {k: sum(1 for x in per_case if 0 < x["rank"] <= k) / n for k in RECALL_KS}
    mrr = sum((1.0 / x["rank"]) if x["rank"] else 0.0 for x in per_case) / n
    misses = [x for x in per_case if x["rank"] == 0]
    buried = [x for x in per_case if x["rank"] > 3]

    summary = {
        "cases": n,
        "search": label,
        "recall_at": {str(k): round(recall[k], 3) for k in RECALL_KS},
        "mrr": round(mrr, 3),
        "misses": len(misses),
        "buried_below_3": len(buried),
    }

    if as_json:
        # Force UTF-8 stdout: on Windows a pipe defaults to cp1252, which cannot
        # encode every character a case question or note path may carry.
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
        print(json.dumps({"summary": summary, "cases": per_case}, ensure_ascii=False, indent=2))
        return 0

    print(f"\nRetrieval eval - {n} cases  (engine: {summary['search']})")
    print("-" * 64)
    for k in RECALL_KS:
        bar = "#" * round(recall[k] * 40)
        print(f"  recall@{k:<2} {recall[k]*100:5.1f}%  {bar}")
    print(f"  MRR      {mrr:.3f}")
    print(f"  misses (gold not in top {SEARCH_LIMIT}): {len(misses)}   buried (rank>3): {len(buried)}")

    if misses:
        print("\nMisses - the right note never surfaced:")
        for x in misses[:15]:
            print(f"  Q: {x['q'][:70]}")
            print(f"     want: {x['gold'][0] if x['gold'] else '?'}")
            print(f"     #1 was: {x['top_hit']}")
    if buried:
        print("\nBuried - right note ranked below #3 (often a noisy high-mention note on top):")
        for x in buried[:10]:
            print(f"  rank {x['rank']}: {x['gold'][0] if x['gold'] else '?'}  (Q: {x['q'][:48]})")
            print(f"           #1 was: {x['top_hit']}")
    print()
    return 0


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Vault retrieval-quality eval harness")
    ap.add_argument("--generate", type=int, metavar="N",
                    help="Bootstrap N eval cases from the vault instead of evaluating")
    ap.add_argument("--style", choices=("semantic", "keyword"), default="semantic",
                    help="Question style when generating: semantic (avoid title words, "
                         "the hard case) or keyword (realistic lookup; default semantic)")
    ap.add_argument("--cases", type=Path, default=DEFAULT_CASES,
                    help=f"Cases JSONL path (default: {DEFAULT_CASES})")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of a text report")
    ap.add_argument("--mode", choices=("lexical", "default", "semantic", "hybrid", "external"),
                    default="lexical",
                    help="Retrieval to score: lexical (pure word-match, default), "
                         "default (exactly what the shipped MCP serves), semantic "
                         "(local embeddings), or hybrid (pure lexical + semantic, "
                         "single RRF). semantic/hybrid need Ollama.")
    ap.add_argument("--force", action="store_true",
                    help="Allow --generate to overwrite an existing cases file")
    args = ap.parse_args()

    if args.generate is not None:
        if args.cases.exists() and not args.force:
            print(
                f"Refusing to overwrite existing cases at {args.cases}: regenerating "
                f"mid-experiment breaks the before/after comparison on the SAME cases.\n"
                f"Pass --force to overwrite, or --cases <new-path> for a fresh set.",
                file=sys.stderr,
            )
            return 1
        return generate(args.generate, args.cases, args.style)
    return evaluate(args.cases, args.json, args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
