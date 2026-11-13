# Crew: 4 agents, one logbook

Crew stores one Markdown logbook for Claude Code, Codex, Cursor, and Grok Bot.
It works in a plain folder without Obsidian. Python 3.10 or later is required; Crew uses only the standard library.

## Install and setup

The README installer makes `/crew setup` available in Claude Code:

```bash
curl -fsSL https://raw.githubusercontent.com/eugeniughelbur/obsidian-second-brain/main/scripts/quick-install.sh | bash
```

Restart Claude Code, then type `/crew setup`. Choose `~/crew` or `wiki/team/` inside your vault.
With the plugin install, use `/obsidian-second-brain:crew setup`.
Codex's Agent Skills build exposes `$crew setup`; the existing adapters also compile Crew for the other supported hosts.
Cursor users can run the Python setup directly from a checkout.

From this repository, these commands need no package installation:

```bash
python3 scripts/crew.py --dir ~/crew setup --agents claude codex cursor
python3 scripts/crew.py setup --vault "/path/to/vault"
```

Choose one location. Setup stores it in `~/.config/crew/config.json` and copies the runtime beside that file.
Rerun setup after upgrading Crew to refresh that copy.

| Agent | Read events | Rules file |
|---|---|---|
| Claude Code | `SessionStart`, `UserPromptSubmit` | `~/.claude/CLAUDE.md` |
| Codex | `SessionStart`, `UserPromptSubmit` | `~/.codex/AGENTS.md` |
| Cursor | `sessionStart`, `postToolUse` | `~/.cursor/rules/crew.mdc` |
| Grok Bot | Read before each job through its runner | Paste `~/.config/crew/grok-profile.md` into its profile |

Codex requires `/hooks` to review and trust new or changed hooks. Until trusted, its Crew hooks inject nothing.
See the [Codex hook reference](https://developers.openai.com/codex/hooks).
Cursor uses `additional_context` JSON for its supported events; see the [Cursor hook reference](https://cursor.com/docs/hooks).
Claude uses event-specific `additionalContext` JSON; see the [Claude hook reference](https://code.claude.com/docs/en/hooks).
Restart agents after setup. Test model-visible context in each host; a successful script run only verifies its output.

Setup preserves unrelated settings, hooks, and rules. Broken JSON or Crew markers stop setup with an error.
A rerun replaces Crew's entries without adding duplicates. The installer tracks its own command strings to avoid removing another tool's hooks.
Existing prototype hooks remain untouched. Remove their entries only after approving a switch and testing Crew.

## Daily use

```bash
export CREW_DIR=~/crew
python3 scripts/crew.py add --agent claude --area side --did "Built 1 parser" --where "src/parser.py"
python3 scripts/crew.py show --agent codex --new
python3 scripts/crew.py lesson --from codex --for claude --kind gap --text "Cover empty input" --evidence "tests/test_parser.py"
python3 scripts/crew.py digest --date 2026-10-17
python3 scripts/crew.py keep L1
```

Run `keep` only after the human chooses that lesson. Use `drop L1` for a lesson they decline.
Both commands preserve the record and evidence. Repeating a decision is harmless; changing a final decision requires manual review.
The CLI is a local tool, so the human gate depends on the caller following this rule.

A job looks like this:

```text
- 18:40 | codex | brand | Astra pass, 0 errors | landscape/index.html
```

`YYYY-MM-DD.md` holds jobs. `lessons.md` holds feedback, with stable IDs and `open`, `kept`, or `dropped` status.
Legacy prototype bullet records remain readable. New lessons use a Markdown table; decisions preserve legacy bullet formatting.
Writes use a local file lock and atomic replacement. Coordinate writers on one host; distributed filesystem locks depend on the filesystem.
Concurrent copies through file-sync services can conflict. Crew does not resolve sync conflicts.

`show --new` tracks each agent separately. Hooks also track sessions separately to avoid consuming another session's records.
Reads return the newest 50 unread records and count the older ones. Use `digest --date` for a full day, or set `--limit 100`.
Without `--new`, `show` returns the latest records. `--date YYYY-MM-DD` narrows either mode.
`digest` includes all agents' jobs and lessons created that day without consuming them.
Control characters are stripped, pipes are replaced inside fields, and each input field is capped at 600 characters.

## Grok Bot profile

Setup prints a complete paste block and saves it to `~/.config/crew/grok-profile.md`.
Paste that block into Grok Bot's profile. It directs Grok Bot to:

- Read the log before each job.
- Add one factual line after each job.
- Leave lessons for human review.
- List open lessons during an existing nightly review.

A remote Grok Bot needs a runner that can execute Crew against the same folder.
Use an existing remote shell connection or shared mount. Adapt the printed Python and folder paths to that runner.
Crew does not set up transport, post to Slack, or start a scheduler.
If the bot only has vault note tools, the Python commands remain unavailable until a runner is connected.
A kept Grok Bot lesson changes the local profile draft. Paste the changed block into the remote profile to activate it.

## Verification and limits

1. Add a job as Claude with the command above.
2. Ask Codex, Cursor, and Grok Bot, "What did Claude do today?"
3. Run `show --agent codex --new` twice in a terminal. The second read should contain no repeated job.
4. Add a lesson. Check that the recipient's rules change only after `keep`.
5. Rerun setup. Existing settings and unrelated rules should remain intact.

Every read labels records as data and quotes each entry. This framing does not guarantee immunity to prompt injection.
Agents must follow their own rules when records contain instructions.
Crew makes no model calls and runs no background loop. Agent hosts decide when hooks fire and whether returned context reaches the model.

<!-- author-credit -->

---

From [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain), created by Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator). Questions or consulting: [LinkedIn](https://www.linkedin.com/in/eugeniu-ghelbur/) or [e.ghelbur@gmail.com](mailto:e.ghelbur@gmail.com). More: [The AI Operator](https://theaioperator.io/?utm_source=github&utm_medium=file-credit) | [X](https://x.com/eugeniu_ghelbur) | [GitHub](https://github.com/eugeniughelbur). MIT license.
