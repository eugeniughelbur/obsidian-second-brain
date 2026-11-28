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
The current numbers are in "Re-measured 2026-11-22" below; the first
table is the 2026-07 reference.

## Shipped default (`--mode default` - what the MCP serves)

| case set | recall@1 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| EN paraphrase | 0.371 | 0.629 | 0.771 | 0.476 |
| EN keyword | 0.733 | 0.933 | 1.000 | 0.820 |
| RU/ES paraphrase | 0.188 | 0.625 | 0.625 | 0.377 |

Re-measured 2026-07-18 on the same three case sets after a week of live vault
growth: **stable, no regression**. EN paraphrase and EN keyword byte-identical
(EN paraphrase MRR 0.474, within noise); RU/ES improved slightly (recall@1
0.250, MRR 0.408). The index tracks vault changes without drift.

Correction (2026-11-22): that re-measure ran on the semantic index built
2026-07-11, which was never rebuilt. On 2026-07-26 it still held 1,303 of
1,828 notes (see "O1 resolved" below), so the semantic arm kept seeing the
2026-07-11 vault. "Stable" came from the stale index, not from the vault. The
2026-07-26 sweep tables below repeat the 2026-07-11 EN paraphrase numbers, so
they most likely ran on the same stale index. A fresh index on the 2026-07-27
vault gives EN paraphrase recall@10 0.714, not 0.771.

## Re-measured 2026-11-22: the vault more than doubled

These are the current numbers. Same three case sets, same code defaults,
`--mode default`. The vault grew from 1,828 scanned notes (2026-07-26) to
4,254. The index covers 4,226 of them (99%). Every query used the semantic arm.

| case set | recall@1 | recall@5 | recall@10 | MRR | misses |
|---|---|---|---|---|---|
| EN paraphrase | 0.229 | 0.543 | 0.686 | 0.365 | 11 |
| EN keyword | 0.733 | 0.900 | 0.933 | 0.802 | 2 |
| RU/ES paraphrase | 0.250 | 0.562 | 0.562 | 0.359 | 7 |

Against July, EN paraphrase fell from 13 to 8 cases at rank 1, and from 8 to
11 misses. EN keyword went from 0 to 2 misses, RU/ES from 6 to 7.

Where the EN paraphrase drop comes from:

1. Not the code. The 2026-07-27 code (`3efeb1e`) on today's vault and
   index gives the same numbers.
2. New notes take rank 1. Hide the 2,419 notes dated after 2026-07-26
   (frontmatter date, else filename date) and recall@1 climbs back to 0.343
   (12 of 35), MRR to 0.432. The vault grew by 2,426 notes, so the dating is
   close. That recovers 4 of the 5 lost rank-1 cases.
3. The top-10 loss is vault growth too, and it began in July. `diagnose.py`
   sorts today's 11 misses as 8 pool, 3 ordering and 0 coverage.
   - A 2026-07-12 vault copy with a fresh index reproduces the July table
     exactly: recall@1 0.371, recall@10 0.771, MRR 0.476.
   - A 2026-07-27 copy gives recall@10 0.714 (25 of 35), with the July code
     and today's code alike.
   - Two cases sat at rank 9 on 2026-07-11 and left the top 10 by 2026-07-27.
   - A third slid from rank 3 to rank 6 to a miss as its answer note was
     edited and the vault grew.

What it means: ranking gets worse as the vault grows. New notes on the same
topics push the right note off rank 1, and push borderline cases out of the
top 10. Treat the 2026-07 tables above as history, and quote this table as
the current state.

Rebuild the semantic index before every re-measure. A stale index hides this
slide, as the 2026-07-18 correction above shows.

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
# rebuild the index first: a stale index hides vault growth (see the 2026-07-18 correction)
uv run python scripts/eval/semantic_search.py --path <vault> --build
# per mode x case set; --generate NEW sets only with --force or a new --cases path
uv run python scripts/eval/retrieval_eval.py --mode default --cases scripts/eval/retrieval_cases.jsonl --json
```

## No-answer cases (2026-11-22)

A case with `"gold": null` asks something the vault cannot answer. It passes
only if no result scores above a threshold, and it never counts toward recall
or MRR. The set has 5 hand-written cases in their own gitignored file,
`retrieval_cases_noanswer.jsonl`:

- 3 near misses that share topic words with real notes
- 2 topics that appear nowhere in the vault

Both thresholds follow one rule: a no-answer case must score lower than every
real question's top hit on the EN paraphrase set.

- **lexical, 9.8.** The #1 lexical score on the 35 real questions ran 9.82 to
  40.01 (median 19.41).
- **default, 0.48 cosine.** Each fused result is judged on its best-chunk
  cosine, which ran 0.489 to 0.720 (median 0.616).

The fused RRF score cannot carry a threshold. The #1 hit scored 0.328 to 0.350
on every real question, and 0.35 is the ceiling. It encodes rank, not
confidence.

| mode | passed | failed |
|---|---|---|
| lexical | 0 | 5 |
| default | 1 | 4 |

Search never says "not found". On each near miss it returns the note on the
right topic, and that note scores like a real answer. In lexical mode one near
miss outscored 32 of the 35 real questions.

The absent topics fared little better. They landed over the lexical line by
0.132 and 0.282, and the one default pass cleared its line by 0.005. Deciding
that an answer is missing falls to the agent reading the notes, not to search.

```bash
uv run python scripts/eval/retrieval_eval.py --mode default --cases scripts/eval/retrieval_cases_noanswer.jsonl --json
```

## Rejected: type weighting on the fused rank (2026-07-26)

Fix 13/24 rejected multiplicative type weights applied to raw cosine: log notes
were deleted outright and recall halved. It was scored on the two English case
sets, which did not yet include the multilingual one, so the same idea was worth
re-testing at a different layer against the set it had never seen.

Hypothesis: RU/ES misses are not ranking failures but the canonical note losing
to a longer log about the same topic. Inspecting all 6 misses supports that -
the query for a project note returns a dated research write-up about that same
project, a log. The lexical arm already applies a type weight, but a Russian or Spanish
query shares no terms with an English note, so that arm contributes nothing and
the fused rank is effectively pure cosine with no type awareness.

Applied `_SEARCH_ENTITY_BOOST` / `_SEARCH_LOG_WEIGHT` to the RRF score rather
than to cosine, on the reasoning that RRF is rank-based and bounded so the same
weight is a far gentler nudge.

Measured on all three sets. It is worse everywhere, including the target:

| case set | metric | before | after |
|---|---|---|---|
| EN paraphrase | MRR | 0.474 | 0.335 |
| EN paraphrase | recall@1 | 0.371 | 0.171 |
| EN keyword | recall@10 | 1.000 | 0.833 |
| EN keyword | misses | 0 | 5 |
| RU/ES | MRR | 0.440 | 0.249 |
| RU/ES | misses | 6 | 7 |

Reverted. The likely reason it fails at either layer: a large share of correct
answers ARE logs and dailies, so a flat 0.5 on that type costs more than the
entity boost recovers. Fix 13/24's conclusion holds at the fusion layer too.

**O1 remains open.** The diagnosis stands - r@5 and r@10 are both exactly 0.625,
so for 6 of 16 cases the gold note never enters the candidate pool and no
re-ranking can reach it. Whatever fixes it has to change what the retrieval
stage surfaces, not how the results are ordered.

## Swept and left alone: entity boost / log weight (2026-07-26)

O2 asked why 19 of 35 EN paraphrase cases are missed or buried below rank 3.
Inspecting them shows the opposite pattern to the multilingual set: here an
ENTITY note wins when the answer lives in a log or concept note. A query of the
shape "what fix resolved <issue> for <person>" returns that person's dossier
rather than the daily log recording the fix; "what process does <person>
recommend" returns the dossier rather than the concept note.

That points straight at `_SEARCH_ENTITY_BOOST` (1.5) and `_SEARCH_LOG_WEIGHT`
(0.5). Both are env-tunable, so the sweep needed no code change.

| entity / log | EN-para r@1 | r@5 | r@10 | MRR | misses |
|---|---|---|---|---|---|
| 1.5 / 0.5 (shipped) | 0.371 | 0.629 | 0.771 | 0.474 | 8 |
| 1.0 / 0.5 | 0.371 | 0.629 | 0.771 | 0.481 | 8 |
| 1.5 / 0.7 | 0.371 | 0.629 | 0.771 | 0.475 | 8 |
| 1.2 / 0.7 | 0.371 | 0.629 | 0.771 | 0.482 | 8 |
| 1.0 / 1.0 | 0.371 | 0.657 | 0.771 | 0.478 | 8 |
| 1.0 / 0.3 | 0.314 | 0.629 | 0.771 | 0.452 | 8 |

EN keyword and RU/ES were byte-identical across every setting tried.

**Defaults unchanged.** The best variant buys one extra case out of 35 on r@5
and 0.008 MRR. On a 35-case set that is noise, and moving a shipped default to
chase it is overfitting to this eval, not improving retrieval.

Two things the sweep did establish, which are worth more than the tuning would
have been:

1. **The type weights barely reach the fused result.** They apply to the lexical
   arm only, and in default mode the semantic arm dominates - which is also why
   the fusion-layer experiment above failed. Anyone reaching for these knobs to
   fix a default-mode ranking is pulling a lever that is mostly disconnected.

2. **The 8 misses are immovable by weighting.** The count is identical in all six
   configurations, so those cases are recall failures like O1's, not ranking
   failures. r@10 never moved either.

**O2 therefore reduces to the same open problem as O1**: the gold note is not in
the candidate pool, and nothing downstream of retrieval can put it there.

---

## O1 resolved: the multilingual gap is not a multilingual problem (2026-07-26)

O1 read the RU/ES set's `recall@5 == recall@10 == 0.625` as a cross-language
recall failure and called it the highest-value retrieval target. Measured
end-to-end, that diagnosis was wrong in three separate ways.

### The index was 29% stale, and that is a real bug the benchmark did not catch

The vault held 1,828 notes; the semantic index held 1,303. 524 of the 525
missing notes had been modified after the index was last written. Nothing warned
about it - the index never invalidates itself and the README said to build it
"once".

That matters more for non-English queries than the numbers here suggest. On this
case set every single hit came from the semantic arm; the lexical rank of the
target note was absent or in the hundreds. So an unindexed note is not "ranked
lower" for these queries, it is unretrievable. Search and `/obsidian-health` now
report coverage.

Rebuilding to 1,828/1,828 changed the score not at all - RU/ES `recall@10` stayed
0.625. Every target in this case set was already indexed, so the benchmark was
blind to a defect that costs real users whole notes. Worth remembering before
treating a flat score as evidence that nothing is wrong.

### The same three concepts fail in every language

The six misses are not six cases. They are three concepts, each asked once in
Russian and once in Spanish. If cross-language alignment were the problem, RU
and ES would fail on different concepts.

Asking the same three in English, translated faithfully:

| concept | RU rank | ES rank | EN rank |
|---|---|---|---|
| A | 198 | 171 | 176 |
| B | 54 | 27 | 22 |
| C | 153 | 12 | 38 |

English does not rescue any of them, and makes one materially worse. These notes
are hard to retrieve semantically in any language, and "RU/ES recall" was the
wrong frame - the set simply happens to contain three hard concepts, each
counted twice.

### No weighting can reach them, and here is the number that proves it

For each miss, how far below the rank-10 cutoff the target sits:

| case | target cosine | rank-10 cosine | lift needed | notes ranked above |
|---|---|---|---|---|
| 5  | 0.5059 | 0.5773 | 0.0714 | 197 |
| 6  | 0.5408 | 0.5802 | 0.0393 | 53 |
| 7  | 0.5535 | 0.5956 | 0.0421 | 152 |
| 13 | 0.4480 | 0.5055 | 0.0575 | 170 |
| 14 | 0.5567 | 0.5822 | 0.0255 | 26 |
| 15 | 0.5663 | 0.5753 | 0.0090 | 11 |

The whole rank-1-to-rank-10 band is 0.02 to 0.04 cosine wide. Four of these six
need a lift larger than that entire band. Any per-note weight big enough to fix
case 5 would reorder the top 10 of every other query in the vault. This is the
ceiling on the whole family of weighting fixes, and it is why five separate
attempts all failed:

1. Type weighting on raw cosine (fix 13/24) - recall halved.
2. Type weighting at the fusion layer - worse on all three sets.
3. Entity/log weight sweep, 6 configs - best bought 1 case of 35.
4. Chunk-scoring variants, 7 of them (mean, top-2 mean, 0.7max+0.3mean, and
   three chunk-count penalties) - no variant was Pareto-positive. The count
   penalties help EN paraphrase (`max/(1+0.05*ln k)`: r@10 0.743 -> 0.829) and
   hurt RU/ES (0.625 -> 0.562). `0.7max+0.3mean` and `top2 mean` each buy one
   RU/ES case and cost MRR everywhere.
5. Rocchio pseudo-relevance feedback, 9 configs of alpha x k - best (a=0.7,
   k=10) buys one RU/ES case at r@5 and one at r@10, costs one EN paraphrase
   case at r@5, and drops EN keyword MRR 0.825 -> 0.786.

Defaults left unchanged. Each of these is one or two cases on a 16-case set,
which is noise, and the honest reading of the table above is that the targets
are not near the cut in the first place.

### What the misses actually are

Inspected: in each case the target is the canonical note and the notes above it
are derivative material genuinely about the same subject - research write-ups on
the project, meeting notes on the topic, article collections by the person. For
at least one of the three, several notes ranked above the target are defensible
answers to the question as asked. Single-gold scoring cannot express that, so
part of this residual is the benchmark's shape rather than the retrieval's
quality. Adjusting gold sets to raise one's own score is not a fix, so the cases
are left as they are and the limitation is recorded here instead.

### Shipped instead

`scripts/eval/diagnose.py`, which classifies each miss as coverage (no vector),
pool (below fusion depth in both arms), or ordering (in the pool, ranked out),
and with `--gap` reports the cosine lift a fix would have to supply. The four
weighting experiments above were run against cases that no weight could move;
one run of this tool would have shown that first. Output carries rank numbers
only, so a run against a private vault is safe to share.
