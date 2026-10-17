"""Check 5 must preserve filename punctuation inside closed Obsidian links."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from _bash import BASH

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / "hooks/validate-ai-first.sh"

EM_DASH = "\u2014"
EN_DASH = "\u2013"
LEFT_QUOTE = "\u201c"
NBSP = "\u00a0"
FRONTMATTER = (
    "---\ndate: 2026-10-07\ntype: concept\ntags:\n  - concept\nai-first: true\n---\n\n"
    "## For future agent\n"
)


def run(vault: Path, note: Path):
    return subprocess.run(
        [BASH, str(HOOK)],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(note)}}),
        env=dict(os.environ, OBSIDIAN_VAULT_PATH=str(vault)),
        capture_output=True,
        text=True,
    )


def message(result) -> str:
    assert result.returncode == 0, result.stderr
    if not result.stdout.strip():
        return ""
    return json.loads(result.stdout)["systemMessage"]


@pytest.fixture()
def vault(tmp_path):
    path = tmp_path / "vault"
    path.mkdir()
    return path


def write(vault: Path, body: str) -> Path:
    note = vault / "note.md"
    note.write_text(FRONTMATTER + body, encoding="utf-8")
    return note


def test_em_dash_in_closed_wikilink_target_is_not_flagged(vault):
    body = f"See [[Dev Logs/2026-08-09 {EM_DASH} Harness pass]] for detail.\n"
    assert message(run(vault, write(vault, body))) == ""


def test_em_dash_in_closed_embed_target_is_not_flagged(vault):
    body = f"![[Daily/2026-08-09 {EM_DASH} Harness pass]]\n"
    assert message(run(vault, write(vault, body))) == ""


def test_em_dash_in_target_with_heading_anchor_is_not_flagged(vault):
    body = f"See [[Daily/2026-08-09 {EM_DASH} Harness pass#Checks]]\n"
    assert message(run(vault, write(vault, body))) == ""


def test_em_dash_in_frontmatter_link_target_is_not_flagged(vault):
    note = vault / "note.md"
    note.write_text(
        f'---\ndate: 2026-10-07\ntype: concept\ntags: [concept]\nai-first: true\nsource: "[[Daily/{EM_DASH}]]"\n---\n\n'
        "## For future agent\nNo substitution characters here.\n",
        encoding="utf-8",
    )
    assert message(run(vault, note)) == ""


def test_only_target_is_skipped_while_alias_and_adjacent_prose_are_checked(vault):
    body = (
        f"Before {EN_DASH} [[Daily/{EM_DASH}|name {LEFT_QUOTE}alias{LEFT_QUOTE}]] "
        f"after {EN_DASH}.\n"
    )
    msg = message(run(vault, write(vault, body)))
    assert "U+2014" not in msg
    assert "U+2013" in msg
    assert "U+201C" in msg


def test_non_ascii_alias_text_is_still_checked(vault):
    body = f"[[Daily/normal|alias {EM_DASH}]]\n"
    assert "U+2014" in message(run(vault, write(vault, body)))


def test_non_ascii_prose_next_to_a_link_is_still_checked(vault):
    body = f"[[Daily/{EM_DASH}]] text {EN_DASH}\n"
    assert "U+2013" in message(run(vault, write(vault, body)))


def test_nonbreaking_space_inside_target_is_still_checked(vault):
    body = f"[[Daily/part{NBSP}two]]\n"
    assert "U+00A0" in message(run(vault, write(vault, body)))


def test_unclosed_wikilink_forms_remain_checked(vault):
    body = (
        f"[[unclosed {EM_DASH}\n"
        f"`[[code span {EM_DASH}\n"
        f"[[unclosed|alias {EM_DASH}\n"
    )
    assert message(run(vault, write(vault, body))).count("U+2014") == 3


def test_cjk_punctuation_carveout_is_unchanged(vault):
    body = f"\u8fc7\u5ea6\u62df\u5408 {EM_DASH}{EM_DASH}\n"
    assert message(run(vault, write(vault, body))) == ""


def test_em_dash_in_code_span_outside_a_link_is_still_checked(vault):
    body = f"`example {EM_DASH} text`\n"
    assert "U+2014" in message(run(vault, write(vault, body)))
