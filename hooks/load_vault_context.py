#!/usr/bin/env python3
"""SessionStart hook: inject _CLAUDE.md into context once per session.

Gated to the AI-Brain vault: fires only when the session's cwd is inside
$OBSIDIAN_VAULT_PATH. Skips silently otherwise (any output would land in
the model's context for non-vault sessions, which is not what we want).

Setup:
    1. Set OBSIDIAN_VAULT_PATH in ~/.claude/settings.json env section
    2. Register as a SessionStart hook in ~/.claude/settings.json:
         { "type": "command",
           "command": "python ~/.claude/skills/obsidian-second-brain/hooks/load_vault_context.py" }

Path normalization handles Windows ("C:\\..."), MSYS ("/c/..."), and POSIX
("/...") — match works regardless of which form the harness or env var uses.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


def normalize(p: str) -> str:
    """Lowercase drive letter, forward slashes, no trailing slash."""
    if not p:
        return ""
    p = p.replace("\\", "/")
    m = re.match(r"^([A-Za-z]):(.*)$", p)
    if m:
        p = f"/{m.group(1).lower()}{m.group(2)}"
    return p.rstrip("/")


def main() -> int:
    vault = os.environ.get("OBSIDIAN_VAULT_PATH", "")
    if not vault:
        return 0

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    cwd = payload.get("cwd", "")
    vault_n = normalize(vault)
    cwd_n = normalize(cwd)

    if not (cwd_n == vault_n or cwd_n.startswith(vault_n + "/")):
        return 0

    claude_md = Path(vault) / "_CLAUDE.md"
    if not claude_md.is_file():
        return 0

    content = claude_md.read_text(encoding="utf-8")

    v = Path(vault)
    header = (
        f"**Vault root**: `{vault}`\n"
        f"**Key files** (absolute paths — use these directly, no discovery needed):\n"
        f"  - `{v / '_CLAUDE.md'}` — this operating manual (already loaded)\n"
        f"  - `{v / 'index.md'}` — navigation hub\n"
        f"  - `{v / 'log.md'}` — operation log\n"
        "**Do NOT run `ls`, `Glob`, or `Bash` to discover the vault or its folders.**\n"
        "Use the vault root path above and the folder names from the manual below directly.\n\n"
        "---\n\n"
        "Vault operating manual (_CLAUDE.md, loaded once at session start "
        "by the load_vault_context hook — do not re-read on each command):\n\n"
    )

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": header + content,
        }
    }
    json.dump(output, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
