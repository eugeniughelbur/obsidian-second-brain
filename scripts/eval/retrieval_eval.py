# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer working on agent memory), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
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

No-answer cases: a case with "gold": null asks a question the vault has no
answer for. It passes only if no result scores above a threshold, so it tests
whether search admits "not found" or serves a wrong note with confidence.
--mode lexical judges the raw lexical score (--no-answer-threshold); --mode
default judges each fused result's embedding cosine
(--no-answer-cosine-threshold), or the lexical score when a query fell back to
lexical. These cases are reported on their own and never count toward recall
or MRR. The semantic, hybrid and external modes do not judge them.

Usage:
    uv run python scripts/eval/retrieval_eval.py --generate 30
    uv run python scripts/eval/retrieval_eval.py
    uv run python scripts/eval/retrieval_eval.py --cases scripts/eval/retrieval_cases.jsonl --json

Env (from ~/.config/obsidian-second-brain/.env): OBSIDIAN_VAULT_PATH required;
XAI_API_KEY optional (enables the LLM question generator).

--mode default counts, per query, whether the shipped search fused, skipped
fusion on purpose, or fell back to lexical, and exits 1 without a report when
any query fell back (#386).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
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
# A no-answer case ("gold": null) passes only when no result's raw lexical
# score goes above this line. Calibrated 2026-11-22 on the maintainer's vault:
# the #1 lexical score on 35 answerable paraphrase questions ran 9.82 to 40.01
# (median 19.41), so 9.8 sits just under the weakest real question. A
# no-answer question passes only if search's best match is weaker than every
# real question's best match. Lexical scale only; re-calibrate per vault.
NO_ANSWER_THRESHOLD = 9.8
# The same rule for --mode default, on the embedding scale: a fused result is
# judged on its best-chunk cosine. Same calibration run: the best cosine on the
# 35 answerable questions ran 0.489 to 0.720 (median 0.616), so 0.48 sits just
# under the weakest real question. The fused RRF score itself is useless here:
# the #1 hit scored 0.328 to 0.350 on every question (0.35 is the ceiling).
NO_ANSWER_COSINE_THRESHOLD = 0.48

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


def _judged_score(r: dict[str, Any]) -> tuple[str, float] | None:
    """The score a no-answer case is judged on, with its scale. A fused result
    is judged on its embedding cosine, because the fused RRF score is built from
    rank positions alone and the #1 hit gets nearly the same value on every query."""
    if r.get("score_kind") == "fused":
        cos = r.get("semantic_score")
        return ("cosine", float(cos)) if isinstance(cos, (int, float)) else None
    s = r.get("score")
    return ("lexical", float(s)) if isinstance(s, (int, float)) else None


def _judge_no_answer(
    case: dict[str, Any], results: list[dict[str, Any]], judged: bool,
    thresholds: dict[str, float],
) -> dict[str, Any]:
    """Score one "gold": null case. passed is None when the mode has no
    comparable score; otherwise True only if no result scores above the
    threshold for its scale (an empty result list counts as admitting "not found")."""
    scored = [js for js in (_judged_score(r) for r in results) if js is not None]
    top = _judged_score(results[0]) if results else None
    passed: bool | None = None
    if judged:
        passed = all(value <= thresholds[scale] for scale, value in scored)
    # One query's results share one scale: all fused, or all lexical on fallback.
    best = max((value for _, value in scored), default=None)
    return {
        "q": case["q"],
        "top_hit": results[0]["path"] if results else None,
        "scale": top[0] if top else None,
        "top_score": round(top[1], 3) if top else None,
        "max_score": round(best, 3) if best is not None else None,
        "passed": passed,
        "title": case.get("title", ""),
    }


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


# Reasons vault_ops.search() reports (through on_semantic_fallback) when fusion
# was never attempted on purpose. Anything else it reports means fusion was
# enabled and an index exists, but the semantic arm still returned nothing.
_SKIPPED_BY_DESIGN = ("disabled by configuration", "semantic index missing")


class _FusionTally:
    """Record, per query, whether the shipped default search really fused (#386).

    `vault_ops.search` serves pure lexical results whenever `_semantic_fuse`
    returns None, and nothing in its return value says which happened. The
    reason it gives (the `on_semantic_fallback` callback, #389) says why; this
    sorts each query of a default-mode run into one of three outcomes:

      fused     the semantic arm ran and its ranking was fused in
      skipped   fusion was not attempted, on purpose: a single-term query
                (search turns fusion off for those), "disabled by
                configuration", "semantic index missing", or a query with no
                searchable terms
      fallback  fusion was enabled and an index exists, but the fuse returned
                None (slow or missing embedder, empty index, any error)

    Only `fallback` means the row is not what its label says.
    """

    def __init__(self) -> None:
        self.outcome: str | None = None
        self.reason: str | None = None
        self._real_fuse = vault_ops._semantic_fuse

    def install(self) -> None:
        vault_ops._semantic_fuse = self._fuse

    def uninstall(self) -> None:
        vault_ops._semantic_fuse = self._real_fuse

    def start_query(self) -> None:
        self.outcome, self.reason = None, None

    def report(self, reason: str) -> None:
        """The `on_semantic_fallback` callback: vault_ops names why it fell short."""
        self.outcome = "skipped" if reason in _SKIPPED_BY_DESIGN else "fallback"
        self.reason = reason

    def search_raised(self, error: Exception) -> None:
        # Not fused, and not skipped on purpose either: the row must not pass.
        self.outcome = "fallback"
        self.reason = f"search raised {type(error).__name__}: {error}"

    def result(self) -> tuple[str, str | None]:
        if self.outcome is None:  # search returned before it reached the fuse
            return "skipped", "no searchable terms"
        return self.outcome, self.reason

    def _fuse(self, query: str, lexical: Any, vault: Path, limit: int,
              enabled: bool | None = None, **kwargs: Any) -> Any:
        fused = self._real_fuse(query, lexical, vault, limit, enabled=enabled, **kwargs)
        if self.outcome is not None:  # vault_ops gave a reason through report()
            return fused
        if enabled is False:  # search turned fusion off itself: a single-term query
            self.outcome, self.reason = "skipped", "single-term query"
        elif fused is not None:
            self.outcome = "fused"
        else:  # no reason reported, but the semantic arm still returned nothing
            self.outcome, self.reason = "fallback", "semantic arm returned nothing"
        return fused


def _searcher(mode: str, on_semantic_fallback=None):
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
        # with_scores keeps the raw score for no-answer judging; ranking is unchanged.
        return "pure lexical: term-frequency, title-weighted (fusion off)", \
            lambda q: vault_ops.search(q, limit=SEARCH_LIMIT, semantic=False, with_scores=True)
    if mode == "default":
        if on_semantic_fallback is not None:
            return "shipped default: vault_ops.search (lexical + semantic RRF when available)", \
                lambda q: vault_ops.search(
                    q, limit=SEARCH_LIMIT, on_semantic_fallback=on_semantic_fallback,
                    with_scores=True,
                )
        return "shipped default: vault_ops.search (lexical + semantic RRF when available)", \
            lambda q: vault_ops.search(q, limit=SEARCH_LIMIT, with_scores=True)
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
        # A bare "bash" resolves through CreateProcess on Windows, which checks
        # System32 before PATH, so with WSL installed it starts WSL's launcher
        # and the Windows script path arrives mangled (#308). Resolved here, not
        # in _split_external_cmd, which only parses argv.
        if parts and parts[0] == "bash":
            parts[0] = shutil.which("bash") or "bash"

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


def _score_cases(
    cases: list[dict[str, Any]], search_fn: Any, tally: _FusionTally | None = None,
    judge_no_answer: bool = False, thresholds: dict[str, float] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run every case. Returns (ranked cases, "gold": null cases). Both kinds
    go through the fusion tally, so a fallback on a no-answer query is caught too."""
    per_case: list[dict[str, Any]] = []
    no_answer: list[dict[str, Any]] = []
    for c in cases:
        if tally:
            tally.start_query()
        search_failed = False
        try:
            results = search_fn(c["q"])
        except Exception as e:
            search_failed = True
            # One bad case must not discard every case already scored. In
            # semantic/hybrid mode embed() uses the full (1,3,8,15) retry ladder
            # at 120s per attempt, so a slow backend can burn ~10 minutes here
            # and then take the entire run down with it. Count it as a miss.
            print(f"  case failed, counted as a miss: {c['q'][:60]!r}: {e}", file=sys.stderr)
            results = []
            if tally:
                tally.search_raised(e)
        if "gold" in c and c["gold"] is None:
            entry = _judge_no_answer(c, results, judge_no_answer, thresholds or {})
            if search_failed and judge_no_answer:
                # A crashed search returned nothing; that is not "admitted not found".
                entry["passed"] = False
            no_answer.append(entry)
        else:
            rank = _rank_of_gold(results, c.get("gold", []))
            top = results[0]["path"] if results else None
            entry = {
                "q": c["q"],
                "gold": c.get("gold", []),
                "rank": rank,
                "top_hit": top,
                "title": c.get("title", ""),
            }
            per_case.append(entry)
        if tally:
            entry["fusion"], reason = tally.result()
            if reason:
                entry["fusion_reason"] = reason
    return per_case, no_answer


def _fusion_summary(per_case: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(x["fusion"] for x in per_case)
    return {
        "fused": counts["fused"],
        "skipped": counts["skipped"],
        "fallback": counts["fallback"],
        "skipped_reasons": dict(sorted(Counter(
            x["fusion_reason"] for x in per_case if x["fusion"] == "skipped").items())),
    }


def _fusion_line(fusion: dict[str, Any]) -> str:
    why = ", ".join(f"{r}: {c}" for r, c in fusion["skipped_reasons"].items())
    return (f"fusion: {fusion['fused']} fused, {fusion['skipped']} skipped by design"
            f"{' (' + why + ')' if why else ''}, {fusion['fallback']} fell back")


def _fallback_error(fusion: dict[str, Any], n: int, per_case: list[dict[str, Any]]) -> str:
    fell = [x for x in per_case if x["fusion"] == "fallback"]
    lines = [
        f"Refusing to report a default-mode row: {len(fell)} of {n} queries fell back "
        f"to pure lexical although fusion was enabled and a semantic index exists.",
        f"  {_fusion_line(fusion)}",
    ]
    for reason, count in Counter(x["fusion_reason"] for x in fell).most_common(5):
        lines.append(f"  {count}x {reason}")
    # Reasons quote the embedder's own error text. Keep the report printable
    # on a console that cannot encode it (cp1252 on Windows).
    lines = [x.encode("ascii", "backslashreplace").decode("ascii") for x in lines]
    lines.append(
        "  Check that the embedder is running and the model is loaded, or raise "
        "OBSIDIAN_EMBED_QUERY_TIMEOUT, then rerun. For lexical numbers use --mode lexical."
    )
    return "\n".join(lines)


def evaluate(
    cases_path: Path, as_json: bool, mode: str = "lexical",
    no_answer_threshold: float = NO_ANSWER_THRESHOLD,
    no_answer_cosine_threshold: float = NO_ANSWER_COSINE_THRESHOLD,
) -> int:
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

    # Default mode only: it is the one mode that goes through search()'s
    # silent lexical fallback. lexical forces fusion off; semantic and hybrid
    # call the embedder themselves.
    tally = _FusionTally() if mode == "default" else None
    label, search_fn = _searcher(
        mode, on_semantic_fallback=tally.report if tally else None,
    )
    judge_no_answer = mode in ("lexical", "default")
    thresholds = {"lexical": no_answer_threshold}
    if mode == "default":
        thresholds["cosine"] = no_answer_cosine_threshold
    if tally:
        tally.install()
    try:
        per_case, no_answer = _score_cases(cases, search_fn, tally, judge_no_answer, thresholds)
    finally:
        if tally:
            tally.uninstall()

    n = len(per_case)
    fusion = None
    if tally:
        every_query = per_case + no_answer
        fusion = _fusion_summary(every_query)
        if fusion["fallback"]:
            # A default row with fallbacks is part lexical under a fused label.
            # Refuse to report it: in #342 a whole pass came out lexical and
            # was caught only because one score looked wrong.
            print(_fallback_error(fusion, len(every_query), every_query), file=sys.stderr)
            return 1
    # A file of only no-answer cases leaves nothing to rank; report zeros, not a crash.
    d = n or 1
    recall = {k: sum(1 for x in per_case if 0 < x["rank"] <= k) / d for k in RECALL_KS}
    mrr = sum((1.0 / x["rank"]) if x["rank"] else 0.0 for x in per_case) / d
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
    if fusion is not None:
        summary["fusion"] = fusion
    if no_answer:
        summary["no_answer"] = {
            "cases": len(no_answer),
            "thresholds": thresholds if judge_no_answer else None,
            "passed": sum(1 for x in no_answer if x["passed"] is True),
            "failed": sum(1 for x in no_answer if x["passed"] is False),
            "judged": judge_no_answer,
        }

    if as_json:
        # Force UTF-8 stdout: on Windows a pipe defaults to cp1252, which cannot
        # encode every character a case question or note path may carry.
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
        payload: dict[str, Any] = {"summary": summary, "cases": per_case}
        if no_answer:
            payload["no_answer_cases"] = no_answer
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"\nRetrieval eval - {n} cases  (engine: {summary['search']})")
    print("-" * 64)
    for k in RECALL_KS:
        bar = "#" * round(recall[k] * 40)
        print(f"  recall@{k:<2} {recall[k]*100:5.1f}%  {bar}")
    print(f"  MRR      {mrr:.3f}")
    if fusion is not None:
        print(f"  {_fusion_line(fusion)}")
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
    if no_answer:
        if judge_no_answer:
            na = summary["no_answer"]
            lines = ", ".join(f"{scale} {value}" for scale, value in thresholds.items())
            print(f"\nNo-answer cases - pass only if no result scores above ({lines}): "
                  f"{na['passed']} passed, {na['failed']} failed")
        else:
            print(f"\nNo-answer cases - not judged in --mode {mode} (only lexical and "
                  "default modes have a score to compare):")
        for x in no_answer:
            verdict = {True: "PASS", False: "FAIL", None: "n/a"}[x["passed"]]
            best = f"{x['max_score']:.3f}" if x["max_score"] is not None else "-"
            print(f"  {verdict:4}  best {x['scale'] or '-'} {best:>7}  Q: {x['q'][:52]}")
            print(f"        #1 was: {x['top_hit']}")
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
    ap.add_argument("--no-answer-threshold", type=float, default=NO_ANSWER_THRESHOLD,
                    help="Raw lexical score line for \"gold\": null cases: one passes only "
                         f"if no result scores above it (default {NO_ANSWER_THRESHOLD}). "
                         "Used in --mode lexical, and in --mode default when a query "
                         "falls back to lexical.")
    ap.add_argument("--no-answer-cosine-threshold", type=float,
                    default=NO_ANSWER_COSINE_THRESHOLD,
                    help="Embedding cosine line for \"gold\": null cases in --mode default "
                         f"(default {NO_ANSWER_COSINE_THRESHOLD}).")
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
    return evaluate(args.cases, args.json, args.mode, args.no_answer_threshold,
                    args.no_answer_cosine_threshold)


if __name__ == "__main__":
    raise SystemExit(main())
