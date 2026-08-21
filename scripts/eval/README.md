# Retrieval-quality eval harness

Measures how well the vault's search actually finds the right note for a
natural-language question - **before** anyone reaches for a vector index or a
bigger model. It reuses the real `search()` from the MCP connector
(`integrations/obsidian-mcp-server/vault_ops.py`), so it scores the exact
term-frequency, title-weighted ranking the skill ships with today.

**Want reproducible numbers rather than numbers about one private vault?** See [BENCHMARK.md](BENCHMARK.md). `corpus.py` generates a deterministic 300-note synthetic vault plus three gold query sets, so anyone can run the same measurement and compare. The case files below are gitignored because they contain real notes; the benchmark corpus contains none.

## Why

"Retrieval quality" was the top research theme from the skill audit: `/find` and
the MCP search float high-mention notes (and even `raw/` transcripts) above the
canonical note, and there was no way to *measure* it. You cannot improve what you
do not measure. This harness gives a number and a list of concrete failures.

## Use

```bash
# 1. Bootstrap an eval set FROM your vault (one-time, re-runnable).
#    Samples notes; for each, an LLM writes a question whose answer is in that
#    note, deliberately avoiding the note's title words. Gold = that note.
uv run python scripts/eval/retrieval_eval.py --generate 30

# 2. Score the current search against the cases.
uv run python scripts/eval/retrieval_eval.py

# JSON for piping / tracking over time:
uv run python scripts/eval/retrieval_eval.py --json
```

`OBSIDIAN_VAULT_PATH` must be set (it is, in `~/.config/obsidian-second-brain/.env`).
`XAI_API_KEY` is optional - with it, questions are LLM-generated (realistic
paraphrases); without it, a key-free heuristic generator is used (weaker, but
runs offline).

## Output

- **recall@1/3/5/10** - fraction of questions where the right note appears in the
  top K results.
- **MRR** - mean reciprocal rank of the right note (1.0 = always #1).
- **Misses** - the right note never surfaced; shows which note ranked #1 instead.
- **Buried** - the right note ranked below #3 (usually because a noisy
  high-mention note or a `raw/` transcript outscored the canonical note).

The generated cases (`retrieval_cases.jsonl`) contain your private note paths and
are gitignored. Only `retrieval_cases.example.jsonl` (the format) is committed.

## What it is not

This scores ranking, not answer quality. A low score is the signal to improve
retrieval (skip `raw/` in search, weight canonical `type:` notes, add semantic
matching) - and then re-run to confirm the change actually helped, on the same
cases, instead of guessing.

## Behavior eval (separate from retrieval - answer quality, not ranking)

`behavior_eval.py` is a second, complementary harness - it does not replace
the retrieval eval above, and it is not part of the reproducible retrieval
benchmark in [BENCHMARK.md](BENCHMARK.md). It asks whether having the vault
actually makes an *answer* better, not whether search ranks the right note
highly.

For each question in a behavior case set (sampled deterministically from
`corpus.py`'s synthetic corpus, so it needs no private data), it generates
two answers with `research.lib.grok` - one with vault retrieval available,
one from the model alone - then grades both with a **different** model,
`research.lib.gpt`, blind to which condition produced which answer, against
the question's known canonical fact (`answer_key`). The judge is deliberately
never the same model that wrote the answers: a model grading its own output
risks self-preference bias inflating the vault-on score, so a startup check
refuses to run if the two resolve to the same provider+model. It reports the
overall delta (vault-on score minus vault-off score), a breakdown by question
category (fact, decision, relationship, cross-note synthesis,
contradiction), and a complete, never-truncated list of cases where the
vault-on answer scored *worse*.

```bash
uv run python scripts/eval/corpus.py --out /tmp/bench-vault
OBSIDIAN_VAULT_PATH=/tmp/bench-vault uv run python scripts/eval/behavior_eval.py \
    --generate 20
OBSIDIAN_VAULT_PATH=/tmp/bench-vault uv run python scripts/eval/behavior_eval.py \
    --cases scripts/eval/behavior_cases.jsonl

# Override either model (both must still resolve to distinct providers/models):
uv run python scripts/eval/behavior_eval.py --answer-model grok-4.5 --judge-model gpt-4o-mini
```

Requires **both** `XAI_API_KEY` (answers) and `OPENAI_API_KEY` (judging) -
unlike the retrieval eval's question generator, there is no key-free
fallback, since both answering and judging are LLM calls. `--generate` alone
needs neither key; it only samples from the synthetic corpus.

**Delta** is the judge's score for the vault-on answer minus its score for
the vault-off answer on the same question, averaged across cases (or within
a category). Positive means the vault helped on average; zero or negative is
a valid result, not a failure of the harness. **Regressions** are the subset
of cases where the vault-on answer scored strictly lower than vault-off -
where having the vault made the answer worse, e.g. by retrieving a
noisy or superseded note instead of the reconciling one.

LLM-judged evals on a small synthetic corpus are inherently noisy signal, not
a scientific measurement - treat any single run's delta as suggestive. No
numbers from this harness are promoted into `BASELINE.md` or `BENCHMARK.md`;
those stay retrieval-only.
