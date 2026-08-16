# The freshness policy

> Part of **OKM - Open Knowledge Metabolism**, an open spec for keeping AI-maintained knowledge folders true, by Eugeniu Ghelbur (theaioperator.io). MIT-licensed. Where OKF (Open Knowledge Format) standardizes how agent knowledge is written, OKM is a companion spec for keeping it true.

One rule, enforced by a lint: **every stored fact must be timeless, dated, or a pointer. Nothing may claim to be current without a stamp.**

This spec is storage-agnostic. It applies to any folder of markdown that an AI treats as a source of truth: a personal vault, a team's GitHub knowledge repo, an exported wiki. It does not care which viewer renders the files.

## Definitions

- **Slow fact** ("the wiring"): stable for roughly 7 days or longer. How a system is built, who owns what, what was decided and why. Slow facts are what this folder exists to store.
- **Fast fact** ("the meter"): can change within 7 days. Live counts, open tickets, balances, deal totals, statuses of in-flight work. Fast facts live in their home systems; the folder only points at them.

## The three legal forms of a fact

**1. Timeless.** No date needed because it does not decay.

```markdown
Deals live in the CRM. Invoices are issued monthly.
```

**2. Snapshot.** A dated observation. Snapshots never go stale because they claim what was true on a date, not what is true now. Anything inside a dated note (daily note, log entry, monthly tracker) or under a dated heading is automatically a snapshot.

```markdown
2026-07-13: pipeline at 13 open deals.
```

**3. Pointer.** For facts where current state matters, store where the truth lives, plus (optionally) the last observed value with a stamp.

```markdown
**Where truth lives:** [CRM pipeline board](https://crm.example.com/pipeline)
Last observed: 13 open deals (as of 2026-07-13)
```

## The one illegal form

A present-tense claim about a fast fact, with no date, outside a dated container:

```markdown
The pipeline has 13 open deals.        <- illegal: will silently rot
```

This is the sentence that becomes a lie next Tuesday while still reading as truth. It is the entire failure mode this policy exists to prevent.

## The stamp

`(as of YYYY-MM-DD)` or `(as of YYYY-MM)`, with a source when the fact came from outside: `(as of 2026-07-13, crm.example.com)`. Stamps are already required by [ai-first-rules.md](ai-first-rules.md) for external claims; this policy extends them to every fast fact, internal or external.

## Lint rules (what a checker enforces)

The reference checker is [scripts/freshness_lint.py](../scripts/freshness_lint.py): `python scripts/freshness_lint.py --path /any/markdown/folder [--json] [--strict]`. On a repo written under this policy it can gate CI; on a legacy vault it is an audit report to work down (heuristics favor precision, and FRESH-1 will still surface some prose that only reads like a claim).

- **FRESH-1 (error):** a quantitative present-tense claim about a volatile noun (counts, balances, totals, statuses) outside a dated container must carry an `as of` stamp or be rewritten as a pointer. A line that *quotes* the illegal form as an example - a policy doc, teaching material - carries `<!-- freshness: example -->` on that line: FRESH-1 is suppressed for that line only, invisible when rendered, greppable in source. FRESH-2 and FRESH-3 on the same line still fire - the directive says "this claim is quotation", not "skip this line". No block form: fences and blockquotes are the whole-region exemptions. Place the directive at the end of the line - a comment before a `#` stops markdown treating the line as a heading, which would break dated-heading detection.
- **FRESH-2 (warning):** a stamp older than the freshness window (default 7 days; configurable per folder) flags the line: refresh the observation or convert it to a pointer. Nothing is deleted; stale lines fade in search and surface in health reports.
- **FRESH-3 (error):** a pointer must have a resolvable target: a URL, or a typed id the folder's config maps to one (`linear:TICKET-123`, `crm:pipeline/main`).
- **FRESH-4 (exempt):** dated containers are immutable history. The lint never touches a snapshot.
- **FRESH-5 (warning):** a `freshness: example` directive that suppressed nothing is an unused suppression - remove it before it accumulates as cargo cult. Duplicate directives on one line warn the same way. The directive is recognized only where FRESH-1 could apply: backticked it is documentation, inside a code fence or `%%` comment it is invisible, in frontmatter or a FRESH-4 snapshot container it is inert - none of those suppress, and none warn.

## Frontmatter (optional, for tooling)

```yaml
freshness: wiring | snapshot | pointer   # declares the note's dominant form
freshness-window: 7d                     # overrides the default for this note
```

## The refresh loop (what maintenance actually is)

Detection is half the job. An aged stamp (FRESH-2 warning) needs one of three answers, and this loop IS the maintainer:

1. **Re-observe.** Check the home system, update the value and the stamp: `13 deals (as of 2026-07-12)` becomes `11 deals (as of 2026-08-02)`.
2. **Convert.** If nobody re-observes it, the value did not matter - keep only the pointer to where truth lives and drop the number.
3. **Retire.** If the claim is history worth keeping, move it into a dated note (or under a dated heading), where it becomes an immutable snapshot and stops asking for refreshes.

Run on a schedule (weekly fits the default 7-day window), this loop keeps a knowledge folder honest forever with minutes of work: the lint finds what aged, a human or an AI agent answers re-observe, convert, or retire per line, and nothing silently rots.

## Why this works

Slow facts compound: the more you store, the smarter the folder gets. Fast facts rot: every stored one is a future lie. The policy keeps the folder full of the first kind and honest about the second, and the lint makes that a property of the system instead of a habit of the writer.
