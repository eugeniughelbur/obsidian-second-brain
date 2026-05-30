# Fork Insights - what 166 forks actually built, and the 50 things to add

Analysis date: 2026-05-30. Repo at analysis time: 1,462 stars, 166 forks (167 returned by the GitHub API).

This is a roadmap doc, not a spec. It captures what every diverging fork built, ranked into 50 concrete additions for the upstream repo. Items are tagged P0 (highest-ROI quick win), P1 (strong), P2 (strategic). Each names the fork that proved it so the implementation can be cross-referenced against real code.

## Method

Every fork was compared against `main` via the GitHub compare API (`/repos/eugeniughelbur/obsidian-second-brain/compare/main...<owner>:<branch>`) to get an exact ahead/behind count, then the diverging forks had their actual file contents deep-read. The "pushed after creation" heuristic was discarded as unreliable (it produced false positives like `overbit`, which is 0 ahead / 18 behind despite a recent push from a fork sync).

## The fork landscape

- 156 forks are untouched mirrors (0 commits ahead). No signal.
- 11 forks have their own commits. Of those, 3 did substantial work and 8 did focused single-purpose work.

| Fork | Ahead | What they built |
|---|---|---|
| `a0919376604` | +158 | Free/key-less research toolkit (11 sources), `/obsidian-architect` codebase scanner (27 modules), `/obsidian-roadmap`, `/idea-discovery`, `/vault-deep-synthesis`, Notion sync, launchd cron, `--project` routing |
| `CP250/mbs_automation` | +16 | Anti-fabrication + false-absence guards, `/obsidian-dashboard` (live queries), `/obsidian-calendar`, `/obsidian-normalize`, two TypeScript Obsidian plugins, launchd review cadence, opt-in bg-agent gating |
| `johanvillalbab/sho-second-brain-tooling` | +7 | Google Calendar commands (agenda, schedule, meeting), 6 workflow commands (1on1, panel, proposal, recurring, event, launch-block), task-graph schema fields, em-dash linter + pre-commit hook |
| `vectorstone` | +2 | Codex executable invocation path (`run-command.sh` + PATH shims via `codex exec`) |
| `eda3` | +2 | Nushell installers (`install.nu`, `setup.nu`), `## For future Codex` AGENTS.md vault template |
| `bmassenz` | +1 | `tests/test_smoke.py` (only test in any fork), `ECOSYSTEM.md` upstream-core/domain-fork contract |
| `captainyorgen` | +1 | Windows install fixes (`mv`->`cat>` settings write), stripped bg-agent |
| `knt0613pow` | +1 | Codex AGENTS.md (hand-written, superseded by adapter) |
| `TrevAtArena` | +1 | `DELTAS.md` fork-drift-survival pattern; 2 bug reports |
| `zzzichen277` | +1 | `README_zh.md` Chinese i18n |
| `drsedhuraman-bot` | +2 | CLAUDE.md `/init` rewrite (low quality, closed as PR #29) |

The strongest cross-fork signals: (1) the paid-API research toolkit is an adoption wall, (2) multiple forks want calendar integration, (3) zero tests exist, (4) Codex/Windows support is demanded independently by 5+ forks, (5) there is no anti-hallucination guard anywhere upstream.

## The 50 additions

### A. Free / zero-key research toolkit (the biggest adoption barrier)
1. **[P0] Free mode for the whole research toolkit** (`a0919376604`) - runs on a fresh `uv` install with zero API keys. Keep BYO-key as an opt-in path.
2. **[P0] 11 key-less source clients** (`a0919376604`) - arXiv, Semantic Scholar, OpenAlex, CrossRef, Wikipedia, HackerNews (Algolia), Reddit JSON, Lobsters, dev.to, DuckDuckGo, SearXNG fallback. Clean general-purpose Python, no personal coupling.
3. **[P1] Move synthesis into the calling Claude session** (`a0919376604`) - Python fetches raw JSON; the command body tells Claude to write the dossier. Removes the paid-synthesis dependency.
4. **[P1] Parallel source aggregator with a graceful-degradation contract** (`a0919376604`) - ThreadPoolExecutor, 30s timeout, "success if >=3 sources returned results", each client returns `[]` on failure.
5. **[P1] 24h-TTL file cache** (`a0919376604`) - polite UA + retries on a shared HTTP session at `~/.cache/obsidian-second-brain/research/`.
6. **[P2] `--academic` source profile** (`a0919376604`) - arXiv + S2 + OpenAlex + CrossRef vs the default discourse profile.

### B. Calendar and scheduling commands (two forks built this independently)
7. **[P0] Fix the `/obsidian-daily` calendar bug** (`johanvillalbab`) - it references a placeholder tool name `google_calendar_list_events` that never matches; the real MCP tool is `mcp__claude_ai_Google_Calendar__list_events`. The calendar pull is currently dead.
8. **[P1] `/obsidian-agenda`** (`johanvillalbab`) - calendar snapshot for a range with four quality detectors: overlap conflicts, 3+ back-to-back stretches, focus-gap detection, externally-organized events. Cross-links attendees to person notes.
9. **[P1] `/obsidian-schedule`** (`johanvillalbab`) - writes events to Google Calendar (standalone / from-task / suggest-time modes), pulls attendee emails from person-note `email:` fields and never guesses, conflict-checks before writing, round-trips the event URL into task frontmatter.
10. **[P1] `/obsidian-meeting`** (`johanvillalbab`) - generates a meeting note from a calendar event with empty Notes/Decisions/Action-items sections (refuses to fabricate), backlinks tasks whose frontmatter matches the event ID.
11. **[P1] `/obsidian-calendar` reconciliation** (`CP250`) - flags vault-implied commitments that are not on the calendar, flag-only, never writes events. The inverse of the daily pull.

### C. New thinking / workflow commands
12. **[P1] `/obsidian-panel`** (`johanvillalbab`) - convene a panel of `Advisors/` persona notes on a decision; one independent verdict each plus synthesis. Fits the thinking-tools layer alongside `/obsidian-challenge`.
13. **[P1] `/idea-discovery`** (`a0919376604`) - surface 3-5 next-direction candidates by scanning `Ideas/`, project Open Questions, and orphan Research notes, ranked by recency x orphan_count x external_signal. Does not auto-graduate.
14. **[P1] `/vault-deep-synthesis`** (`a0919376604`) - pure-vault, zero-network cross-reference that finds agreements/contradictions/stale-claims/coverage-gaps across notes matching a topic. Distinct from `/obsidian-synthesize`.
15. **[P1] `/obsidian-recurring`** (`johanvillalbab`) - track a recurring obligation with a cadence and a computed `next-due`; advances on each completion. `/obsidian-task` is one-shot only.
16. **[P2] `/obsidian-event`** (`johanvillalbab`) - event-ops note with pre / day-of / post checklists; spawns a day-of task card.
17. **[P2] `/obsidian-launch-block`** (`johanvillalbab`) - a "mother task" holding subtasks as an internal checklist instead of scattering loose task notes; uses `depends-on` edges.
18. **[P2] `/obsidian-proposal`** (`johanvillalbab`) - B2B proposal generator that keeps a `type: opportunity` deal tracker in sync. Generalize the hardcoded Spanish/"Interface School" sections first.
19. **[P2] `/obsidian-1on1`** (`johanvillalbab`) - structured 1:1 capture minting sequential learning IDs. Niche (teaching), but the "sequential ID into a running log" pattern is reusable.

### D. Codebase -> vault (the architect engine)
20. **[P1] `/obsidian-architect`** (`a0919376604`) - scan a codebase into a maintained, diff-aware architecture note set (overview + per-module notes + decisions + personas + Mermaid). Ship a focused English-first v1; drop the fork's v2/v3 migration baggage and zh-TW defaults.
21. **[P0] Sentinel-based safe regeneration** (`a0919376604`) - `@generated:start/end` blocks get overwritten, `@user:start/end` blocks are never touched, with a lockfile of per-block SHA hashes. A general primitive every write-command should use to stop clobbering user edits.
22. **[P1] commit-decisions mining** (`a0919376604`) - scan the last ~200 commits for decision-shaped messages and surface them as ADR candidates. Feeds `/obsidian-adr`.
23. **[P2] `/obsidian-roadmap`** (`a0919376604`) - synthesize architecture signals + research into a prioritized backlog with `T-NNN` tasks and board cards, evidence-linked. Depends on architect landing first.
24. **[P2] repomix integration** (`a0919376604`) - pack a codebase for LLM synthesis, with a pure-Python pathspec walker fallback when repomix is not installed.
25. **[P2] Personas inference** (`a0919376604`) - lift an explicit README `## Personas` section or have the model infer 2-5 personas with confidence levels.

### E. Anti-fabrication and vault integrity (no guard exists upstream today)
26. **[P0] False-absence guard** (`CP250`) - verbatim-portable: false-absence (saying "no note exists" when one does) is the most common failure mode, more common than fabrication. Verify presence/absence by listing and grepping, not from memory. Add to `ai-first-rules.md`.
27. **[P0] Search-completeness rule** (`CP250`) - enumerate exhaustively, do not sample; list every matching file, not a representative few. Reference it from every read/search command footer.
28. **[P0] Per-command anti-fabrication footer** (`CP250`) - a standard "hard rule" block threaded through every command. Cheap, mechanical, high-value.
29. **[P1] Read-before-edit guard plus bounded-section discipline** (`CP250`) - concrete fixes applied to `obsidian-daily`, `obsidian-decide`, `obsidian-log`, `obsidian-ingest`.
30. **[P1] `/obsidian-dashboard` "can't-fabricate" pattern** (`CP250`) - render live query blocks instead of a static list, so a stale snapshot cannot be invented. Concept ports even though upstream uses kanban, not the Tasks plugin.
31. **[P2] `/obsidian-normalize`** (`CP250`) - interruptible, approval-gated, per-note before/after-diff schema true-up for legacy notes. The pattern matters more than the command.

### F. Scheduled-agent / automation infrastructure
32. **[P0] PostCompact opt-in double-flag gating** (`CP250`) - require both `OBSIDIAN_VAULT_PATH` and `OBSIDIAN_BG_AGENT_ENABLED=1`. Today the bg-agent auto-arms on one env var and writes unattended with `--dangerously-skip-permissions`. Pure safety win.
33. **[P0] `hooks/obsidian-bg-agent.hook.yaml` (`enabled: false`) plus `postcompact.hook.example.json`** (`CP250`) - ships the agent inert with a paste-in template.
34. **[P0] `claude -p` slash-command-expansion workaround** (`CP250`, `a0919376604`) - slash commands do not expand in non-interactive mode; point Claude at the command file. Document this; anyone running the skill headless is currently blocked.
35. **[P1] launchd review cadence** (`CP250`) - daily/weekly/monthly/quarterly/yearly review-note generators with osascript notifications.
36. **[P1] Idempotent per-period run-stamp idiom** (`CP250`) - stamp written only on success + wake-from-sleep coalescing + RunAtLoad fallback, so failures retry and triggers do not double-fire.
37. **[P1] "Report-only on unattended runs" rule** (`CP250`) - scheduled `/obsidian-health` reports, never auto-fixes.
38. **[P2] "Add/update only, never delete/move/archive" constraint** (`CP250`) - baked into the bg-agent prompt.

### G. Obsidian plugins (zero ship upstream - this is greenfield)
39. **[P2] Companion status plugin** (`CP250`) - status bar showing whether today's/this-week's agents ran, command-palette headless runs, inline status cycling. First in-app surface for scheduled agents.
40. **[P2] Daily auto-open plugin** (`CP250`) - cross-platform (desktop + mobile, no Node), opens today's daily note(s) on launch, rotates stale tabs.
41. **[P2] A stamp-file convention** (`CP250`) - so any plugin/UI can read agent run-state. Small primitive that unlocks the above.

### H. Platform and install (5+ forks demanded this independently)
42. **[P1] Codex executable invocation path** (`vectorstone`) - `run-command.sh` + PATH shims wrap each command as a real `codex exec` call. The codex adapter currently ships inert command markdown with no runner; this is the genuine gap.
43. **[P1] Vault-facing AGENTS.md template with `## For future Codex` preamble** (`eda3`) - the only fork that did Codex right. Others just renamed `_CLAUDE.md` and left "future-Claude" in the body, proving hand-maintaining it does not scale and validating the auto-generation approach.
44. **[P1] Windows `setup.sh` rename fix** (`captainyorgen`) - change settings.json writes from `mv tmp dest` to `cat tmp > dest && rm tmp`. `mv`/atomic-rename breaks on WSL mounts and OneDrive-synced dirs.
45. **[P2] Nushell installers** (`eda3`) - `install.nu`/`setup.nu`, a real jq/bash-free Windows install story.
46. **[P2] A minimal / no-background-agent install profile** (`captainyorgen`) - the PostCompact agent is the #1 Windows pain point; offer a clean opt-out at install.

### I. Quality, testing, CI (none exist upstream)
47. **[P0] `tests/test_smoke.py`** (`bmassenz`) - the only test in any fork. Two stdlib tests: (1) `build.sh --platform codex-cli` produces expected files, (2) `vault_health.py --json` reports clean on a known 2-note vault. Runs against existing scripts unchanged.
48. **[P0] A CI workflow plus pytest dev-dependency** (`bmassenz`) - to run those tests on every PR. CLAUDE.md currently states "There is no automated test suite yet."
49. **[P1] Source-level em-dash linter + pre-commit hook** (`johanvillalbab`) - code-span-aware (skips inline code so `` `YYYY-MM-DD - slug.md` `` survives), check + `--fix`. Complements the write-time `validate-ai-first.sh`; broaden to the full banned-char set and add to CI.

### J. Docs, ecosystem, i18n, fork management
50. **[P1] `DELTAS.md` fork-customization template** (`TrevAtArena`) - a merge-safe "your local deltas live here" file that survives `git merge upstream`. Ships two real bug reports: `bootstrap_vault.py --preset` is unimplemented despite the README claiming it (also tracked as issue #13 / unclesamwk), and the printed `mcp-obsidian` block is never auto-wired into settings. Both worth fixing regardless.

### Bonus / strategic (did not make the 50)
- `ECOSYSTEM.md` defining an upstream-core/domain-fork contract with a pluggable Phase-3 "backend protocol" (`bmassenz`).
- `README_zh.md` plus a language switcher (`zzzichen277`).
- `--project` subtree routing flag and `/obsidian-board --refresh` from git-history mode (`a0919376604`).

## What NOT to copy

- **CP250's philosophy flip.** The fork deletes the `## For future Claude` preamble and `ai-first: true` flag (reframed as a human "amnesia test"). This directly contradicts the non-negotiable AI-first rule. Take the guards, not the model.
- **`/obsidian-notion-sync` and the cron scripts as-is.** Hardwired to leric's Notion workspace, a Discord channel, and zh-TW. Patterns only.
- **The corrupted `AGENTS.md` in johanvillalbab's fork.** A global "Claude->Codex" find/replace broke it (`~/.Codex/`, "future-Codex preamble"). Do not merge.

## Suggested first wave (the 8 P0 items)

These land most of the real value with no design debate:

1. Fix the `/obsidian-daily` calendar tool-name bug (#7).
2. Add `tests/test_smoke.py` + CI workflow (#47, #48).
3. Add the anti-fabrication + false-absence + search-completeness guards (#26, #27, #28).
4. Gate the PostCompact bg-agent behind a double flag + ship it inert (#32, #33).
5. Ship free mode for the research toolkit (#1, #2).
6. Adopt sentinel-based safe regeneration as a write primitive (#21).
7. Document the `claude -p` slash-command-expansion workaround (#34).

Scrub list before merging anything from `a0919376604`: hardcoded `/Users/leric/...` and `~/Documents/SecondBrain` paths, `langlive-line-oa` defaults, Discord `#langlive-line-oa`, zh-TW header defaults. From `CP250`: `/Users/cpreston/...` paths, the eight-pillar layout, the `mbs_automation` skill rename. From `johanvillalbab`: Spanish section headers, "Interface School", the faith-oriented `area` taxonomy.
