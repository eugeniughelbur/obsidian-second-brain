# Windows Codex Deployment Repair Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make the Codex CLI build reliable on Windows CRLF checkouts, redeploy complete native skills, finish Vault initialization, and verify the Obsidian-side configuration.

**Architecture:** Normalize CRLF at the adapter parser boundary and also force LF for command sources. Prove the behavior with a regression test that checks real generated Skill bodies, trigger descriptions, and platform exclusions. Keep source code outside the Vault, then copy only the generated Codex distribution into the Vault and validate the resulting system end to end.

**Tech Stack:** Bash/AWK adapters, pytest, PowerShell, Codex native Agent Skills, Obsidian CLI.

---

### Task 1: Add a failing Windows CRLF regression test

**Files:**
- Modify: `tests/test_smoke.py`

- [x] Extend the Codex build smoke test to require a non-empty command body.
- [x] Require trigger text from command frontmatter.
- [x] Require the Codex-excluded `obsidian-calendar` skill to be absent.
- [x] Run the targeted test against the current CRLF checkout and confirm the expected failure.

### Task 2: Make adapter parsing CRLF-safe

**Files:**
- Modify: `adapters/lib.sh`
- Modify: `.gitattributes`
- Modify: `integrations/obsidian-mcp-server/vault_ops.py`

- [x] Strip a trailing carriage return before parsing delimiters and emitting command bodies.
- [x] Force `commands/*.md` to LF in future checkouts.
- [x] Return MCP note paths in portable POSIX form on Windows.
- [x] Re-run the targeted test and confirm it passes.
- [x] Run the full repository test suite.

### Task 3: Rebuild and redeploy the Codex distribution

**Files:**
- Generated: `dist/codex-cli/**`
- Replace from generated output: `D:/MyMind/.agents/**`, `D:/MyMind/.codex/**`, `D:/MyMind/AGENTS.md`, `D:/MyMind/INSTALL.md`

- [x] Build `codex-cli` with Git Bash.
- [x] Verify exactly 43 skills, 43 non-empty bodies, trigger descriptions present, and no calendar skill.
- [x] Remove only the previous generated deployment namespaces after absolute-path validation.
- [x] Copy the new distribution into the Vault.
- [x] Compare all generated files by hash.

### Task 4: Complete Vault initialization

**Files:**
- Create: `D:/MyMind/index.md`
- Create: `D:/MyMind/log.md`
- Create: `D:/MyMind/Logs/2026-07-10.md`
- Preserve: `D:/MyMind/_CLAUDE.md`

- [x] Generate an exhaustive user-note catalog excluding support directories.
- [x] Create the AI-first log pointer and today's append-only init/repair log.
- [x] Preserve the current `_CLAUDE.md` because overwriting requires a separate diff approval.

### Task 5: Finish Obsidian configuration

**Files:**
- Managed by Obsidian CLI: `.obsidian/plugins/**`, `.obsidian/community-plugins.json`
- Update only if needed: `Home.md`, `_CLAUDE.md`

- [x] Install and enable Dataview, Templater, and Kanban using Obsidian CLI.
- [x] Replace or remove demonstrably broken bootstrap links without inventing user data.
- [x] Remove the known temporary scan file from `.codex` if it is not part of the new distribution.

### Task 6: End-to-end verification

- [x] Run the Codex build smoke test and full test suite.
- [x] Re-run `vault_health.py` and confirm support/source files are no longer scanned.
- [x] Verify initialization artifacts and Bases.
- [x] Verify Obsidian plugins are installed and enabled, reload the Vault, and inspect errors.
- [x] Resume Obsidian Sync only after verification succeeds.
