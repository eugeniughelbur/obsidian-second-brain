"""Adversarial frontmatter inputs for the adapter parser.

Both defects here share a failure shape: the parser produced something
non-empty, so every downstream fallback thought it had a real value and the
build exited 0 with a broken artifact.

  B5 A UTF-8 BOM makes line 1 `﻿---`, which never matches /^---$/. The
     frontmatter fence is therefore never found: `description` falls back to the
     generic "Run the <name> command" string and command_body prints nothing, so
     the platform ships a skill whose instructions are an empty file.

  B6 `description: >` puts only the indicator on the key line, so the parser
     returned a literal ">". Non-empty, so the empty-value fallback never fired,
     and Codex, Antigravity, OpenCode and Hermes all select skills by
     description - making the command permanently unreachable. Not hypothetical:
     adapters/pi/adapter.sh emits a folded description itself.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LIB = REPO_ROOT / "adapters" / "lib.sh"
# Resolved by path: on Windows a bare "bash" can resolve to WSL's launcher in System32.
BASH = shutil.which("bash") or "/bin/bash"


def _call(fn: str, path: Path, *args: str) -> str:
    """Invoke one lib.sh helper in isolation."""
    cmd = f'source "{LIB}"; {fn} "{path}" {" ".join(args)}'
    result = subprocess.run([BASH, "-c", cmd], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout


PLAIN = "---\ndescription: Save the conversation to the vault.\ncategory: vault\n---\n\nStep one.\nStep two.\n"


def test_plain_frontmatter_is_the_control(tmp_path):
    f = tmp_path / "cmd.md"
    f.write_text(PLAIN, encoding="utf-8")
    assert _call("parse_frontmatter", f, "description").strip() == "Save the conversation to the vault."
    assert "Step one." in _call("command_body", f)


def test_a_bom_does_not_hide_the_frontmatter(tmp_path):
    f = tmp_path / "bom.md"
    f.write_text(PLAIN, encoding="utf-8-sig")

    desc = _call("parse_frontmatter", f, "description").strip()
    assert desc == "Save the conversation to the vault.", (
        f"a BOM'd command file parsed its description as {desc!r}; the fence never "
        "matched, so the build falls back to a generic string"
    )


def test_a_bom_does_not_empty_the_command_body(tmp_path):
    f = tmp_path / "bom.md"
    f.write_text(PLAIN, encoding="utf-8-sig")

    body = _call("command_body", f)
    assert "Step one." in body and "Step two." in body, (
        "a BOM'd command file emitted an empty body, so the platform ships a "
        f"skill with no instructions in it. Got: {body!r}"
    )


@pytest.mark.parametrize("indicator", [">", "|", ">-", "|-"])
def test_a_block_scalar_description_is_folded_not_returned_literally(tmp_path, indicator):
    f = tmp_path / "folded.md"
    f.write_text(
        f"---\ndescription: {indicator}\n"
        "  Save the conversation to the vault.\n"
        "  Use when the user says save this.\n"
        "category: vault\n---\n\nStep one.\n",
        encoding="utf-8",
    )

    desc = _call("parse_frontmatter", f, "description").strip()
    assert desc not in (">", "|", ">-", "|-"), (
        f"a `description: {indicator}` block returned the bare indicator. It is "
        "non-empty, so the generic fallback never fires, and the platforms that "
        "select skills by description cannot reach this command at all."
    )
    assert "Save the conversation to the vault." in desc
    assert "Use when the user says save this." in desc


def test_a_block_scalar_does_not_swallow_the_rest_of_the_frontmatter(tmp_path):
    """Folding must stop at the next key, not run into the closing fence."""
    f = tmp_path / "folded.md"
    f.write_text(
        "---\ndescription: >\n  Folded text.\ncategory: vault\n---\n\nStep one.\n",
        encoding="utf-8",
    )
    assert _call("parse_frontmatter", f, "category").strip() == "vault", (
        "the block-scalar fold consumed the following key"
    )
    assert "Step one." in _call("command_body", f)


def test_crlf_line_endings_still_parse(tmp_path):
    """Pre-existing behaviour that the BOM change must not disturb."""
    f = tmp_path / "crlf.md"
    f.write_bytes(PLAIN.replace("\n", "\r\n").encode("utf-8"))
    assert _call("parse_frontmatter", f, "description").strip() == "Save the conversation to the vault."
    assert "Step one." in _call("command_body", f)
