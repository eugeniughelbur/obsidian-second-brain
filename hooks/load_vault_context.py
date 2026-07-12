#!/usr/bin/env python3
"""SessionStart hook: tell the session where the skill lives, and (inside the vault)
load the vault's _CLAUDE.md operating manual.

Two pieces of context are injected:

1. **Skill root** - always. Slash commands run bundled scripts (`uv run --directory
   <root> -m scripts...`) and read bundled `references/`, but CLAUDE_PLUGIN_ROOT is
   only set for plugin hook/MCP subprocesses, NOT for the Bash a command later runs.
   So the model must carry the absolute install path itself; this hook publishes it.
   The path comes from CLAUDE_PLUGIN_ROOT when set, else from this file's own location
   (the hook always lives at <skill root>/hooks/, in every install mode).

2. **Vault manual** - only when the session's cwd is inside $OBSIDIAN_VAULT_PATH and
   that vault has a _CLAUDE.md. Gated so a non-vault session doesn't get a manual it
   has no use for.

Path normalization handles Windows ("C:\\..."), MSYS ("/c/..."), and POSIX ("/...")
so the vault match works regardless of which form the harness or env var uses.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def normalize(p: str) -> str:
    """Lowercase drive letter, forward slashes, no trailing slash."""
    if not p:
        return ""
    p = p.replace("\\", "/")
    import re
    m = re.match(r"^([A-Za-z]):(.*)$", p)
    if m:
        p = f"/{m.group(1).lower()}{m.group(2)}"
    return p.rstrip("/")


def skill_root_block() -> str:
    """Where this skill is installed, plus how to run its scripts from anywhere."""
    root = os.environ.get("CLAUDE_PLUGIN_ROOT") or str(Path(__file__).resolve().parents[1])
    return (
        f"**Skill root** (obsidian-second-brain): `{root}`\n"
        f"Its bundled `scripts/`, `references/`, and `commands/` live under that path. "
        f"To run a bundled script from any working directory, hand the root to uv, e.g. "
        f'`uv run --directory "{root}" -m scripts.research.research "<topic>"`. '
        f"Do not cd, and do not assume a cloned-repo location.\n"
    )


def vault_manual_block() -> str:
    """The vault _CLAUDE.md manual, or "" when the session is not inside the vault."""
    vault = os.environ.get("OBSIDIAN_VAULT_PATH", "")
    if not vault:
        return ""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return ""

    cwd_n = normalize(payload.get("cwd", ""))
    vault_n = normalize(vault)
    if not (cwd_n == vault_n or cwd_n.startswith(vault_n + "/")):
        return ""

    claude_md = Path(vault) / "_CLAUDE.md"
    if not claude_md.is_file():
        return ""

    v = Path(vault)
    header = (
        f"**Vault root**: `{vault}`\n"
        f"**Key files** (absolute paths - use these directly, no discovery needed):\n"
        f"  - `{v / '_CLAUDE.md'}` - this operating manual (already loaded)\n"
        f"  - `{v / 'index.md'}` - navigation hub\n"
        f"  - `{v / 'log.md'}` - operation log\n"
        "**Do NOT run `ls`, `Glob`, or `Bash` to discover the vault or its folders.**\n"
        "Use the vault root path above and the folder names from the manual below directly.\n\n"
        "---\n\n"
        "Vault operating manual (_CLAUDE.md, loaded once at session start "
        "by the load_vault_context hook - do not re-read on each command):\n\n"
    )
    return header + claude_md.read_text(encoding="utf-8")


def main() -> int:
    sections = [skill_root_block()]
    manual = vault_manual_block()
    if manual:
        sections.append(manual)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n".join(sections),
        }
    }
    json.dump(output, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
