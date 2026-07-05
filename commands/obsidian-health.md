---
description: Run a vault health check - grouped by severity, detects contradictions, concept gaps, stale claims, and structural issues
category: meta
triggers_en: ["vault health", "check vault", "audit vault", "vault diagnostics"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-health`:

1. Read `_CLAUDE.md` first to find the vault path
2. Run: `python scripts/vault_health.py --path ~/path/to/vault --json`
   (replace vault path with the one from `_CLAUDE.md`)
3. Parse the JSON output and split findings into categories
4. Spawn parallel subagents to handle each category simultaneously:
   - **Wanted-notes agent**: the script reports `wanted_note` items - links to a note that does not exist yet. These are NOT errors: in a wiki-style vault you link a thing the moment you mention it, so wanted notes are a demand-ranked wishlist of pages worth writing, not breakage. Triage them with `python scripts/triage_links.py --path <vault> --limit N`, which sorts each into keep (a deliberate seed, leave it), create (referenced enough to deserve a real note now), or delete (junk or a typo - fix the link). Report-only by default; needs `ANTHROPIC_API_KEY`. Headless on purpose: it can run unattended or on a schedule. The goal is to triage the backlog, never to drive the count to zero.
   - **Duplicates agent**: confirm duplicates are truly the same concept, not just similar names
   - **Frontmatter agent**: identify notes missing required fields by type. If the script reports a `code_fence_wrapped` note (frontmatter trapped inside a leading ```` ```markdown ```` fence), the fix is to **unwrap it** - strip the opening fence line and the matching closing ```` ``` ```` so the inner `---` frontmatter and body become real markdown. **Never add a new frontmatter block to a wrapped note** - that produces duplicate frontmatter and leaves the body trapped. If the note already has both a prepended frontmatter block and an inner wrapped one, merge them (keep the richer fields) and unwrap.
   - **Staleness agent**: check overdue tasks and unfilled template syntax
   - **Orphans agent**: check orphaned notes and empty folders
   - **Contradictions agent**: scan Key Decisions sections and reference/concept notes (the concept or knowledge folder per `references/folder-map.md` - wiki-style `wiki/concepts/`, Obsidian-style `Knowledge/`) for claims that conflict with each other or have been superseded by newer sources
   - **Concept gaps agent**: find terms mentioned 3+ times across different notes that lack a dedicated page - these are missing concepts the vault should have
   - **Stale claims agent**: compare reference/concept notes (the concept or knowledge folder per `references/folder-map.md` - wiki-style `wiki/concepts/`, Obsidian-style `Knowledge/`) against their source dates - flag any note older than 6 months that references fast-moving topics (tools, APIs, pricing, team structure)
5. Merge results and group by severity:
   - 🔴 Critical: unfilled template syntax, contradictions between notes, code-fence-wrapped notes (frontmatter trapped in a fence)
   - 🟡 Warning: duplicates, stale tasks, missing frontmatter, stale claims, concept gaps
   - ⚪ Info: wanted notes (linked but unwritten - a wishlist, not errors), orphaned notes, empty folders
6. For safe fixes (missing frontmatter, unwrapping code-fence-wrapped notes, obvious duplicates, creating pages for concept gaps), offer to fix automatically. For a `code_fence_wrapped` note, unwrap the fence rather than adding frontmatter (see the Frontmatter agent note above).
7. For destructive fixes (archiving, merging, resolving contradictions), list them and ask for explicit confirmation first
8. Append to the operation log: if `Logs/` exists write `**HH:MM** - health | X critical, Y warnings, Z info` to `Logs/YYYY-MM-DD.md`; otherwise append `## [YYYY-MM-DD] health | X critical, Y warnings, Z info` to `log.md`

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.
