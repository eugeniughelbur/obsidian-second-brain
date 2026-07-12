"""Install-portability fences (stress-test round 2).

A plugin-installed command runs from the user's vault, not from a clone of this repo,
and CLAUDE_PLUGIN_ROOT is not exported to the Bash a command later runs. So a command
must never point at the maintainer's personal clone path, and every bundled-script
invocation must anchor to the skill root the SessionStart hook publishes
(`uv run --directory "SKILL_ROOT" ...`). These tests fail the build if either drifts.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMANDS = sorted((REPO_ROOT / "commands").glob("*.md"))

sys.path.insert(0, str(REPO_ROOT / "hooks"))
import load_vault_context  # noqa: E402  (import after sys.path shim, matching sibling tests)


def test_commands_exist_to_check():
    assert COMMANDS, "no command files found - glob or layout changed"


def test_no_command_hardcodes_the_maintainer_clone_path():
    offenders = [
        c.name for c in COMMANDS
        if "Projects/personal/obsidian-second-brain" in c.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"commands hardcode a personal clone path: {offenders}"


# A bundled-script invocation is a `uv run`/`python` command that runs `-m scripts.<x>`
# or a `scripts/<x>.py` file. `[^`\n]*` keeps the match inside one inline-code span or
# fenced line so surrounding prose can't smear across it.
_INVOCATION = re.compile(r"(?:uv run|python3?)[^`\n]*\bscripts[./]")


def test_every_bundled_script_invocation_anchors_to_skill_root():
    problems = []
    for c in COMMANDS:
        for lineno, line in enumerate(c.read_text(encoding="utf-8").splitlines(), 1):
            if _INVOCATION.search(line) and '--directory "SKILL_ROOT"' not in line:
                problems.append(f"{c.name}:{lineno}: {line.strip()}")
    assert problems == [], (
        "these script invocations are not anchored to the published skill root "
        '(expected `uv run --directory "SKILL_ROOT" ...`):\n' + "\n".join(problems)
    )


def test_hook_publishes_skill_root_for_this_repo():
    block = load_vault_context.skill_root_block()
    assert "**Skill root**" in block
    assert str(REPO_ROOT) in block
    # It must teach the exact portable invocation the commands depend on.
    assert "uv run --directory" in block


def test_hook_prefers_claude_plugin_root_when_set(monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/opt/plugins/osb")
    block = load_vault_context.skill_root_block()
    assert "/opt/plugins/osb" in block
    assert "Projects/personal" not in block
