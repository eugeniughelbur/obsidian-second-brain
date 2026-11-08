# Windows setup

obsidian-second-brain runs on Windows through Git Bash. Eleven people had reported Windows problems by November 2026, and the code fixes are all merged. This page collects the setup steps so you skip the traps they hit.

## Before you install

1. Install [Git for Windows](https://git-scm.com/download/win). It gives you Git Bash, the shell every script here runs in.
2. Install a real Python 3 from [python.org](https://www.python.org/downloads/windows/), or install [uv](https://docs.astral.sh/uv/). The `python3` command that comes with Windows is a Microsoft Store shortcut that runs nothing. The hooks try `python3`, `python`, `py -3` and `uv run` in that order, so any real install works (#269, #281).
3. For the classic script install (`scripts/setup.sh`), also install `jq`: `winget install jqlang.jq`.
4. Install [Claude Code](https://claude.com/claude-code), or the agent you use.

## Install

1. Open **Git Bash**. Do not type `bash` in PowerShell: if WSL is installed, that starts the Linux shell, which has a different home folder and a different Python (#308).
2. Run the quick install from the [README](README.md#install).
3. Restart Claude Code.

## Update

On Windows the slash commands are copied, not linked. After every `git pull`, run `bash update.sh` in Git Bash, then restart Claude Code. If a new command is missing, this step was skipped.

## Where your settings live

The config file is `%USERPROFILE%\.config\obsidian-second-brain\.env`. Python, Claude Code and the scripts all look there, even when a company setup points `HOME` at another drive (#242). To keep it somewhere else, set `OBSIDIAN_ENV_FILE` to a native path such as `C:/Users/you/osb.env`. The README has the [exact commands](README.md#research-toolkit-optional).

## Text encoding

Every script reads and writes UTF-8. A note that an old Windows run saved in the cp1252 code page stays as it is, and the research toolkit skips appending to it (#246, #248). Open that note in Obsidian or VS Code and save it once. The next run appends as normal.

## Vault in OneDrive or another synced folder

This works. Moving a note inside a synced folder is safe since #343 (#324).

## If something looks wrong

- **"no working Python found (tried python3, python, py -3, uv run)"**: install Python from python.org or uv, then restart Claude Code.
- **A slash command is missing after an update**: run `bash update.sh`, then restart.
- **A research command saved its note, but the daily note did not change**: see [Text encoding](#text-encoding).
- **Something else**: open a [bug report](https://github.com/eugeniughelbur/obsidian-second-brain/issues/new?template=bug_report.yml) and pick Windows as the operating system.
