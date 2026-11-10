#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""Find other vault tooling that registers a SessionStart hook (#300).

Claude Code merges hook entries instead of replacing them: "Hook entries merge
across settings levels", "All matching hooks run in parallel", and "A plugin's or
skill's copy of the same handler stays separate"
(https://code.claude.com/docs/en/hooks). SessionStart adds every hook's stdout to
context. So a user running a second Obsidian plugin gets two operating manuals in
one session, each describing a different folder map and frontmatter schema for the
same vault, with nothing saying which one governs a write.

This module finds the other hook. It does not touch it. The caller states
precedence; nobody's settings are edited, disabled or unregistered.

Two places register a SessionStart command hook:

1. Settings files - `~/.claude/settings.json`, and a project's `.claude/settings.json`
   and `.claude/settings.local.json`. Entries live under `hooks.SessionStart[].hooks[]`.
2. Plugins - each installed plugin's own `hooks/hooks.json`, in the same shape.
   `~/.claude/plugins/installed_plugins.json` maps a plugin name to its `installPath`.
   Only installs that load in this session count (#355): a `project` or `local`
   install applies to its `projectPath` and the folders under it, and a plugin set
   to false in `enabledPlugins` (user, then project, then local settings, the
   narrower file winning) does not run at all.

Every read is defensive. This runs inside the SessionStart hook, where an exception
costs the session its skill root and its vault manual, so a malformed settings file
or a plugin directory that moved yields no detections rather than a traceback.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# A hook is ours when its command names the entry point, under any install mode
# (plugin, skill symlink, direct clone) and any path spelling.
OURS = "load_vault_context"

# Detection is a substring test on the hook command, because a plugin is free to
# name its entry point anything. A bare "vault" was considered and dropped: it
# matches HashiCorp Vault tooling, and a wrong precedence note is worse than a
# missed one, since it tells a session to follow a manual against rules that were
# never in competition with it.
VAULT_MARKERS = ("obsidian", "second-brain", "secondbrain")


def _load_json(path: Path) -> dict:
    """A settings or manifest file as a dict; {} for missing, unreadable or malformed."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _commands(settings: dict) -> list[str]:
    """Every SessionStart command string in one hooks manifest.

    Claude Code accepts the command as a bare string and as a string plus `args`
    (claude-obsidian registers `"command": "python3"` with the script in `args`),
    so both forms are flattened into one line to test.
    """
    found: list[str] = []
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return found
    groups = hooks.get("SessionStart")
    if not isinstance(groups, list):
        return found
    for group in groups:
        if not isinstance(group, dict):
            continue
        entries = group.get("hooks")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            command = entry.get("command")
            if not isinstance(command, str):
                continue
            args = entry.get("args")
            if isinstance(args, list):
                command = " ".join([command] + [a for a in args if isinstance(a, str)])
            found.append(command)
    return found


def _is_other_vault_tool(command: str) -> bool:
    """True for a SessionStart hook that is vault tooling and is not ours."""
    lowered = command.lower()
    if OURS in lowered:
        return False
    return any(marker in lowered for marker in VAULT_MARKERS)


def _settings_files(home: Path, project_dir: Path | None) -> list[Path]:
    files = [home / ".claude" / "settings.json"]
    if project_dir is not None:
        files.append(project_dir / ".claude" / "settings.json")
        files.append(project_dir / ".claude" / "settings.local.json")
    return files


def _disabled_plugins(home: Path, project_dir: Path | None) -> set[str]:
    """Plugin names set to false in `enabledPlugins` for this session.

    Later settings files override earlier ones, as in Claude Code, so a project can
    turn back on a plugin the user turned off. Only an explicit false counts: an
    install with no entry is left enabled, which is how a user-scope install looks.
    """
    enabled: dict[str, object] = {}
    for path in _settings_files(home, project_dir):
        entries = _load_json(path).get("enabledPlugins")
        if isinstance(entries, dict):
            enabled.update(entries)
    return {str(name) for name, value in enabled.items() if value is False}


def _applies_here(install: dict, project_dir: Path | None) -> bool:
    """True when this install loads in a session started in `project_dir`.

    A `project` or `local` install belongs to its `projectPath`. A session in that
    folder or one under it counts, since missing a real collision costs more than
    a note about one; a sibling project does not.
    """
    if install.get("scope") not in ("project", "local"):
        return True
    project_path = install.get("projectPath")
    if project_dir is None or not isinstance(project_path, str):
        return False
    try:
        here = project_dir.resolve()
        there = Path(project_path).resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    return here == there or there in here.parents


def _plugin_manifests(home: Path, project_dir: Path | None) -> list[tuple[str, Path]]:
    """(plugin name, its hooks.json) for every plugin this session loads that ships one."""
    registry = _load_json(home / ".claude" / "plugins" / "installed_plugins.json")
    plugins = registry.get("plugins")
    if not isinstance(plugins, dict):
        return []
    disabled = _disabled_plugins(home, project_dir)
    manifests: list[tuple[str, Path]] = []
    for name, installs in plugins.items():
        if not isinstance(installs, list) or str(name) in disabled:
            continue
        for install in installs:
            if not isinstance(install, dict) or not _applies_here(install, project_dir):
                continue
            install_path = install.get("installPath")
            if not isinstance(install_path, str):
                continue
            manifest = Path(install_path) / "hooks" / "hooks.json"
            if manifest.is_file():
                manifests.append((str(name), manifest))
    return manifests


def scan(home: Path | None = None, project_dir: Path | None = None) -> list[dict]:
    """Other vault tooling holding a SessionStart hook, as {source, command} dicts.

    `home` defaults to the user's home directory and `project_dir` to the working
    directory, both injectable so the tests never read the developer's own install.
    """
    home = Path.home() if home is None else home
    if project_dir is None:
        try:
            project_dir = Path.cwd()
        except OSError:
            project_dir = None

    found: list[dict] = []
    seen: set[str] = set()

    def record(source: str, command: str) -> None:
        # One line per command: the same plugin registered in settings and shipped
        # in a manifest is one piece of tooling, and saying so twice helps nobody.
        if command in seen:
            return
        seen.add(command)
        found.append({"source": source, "command": command})

    for path in _settings_files(home, project_dir):
        for command in _commands(_load_json(path)):
            if _is_other_vault_tool(command):
                record(str(path), command)

    for name, manifest in _plugin_manifests(home, project_dir):
        for command in _commands(_load_json(manifest)):
            if _is_other_vault_tool(command):
                record(f"plugin: {name}", command)

    return found


def precedence_block(detected: list[dict], manual_path: Path) -> str:
    """The precedence note injected ahead of the manual when other tooling is found.

    Says what else is loading vault rules into this session and which rules win, so
    a second schema does not arrive unannounced. The vault's own `_CLAUDE.md` wins
    because it is the file the user owns and edits.
    """
    lines = "\n".join(f"  - `{d['command']}` (from {d['source']})" for d in detected)
    plural = "hook" if len(detected) == 1 else "hooks"
    return (
        f"**Other vault tooling is active in this session.** {len(detected)} other SessionStart "
        f"{plural} also loads vault rules into your context:\n"
        f"{lines}\n"
        f"Claude Code runs every SessionStart hook and adds each one's output here, so you are "
        f"holding more than one set of folder and frontmatter rules for this vault.\n"
        f"**`{manual_path}` governs every write.** Where the other tooling's conventions "
        f"disagree with it - folder names, frontmatter fields, note titles - follow the manual "
        f"and say so in your reply. Do not mix the two schemas in one note.\n"
    )


def main() -> int:
    """`python -m scripts.vault_plugin_scan` - what an install would find, as a report.

    `--quiet` says nothing when there is nothing to say, which is how the installer
    calls it: a clean install should not print a line about a problem it does not
    have. Run by hand, the same clean result is worth confirming out loud.
    """
    quiet = "--quiet" in sys.argv[1:]
    detected = scan()
    if not detected:
        if not quiet:
            print("No other vault tooling found holding a SessionStart hook.")
        return 0
    print(f"Found {len(detected)} other SessionStart hook(s) that load vault rules:")
    for d in detected:
        print(f"  - {d['command']}\n      from {d['source']}")
    print(
        "\nClaude Code runs all of them and adds every output to context, so a session sees "
        "more than one folder and frontmatter schema for one vault.\n"
        "This skill does not change those hooks. Its SessionStart context names them and "
        "states that the vault's own _CLAUDE.md governs writes.\n"
        "To run only one, remove the other plugin or its hook entry yourself."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
