# Contributing to obsidian-second-brain

Thanks for your interest in contributing! This skill exists because the people who use it keep making it better. Whether you're filing a bug, requesting a feature, or shipping a new command, you're welcome here.

This guide explains **how to contribute** so your work lands fast.

---

## Before you start

1. **Be respectful.** This project follows a [Code of Conduct](CODE_OF_CONDUCT.md). Disagreement is welcome; rudeness is not.
2. **Search first.** Check [open issues](https://github.com/eugeniughelbur/obsidian-second-brain/issues) and [discussions](https://github.com/eugeniughelbur/obsidian-second-brain/discussions). Someone may already be working on what you're proposing.
3. **For ideas / questions / "what if..."**, prefer [Discussions](https://github.com/eugeniughelbur/obsidian-second-brain/discussions). Issues are for concrete bugs or feature proposals.

---

## Quick links

- 📜 [AI-first vault rule](references/ai-first-rules.md) - required reading before adding any command that writes to the vault
- 📖 [SKILL.md](SKILL.md) - the operating manual for Claude
- 🏗 [architecture.md](architecture.md) - how the layers fit together
- 🐛 [Bug report form](https://github.com/eugeniughelbur/obsidian-second-brain/issues/new?template=bug_report.yml)
- ✨ [Feature request form](https://github.com/eugeniughelbur/obsidian-second-brain/issues/new?template=feature_request.yml)

---

## Setting up a development environment

```bash
# Clone the repo
git clone https://github.com/eugeniughelbur/obsidian-second-brain ~/Projects/obsidian-second-brain
cd ~/Projects/obsidian-second-brain

# Install Python deps via uv (auto-creates .venv)
uv sync

# Set up API keys for the research toolkit (optional — only needed if you're working on /x-read, /x-pulse, /research, /research-deep, or /youtube)
mkdir -p ~/.config/obsidian-second-brain
cp .env.example ~/.config/obsidian-second-brain/.env
chmod 600 ~/.config/obsidian-second-brain/.env
# then paste your xAI / Perplexity / YouTube keys into the file

# Link the skill into Claude Code (if you're testing slash commands)
ln -s "$(pwd)" ~/.claude/skills/obsidian-second-brain
ln -s commands/* ~/.claude/commands/
```

Now restart Claude Code and your slash commands will use the local checkout.

---

## Types of contributions

### 🐛 Bug fixes

1. File a bug report first if one doesn't exist (use the form so you don't miss required info)
2. Reproduce locally
3. Fix on a branch named `fix/short-description`
4. Open a PR linking the issue: `Closes #123`

### ✨ New slash commands

This is the most common contribution. The skill currently has 31 commands across 4 layers; adding a 32nd is a clear path.

**Required steps:**
1. **Open a feature request issue first.** Get a thumbs-up before building. Saves you wasted work if the command isn't a fit.
2. Add `commands/<command-name>.md` with frontmatter and instructions
3. If the command runs Python (research-style), add `scripts/research/<script>.py`
4. **Apply the [AI-first rule](references/ai-first-rules.md) to any vault writes.** This is non-negotiable. Every saved note must:
   - Have a `## For future Claude` preamble
   - Have rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields)
   - Use `[[wikilinks]]` for every person, project, idea, decision referenced
   - Preserve external claims with recency markers (`(as of 2026-04, source.com)`)
   - Include source URLs verbatim
   - Mark confidence where applicable (`stated | high | medium | speculation`)
5. Update `SKILL.md` - add a section under the appropriate Layer with the command name and full operating instructions
6. Update `README.md` - add the command to the relevant table in the "Commands" section
7. Update `references/ai-first-rules.md` - if your command produces a NEW note type, add its frontmatter schema there
8. Add an entry to `CHANGELOG.md` under "Unreleased"

### 🔌 New integrations / sources

Adding a new research source (Reddit, podcasts, papers, etc.) follows the same path as a new command, plus:
- Document API setup in `.env.example` and the README's "Research toolkit" install section
- Add the API key to `scripts/research/lib/config.py` with `get_optional()` (degrades gracefully if missing)
- Use the `lib/grok.py` and `lib/perplexity.py` patterns for retry + error handling

### 📚 Documentation

Documentation PRs are always welcome. Specifically helpful:
- Examples of vault setups for different roles (founder, researcher, student)
- Screenshots of real vault notes after running specific commands
- Translation of docs into other languages
- Fixing typos and unclear wording

No issue required for typo fixes - just open a PR.

### 🌍 Translating trigger phrases (multilingual support)

Every command in `commands/<name>.md` declares trigger phrases per language in its frontmatter:

```yaml
---
description: Save everything worth keeping from this conversation to the vault
category: vault
triggers_en: ["save this", "save the conversation", "save to vault", "obsidian save"]
---
```

To add a new language, add a `triggers_<two-letter-code>:` line right after the existing `triggers_en:` line, with a list of equivalent phrases in that language. **Important:** use natural, conversational phrases a native speaker would actually say - not literal word-for-word translations of the English.

Supported language codes (add more by editing `_lang_label()` in `adapters/lib.sh`):

| Code | Label |
|---|---|
| `en` | English |
| `es` | Español |
| `it` | Italiano |
| `fr` | Français |
| `de` | Deutsch |
| `pt` | Português |
| `ru` | Русский |
| `ja` | 日本語 |

Example: adding Spanish to `obsidian-save`:

```yaml
triggers_en: ["save this", "save the conversation", "save to vault"]
triggers_es: ["guarda esto", "guarda la conversación", "guarda al vault"]
```

When you rebuild (`bash scripts/build.sh`), the new language automatically appears as its own section under `## Trigger phrases` in the dispatcher files (`AGENTS.md`, `GEMINI.md`). No adapter code changes needed.

Translation PRs welcome for any of the 31 commands. Send one language at a time, full coverage. Open `commands/*.md`, add your `triggers_<code>:` line under the existing `triggers_en:`, and open a PR titled `Add <Language> trigger phrases`.

### 🐧 Cross-platform support

The skill currently assumes macOS (`install.sh`, `~/.config` paths, the `open` command for auto-opening notes in Obsidian). Linux/Windows support PRs are welcome. Touch:
- `install.sh` (or add `install.ps1` for Windows)
- `scripts/research/lib/vault.py` (the `open` subprocess call)
- `.env.example` and README install section

---

## Style guide

### Python
- **Formatter:** ruff (line length 100, target Python 3.10)
- **Imports:** standard library first, third-party second, local third (`from .lib import ...`)
- **Type hints** on public functions; not required for trivial helpers
- **Error handling:** translate API errors to plain-English `SystemExit` messages with fix instructions, not stack traces

### Markdown (commands, docs)
- **Headers:** sentence case (`## What it does`, not `## What It Does`)
- **Code blocks:** language tag (`bash`, `python`, `yaml`)
- **No trailing whitespace**
- **One blank line between sections**

### Commits
- **Subject line:** imperative mood, focus on WHY ("Add /x-pulse command for X trend scanning"), not WHAT ("Added file")
- **Body:** explain motivation if non-obvious. Wrap at 72 chars.
- **Co-author tag** if Claude pair-programmed: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

### PR titles
Same as commits - imperative + WHY-focused. Examples that ship fast:
- ✅ `Add /obsidian-shipped for weekly retrospectives`
- ✅ `Fix /research-deep retry logic when Grok times out`
- ❌ `Updates`
- ❌ `WIP fix`

---

## Testing locally

Right now the project has no formal test suite (planned post-v1.0). Until then:

**For Python changes:**
```bash
# Verify imports
uv run python -c "from scripts.research import x_read, x_pulse, research, research_deep, youtube_extract; print('OK')"

# Smoke test a command (requires API keys)
uv run -m scripts.research.x_read "https://x.com/some/post"
```

**For slash command changes:**
1. Symlink your local checkout into `~/.claude/commands/`
2. Restart Claude Code
3. Invoke the command and verify the output matches the AI-first rule

**For vault note writes:**
- Open the resulting note in Obsidian
- Check the frontmatter is valid YAML
- Verify all `[[wikilinks]]` resolve
- Confirm the `## For future Claude` preamble is present and accurate

---

## Pull request process

1. Fork the repo and create a branch from `main`
2. Make your changes following the AI-first rule and style guide
3. Update `SKILL.md`, `README.md`, and `CHANGELOG.md` as needed
4. Run `uv sync` to verify dependencies still resolve
5. Open a PR using the [PR template](.github/PULL_REQUEST_TEMPLATE.md)
6. Maintain a respectful tone in review discussions
7. Address feedback by pushing additional commits (don't force-push during review)
8. Once approved, the maintainer will squash-merge

---

## Release process

(For maintainers - included so contributors understand the cadence.)

1. Merge approved PRs to `main`
2. Update `CHANGELOG.md` - move "Unreleased" entries under a new version header with date
3. Bump version in `pyproject.toml` and `CITATION.cff`
4. Tag the release: `git tag v0.X.0 && git push origin v0.X.0`
5. Create a GitHub release with detailed notes covering: new commands, breaking changes, bug fixes, contributors

---

## Getting help

- **Questions about how to use a command:** [Discussions Q&A](https://github.com/eugeniughelbur/obsidian-second-brain/discussions/categories/q-a)
- **Showcase your vault setup:** [Discussions Show & Tell](https://github.com/eugeniughelbur/obsidian-second-brain/discussions/categories/show-and-tell)
- **Bugs:** [bug report form](https://github.com/eugeniughelbur/obsidian-second-brain/issues/new?template=bug_report.yml)
- **Direct contact (private / security):** see [SECURITY.md](SECURITY.md) (when added) or DM [@eugeniu_ghelbur](https://x.com/eugeniu_ghelbur)

---

## Recognition

Contributors are listed in release notes for the version their work shipped in. Significant contributions earn a permanent mention in the README.

Thanks for making this skill better. The vault gets smarter every time someone ships a new command. 🧠
