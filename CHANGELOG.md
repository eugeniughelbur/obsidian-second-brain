# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Codex executable invocation path.** `scripts/run-command.sh` wraps any command's markdown into a `codex exec` prompt so the (otherwise inert) command files actually run on Codex CLI, and `scripts/install-codex-wrappers.sh` installs one PATH shim per command into `~/.codex/bin/`. A `--print` mode prints the assembled prompt without running, for preview/testing. Fixes two bugs from the source fork (a self-referential vault default and an `eval echo` tilde-expansion that mis-parses paths with apostrophes). (FORK_INSIGHTS.md #42; from the Codex-runner fork)
- **`scripts/mine_commit_decisions.py`** surfaces decision-shaped commits (switch to / replace / adopt / rename / migrate, etc.) from a git history as ADR candidates, so directional decisions made in code but never recorded can be written up via `/obsidian-adr` (which now references it). Conservative matcher (low false positives); read-only. (FORK_INSIGHTS.md #22)
- **Four more commands.** `/obsidian-calendar` (Claude Code only) reconciles the vault against your calendar and flags commitments implied by notes that are not scheduled - flag only, never writes events (the inverse of `/obsidian-daily`'s calendar pull). `/vault-deep-synthesis [topic]` cross-references every note on a topic into agreements / contradictions / stale claims / coverage gaps (pure vault; topic-driven, distinct from the unprompted `/obsidian-synthesize`). `/idea-discovery` ranks 3-5 next-direction candidates from ungraduated ideas, open project questions, and orphan research. `/obsidian-panel` convenes a panel of distinct lenses on a decision (uses an optional `Advisors/` folder, else four generic lenses), a multi-persona complement to `/obsidian-challenge`. The three thinking commands reuse the existing `type: synthesis` schema. (FORK_INSIGHTS.md #11-14.)
- **CI gate for substitution characters.** `scripts/sweep_non_ascii.py` gained a `--check` mode that exits non-zero when a banned substitution character (em-dash, en-dash, curly quotes, Unicode math, ellipsis, non-breaking space) appears in prose in any tracked `.md`/`.py`/`.sh` file. Characters inside code fences and inline backtick spans are preserved and never fail the check. Wired into `.github/workflows/ci.yml` so the rule is enforced on every push and PR (complements the write-time `validate-ai-first.sh` hook, which only covers vault notes). Two new smoke tests lock the behavior. (FORK_INSIGHTS.md #49; pattern from the calendar/workflow fork, generalized to the full banned-character set.)

## [0.9.0] - 2026-05-31

### Changed

- **Background agent (PostCompact hook) is now opt-in and ships inert.** It writes to the vault unattended with `--dangerously-skip-permissions`, but previously armed on `OBSIDIAN_VAULT_PATH` alone (which `setup.sh` sets for the research toolkit), so a normal install left it firing on every compaction. It now also requires a second deliberate flag, `OBSIDIAN_BG_AGENT_ENABLED=1`, which `setup.sh` never sets - so it stays inert until the user enables it, and clearing the flag is enough to disable it again. `setup.sh` now reports the hook as "registered (inert by default)" with enable instructions. (FORK_INSIGHTS.md #32)
- **Non-ASCII substitution sweep across all tracked `.md`, `.py`, `.sh` files:** automated conversion of em-dashes, en-dashes, curly/smart quotes, Unicode math substitutions, ellipsis, and non-breaking spaces to ASCII equivalents. Code fences and inline backtick spans preserved verbatim. `hooks/validate-ai-first.sh` and `scripts/sweep_non_ascii.py` exempted (intentional banned chars in detection logic). `README.md` handled separately with a manual pass. All 78 affected files now pass `validate-ai-first.sh` check 5.

### Added

- **`/obsidian-recurring` - track a recurring obligation with a cadence and a computed next-due date.** Builds a `type: recurring-task` note (What / Cadence / Blockers / History), adds a board card for the next occurrence, and advances `next-due` on each completion. Fills the gap that `/obsidian-task` (one-shot) leaves. Adds the `recurring-task` schema to `references/ai-first-rules.md`. (FORK_INSIGHTS.md #15; from the calendar/workflow fork. The other workflow commands in that fork - proposal, event, 1on1, launch-block - were intentionally left to domain forks per ECOSYSTEM.md rather than added upstream.)
- **Google Calendar commands: `/obsidian-agenda`, `/obsidian-schedule`, `/obsidian-meeting`.** Claude Code only (they use the claude.ai Google Calendar MCP connector, so they are excluded from the Codex/Gemini/OpenCode builds). `/obsidian-agenda` writes a re-derivable `agenda-snapshot` note for a range (today/tomorrow/week/next-week/date/range) with conflict, back-to-back, focus-block, and external-organizer detection, cross-linking attendees to person notes. `/obsidian-schedule` creates or reschedules events from a task or standalone, resolving attendee emails from person notes (never guessing) and writing the event id/url back to the task. `/obsidian-meeting` generates a `meeting` note from an event with empty Notes/Decisions/Action-items sections (never fabricated). Adds `agenda-snapshot` and `meeting` schemas to `references/ai-first-rules.md`. (FORK_INSIGHTS.md #8-11; from the calendar/workflow fork)
- **Free (key-less) mode for `/research` and `/research-deep`.** Both commands now work with no API keys. Mode is auto-selected: when `PERPLEXITY_API_KEY` is set they use Perplexity/Grok exactly as before; when it is not (or `--free` is passed) they aggregate free, key-less sources in parallel - Wikipedia, HackerNews, arXiv, Reddit, Lobsters, dev.to, OpenAlex, Semantic Scholar, CrossRef, DuckDuckGo (SearXNG fallback) - and emit JSON that the calling Claude synthesizes into the same AI-first dossier. `--academic` restricts free mode to scholarly sources. New `scripts/research/lib/` layer: 11 source clients, a parallel aggregator (30s timeout, "success" at >= 3 sources, never crashes on a per-source failure), a 24h-TTL cache, a shared polite-UA session, and an env-based `source_config` deliberately decoupled from the vault path so the sources import with no vault and no keys. Previously these commands hard-errored without a Perplexity key - the main adoption barrier. 6 new no-network unit tests; CI installs `requests`. (FORK_INSIGHTS.md #1-6; from the research-toolkit fork)
- **Anti-fabrication and search-completeness guards.** Adds a non-negotiable hard-rules section to `references/ai-first-rules.md` covering three failure modes: false absence (never claim a note/person/file is absent without an exhaustive search - the single most common observed failure), search completeness (enumerate exhaustively, do not sample), and no fabrication (never invent facts/entities/dates; mark unknowns `TBD`; an empty section is correct when nothing was said). Echoed in the SKILL.md operating principles and `references/write-rules.md`, plus a per-command **Anti-fabrication** footer on the 33 commands that write vault notes (`create-command` excepted - it writes command files, not notes). Fills a real gap: the repo had an AI-first write spec but no hallucination guard. (FORK_INSIGHTS.md #26-28; from the pillar-vault fork)
- **First automated tests + CI.** `tests/test_smoke.py` adds two stdlib-only smoke tests (the codex-cli adapter build emits `AGENTS.md` plus command bodies; `vault_health.py --json` reports a clean two-note linked vault) and `.github/workflows/ci.yml` runs them on every push to `main` and every PR. Adds a pytest `dev` dependency group to `pyproject.toml`. Closes the long-standing "no automated test suite yet" gap. (FORK_INSIGHTS.md #47, #48; pattern from the tests fork)
- **`hooks/obsidian-bg-agent.hook.yaml` and `hooks/postcompact.hook.example.json`:** the background agent now ships with an `enabled: false` hook declaration and a paste-in settings template documenting the opt-in steps. (FORK_INSIGHTS.md #33)
- **`references/DELTAS.template.md`:** a fork-customization template. Forkers copy it to `DELTAS.md` at their fork root to record local deviations in one place that upstream never touches, so `git merge upstream/main` stays conflict-free. Pointer added to the README fork section. (FORK_INSIGHTS.md #50; pattern from the DELTAS fork)
- **Non-ASCII substitution character check in `validate-ai-first.sh` (check 5):** the hook now detects banned Unicode that slips in silently via LLM defaults: em-dashes (`—`), en-dashes (`–`), curly/smart quotes, Unicode math substitutions (`≥ ≤ ≠`), ellipsis (`…`), and non-breaking spaces. Each violation reports the exact codepoint, line number, and a suggested ASCII replacement. Whitelist covers box-drawing chars (U+2500-257F), arrows (`→ ←`), currency symbols (`€ £ ¥`), private-use / Nerd Font codepoints, and emoji - all carry semantic meaning rather than substituting for ASCII. Specific em-dash ban was unenforceable in practice; the broader codepoint-level check catches the full substitution-Unicode class. Rule documented in `CLAUDE.md` conventions and `references/ai-first-rules.md` anti-patterns table.

### Documentation

- **`claude -p` slash-command-expansion gotcha documented in `SKILL.md`.** Custom slash commands do not expand in non-interactive mode, so a cron/launchd job running `claude -p "/obsidian-daily"` sends the literal text and does nothing. Documents the reliable headless pattern (point Claude at the command file and tell it to carry out the steps) plus the launchd `PATH` caveat. (FORK_INSIGHTS.md #34)
- **Per-project vault setup documented** (closes question in Discussion #11): added a "Per-Project Vaults (multi-repo workflows)" section to `SKILL.md` and a matching FAQ entry in `README.md`. Recipe: drop `{"env": {"OBSIDIAN_VAULT_PATH": "..."}}` into each repo's `.claude/settings.json`; Claude Code's per-project settings merge over the global one and every hook reads `OBSIDIAN_VAULT_PATH` from env at fire-time, so each project session routes to its own vault. The pattern always worked; nobody had written down the recipe.

### Fixed

- **Dead calendar tool reference in `/obsidian-daily`.** The calendar pull referenced a bare `google_calendar_list_events`, which can never match a tool (MCP tools are namespaced `mcp__<server>__<name>`), so the `## Calendar` section was effectively never populated. Now points at the real claude.ai Google Calendar connector tools (`list_calendars` + `list_events`), resolves the primary calendar first, and keeps a fallback note for users whose calendar MCP namespaces differently. (FORK_INSIGHTS.md #7; bug surfaced by the calendar/workflow fork)
- **Removed remaining `--style obsidian` example from `SKILL.md`.** Issue #15 dropped the unimplemented `--style` example from the README but left the matching one in `SKILL.md`; this finishes that cleanup so the docs no longer advertise a flag `bootstrap_vault.py` does not accept.
- **`bootstrap_vault.py` templates now AI-first compliant (#16):** all 17 templates emitted by the bootstrapper (`Daily Note`, `Project`, `Person`, `Task`, `Dev Log`, `Goal`, `Mention`, `Meeting`, `Decision`, `OKR`, `Architecture`, `Debug`, `Post`, `Audience Note`, `Source`, `Literature Note`, `Hypothesis`) now include `type:` and `ai-first: true` in frontmatter plus a `## For future Claude` preamble in the body. Notes created from these templates now pass `hooks/validate-ai-first.sh` cleanly. Previously every Write/Edit on a templated note warned, undermining the AI-first rule the skill is built around. `Templates/Source.md` renamed its existing `type:` field to `source_kind:` to free up `type:` for the ai-first frontmatter (the field was for book/paper/podcast/video, never the note's ai-first type). Added a `references/ai-first-rules.md` reference block to the top of `bootstrap_vault.py` so future contributors see the rule.
- **Removed broken `--style obsidian` example from README (#15):** the `scripts/bootstrap_vault.py --style obsidian` example in the Vault Architecture section advertised a flag that was never implemented. PR #14 wired `--preset` and `--mode` but not `--style`. Dropped the stale example per the issue's recommended Option B. If a `--style` flag ships later it gets re-added then.
- **README command count refreshed to 34:** banner alt text, tagline, anchor, and `## 34 Commands` heading now match the actual file count after PR #7 landed `/podcast`.
- **`install.sh` cross-platform editor and uv-install hint:** the `${EDITOR:-open}` fallback was macOS-only - on Linux it threw `open: command not found`, on Windows (Git Bash) likewise. Now picks `xdg-open` on Linux, `notepad` on Windows (MSYS/MINGW/Cygwin), `open` on macOS. The "uv not found" hint also branches per platform: `brew install uv` on macOS, `curl … | sh` on Linux, the PowerShell one-liner on Windows. Matches the same pattern PR #34 applied to `scripts/research/lib/vault.py`.

### Added

- **`/podcast [url]` - new research-toolkit command.** Accepts Apple Podcasts URLs (resolved to RSS via the free iTunes Lookup API, no key) or RSS feed URLs directly. Transcript priority: `<podcast:transcript>` tag in the RSS feed (free, high fidelity) → Whisper API if `OPENAI_API_KEY` is set (~$0.006/min) → show-notes fallback. Summarizes via Grok and saves an AI-first note to `Research/Podcasts/`. Adds `type: podcast` schema to `references/ai-first-rules.md`. Spotify URLs are rejected with a clear message (DRM blocks audio + transcript access). Wikilinks mandated for show/host/guests; all diagnostic output routed to stderr so it never contaminates the Grok prompt or vault note body.
- **Centrality ranking in `/obsidian-visualize`:** the text summary now surfaces hub nodes (degree at least 3x the median or top 1% of the vault), bridge nodes ranked by approximate betweenness, stale-orphan flagging (>30 days old), silo clusters (<3 cross-cluster edges), and a centrality-skew warning when one node holds >25% of total edges. Turns the canvas into a structural diagnostic of the vault, not just a picture.
- **Suggested questions for future-Claude in `/obsidian-recap` and `/obsidian-review`:** both commands now end with 4 to 5 questions the period's vault content is uniquely positioned to answer that the user has not asked yet. Each question cites at least one specific note via `[[wikilink]]`. Prefers questions that surface contradictions, connect co-appearing-but-unlinked entities, or name unstated next actions. Turns passive recaps into actionable prompts.
- **SessionStart hook (`hooks/load_vault_context.py`):** injects `_CLAUDE.md` into context once per session when the session starts inside the vault. Eliminates the per-command re-read of `_CLAUDE.md` that burned tokens on every invocation. Wired automatically by `scripts/setup.sh`.
- **`scripts/setup.sh` updated:** wires the new SessionStart hook (`hooks/load_vault_context.py`) in addition to the existing PostCompact background agent.
- **Per-day operation logs:** `/obsidian-init` now creates a `Logs/` folder with per-day files (`Logs/YYYY-MM-DD.md`) instead of a monolithic `log.md`. Root `log.md` becomes a pointer file only. Cheaper to read, faster to query.
- **`scripts/vault_stats.py`:** computes vault stats (notes by type, project/task counts by status, people by strength) and rewrites the `<!-- BEGIN STATS -->`/`<!-- END STATS -->` markers in `index.md`. Idempotent and re-runnable.
- **`scripts/migrate_log.py`:** splits an existing monolithic `log.md` (with `## YYYY-MM-DD` section headers) into per-day files under `Logs/`. Idempotent - skips days that already exist. Replaces root `log.md` with a pointer file after migration.

### Fixed

- **`scripts/setup.sh` robustness:** four issues fixed together. Vault paths containing apostrophes or other shell metacharacters (`Joe's Notes`) no longer crash the installer - `eval echo` replaced with bash parameter substitution. `python` replaced with `python3` for compatibility with macOS 13+ and Ubuntu 22+ which don't ship a `python` symlink. All three `settings.json` writes are now atomic (`mv` instead of `cat … && rm`). The MCP setup prompt is skipped when stdin is not a terminal so `curl | bash` installs and CI don't hang.

- **`vault_stats.py` people count:** now counts both `type: person` and `type: entity` in the People aggregate. Real vaults using either convention report the correct count.
- **Log layout routing in all commands:** every `/obsidian-*` command that reads or appends to the operation log now explicitly detects the vault layout (`Logs/YYYY-MM-DD.md` vs monolithic `log.md`) and uses the correct file and format. Previously, commands hardcoded `log.md` with the old `## [YYYY-MM-DD]` section-header format, which would write incorrectly formatted entries on modernized vaults.
- **`vault_stats.py` folder exclusions case-insensitive:** `EXCLUDED_FOLDERS` comparison now uses `part.lower()`, so `templates/` and `Templates/` are both excluded. Added `raw/` to the exclusion set (immutable source folder convention).
- **Em-dashes swept from `vault_stats.py` output, `commands/obsidian-init.md` entry template, and `SKILL.md` format spec:** all user-facing and vault-facing prose now uses ` - ` per the no-em-dash rule.

## [0.8.0] - 2026-05-15

### Added

- **`/notebooklm` command rewritten end to end - no browser, one HTTP call.** Replaces the prior bundle-and-paste workflow (which required opening notebooklm.google.com manually and pasting the response back into the terminal) with a single-phase command that calls Google's Gemini File Search API directly. Same architectural shape as `/research-deep`: one HTTP call, no manual step. Under the hood: scans the vault for the top 12 relevant notes (Research/NotebookLM/ excluded so the synthesis doesn't self-reference its own bundle), uploads them to an ephemeral Gemini File Search store, asks Gemini (default `gemini-2.5-flash`, free-tier friendly) for a citation-style synthesis grounded only against those sources, writes the AI-first synthesis to `Research/NotebookLM/YYYY-MM-DD - <slug>.md`, deletes the store, and emits a propagation payload for `/obsidian-save`. Requires `GEMINI_API_KEY` from https://aistudio.google.com/apikey (free tier covers it). Cost: roughly $0.004 per run on Flash, $0.06 per run on Pro (override via `NOTEBOOKLM_MODEL` env). Filenames written by this command use ASCII separators (`2026-05-15 - <slug>.md`) instead of em-dashes; existing `/research-deep` filenames untouched. The two research tracks (open-web via `/research-deep`, vault-grounded via `/notebooklm`) are designed to run in parallel for high-stakes topics. Contradictions across the two tracks are where the insight is.

### Fixed

- **`/notebooklm` self-reference bug.** Previous implementation re-scanned the vault during the save phase, which scored the bundle file (written during the start phase) as a top hit. The synthesis linked to its own input bundle as a vault baseline. Fix: `vault_scan` now excludes anything under `Research/NotebookLM/`.
- **`/notebooklm` em-dash filenames blew up the Gemini SDK upload.** Vault filenames in `Research/Deep/` and `wiki/logs/` often contain em-dashes (from the prior `/research-deep` convention). The Gemini SDK puts the basename in a Content-Disposition header, and httpx rejects non-ASCII headers. Fix: copy each source to a temp path with an ASCII-safe name before upload; preserve the original path as the human-readable `display_name`.
- **`/notebooklm` em-dashes baked into vault output.** The synthesis H1 used `topic — NotebookLM synthesis (date)` and the preamble had mid-sentence em-dashes. The voice rule says no em-dashes anywhere. Both now use a colon and a period-restructure respectively.

## [0.7.0] - 2026-05-13

### Added

- **`bootstrap_vault.py --preset` and `--mode` flags:** wires the preset/mode interface that `SKILL.md` documented but the script never implemented (running `--preset researcher` errored with `unrecognized arguments: --preset researcher --mode personal`). Five presets land at once, matching the existing SKILL.md description verbatim: `default` (preserves existing Life-OS layout - no change in behavior when no flag is passed), `executive` (Decisions/People/Meetings/OKRs · Boards: OKRs/Quarterly/Weekly), `builder` (Projects/Dev Logs/Architecture/Debugging · Boards: Backlog/Sprint/In Progress/Done), `creator` (Content/Ideas/Audience/Publishing · Boards: Ideas/Drafts/Scheduled/Published), `researcher` (Sources/Literature/Hypotheses/Methodology/Synthesis · Boards: Reading/Processing/Synthesized/Done). Each preset declares its folder list, kanban columns, `_CLAUDE.md` folder map, Home dashboard nav, and template extras via a single `PRESETS` dict at the top of the file - adding a new preset is one dict entry plus optional template lines in `write_preset_extras()`. Two modes: `personal` (default - owner-style `_CLAUDE.md`) and `assistant` (uses the `references/claude-md-assistant-template.md` schema, requires `--subject "Name"` and renders the operator/subject distinction). Fully backwards-compatible: `--path`, `--name`, `--jobs`, `--no-sidebiz` keep their meaning under the default preset; `--no-sidebiz` is silently ignored on non-default presets. The vault-not-empty check now ignores `.obsidian/` so re-running on a vault that only has Obsidian config no longer prompts.
- **`/create-command` interview flow (Phase 5):** new meta command that scaffolds a new `commands/<name>.md` through a 9-phase conversation - zero markdown editing. Asks intent, name, category, triggers, behavior steps, AI-first compliance, and external API needs, then writes a fully-formed command file (frontmatter + body + AI-first footer where applicable) using the Write tool. The new file flows automatically into every platform via the existing adapters - no extra build steps. Lowers the contribution bar so anyone can extend the skill, and every command added through this flow lands AI-first-compliant by construction. Listed under `meta` category; total command count is now 32 (was 31).
- **Write-time AI-first validator (Phase 4):** new `hooks/validate-ai-first.sh` runs as a Claude Code `PostToolUse` hook after every `Write` or `Edit` on a markdown file inside `OBSIDIAN_VAULT_PATH`. Warns (non-blocking) when the file fails the AI-first rule: missing frontmatter delimiters, missing required fields (`date`, `type`, `tags`, `ai-first: true`), tabs in YAML, or missing `## For future Claude` preamble. Surfaces specific warnings on stderr so Claude can repair the note in the same turn. Skips `raw/`, `templates/`, `_export/`, `.obsidian/`, `.git/`, `.trash/` and anything outside the vault. Platform-neutral spec at `hooks/validate-ai-first.hook.yaml`. Setup instructions in `SKILL.md` under "Write-Time AI-First Validator (PostToolUse Hook)". This is the **write-time cleanup primitive** that the Second Brain for Companies thesis depends on - humans write inconsistent input, the validator enforces AI-first discipline automatically.
- **Multilingual trigger phrases (Phase 3):** every command now declares `triggers_<lang>:` lines in its frontmatter. English (`triggers_en:`) is populated for all 31 commands; the schema is extensible to any language via `triggers_es:`, `triggers_it:`, `triggers_fr:`, `triggers_de:`, `triggers_pt:`, `triggers_ru:`, `triggers_ja:` (community contributions welcome). The non-Claude dispatchers (`AGENTS.md`, `GEMINI.md`) now include a `## Trigger phrases` section grouped by language then by category, so AI agents on those platforms can match natural-language requests without seeing the slash form. Adapters auto-detect which languages are populated; empty languages do not appear in the output. Documented in `CONTRIBUTING.md` under "Translating trigger phrases (multilingual support)".
- **Command categorization (Phase 2):** each command in `commands/` now declares a `category:` (vault, thinking, research, meta). Non-Claude dispatcher tables in `AGENTS.md` / `GEMINI.md` are now emitted as four grouped sections instead of one 31-row blob. Adapters use the shared `emit_routing_table_grouped` helper in `adapters/lib.sh`, so the categorization carries through automatically when a new command is added. No breaking changes - Claude Code build is still a byte-exact identity copy.
- **Multi-platform adapter pattern (Phase 1):** one source, four platforms.
  - `scripts/build.sh` orchestrator + `scripts/lib.sh` utility helpers
  - `adapters/lib.sh` shared parsing, path rewriting, tool-name neutralization
  - `adapters/claude-code/adapter.sh` - identity copy (Claude Code is the canonical platform)
  - `adapters/codex-cli/adapter.sh` - emits `AGENTS.md` + `.codex/commands/`
  - `adapters/gemini-cli/adapter.sh` - emits `GEMINI.md` + `.gemini/commands/`
  - `adapters/opencode/adapter.sh` - emits `AGENTS.md` + `.opencode/commands/`
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
- `SECURITY.md` - vulnerability reporting policy and coordinated disclosure timeline
- Schema.org JSON-LD `SoftwareApplication` block on the Pages site (`_includes/head_custom.html`) for rich-result eligibility and AI-search citation
- 3 new FAQ entries targeting "Obsidian plugin vs Claude Code skill" search intent

### Changed

- GitHub About description rewritten to lead with "Claude Code skill for Obsidian"
- README banner alt text now contains the full search-intent phrasing
- GitHub topics: swapped `markdown` and `pkm` for `obsidian-skill` and `claude-code-skill`

### Fixed

- **`bootstrap_vault.py` `UnicodeEncodeError` on Windows `cp1252` consoles.** The script's emoji print statements (`🧠 Bootstrapping vault: ...`, `📁 Folders created`, `✅ Vault bootstrapped at: ...`) crashed on Windows before doing any work because the default Python `sys.stdout` encoding on Windows PowerShell / cmd is `cp1252`, which has no codepoints for those characters. `sys.stdout` and `sys.stderr` are now reconfigured to UTF-8 at script start, wrapped in `try/except (AttributeError, ValueError)` so non-text streams or environments without `.reconfigure()` fall back gracefully.
- **Removed dead `--minimal` flag from `bootstrap_vault.py`.** `argparse` accepted `--minimal` but the value was never passed into `bootstrap()` - the flag had no effect for any user since v0.1.0. Removing it changes no behavior.
- `pyproject.toml` version was `0.1.0`, now matches the v0.6.0 release tag.

## [0.6.0] - 2026-04-26

### Added

- `references/ai-first-rules.md` - canonical spec for vault writes (the 7 rules, frontmatter schemas per note type, preamble templates, anti-patterns, audit checklist).

### Changed

- All 31 commands now explicitly reference the AI-first rule. Surgical cross-reference per command file, no body rewrites. Closes the gap where two Claude sessions on the same conversation could produce inconsistently structured notes.
- `references/write-rules.md` now points to `ai-first-rules.md` as the foundation.
- `SKILL.md` - new "AI-first vault rule" section under Core Operating Principles.

### Notes

- 29 files changed, +406 lines, 0 breaking changes. Additive only.

## [0.5.0] - 2026-04-26

### Added

- **Research Toolkit** - five new commands that turn the vault into a live research workspace.
  - `/x-read [url]` - verbatim X post + thread + TL;DR + key claims + reply sentiment (Grok-4 + x_search).
  - `/x-pulse [topic]` - what's hot on X, gaps, working hooks, post ideas (Grok-4.20-reasoning + x_search).
  - `/research [topic]` - web research dossier with citations, recency markers, contrarian views, open questions (Perplexity Sonar Pro).
  - `/research-deep [topic]` - vault-first: scans vault, identifies gaps, fills only those, synthesizes a delta report, propagates updates via `/obsidian-save` (Perplexity sonar-reasoning-pro + Grok + vault scan).
  - `/youtube [url]` - transcript + metadata + top comments, summarized AI-first (youtube-transcript-api + YouTube Data API v3 + Grok-4).
- Section 0 of `_CLAUDE.md` template - first version of the AI-first vault rule, applied to all 5 research commands from day one.
- API key handling at `~/.config/obsidian-second-brain/.env` (Mac-local, never synced).
- `pyproject.toml` + `uv.lock` for Python dependency management.
- Auto-open behavior: every research save pops Obsidian to the new note via `obsidian://open?...`.

### Notes

- Command count went 26 → 31. Same install, same `_CLAUDE.md`.
- Without API keys, the original 26 commands still work - research toolkit degrades gracefully.

[Unreleased]: https://github.com/eugeniughelbur/obsidian-second-brain/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/eugeniughelbur/obsidian-second-brain/releases/tag/v0.6.0
[0.5.0]: https://github.com/eugeniughelbur/obsidian-second-brain/releases/tag/v0.5.0
