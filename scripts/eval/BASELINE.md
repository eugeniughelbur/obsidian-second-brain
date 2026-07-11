# Retrieval quality baseline

Reference numbers for the vault search stack, measured with the honest eval
harness (`retrieval_eval.py`, all four mode labels true since the 2026-07
stress-test fixes). Re-measure against these before shipping any retrieval
change: **no retrieval change ships without before/after numbers on the same
cases** (the rule since stress-test fix 10).

Case sets are generated per-vault and are gitignored (they contain vault
content). The three reference sets: 35 English paraphrase questions
(`--generate --style semantic`), 30 English keyword lookups
(`--generate --style keyword`), and 16 hand-written Russian/Spanish
paraphrases. Metrics below were measured on the maintainer's ~2,350-note vault,
2026-07-11, embedding model `bge-m3`, fusion weight 20.

## Shipped default (`--mode default` - what the MCP serves)

| case set | recall@1 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| EN paraphrase | 0.371 | 0.629 | 0.771 | 0.476 |
| EN keyword | 0.733 | 0.933 | 1.000 | 0.820 |
| RU/ES paraphrase | 0.188 | 0.625 | 0.625 | 0.377 |

## Phase B start vs end (default mode)

Start = first honest measurement after the ruler fix (mxbai-embed-large, flat
1:1 fusion, mean-pooled whole-note vectors, no dispatch/freshness):

| case set | metric | start | end | change |
|---|---|---|---|---|
| EN paraphrase | MRR | 0.207 | 0.476 | +130% |
| EN paraphrase | recall@10 | 0.429 | 0.771 | +80% |
| EN keyword | MRR | 0.621 | 0.820 | +32% |
| EN keyword | recall@10 | 0.767 | 1.000 | perfect |
| RU/ES | MRR | 0.094 | 0.377 | x4 |
| RU/ES | recall@5 | 0.125 | 0.625 | x5 |

## All modes, end state (context for tuning)

Pure semantic slightly leads the default on paraphrase MRR (0.481 vs 0.476);
the default keeps the lexical arm as a tiebreak and as coverage for notes
written since the last index build, plus single-token dispatch (exact lookups
stay lexical) and the freshness re-rank. `--mode hybrid` (flat 1:1) is now
strictly worse than semantic everywhere and exists as a lab reference only.

What produced the gains, in order of impact: multilingual embedding model
(bge-m3), per-chunk vectors with identity headers + best-chunk scoring,
semantic-weighted fusion (w=20, swept per model), single-token dispatch,
freshness re-rank + status fade, 100% index coverage via adaptive splitting.

## How to re-measure

```bash
# per mode x case set; --generate NEW sets only with --force or a new --cases path
uv run python scripts/eval/retrieval_eval.py --mode default --cases scripts/eval/retrieval_cases.jsonl --json
```
