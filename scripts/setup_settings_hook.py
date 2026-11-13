#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""Register the SessionStart context hook in ~/.claude/settings.json (idempotent).

install.sh calls this for the skill / manual install so slash commands get the skill
root published into context, exactly as the plugin install does on its own. Without it,
a skill-installed command has no way to locate its bundled scripts.

Safe to re-run: it adds the hook only when an equivalent one is absent, refreshes the
path if the skill moved, and never touches unrelated settings. If settings.json is not
valid JSON it prints a manual instruction and exits 0 rather than clobbering the file.
"""
from __future__ import annotations

import json
import shlex
from pathlib import Path

# The hook is registered at the canonical skill-install location (a symlink or a direct
# clone that install.sh sets up), not the repo clone path, so it stays valid if the repo
# lives elsewhere. The hook resolves its own real path at runtime, so this is enough.
# The .sh wrapper, not the .py. `python3` is the Microsoft Store App Execution
# Alias on a stock Windows install: it exists, prints nothing, exits non-zero, so
# the hook injected nothing and said nothing (#269). The wrapper resolves an
# interpreter that runs before handing over.
HOOK_PATH = Path.home() / ".claude" / "skills" / "obsidian-second-brain" / "hooks" / "load_vault_context.sh"


def hook_command(path: Path) -> str:
    """The hook command as the shell that runs it will read it.

    Claude Code hands a command hook to a shell, Git Bash on Windows. str(path) is
    C:\\Users\\... there, and Git Bash reads every backslash as an escape, so the hook
    failed with "No such file or directory" at every session start (#281); an unquoted
    path with a space splits in two on any platform. Forward slashes run in Git Bash, and
    shlex.quote leaves an ordinary POSIX path exactly as str() wrote it, so an entry
    registered on macOS or Linux before this change still reads as unchanged.
    """
    return shlex.quote(path.as_posix())


HOOK_CMD = hook_command(HOOK_PATH)


def register(settings: dict) -> tuple[dict, str]:
    """Add or refresh the load_vault_context SessionStart hook. Pure: no I/O."""
    hooks = settings.setdefault("hooks", {})
    session_start = hooks.setdefault("SessionStart", [])
    for group in session_start:
        for h in group.get("hooks", []):
            # Matched without the extension so an entry registered before #269
            # (`python3 <...>/load_vault_context.py`) is found and rewritten, not
            # left in place next to a second, working one.
            if "load_vault_context" in h.get("command", ""):
                if h["command"] == HOOK_CMD:
                    return settings, "unchanged"
                h["command"] = HOOK_CMD
                return settings, "refreshed"
    session_start.append({"matcher": "", "hooks": [{"type": "command", "command": HOOK_CMD}]})
    return settings, "added"


def main() -> int:
    path = Path.home() / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.is_file():
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            print("  settings.json is not valid JSON - add this SessionStart hook manually:")
            print(f"    {HOOK_CMD}")
            return 0
    else:
        settings = {}

    settings, action = register(settings)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    print(f"  SessionStart context hook {action} in {path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
