# DELTAS - your local fork customizations

Copy this file to `DELTAS.md` at the root of YOUR fork. It is the one place your
personal deviations from upstream live, so they survive every `git merge upstream/main`.

Why this exists: when you fork obsidian-second-brain and customize it (different vault
path, disabled commands, your own conventions), those edits collide with upstream updates.
Keeping them in stock files means painful merge conflicts forever. Keeping them HERE - in a
file upstream never touches - means you can always `git merge upstream/main` cleanly and
re-apply anything that drifted, in one place.

Upstream ships this as `references/DELTAS.template.md` and never edits your `DELTAS.md`.

---

## Config decisions

- **Vault path:** `<where your vault lives>`
- **Owner / name:** `<you>`
- **Preset used:** `<default | executive | builder | creator | researcher>`
- **Research toolkit:** `<enabled with which keys | deferred | free-only>`
- **Open questions:** `<anything you have not decided yet>`

## Bootstrap status

- [ ] Ran `scripts/bootstrap_vault.py` (or set up the vault by hand)
- [ ] Ran `scripts/setup.sh` (env var + hooks)
- [ ] Symlinked the skill into `~/.claude/skills/` (so `git pull` auto-deploys)
- [ ] Decided whether to enable the background agent (`OBSIDIAN_BG_AGENT_ENABLED`)
- [ ] Configured the obsidian-vault MCP server (optional)

## Deviations from upstream defaults

List anything you changed from the shipped behavior, and why. Examples:

- `<e.g. disabled /obsidian-x because ...>`
- `<e.g. use a different folder layout than the preset because ...>`
- `<e.g. semantic commits instead of time-based Obsidian-Git commits>`

## Personal conventions

- `<e.g. secrets live in 1Password, never in the vault>`
- `<e.g. daily note always has an "Open loops" section>`

## Intentionally NOT using

- `<features you deliberately skip, so future-you does not re-enable them by accident>`

## Upgrade hygiene

```bash
git fetch upstream
git merge upstream/main
```

On a conflict inside a stock command or script: prefer the upstream version, then
re-apply your change here as a delta. Never let a local tweak block an upstream update -
move the tweak into this file instead.

## Bugs / mismatches you have noticed in upstream

Track anything you spot so you can file it (or fix it) later. Example format:

- `<file:line>` - `<what is wrong>` - `<filed as issue #N | not yet filed>`
