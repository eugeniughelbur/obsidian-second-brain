# CLAUDE.md

Operating instructions for agents (Claude Code, Codex) working on this repo. `AGENTS.md` is a symlink to this file.

This is a slimmed fork of obsidian-second-brain: five skills that run a Karpathy-style LLM Wiki over an Obsidian vault, on Claude Code and Codex only, with no external LLM APIs. If you are operating on a user's vault, read that vault's `AGENTS.md`, not this file.

## Repo layout

- `skills/<name>/SKILL.md` - the five skills (`obsidian-init`, `obsidian-save`, `obsidian-find`, `obsidian-health`, `obsidian-review`). One file serves both hosts. `{{OSB_ROOT}}` is replaced with the absolute toolkit path by the installer.
- `references/` - `ai-first-rules.md` (canonical note spec, non-negotiable), `folder-map.md` (vault layout), `agents-md-template.md` (vault schema template), `write-rules.md`, `freshness-policy.md`, `source-quality-check.md`.
- `scripts/` - stdlib-first Python helpers. `osb_env.py` resolves config (vault path, language, toolkit root); `bootstrap_vault.py` creates the vault; `host_config.py` edits Claude/Codex config; `quick-install.sh` is the only installer.
- `hooks/validate-ai-first.sh` - PostToolUse validator. Handles Claude `Write|Edit` payloads and Codex `apply_patch` payloads.
- `tests/test_core.py` - CI suite.

## Invariants

- Skills resolve the vault through `python3 {{OSB_ROOT}}/scripts/osb_env.py` and stop if it fails. Never fall back to the working directory: skills run from any project.
- Skills must not depend on host-only tools or env vars. Subagents: parallel if the host supports them, otherwise sequential, same result.
- Every vault write follows `references/ai-first-rules.md` and is re-checked with `scripts/check_notes.py` at the end of the skill, hook or no hook.
- Existing vault notes change only after the user approves a proposal (unless the vault sets `rewrite_policy: unattended`). Notes are never deleted; merges leave `type: redirect`.
- `host_config.py` must stay idempotent, back up before writing, keep other tools' hooks in place (Codex trusts hooks by position), and verify the TOML it writes parses.
- No em-dashes, en-dashes, curly quotes or Unicode math in source files (`scripts/sweep_non_ascii.py --check`).

## Conventions

- Python: ruff (`F`, `I`, `PTH`), target py310, line length 100 as convention.
- Commits: imperative mood. Co-author Claude when pair-programmed.
- Skill bodies are written in Korean; frontmatter `description` is English plus Korean trigger phrases.

## Checks

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
python3 scripts/sweep_non_ascii.py --check
bash scripts/quick-install.sh --local   # install from this checkout
```

Changes that can affect Codex behavior (skills, hooks, host_config, installer) get a Codex review before merging.
