# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""Why a retrieval case missed: coverage, pool, or ordering.

`retrieval_eval.py` answers "how good is search" with recall and MRR. It cannot
answer "why did THIS case fail", and those failures have three unrelated causes
that need three unrelated fixes:

  coverage  the note has no vector at all, so the semantic arm cannot see it.
            No amount of tuning helps; the index needs rebuilding.
  pool      the note is ranked below the fusion depth in both arms, so it is
            never a candidate. Re-ranking cannot reach it.
  ordering  the note is in the pool but placed below the cut. This is the only
            category any weighting or fusion change can fix.

Guessing wrong here costs days. During the O1 investigation four separate
reweighting experiments were run against cases that turned out to be unreachable
by reweighting at all, because the note's cosine sat further below the rank-10
cutoff than the entire rank-1-to-rank-10 spread was wide. `--gap` reports that
distance, which is the number that decides whether a nudge could ever work.

Usage:
    uv run python scripts/eval/diagnose.py --path "<vault>" --cases <file.jsonl>
    uv run python scripts/eval/diagnose.py --path "<vault>" --cases <f> --gap

Prints rank numbers only. Note paths appear solely under --show-paths, which is
off by default so the output of a run against a private vault is safe to paste.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "integrations" / "obsidian-mcp-server"))

import vault_ops as ops  # noqa: E402


def _rank(order, gold) -> int:
    """1-based rank of the first gold path, or 0 when absent."""
    g = {x.strip() for x in gold}
    for i, p in enumerate(order, 1):
        if p in g:
            return i
    return 0


def _semantic_order(qunit, notes):
    return sorted(
        ((rel, max(ops._dot(qunit, v) for v in units)) for rel, units in notes),
        key=lambda t: t[1], reverse=True,
    )


def diagnose(vault: Path, cases_path: Path, gap: bool, show_paths: bool) -> int:
    index_path = vault / ops._SEMANTIC_INDEX_FILE
    if not index_path.exists():
        print(f"No semantic index at {index_path}. Build one first:\n"
              f'  uv run python scripts/eval/semantic_search.py --path "{vault}" --build',
              file=sys.stderr)
        return 1
    index = ops._load_index_cached(index_path)
    notes = index.get("notes") or {}
    vectored = [(rel, n["_unit"]) for rel, n in notes.items() if n.get("_unit")]
    if not vectored:
        print("The index holds no vectors.", file=sys.stderr)
        return 1

    cov = ops.index_coverage(vault)
    print(f"index covers {cov['indexed']} of {cov['scanned']} notes "
          f"({100 - cov['pct_missing']:.0f}%)   fuse depth {ops._FUSE_DEPTH}")
    if cov["pct_missing"] >= 5.0:
        print("  the index is behind the vault; rebuild before trusting any of this")
    print()

    cases = [json.loads(x) for x in
             cases_path.read_text(encoding="utf-8").splitlines() if x.strip()]

    head = f"{'case':>4} {'sem':>6} {'fused':>6} {'verdict':<12}"
    if gap:
        head += f" {'gold cos':>9} {'cos@10':>8} {'lift needed':>12} {'above':>6}"
    print(head)
    print("-" * len(head))

    tally: dict[str, int] = {}
    for i, c in enumerate(cases, 1):
        gold = c.get("gold", [])
        indexed = any(g.strip() in notes for g in gold)
        vec = ops._embed_query(c["q"], model=index.get("model"))
        qunit = ops._unit(vec) if vec else None
        if qunit is None:
            print(f"{i:>4}  embedding backend unavailable")
            return 1

        order = _semantic_order(qunit, vectored)
        sr = _rank([r for r, _ in order], gold)
        fr = _rank([r["path"] for r in ops.search(c["q"], limit=10)], gold)

        if not indexed:
            v = "coverage"
        elif fr and fr <= 10:
            v = "hit"
        elif sr and sr <= ops._FUSE_DEPTH:
            v = "ordering"
        else:
            v = "pool"
        tally[v] = tally.get(v, 0) + 1

        line = f"{i:>4} {sr or '-':>6} {fr or '-':>6} {v:<12}"
        if gap and v != "hit" and indexed:
            by = dict(order)
            gc = max((by[g.strip()] for g in gold if g.strip() in by), default=0.0)
            cut = order[9][1] if len(order) > 9 else order[-1][1]
            line += (f" {gc:>9.4f} {cut:>8.4f} {cut - gc:>12.4f} "
                     f"{sum(1 for _, s in order if s > gc):>6}")
        if show_paths and gold:
            line += f"   {gold[0]}"
        print(line)

    print("-" * len(head))
    for k in ("hit", "ordering", "pool", "coverage"):
        if k in tally:
            print(f"  {tally[k]:>3}  {k}")
    if gap:
        band = order[0][1] - (order[9][1] if len(order) > 9 else order[-1][1])
        print(f"\nRank 1 to rank 10 spans {band:.4f} cosine on the last case. A lift "
              f"larger than that\nreorders the whole result set, so treat it as the "
              f"ceiling on any per-note weight.")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--path", required=True, help="Vault root")
    ap.add_argument("--cases", required=True, help="Cases JSONL (as used by retrieval_eval.py)")
    ap.add_argument("--gap", action="store_true",
                    help="Also show how far below the rank-10 cutoff each missed note sits")
    ap.add_argument("--show-paths", action="store_true",
                    help="Include gold note paths (off by default so output is shareable)")
    args = ap.parse_args(argv[1:])

    cases_path = Path(args.cases)
    if not cases_path.exists():
        print(f"No cases file at {cases_path}", file=sys.stderr)
        return 1
    return diagnose(Path(args.path).expanduser(), cases_path, args.gap, args.show_paths)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
