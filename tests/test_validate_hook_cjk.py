"""Check 5 of the write-time hook bans substitution Unicode, and CJK prose uses
the same codepoints as its ordinary punctuation (#271). On a Chinese vault every
write came back with its own punctuation listed as rule violations, which leaves
a session two options: rewrite the text into wrong typography, or stop trusting
the hook. These pin the carve-out, what stays banned regardless of language, and
the per-vault opt-out that landed with it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / "hooks/validate-ai-first.sh"
# Resolved by path: on Windows a bare "bash" can resolve to WSL's launcher in System32.
BASH = shutil.which("bash") or "/bin/bash"

FRONTMATTER = (
    "---\ndate: 2026-09-14\ntype: concept\ntags:\n  - concept\nai-first: true\n---\n\n"
    "## For future agent\n"
)

# Written as escapes so this file stays ASCII: the repo bans the very characters
# under test in its own sources, and a literal copy here would trip the fence in
# tests/test_no_banned_chars_in_instructions.py.
EM_DASH = "\u2014"
ELLIPSIS = "\u2026"
LDQUO, RDQUO = "\u201c", "\u201d"
CHINESE = "\u8fc7\u5ea6\u62df\u5408"          # a concept name
JAPANESE = "\u904e\u5b66\u7fd2\u306e\u8a71"   # kana + Han
KOREAN = "\uacfc\uc801\ud569 \uc774\uc57c\uae30"  # Hangul


def run(vault: Path, note: Path, **env):
    return subprocess.run(
        [BASH, str(HOOK)],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(note)}}),
        env=dict(os.environ, OBSIDIAN_VAULT_PATH=str(vault), **env),
        capture_output=True, text=True,
    )


def message(result) -> str:
    """The warning the session is handed, or "" when the hook passed the note."""
    assert result.returncode == 0, result.stderr
    if not result.stdout.strip():
        return ""
    return json.loads(result.stdout)["systemMessage"]


@pytest.fixture()
def vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    return v


def write(vault: Path, name: str, body: str) -> Path:
    note = vault / name
    note.write_text(FRONTMATTER + body, encoding="utf-8")
    return note


@pytest.mark.parametrize("script", [CHINESE, JAPANESE, KOREAN])
def test_cjk_punctuation_is_not_a_substitution(vault, script):
    """A dash, quotes and an ellipsis inside CJK text are that language's own
    punctuation. There is no ASCII equivalent to suggest."""
    body = f"{script}{EM_DASH}{EM_DASH}{LDQUO}{script}{RDQUO}{ELLIPSIS}{ELLIPSIS}\n"
    assert message(run(vault, write(vault, "cjk.md", body))) == ""


def test_the_same_characters_in_english_prose_are_still_flagged(vault):
    """The rule it protects is untouched: English prose with an em-dash and
    curly quotes is still the LLM default the ban exists for."""
    body = f"A line with an em-dash {EM_DASH} and {LDQUO}curly quotes{RDQUO} in it.\n"
    msg = message(run(vault, write(vault, "en.md", body)))
    assert "U+2014 em-dash" in msg and "U+201C" in msg


def test_unicode_math_and_nbsp_stay_banned_inside_cjk(vault):
    """No script writes >= as U+2265, and a non-breaking space is invisible
    damage in any language, so the carve-out does not reach them."""
    body = f"{CHINESE}\uff1a\u9608\u503c \u2265 0.9\u3002\u4e00\u4e2a\u00a0\u7a7a\u683c\u3002\n"
    msg = message(run(vault, write(vault, "math.md", body)))
    assert "U+2265" in msg and "U+00A0" in msg
    assert "em-dash" not in msg


def test_a_cjk_line_does_not_excuse_the_rest_of_the_note(vault):
    """The test is per line, not per file: an English paragraph in a Chinese
    note is still English prose."""
    body = f"{CHINESE}{EM_DASH}{EM_DASH}\u597d\u3002\n\nAn English line {EM_DASH} flagged.\n"
    msg = message(run(vault, write(vault, "mixed.md", body)))
    assert "line 12" in msg, msg
    assert "line 10" not in msg, msg


def test_skip_checks_turns_one_check_off_and_leaves_the_others(vault):
    """AI_FIRST_SKIP_CHECKS is the escape for a vault the hook is wrong about.
    It is per check: silencing 5 must not silence the secret scan."""
    body = (
        f"An em-dash {EM_DASH} here.\n"
        "key sk-test1234567890abcdefghijklmnop here\n"
    )
    note = write(vault, "both.md", body)

    plain = message(run(vault, note))
    assert "U+2014 em-dash" in plain and "secret material" in plain

    skipped = message(run(vault, note, AI_FIRST_SKIP_CHECKS="5"))
    assert "U+2014 em-dash" not in skipped
    assert "secret material" in skipped

    # Whitespace and a multi-value list are accepted as written.
    both = message(run(vault, note, AI_FIRST_SKIP_CHECKS=" 5, 6 "))
    assert both == ""


def test_skip_checks_is_read_from_the_config_env_file(vault, tmp_path):
    """A marketplace install configures the vault in the toolkit .env and never
    exports anything, so a setting only readable from the environment would not
    reach the hook there - the #160/#124 failure the vault path already had."""
    note = write(vault, "en.md", f"An em-dash {EM_DASH} here.\n")
    env_file = tmp_path / ".env"

    env_file.write_text(f"OBSIDIAN_VAULT_PATH={vault}\n", encoding="utf-8")
    control = subprocess.run(
        [BASH, str(HOOK)],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(note)}}),
        env={k: v for k, v in os.environ.items() if k != "OBSIDIAN_VAULT_PATH"}
        | {"OBSIDIAN_ENV_FILE": str(env_file)},
        capture_output=True, text=True,
    )
    assert "U+2014 em-dash" in message(control), "the .env vault path itself stopped working"

    env_file.write_text(
        f'OBSIDIAN_VAULT_PATH={vault}\nAI_FIRST_SKIP_CHECKS="5"\n', encoding="utf-8"
    )
    quiet = subprocess.run(
        [BASH, str(HOOK)],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(note)}}),
        env={k: v for k, v in os.environ.items() if k != "OBSIDIAN_VAULT_PATH"}
        | {"OBSIDIAN_ENV_FILE": str(env_file)},
        capture_output=True, text=True,
    )
    assert message(quiet) == ""


def test_an_unset_or_empty_skip_list_changes_nothing(vault):
    """The default is every check on. An empty value must not read as "skip"."""
    note = write(vault, "en.md", f"An em-dash {EM_DASH} here.\n")
    assert "U+2014 em-dash" in message(run(vault, note, AI_FIRST_SKIP_CHECKS=""))
    assert "U+2014 em-dash" in message(run(vault, note))
