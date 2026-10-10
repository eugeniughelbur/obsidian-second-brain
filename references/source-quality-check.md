# Source quality check

The single reference for `source_quality` (#258). Capture-family commands point here instead of carrying their own copy of the signals.

## What the field says

`source_quality: high | medium | speculation` on a `type: source` note says how much **provenance** capture saw, so that a later step can decide how far to trust the note. It is not a verdict on whether the claims are true, and it is not about retention - that is `capture_scope` (#194). A fully retained SEO listicle is `full-local` and `speculation`; a `url-only` link to a named author's article is `url-only` and `medium`.

`raw/` stays cheap and unfiltered. Capture never blocks and never asks. The field is a label the compile step reads, never a gate on the capture itself.

## Deterministic rule

Judge only from what capture already holds: the frontmatter and a short labelled preamble at the top of the body. No network call, no search, no model judgement. A reviewer must be able to check a label by reading the note.

**`speculation`** - the floor, not an error. Use it when any of these holds:

- the source is **derived**: a summary of a summary, an AI answer, a conversation export, a course recap, with no usable chain back to what it summarises;
- there is **no usable locator** and no labelled provenance: no valid `source_url` and nothing in the preamble that names where it came from;
- provenance **conflicts**: frontmatter points at one thing and the preamble says it is something else (a repository URL on a note that declares itself an agent report), or two declared locators or owners disagree;
- the capture is **empty**.

An uninvestigated source with no provenance signal is `speculation`. That is the honest default.

**`medium`** - provenance is traceable from signals already fetched. Any one of these, with none of the conflicts above:

- a valid `http(s)` `source_url` (a trailing annotation such as `(video)` is part of the locator, not a defect);
- a repository URL on a known forge, with an owner and a repo name;
- a labelled `Source:` line in the first lines of the body that carries a valid URL;
- a local handoff record written inside this vault, which names its own time and agent context but is not a direct decision or event record (see `high`).

The rule asks for a **traceable locator**. An author, channel or publication date with no locator does not reach `medium` on its own: a named author on a pasted summary says nothing about where the text came from. A URL that merely appears in the article body is a citation, not the locator of this note, and does not count.

**`high`** - deliberately out of reach for ordinary captures. Only these:

- an institutional primary document (standard, policy, regulation, official documentation) with an explicit owner and either a stable URL or a version/identifier;
- a local primary record (meeting notes, decision record, event log) with an author or participants, a valid date, a context, and a directly recorded decision, event, statement or action.

`high` is never reached by a check that did not run. A claim-level or corroboration check is a separate, opt-in step.

## Red flag

When the result is `speculation` because of a clear red flag (no byline and no citations on an article claiming facts, a single-commit repository with no README or license, a clickbait video making causal claims with nothing in its description), add one line to the command output. Do not touch the note body, which stays verbatim, and do not ask "capture anyway?". In an unattended vault the answer is always yes, and the label on the note is what protects the compile step.

## Policy

`.vault-config.json`:

```json
{ "source_quality_policy": "silent" }
```

`warn` (default) or `silent`. A missing file, a missing key, a malformed file, a non-string or any other value all mean `warn`. The policy only controls the `/obsidian-health` warning; it never changes what capture writes. There is deliberately no value that refuses a capture.

## Consumers

- `/obsidian-health` (`scripts/vault_health.py`, `Source quality`): a warning for any knowledge note whose every cited source is `speculation`. Daily, log, index and other activity notes are skipped. A source with no `source_quality` is unjudged, not speculative, so a vault written before the field stays silent.
- Later, separately: `/obsidian-ingest` step 6 and `/obsidian-synthesize` treating a `speculation` source as a proposal rather than a direct rewrite of an existing page.

## Optional: lateral read

When the read is ambiguous, an agent may offer a bounded lateral-reading check (Caulfield's SIFT: stop, investigate the source, find better coverage, trace to the original; one or two searches). It runs only on an explicit yes, and the best moment to offer it is when a `speculation` source is about to rewrite existing notes, not at capture. If it ran, the grade may be raised.
