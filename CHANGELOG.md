# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Command categorization (Phase 2):** each command in `commands/` now declares a `category:` (vault, thinking, research, meta). Non-Claude dispatcher tables in `AGENTS.md` / `GEMINI.md` are now emitted as four grouped sections instead of one 31-row blob. Adapters use the shared `emit_routing_table_grouped` helper in `adapters/lib.sh`, so the categorization carries through automatically when a new command is added. No breaking changes — Claude Code build is still a byte-exact identity copy.
- **Multi-platform adapter pattern (Phase 1):** one source, four platforms.
  - `scripts/build.sh` orchestrator + `scripts/lib.sh` utility helpers
  - `adapters/lib.sh` shared parsing, path rewriting, tool-name neutralization
  - `adapters/claude-code/adapter.sh` — identity copy (Claude Code is the canonical platform)
  - `adapters/codex-cli/adapter.sh` — emits `AGENTS.md` + `.codex/commands/`
  - `adapters/gemini-cli/adapter.sh` — emits `GEMINI.md` + `.gemini/commands/`
  - `adapters/opencode/adapter.sh` — emits `AGENTS.md` + `.opencode/commands/`
  - Auto-generated routing tables (parses each command's `description:` frontmatter)
  - Tool-name neutralization for non-Claude platforms (`Read tool` → `read files`, etc.)
  - Per-platform `exclude:` frontmatter field for opt-outs
  - Build output goes to `dist/<platform>/` (gitignored)
- `CODE_OF_CONDUCT.md` (Contributor Covenant v2.1)
- `CONTRIBUTING.md` with full contributor guide
- `CLAUDE.md` at repo root for contributor-facing operating instructions
- `CHANGELOG.md` (this file)
- `.github/` community files: issue templates, PR template, FUNDING.yml
- `CITATION.cff` for Google Scholar / Zenodo / OpenSSF
- `llms.txt` at repo root for AI crawlers (ChatGPT, Claude, Perplexity)
- FAQ section in README to boost AI-search citation rate
- GitHub Pages site with Cayman theme + jekyll-seo-tag + jekyll-sitemap
- Banner image and polished author hero in README
- `examples/sample-vault/` showing 6 AI-first compliant note types (daily, person, project, idea, devlog, plus `_CLAUDE.md` template)
- `SECURITY.md` — vulnerability reporting policy and coordinated disclosure timeline
- Schema.org JSON-LD `SoftwareApplication` block on the Pages site (`_includes/head_custom.html`) for rich-result eligibility and AI-search citation
- 3 new FAQ entries targeting "Obsidian plugin vs Claude Code skill" search intent

### Changed

- GitHub About description rewritten to lead with "Claude Code skill for Obsidian"
- README banner alt text now contains the full search-intent phrasing
- GitHub topics: swapped `markdown` and `pkm` for `obsidian-skill` and `claude-code-skill`

### Fixed

- `pyproject.toml` version was `0.1.0`, now matches the v0.6.0 release tag.

## [0.6.0] — 2026-04-26

### Added

- `references/ai-first-rules.md` — canonical spec for vault writes (the 7 rules, frontmatter schemas per note type, preamble templates, anti-patterns, audit checklist).

### Changed

- All 31 commands now explicitly reference the AI-first rule. Surgical cross-reference per command file, no body rewrites. Closes the gap where two Claude sessions on the same conversation could produce inconsistently structured notes.
- `references/write-rules.md` now points to `ai-first-rules.md` as the foundation.
- `SKILL.md` — new "AI-first vault rule" section under Core Operating Principles.

### Notes

- 29 files changed, +406 lines, 0 breaking changes. Additive only.

## [0.5.0] — 2026-04-26

### Added

- **Research Toolkit** — five new commands that turn the vault into a live research workspace.
  - `/x-read [url]` — verbatim X post + thread + TL;DR + key claims + reply sentiment (Grok-4 + x_search).
  - `/x-pulse [topic]` — what's hot on X, gaps, working hooks, post ideas (Grok-4.20-reasoning + x_search).
  - `/research [topic]` — web research dossier with citations, recency markers, contrarian views, open questions (Perplexity Sonar Pro).
  - `/research-deep [topic]` — vault-first: scans vault, identifies gaps, fills only those, synthesizes a delta report, propagates updates via `/obsidian-save` (Perplexity sonar-reasoning-pro + Grok + vault scan).
  - `/youtube [url]` — transcript + metadata + top comments, summarized AI-first (youtube-transcript-api + YouTube Data API v3 + Grok-4).
- Section 0 of `_CLAUDE.md` template — first version of the AI-first vault rule, applied to all 5 research commands from day one.
- API key handling at `~/.config/obsidian-second-brain/.env` (Mac-local, never synced).
- `pyproject.toml` + `uv.lock` for Python dependency management.
- Auto-open behavior: every research save pops Obsidian to the new note via `obsidian://open?...`.

### Notes

- Command count went 26 → 31. Same install, same `_CLAUDE.md`.
- Without API keys, the original 26 commands still work — research toolkit degrades gracefully.

[Unreleased]: https://github.com/eugeniughelbur/obsidian-second-brain/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/eugeniughelbur/obsidian-second-brain/releases/tag/v0.6.0
[0.5.0]: https://github.com/eugeniughelbur/obsidian-second-brain/releases/tag/v0.5.0
