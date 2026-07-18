# Demos

See obsidian-second-brain working before you install anything. Every demo on this page is real footage: the commands actually ran, and the GIF is rendered from a committed [vhs](https://github.com/charmbracelet/vhs) tape file, so it can be re-rendered pixel-perfect for any future version. All demos use synthetic data (throwaway vaults, fictional names) - no real vault ever appears on this page.

## /obsidian-save - a conversation becomes five notes

The flagship command. Earlier in the recorded session, the user brain-dumped one paragraph: met a new advisor, made a project decision, kickoff Tuesday. Then:

<img src="media/obsidian-save.gif" alt="Running /obsidian-save headlessly: Claude writes a person note, a project note with the decision, a task, a board card, and the daily note, then the person note is shown with AI-first frontmatter." width="100%" />

What you're seeing: one `/obsidian-save` fans out into `People/Grace Hopper.md`, `Projects/Demo Pipeline.md` (decision recorded under Key Decisions), a task due Tuesday, a kanban card, and today's daily note - all cross-linked. The final `head` shows what an AI-first note looks like inside: frontmatter with `TBD` for anything not actually stated, a `## For future Claude` preamble, and dated claims. Note the honesty details: it flags its own "vhs tapes" interpretation as an unverified inference, and refuses to assume anything about Grace Hopper from the famous name.

Honesty note: the model's ~2 minute working pause is cut from the recording (vhs `Hide`/`Show` around the wait); everything shown is unedited real output. The demo runs headless (`claude -p`) with `--permission-mode acceptEdits` against the throwaway vault - in a normal interactive session you approve writes yourself.

Tape: [media/obsidian-save.tape](media/obsidian-save.tape)

## Install as a Claude Code plugin

Two commands and the whole skill is installed: 45 commands, the session hooks, and the vault MCP server.

<img src="media/plugin-install.gif" alt="Adding the marketplace from GitHub, installing the plugin, and the plugin list showing status enabled." width="100%" />

What you're seeing: `claude plugin marketplace add` clones the repo as a marketplace, `claude plugin install` ships the plugin, and `claude plugin list` confirms it's enabled. Same flow works as `/plugin` slash commands inside a session. Full install docs: [README - Install](README.md#install).

Tape: [media/plugin-install.tape](media/plugin-install.tape)

## Bootstrap a vault that passes its own health check

No vault yet? One command creates a ready-to-use one - folders, templates, kanban boards, goals, a `_CLAUDE.md` operating manual - and the health checker proves it's clean.

<img src="media/bootstrap-health.gif" alt="bootstrap_vault.py creating a complete vault for a fictional owner, then vault_health.py reporting zero issues." width="100%" />

What you're seeing: `bootstrap_vault.py` builds the vault (it never overwrites existing files - keep-by-default, `--force` is the only overwrite consent), then `vault_health.py` scans it and reports zero issues. Docs: [README - No vault yet?](README.md#install).

Tape: [media/bootstrap-health.tape](media/bootstrap-health.tape)

## Re-rendering a demo

```bash
brew install vhs   # or: go install github.com/charmbracelet/vhs@latest
vhs media/plugin-install.tape
```

## Adding a demo

1. Write a `.tape` file (see the two committed ones for the house style: Catppuccin Mocha, 1000x520, font 15).
2. Point it at throwaway data only - a `mktemp -d` config dir or a bootstrapped scratch vault with a fictional owner. **Never record a real vault.**
3. Render with `vhs`, check every frame is clean, commit the `.gif` and the `.tape` together under `media/`.
4. Add a section here: what it shows, the GIF, the tape link.
