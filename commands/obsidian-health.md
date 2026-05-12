---
description: Run a vault health check — grouped by severity, detects contradictions, concept gaps, stale claims, and structural issues
category: meta
---

Use the obsidian-second-brain skill. Execute `/obsidian-health`:

1. Read `_CLAUDE.md` first to find the vault path
2. Run: `python ~/.claude/skills/obsidian-second-brain/scripts/vault_health.py --path ~/path/to/vault --json`
   (replace vault path with the one from `_CLAUDE.md`)
3. Parse the JSON output and split findings into categories
4. Spawn parallel subagents to handle each category simultaneously:
   - **Links agent**: verify broken links, attempt to resolve them
   - **Duplicates agent**: confirm duplicates are truly the same concept, not just similar names
   - **Frontmatter agent**: identify notes missing required fields by type
   - **Staleness agent**: check overdue tasks and unfilled template syntax
   - **Orphans agent**: check orphaned notes and empty folders
   - **Contradictions agent**: scan Key Decisions sections and Knowledge/ notes for claims that conflict with each other or have been superseded by newer sources
   - **Concept gaps agent**: find terms mentioned 3+ times across different notes that lack a dedicated page — these are missing concepts the vault should have
   - **Stale claims agent**: compare Knowledge/ notes against their source dates — flag any note older than 6 months that references fast-moving topics (tools, APIs, pricing, team structure)
5. Merge results and group by severity:
   - 🔴 Critical: broken links, unfilled template syntax, contradictions between notes
   - 🟡 Warning: duplicates, stale tasks, missing frontmatter, stale claims, concept gaps
   - ⚪ Info: orphaned notes, empty folders
6. For safe fixes (missing frontmatter, obvious duplicates, creating pages for concept gaps), offer to fix automatically
7. For destructive fixes (archiving, merging, resolving contradictions), list them and ask for explicit confirmation first
8. Append to `log.md`: `## [YYYY-MM-DD] health | X critical, Y warnings, Z info`

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
