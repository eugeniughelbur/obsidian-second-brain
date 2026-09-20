"""The write-time hook skips the vault's config directory, and only that one.

The skip list carried a bare `*/.obsidian/*`, which matches the segment anywhere
in a path rather than under the vault root. A vault kept inside a directory
called `.obsidian` therefore matched on every note, and the hook returned
silently for the whole vault: no warning, no error, nothing to indicate the
checks never ran. These pin the scope to the vault's own config directory and
keep the ordinary case working.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / "hooks/validate-ai-first.sh"

# No frontmatter and no preamble, so a validated note always warns and a skipped
# one always stays quiet. That difference is the whole assertion.
BARE_NOTE = "# A note\n\nBody text.\n"


def run(vault: Path, note: Path):
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(note)}}),
        env=dict(os.environ, OBSIDIAN_VAULT_PATH=str(vault)),
        capture_output=True, text=True,
    )


def message(result) -> str:
    """The warning the session is handed, or "" when the hook passed the note."""
    assert result.returncode == 0, result.stderr
    if not result.stdout.strip():
        return ""
    return json.loads(result.stdout)["systemMessage"]


def write(vault: Path, relative: str) -> Path:
    note = vault / relative
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(BARE_NOTE, encoding="utf-8")
    return note


@pytest.fixture()
def nested_vault(tmp_path):
    """A vault below a directory named `.obsidian`, which is what the bare
    pattern matched on. Obsidian allows it and several setups use it."""
    v = tmp_path / ".obsidian" / "life-os"
    v.mkdir(parents=True)
    return v


@pytest.fixture()
def plain_vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    return v


def test_note_in_a_vault_under_dot_obsidian_is_still_checked(nested_vault):
    note = write(nested_vault, "wiki/concepts/Some Note.md")
    assert message(run(nested_vault, note)), (
        "a vault whose path contains .obsidian had every note skipped silently"
    )


def test_the_vaults_own_config_directory_is_skipped(plain_vault):
    note = write(plain_vault, ".obsidian/plugins/example/README.md")
    assert message(run(plain_vault, note)) == ""


def test_config_directory_is_skipped_in_a_nested_vault_too(nested_vault):
    note = write(nested_vault, ".obsidian/plugins/example/README.md")
    assert message(run(nested_vault, note)) == ""


def test_ordinary_note_is_still_checked(plain_vault):
    note = write(plain_vault, "wiki/concepts/Some Note.md")
    assert message(run(plain_vault, note))


def test_a_note_named_like_the_config_directory_is_checked(plain_vault):
    """`.obsidian` as a folder name deeper in the vault is a user folder, not
    the config directory, so it gets the same checks as anything else."""
    note = write(plain_vault, "wiki/.obsidian/Note.md")
    assert message(run(plain_vault, note))
