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
   has no use for, and capped: Claude Code replaces any hook output over 10,000
   characters with a 2 KB preview plus a file path, so a manual larger than that
   arrives cut off inside its first section. Since the header says the manual is
   already loaded and SKILL.md tells the session not to re-read it, a truncated
   manual reads as a complete one and every rule past the cut silently stops
   applying (#270). Over the budget the hook injects a pointer that says the manual
   is NOT loaded and must be read, instead of a fragment that claims it is.

   The better fix is upstream of this hook: a vault whose `.claude/CLAUDE.md`
   holds `@../_CLAUDE.md` gets the whole manual loaded natively by Claude Code, at
   any size and with no interpreter involved. `/obsidian-init` and
   `bootstrap_vault.py` write that import; this cap is the floor under vaults that
   do not have it.

Path normalization handles Windows ("C:\\..."), MSYS ("/c/..."), and POSIX ("/...")
so the vault match works regardless of which form the harness or env var uses.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import osb_env  # noqa: E402  (depends on the sys.path insert above)

# Claude Code caps a hook's output strings, additionalContext included, at
# 10,000 characters and replaces anything larger with a 2 KB preview. The margin
# covers the skill-root block that shares the payload and any wording change to
# the header, so the manual is never the thing that pushes it over.
CONTEXT_CAP = 10_000
CONTEXT_MARGIN = 500


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


def vault_manual_path() -> Path | None:
    """The vault's _CLAUDE.md when this session is inside that vault, else None."""
    vault = osb_env.vault_path()
    if not vault:
        return None
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return None

    cwd_n = normalize(payload.get("cwd", ""))
    vault_n = normalize(vault)
    if not (cwd_n == vault_n or cwd_n.startswith(vault_n + "/")):
        return None

    claude_md = Path(vault) / "_CLAUDE.md"
    return claude_md if claude_md.is_file() else None


def _key_files(v: Path, manual_note: str) -> str:
    """The vault header both forms share. `manual_note` says whether the manual
    below is the real thing or a pointer to it - the one line a session uses to
    decide whether it still has to read the file."""
    return (
        f"**Vault root**: `{v}`\n"
        f"**Key files** (absolute paths - use these directly, no discovery needed):\n"
        f"  - `{v / '_CLAUDE.md'}` - this operating manual ({manual_note})\n"
        f"  - `{v / 'index.md'}` - navigation hub\n"
        f"  - `{v / 'log.md'}` - operation log\n"
        "**Do NOT run `ls`, `Glob`, or `Bash` to discover the vault or its folders.**\n"
    )


def full_manual_block(claude_md: Path, text: str) -> str:
    """The manual itself, for a session that is about to receive all of it."""
    v = claude_md.parent
    return (
        _key_files(v, "already loaded")
        + "Use the vault root path above and the folder names from the manual below directly.\n\n"
        "---\n\n"
        "Vault operating manual (_CLAUDE.md, loaded once at session start "
        "by the load_vault_context hook - do not re-read on each command):\n\n"
        + text
    )


def pointer_block(claude_md: Path, size: int) -> str:
    """What a session gets when the manual does not fit in a hook payload.

    Says the manual is NOT loaded, in the same breath as the path to read. The
    failure this replaces is not the truncation, it is a truncated manual
    announced as a loaded one (#270).
    """
    v = claude_md.parent
    return (
        _key_files(v, "NOT loaded - read it, see below")
        + "\n"
        f"The vault operating manual is {size:,} characters, over the {CONTEXT_CAP:,}-character "
        "limit Claude Code puts on hook context, so it could NOT be injected here and is "
        "NOT in your context.\n"
        f"**Read `{claude_md}` in full before acting on this vault.** Its rules override the "
        "skill defaults, and you do not have them yet.\n"
        f"To load it automatically instead, put `@../_CLAUDE.md` in `{v / '.claude' / 'CLAUDE.md'}` "
        "- Claude Code imports that natively at any size.\n"
    )


def main() -> int:
    sections = [skill_root_block()]
    claude_md = vault_manual_path()
    if claude_md is not None:
        # Characters, not bytes: the cap counts characters and a CJK manual runs
        # about three bytes to each one, so st_size would reject manuals that fit.
        text = claude_md.read_text(encoding="utf-8")
        manual = full_manual_block(claude_md, text)
        # Measured against the whole payload, because the skill-root block is in
        # it too and the cap applies to the string the hook returns.
        if len(sections[0]) + len(manual) <= CONTEXT_CAP - CONTEXT_MARGIN:
            sections.append(manual)
        else:
            sections.append(pointer_block(claude_md, len(text)))

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
