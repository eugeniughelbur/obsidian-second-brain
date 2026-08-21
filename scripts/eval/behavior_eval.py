"""Behavior eval: does having the vault actually make the ANSWER better?

`retrieval_eval.py` measures whether search returns the right note. It says
nothing about what happens next - whether an agent that can see that note
actually gives a better answer than the same agent with no vault at all. This
harness closes that gap on the synthetic corpus from `corpus.py`:

  1. Load behavior cases (`corpus.behavior_cases()`) - fact, decision,
     relationship, cross-note synthesis, and contradiction questions, each
     carrying an `answer_key`: the canonical fact text the question is about.
  2. For each question, generate two answers: one with vault retrieval
     available (`vault_ops.search()` results assembled as context), one from
     the model alone, no context.
  3. Grade both answers with an LLM judge that is blind to which answer came
     from which condition - it sees "Answer A" / "Answer B" only, labels
     randomized per case (seeded, so re-judging the same cases is
     reproducible) - against the case's `answer_key`.
  4. Report the overall delta (vault-on score minus vault-off score), a
     per-category breakdown, and a complete, never-truncated list of cases
     where the vault-on answer scored WORSE. A zero or negative delta is a
     valid result, not a bug - this harness must show that as cleanly as a
     large positive one.

This is a smaller, noisier instrument than the retrieval eval: LLM judging on
a synthetic corpus of a few dozen cases is not a scientific-grade signal for
"the vault helps." Treat any single run's delta as suggestive, not a claim -
that caveat belongs on every number this script prints, not just in the
README.

Usage:
    uv run python scripts/eval/behavior_eval.py --generate 20
    uv run python scripts/eval/behavior_eval.py
    uv run python scripts/eval/behavior_eval.py --cases scripts/eval/behavior_cases.jsonl --json

Env (from ~/.config/obsidian-second-brain/.env): OBSIDIAN_VAULT_PATH required
(point it at a corpus.py --out vault for a reproducible run); XAI_API_KEY
required (there is no key-free fallback - both answering and judging are LLM
calls, unlike retrieval_eval.py's heuristic question generator).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_DIR = REPO_ROOT / "integrations" / "obsidian-mcp-server"
sys.path.insert(0, str(MCP_DIR))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "eval"))

try:
    from research.lib.config import VAULT_PATH  # noqa: F401  (import triggers dotenv load)
except (Exception, SystemExit):  # pragma: no cover - fall back to a bare dotenv load
    try:
        from dotenv import load_dotenv

        load_dotenv(Path.home() / ".config" / "obsidian-second-brain" / ".env")
    except Exception:
        pass

import corpus  # noqa: E402  (depends on sys.path insert above)
import vault_ops  # noqa: E402

DEFAULT_CASES = REPO_ROOT / "scripts" / "eval" / "behavior_cases.jsonl"
SEARCH_LIMIT = 5
JUDGE_SCALE = 5  # judge scores each answer 1-5


# --------------------------------------------------------------------------- #
# Case loading / generation
# --------------------------------------------------------------------------- #
def generate(cases_path: Path) -> int:
    """Behavior cases come from the synthetic corpus, not the live vault - the
    judge needs a known `answer_key`, which only corpus.py can supply."""
    rows = corpus.behavior_cases()
    cases_path.parent.mkdir(parents=True, exist_ok=True)
    with cases_path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Wrote {len(rows)} behavior cases to {cases_path}")
    print(
        "\nThese cases only make sense against the matching synthetic vault:\n"
        "  uv run python scripts/eval/corpus.py --out /tmp/bench-vault\n"
        "  OBSIDIAN_VAULT_PATH=/tmp/bench-vault uv run python scripts/eval/"
        "behavior_eval.py --cases " + str(cases_path)
    )
    return 0


# --------------------------------------------------------------------------- #
# Answer generation
# --------------------------------------------------------------------------- #
def _answer_without_vault(question: str) -> str | None:
    from research.lib import grok

    prompt = (
        "Answer the following question as best you can from what you already "
        "know. If you do not know, say so plainly rather than guessing.\n\n"
        f"Question: {question}"
    )
    try:
        res = grok.call(prompt, command="behavior-eval-no-vault", max_output_tokens=300)
        return (res.get("text") or "").strip() or None
    except Exception as e:
        print(f"  [no-vault] answer generation failed: {e}", file=sys.stderr)
        return None


def _context_for(question: str) -> str:
    vault = vault_ops.resolve_vault()
    try:
        results = vault_ops.search(question, limit=SEARCH_LIMIT)
    except Exception as e:
        print(f"  [with-vault] search failed: {e}", file=sys.stderr)
        return ""
    chunks = []
    for r in results:
        path = r.get("path")
        if not path:
            continue
        try:
            body = (vault / path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        chunks.append(f"--- {path} ---\n{body}")
    return "\n\n".join(chunks)


def _answer_with_vault(question: str) -> str | None:
    from research.lib import grok

    context = _context_for(question)
    if not context:
        return None
    prompt = (
        "Answer the following question using ONLY the notes below. If the "
        "notes don't contain the answer, say so plainly rather than guessing.\n\n"
        f"Notes:\n{context}\n\nQuestion: {question}"
    )
    try:
        res = grok.call(prompt, command="behavior-eval-with-vault", max_output_tokens=300)
        return (res.get("text") or "").strip() or None
    except Exception as e:
        print(f"  [with-vault] answer generation failed: {e}", file=sys.stderr)
        return None


# --------------------------------------------------------------------------- #
# Blind judging
# --------------------------------------------------------------------------- #
def _ab_order(case_index: int) -> bool:
    """True => vault-on is "Answer A" for this case. Seeded by index, not
    random, so re-judging the same cases file reproduces the same labeling."""
    digest = hashlib.sha256(f"behavior-eval-ab-{case_index}".encode()).hexdigest()
    return int(digest[:8], 16) % 2 == 0


def _judge_prompt(question: str, answer_key: str, answer_a: str, answer_b: str) -> str:
    return (
        "You are a strict, skeptical grading judge. You will see a question, the "
        "known correct facts, and two candidate answers labeled A and B. You do "
        "not know how either answer was produced - grade only what is written.\n\n"
        f"Question: {question}\n\n"
        f"Known correct facts: {answer_key}\n\n"
        f"Answer A:\n{answer_a}\n\n"
        f"Answer B:\n{answer_b}\n\n"
        "Score each answer 1-5 on whether it contains/matches the key facts above "
        "(1 = wrong or contradicts the facts, 5 = fully correct and complete). "
        "An answer that admits it does not know scores 1, not a middle score. "
        "Do not reward answers for matching the known facts' exact wording - "
        "reward them for being factually correct.\n\n"
        'Respond with ONLY strict JSON, no other text: '
        '{"score_a": <1-5>, "score_b": <1-5>, "reasoning": "<one sentence>"}'
    )


def _judge(question: str, answer_key: str, answer_a: str, answer_b: str) -> dict[str, Any] | None:
    from research.lib import grok

    prompt = _judge_prompt(question, answer_key, answer_a, answer_b)
    try:
        res = grok.call(prompt, command="behavior-eval-judge", max_output_tokens=200)
        text = (res.get("text") or "").strip()
    except Exception as e:
        print(f"  [judge] call failed: {e}", file=sys.stderr)
        return None
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        parsed = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        print(f"  [judge] could not parse response as JSON: {text[:120]!r}", file=sys.stderr)
        return None
    if "score_a" not in parsed or "score_b" not in parsed:
        print(f"  [judge] response missing score fields: {parsed}", file=sys.stderr)
        return None
    return parsed


# --------------------------------------------------------------------------- #
# Aggregation / reporting
# --------------------------------------------------------------------------- #
def evaluate(cases_path: Path, as_json: bool) -> int:
    if not cases_path.exists():
        print(
            f"No cases file at {cases_path}.\n"
            f"Bootstrap one first:  uv run python scripts/eval/behavior_eval.py --generate",
            file=sys.stderr,
        )
        return 1
    rows = [json.loads(x) for x in cases_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    if not rows:
        print("Cases file is empty.", file=sys.stderr)
        return 1

    per_case: list[dict[str, Any]] = []
    for i, c in enumerate(rows):
        question = c["q"]
        answer_key = c.get("answer_key", "")
        vault_on = _answer_with_vault(question)
        vault_off = _answer_without_vault(question)
        if vault_on is None or vault_off is None:
            per_case.append({
                "q": question, "category": c.get("category", ""), "title": c.get("title", ""),
                "judged": False, "reason": "answer generation failed",
            })
            continue

        vault_on_is_a = _ab_order(i)
        answer_a = vault_on if vault_on_is_a else vault_off
        answer_b = vault_off if vault_on_is_a else vault_on
        verdict = _judge(question, answer_key, answer_a, answer_b)
        if verdict is None:
            per_case.append({
                "q": question, "category": c.get("category", ""), "title": c.get("title", ""),
                "judged": False, "reason": "judge failed or unparseable",
            })
            continue

        score_a, score_b = verdict["score_a"], verdict["score_b"]
        vault_on_score = score_a if vault_on_is_a else score_b
        vault_off_score = score_b if vault_on_is_a else score_a
        per_case.append({
            "q": question,
            "category": c.get("category", ""),
            "title": c.get("title", ""),
            "judged": True,
            "vault_on_score": vault_on_score,
            "vault_off_score": vault_off_score,
            "delta": vault_on_score - vault_off_score,
            "vault_on_answer": vault_on,
            "vault_off_answer": vault_off,
            "judge_reasoning": verdict.get("reasoning", ""),
        })

    judged = [x for x in per_case if x["judged"]]
    unjudged = [x for x in per_case if not x["judged"]]
    n = len(judged)

    by_category: dict[str, list[dict]] = {}
    for x in judged:
        by_category.setdefault(x["category"], []).append(x)
    category_delta = {
        cat: round(sum(x["delta"] for x in xs) / len(xs), 3) for cat, xs in sorted(by_category.items())
    }
    overall_delta = round(sum(x["delta"] for x in judged) / n, 3) if n else None
    regressions = [x for x in judged if x["delta"] < 0]

    summary = {
        "cases": len(per_case),
        "judged": n,
        "unjudged": len(unjudged),
        "overall_delta": overall_delta,
        "by_category": category_delta,
        "regressions": len(regressions),
    }

    if as_json:
        print(json.dumps({
            "summary": summary, "cases": judged, "unjudged": unjudged, "regressions": regressions,
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"\nBehavior eval - {len(per_case)} cases ({n} judged, {len(unjudged)} unjudged)")
    print("-" * 64)
    if overall_delta is None:
        print("  No cases were judged - nothing to report.")
    else:
        print(f"  overall delta (vault-on minus vault-off): {overall_delta:+.3f} "
              f"(scale 1-{JUDGE_SCALE})")
        for cat, d in category_delta.items():
            print(f"    {cat:<14} {d:+.3f}")
    print(
        "\n  Caveat: LLM-judged deltas on a small synthetic corpus are noisy. "
        "Read this as suggestive, not a benchmark claim."
    )

    if regressions:
        print(f"\nRegressions - vault-on scored WORSE than vault-off ({len(regressions)}, "
              f"never truncated):")
        for x in regressions:
            print(f"  [{x['category']}] delta {x['delta']:+.1f}  Q: {x['q'][:70]}")
            print(f"    vault-on ({x['vault_on_score']}): {x['vault_on_answer'][:120]}")
            print(f"    vault-off ({x['vault_off_score']}): {x['vault_off_answer'][:120]}")
    if unjudged:
        print(f"\nUnjudged ({len(unjudged)}) - answer generation or judging failed, excluded "
              f"from the delta:")
        for x in unjudged[:10]:
            print(f"  {x['reason']}: {x['q'][:70]}")
    print()
    return 0


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Behavior eval: does the vault make answers better, judged blind"
    )
    ap.add_argument("--generate", action="store_true",
                     help="Write behavior cases from the synthetic corpus instead of evaluating")
    ap.add_argument("--cases", type=Path, default=DEFAULT_CASES,
                     help=f"Cases JSONL path (default: {DEFAULT_CASES})")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of a text report")
    ap.add_argument("--force", action="store_true",
                     help="Allow --generate to overwrite an existing cases file")
    args = ap.parse_args()

    if args.generate:
        if args.cases.exists() and not args.force:
            print(
                f"Refusing to overwrite existing cases at {args.cases}: regenerating "
                f"mid-experiment breaks the before/after comparison on the SAME cases.\n"
                f"Pass --force to overwrite, or --cases <new-path> for a fresh set.",
                file=sys.stderr,
            )
            return 1
        return generate(args.cases)
    return evaluate(args.cases, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
