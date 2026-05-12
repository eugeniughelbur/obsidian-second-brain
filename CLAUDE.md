# CLAUDE.md

Operating instructions for Claude Code when working inside this repo.

This is the source repo for **obsidian-second-brain**, a Claude Code skill that turns any Obsidian vault into a living AI-first second brain. The skill ships 31 slash commands across 4 layers (vault management, thinking tools, research toolkit, scheduled agents).

If you are Claude operating on a user's vault, you want `_CLAUDE.md` inside their vault, not this file. This file is for working on the skill's source code.

## Repo layout

- `commands/` — 31 slash command definitions, one `.md` per command. **This is the platform-neutral source.** Adapters compile it for each platform.
- `references/` — shared specs that commands link to. **`ai-first-rules.md` is the canonical vault-write spec** and is non-negotiable.
- `scripts/` — Python helpers (`bootstrap_vault.py`, `vault_health.py`, the `research/` toolkit), plus `build.sh` (the adapter orchestrator) and `lib.sh`.
- `adapters/` — platform translation layer. `lib.sh` holds shared parsing helpers. `claude-code/`, `codex-cli/`, `gemini-cli/`, `opencode/` each ship an `adapter.sh`.
- `dist/` — build output, one tree per platform. **Gitignored.** Regenerate with `bash scripts/build.sh` (all platforms) or `bash scripts/build.sh --platform <name>`.
- `hooks/` — Claude Code hooks shipped with the skill.
- `SKILL.md` — full operating manual loaded by Claude when the skill activates.
- `architecture.md` — how the layers fit together.
- `README.md` — public-facing docs on github.com.
- `pyproject.toml` — Python deps managed via `uv`.
- `install.sh` — one-shot installer that symlinks the skill into `~/.claude/`. (Legacy; for non-Claude platforms see `dist/<platform>/INSTALL.md` after building.)

### The adapter pattern

Source files in `commands/` use Claude Code's slash-command shape. The Claude Code adapter is an identity copy. The other three adapters (Codex CLI, Gemini CLI, OpenCode) emit a platform-appropriate dispatcher file (`AGENTS.md` or `GEMINI.md`) at the dist root with an **auto-generated routing table** built from each command's `description:` frontmatter, plus the command bodies under `.codex/commands/` (or `.gemini/`, `.opencode/`). Tool-name references like `Read tool` are rewritten to neutral wording (`read files`) so the instructions still make sense outside Claude Code.

**When adding a new command, only edit `commands/<name>.md`.** The adapters pick it up automatically on the next build. Optional frontmatter fields: `exclude: [<platform>]` to opt out per platform.

## The AI-first rule (non-negotiable)

Every command that writes to a user's vault MUST follow `references/ai-first-rules.md`. Vault notes are designed for **future-Claude retrieval**, not human reading. This means:

- A `## For future Claude` preamble at the top of every note
- Rich frontmatter: `type`, `date`, `tags`, `ai-first: true`, plus type-specific fields
- `[[wikilinks]]` for every person, project, idea, decision referenced
- External claims carry recency markers like `(as of 2026-04, source.com)`
- Source URLs preserved verbatim inline
- Confidence levels where applicable (`stated | high | medium | speculation`)

If you are editing a command file in `commands/`, do not rewrite the AI-first preamble out of it. Do not "humanize" vault output. Do not drop frontmatter to make notes look cleaner.

## Conventions

- **Markdown:** sentence-case headers (`## What it does`, not `## What It Does`). No emojis in command files. No em-dashes (`—`) in user-facing prose — use a regular dash or restructure the sentence.
- **Python:** ruff with `line-length = 100`, target `py310`. Type hints encouraged, not required.
- **Commits:** imperative mood (`Add`, `Fix`, `Update`). Co-author Claude when pair-programmed.
- **Frontmatter:** YAML, double-quoted strings when in doubt, lowercase tag values.

## Adding a new command

1. Create `commands/<name>.md` with `description:` frontmatter and operating instructions.
2. If it runs Python, add `scripts/research/<name>.py` (or appropriate subfolder).
3. **Apply the AI-first rule to every vault write.** Reference `references/ai-first-rules.md` from the command body so future-Claude has the spec inline.
4. If the command produces a new note type, add its frontmatter schema to `references/ai-first-rules.md`.
5. Update `SKILL.md` (Layer section + command list) and `README.md` (commands table).
6. Add a `CHANGELOG.md` entry under "Unreleased".

## Testing locally

Symlink the local checkout into Claude Code so slash commands run from this repo:

```bash
ln -s "$(pwd)" ~/.claude/skills/obsidian-second-brain
ln -s commands/* ~/.claude/commands/
```

Then restart Claude Code and run the command against a test vault. There is no automated test suite yet — verification is manual: run the command, inspect the resulting vault notes, confirm AI-first compliance.

## Release process

1. PRs land on `main` only when CI is green and the AI-first rule is upheld.
2. Move "Unreleased" entries in `CHANGELOG.md` under a new version header with the release date.
3. Bump version in `pyproject.toml` and `CITATION.cff`.
4. Tag and push: `git tag v0.X.0 && git push origin v0.X.0`.
5. Cut a GitHub Release with notes copied from the CHANGELOG entry.

## What not to do

- Do not rewrite vault output to be "more human-friendly." The vault is for future-Claude, not human readers.
- Do not strip frontmatter or `## For future Claude` preambles from existing commands.
- Do not add emojis to command files or vault output (unless explicitly part of a UI element like a kanban column emoji).
- Do not invent rates, dates, or relationships when writing project notes — mark unknowns as `TBD`.
- **Contributors:** do not push to `main` directly — open a PR.
- **Maintainer (Eugeniu) and Claude assisting him:** may push to `main` directly when working solo. PRs are optional, not mandatory.
