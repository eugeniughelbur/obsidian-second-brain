"""Claude Code replaces hook output over 10,000 characters with a 2 KB preview,
and the SessionStart hook measured nothing (#270). A real vault manual is larger
than that, so the session received its first section plus a header saying the
manual was "already loaded" and a SKILL.md rule telling it not to re-read the
file. Every rule past the cut stopped applying and nothing said so.

These pin the two halves of the fix: the hook refuses to claim a manual it could
not deliver, and a bootstrapped vault carries the native `@../_CLAUDE.md` import
that has no cap at all.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / "hooks/load_vault_context.py"
CAP = 10_000

MARKER = "LAST-RULE-IN-THE-MANUAL"


def run_hook(vault: Path, cwd: str | None = None) -> str:
    """The additionalContext string the session actually receives."""
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"cwd": cwd if cwd is not None else str(vault)}),
        env=dict(os.environ, OBSIDIAN_VAULT_PATH=str(vault)),
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


@pytest.fixture()
def vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    return v


def write_manual(vault: Path, body: str) -> Path:
    manual = vault / "_CLAUDE.md"
    manual.write_text(f"# Manual\n\n{body}\n{MARKER}\n", encoding="utf-8")
    return manual


def test_a_manual_that_fits_is_injected_whole(vault):
    """The ordinary path is unchanged: a small manual arrives complete, last line
    included, and still says it is loaded."""
    write_manual(vault, "one rule per line.\n" * 50)
    context = run_hook(vault)
    assert MARKER in context
    assert "already loaded" in context
    assert len(context) <= CAP


def test_a_manual_over_the_cap_is_not_announced_as_loaded(vault):
    """The bug was never the truncation on its own. It was a fragment delivered
    under a header that told the session it held the whole manual."""
    write_manual(vault, "a rule the session must follow.\n" * 1500)
    context = run_hook(vault)

    assert len(context) <= CAP, "the payload itself must stay under the cap"
    assert MARKER not in context, "the manual is not in there, and must not pretend to be"
    assert "already loaded" not in context
    assert "NOT loaded" in context
    assert "NOT in your context" in context
    assert str(vault / "_CLAUDE.md") in context, "it must say what to read"
    assert "@../_CLAUDE.md" in context, "and how to stop hitting the cap"


def test_the_size_is_counted_in_characters_not_bytes(vault):
    """A CJK manual runs about three bytes to the character. Measuring bytes
    would send a Chinese vault down the pointer path for a manual that fits -
    exactly the vault that filed #271 next door."""
    # \u8bf4\u660e = "explanation"; 3 bytes each, 1 character each.
    body = ("\u8bf4\u660e" * 35 + "\n") * 60
    manual = write_manual(vault, body)
    assert len(manual.read_bytes()) > CAP, "the byte count must exceed the cap for this to prove anything"
    assert len(manual.read_text(encoding="utf-8")) < CAP - 1000

    context = run_hook(vault)
    assert MARKER in context, "a manual that fits in characters must still be injected"


def test_the_skill_root_still_ships_when_the_manual_does_not(vault):
    """The skill root is the half no import can replace: a command needs the
    absolute install path to run a bundled script. It is published either way."""
    write_manual(vault, "a rule the session must follow.\n" * 1500)
    context = run_hook(vault)
    assert "**Skill root**" in context
    assert "obsidian-second-brain" in context


def test_a_session_outside_the_vault_gets_no_manual_either_way(vault, tmp_path):
    """Unchanged gate: the manual is only for a session working in the vault."""
    write_manual(vault, "one rule per line.\n" * 50)
    context = run_hook(vault, cwd=str(tmp_path / "elsewhere"))
    assert MARKER not in context and "NOT loaded" not in context
    assert "**Skill root**" in context


# ── #285: the vault configured only in the marketplace-install config file ──

def run_hook_via_env_file(vault: Path, env_file: Path | None) -> str:
    """Same as run_hook(), except OBSIDIAN_VAULT_PATH is never a real process
    env var - only OBSIDIAN_ENV_FILE points at where the config lives, exactly
    what a marketplace install leaves behind (#285)."""
    env = dict(os.environ)
    env.pop("OBSIDIAN_VAULT_PATH", None)
    if env_file is not None:
        env["OBSIDIAN_ENV_FILE"] = str(env_file)
    else:
        env.pop("OBSIDIAN_ENV_FILE", None)
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"cwd": str(vault)}),
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


def test_a_vault_configured_only_in_the_env_file_still_gets_its_manual(vault, tmp_path):
    """The bug itself: a marketplace install writes OBSIDIAN_VAULT_PATH into the
    config .env and never exports it, so an env-only check finds nothing - on
    every session, including one whose cwd IS the vault. #124, #160, #269 were
    the same root cause in three other callers; this is the fourth, in the
    SessionStart hook itself."""
    write_manual(vault, "one rule per line.\n" * 50)
    env_file = tmp_path / ".env"
    env_file.write_text(f"OBSIDIAN_VAULT_PATH={vault}\n", encoding="utf-8")

    context = run_hook_via_env_file(vault, env_file)
    assert MARKER in context, "the manual must load from the config file alone"
    assert "already loaded" in context


def test_no_config_file_at_all_is_silent_not_an_exception(vault, tmp_path):
    """The fallback must not turn a fresh machine, with no config written yet,
    into a hook that raises instead of a hook that says nothing."""
    context = run_hook_via_env_file(vault, tmp_path / "nope" / ".env")
    assert "**Skill root**" in context
    assert MARKER not in context and "NOT loaded" not in context


def test_skill_md_does_not_tell_a_session_to_skip_on_the_hook_alone():
    """SKILL.md sent the session past `_CLAUDE.md` whenever the hook was
    configured, which is what turned a capped payload into a silent failure."""
    text = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "If the SessionStart hook is active, `_CLAUDE.md` is already in context - skip this step." \
        not in text, "the unconditional skip is back"
    assert "Skip step 1 only when the manual is actually in your context" in text
    assert "10,000" in text, "SKILL.md should name the limit it is protecting against"


def test_bootstrap_writes_the_native_import(tmp_path):
    """A vault built by the bootstrapper loads its manual through Claude Code's
    own import, which has a 4 MiB limit and needs no interpreter - the fix that
    survives whatever the hook cap does next."""
    vault = tmp_path / "vault"
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/bootstrap_vault.py"),
         "--path", str(vault), "--name", "Test", "--preset", "default", "--no-sidebiz"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    imported = vault / ".claude" / "CLAUDE.md"
    assert imported.is_file(), "bootstrap wrote no .claude/CLAUDE.md"
    assert "@../_CLAUDE.md" in imported.read_text(encoding="utf-8")
    assert (vault / "_CLAUDE.md").is_file(), "the import must point at a file that exists"
