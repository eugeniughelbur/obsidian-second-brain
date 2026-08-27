# Tag taxonomy format

Opt-in (#221). If `<vault>/_meta/taxonomy.md` exists, `/obsidian-health` audits every note's `tags:` frontmatter against it and reports two kinds of drift. If the file does not exist, the audit is a no-op - zero findings, no error. An empty vocabulary must not block every tag or flag every tag; it must simply not run, which is why absence is the only trigger, not an empty file with no headings.

This is the taxonomy half of #221. The other half - rejecting tag syntax Obsidian silently mangles (digit-only tags, `.` or whitespace in a tag, disallowed characters) - is a write-time check in `hooks/validate-ai-first.sh` and `scripts/vault_health.py`, unrelated to this file.

## Why `_meta/`, not the wiki

`_meta/taxonomy.md` is config, not a note. It is read by `scripts/vault_health.py`, never by the AI-first pipeline, and none of [ai-first-rules.md](ai-first-rules.md) applies to it: no `## For future agent` preamble, no `ai-first: true`, no required wikilinks. Do not run `/obsidian-ingest` or `/obsidian-save` against it, and do not "enrich" it the way a captured idea gets enriched - it is a vocabulary list a human curates, not a note an agent writes.

## Format

One `##` heading per canonical tag, its synonyms as a bullet list underneath. The heading text IS the canonical tag, exactly as it should appear in a note's `tags:` frontmatter (lowercase, no leading `#`).

```markdown
# Tag Taxonomy

## docker
- containerization
- containers

## llm
- large-language-model
- large-language-models
```

Human-readable and trivially parseable: `scripts/vault_health.py::load_taxonomy` reads it with two regexes (one for `##` headings, one for `-` list items in the block below each heading) - no YAML, no nesting, no per-tag metadata. A canonical tag with no synonyms yet is still valid; give it a heading with an empty list under it (or no list at all) and it is recognized as canonical without anything to fold.

## What the audit reports

Given a taxonomy, every note's tags fall into one of three buckets:

- **Already canonical** - the tag matches a `##` heading verbatim. No finding.
- **A known synonym** (`tag_synonym`, warning) - the tag matches a bullet under some heading. The fix is unambiguous: rename it to that heading's tag. `/obsidian-health`'s taxonomy agent offers this per note, with confirmation - it never batch-rewrites frontmatter unattended.
- **Not in the taxonomy at all** (`tag_not_in_taxonomy`, info) - the tag matches neither a heading nor any bullet. This is informational, not an error: a vault's vocabulary grows, and a new tag is often legitimate before it is added to the file. Never auto-fixed; the taxonomy is a human-curated document, so the fix (if any) is adding a heading or a synonym line, not editing the note.

Matching is case-insensitive; tags and taxonomy entries are compared lowercased, matching this project's `tags:` convention (see `CLAUDE.md` Conventions).
