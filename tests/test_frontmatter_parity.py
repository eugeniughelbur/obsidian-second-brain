"""Frontmatter parity, exclude validation, and two silent-failure holes.

  S9  three regexes disagreed on real input. A note whose opening fence carried
      trailing whitespace had frontmatter to vault_health and vault_stats and
      none to export_okf, which then wrote the frontmatter into the exported
      body as prose and typed the note `note`
  B20 `exclude:` was an unvalidated string match, so a plausible misspelling
      shipped a Claude-only command to every platform with exit 0
  B40 note keys used str(Path), which is backslash-separated on Windows, so
      every `rel.split("/")` saw no separator and the top-folder logic returned
      "" for every note - collapsing the skip-folder and dated-series exemptions
  B35 unattended hooks appended to a fixed, predictable, world-readable path in
      the shared /tmp
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
# Resolved by path: on Windows a bare "bash" can resolve to WSL's launcher in System32.
BASH = shutil.which("bash") or "/bin/bash"


# --- S9 --------------------------------------------------------------------

TRAILING_SPACE_FENCE = "---   \ntype: note\n---  \n\nbody\n"


def test_all_frontmatter_patterns_agree_on_a_trailing_space_fence():
    import export_okf
    import vault_health
    import vault_stats

    results = {
        "vault_health": vault_health.FRONTMATTER_RE.match(TRAILING_SPACE_FENCE),
        "vault_stats": vault_stats.FRONTMATTER.match(TRAILING_SPACE_FENCE),
        "export_okf": export_okf.FM_RE.match(TRAILING_SPACE_FENCE),
    }
    disagreed = [n for n, m in results.items() if not m]
    assert not disagreed, (
        f"{disagreed} do not see frontmatter that the others do. The same note is "
        "typed correctly by one tool and dumped into the body as prose by another."
    )
    for name, m in results.items():
        assert m.group(1).strip() == "type: note", f"{name} captured {m.group(1)!r}"


CRLF_FENCE = "---\r\ntype: note\r\ntags: [a]\r\n---\r\n\r\nbody\r\n"


def test_all_frontmatter_patterns_agree_on_a_crlf_note():
    """S9 again, on line endings. The whitespace class vault_health and
    vault_stats use after a fence absorbs a carriage return; the space-or-tab
    class in export_okf and vault_scan did not, so the byte-exact text of a
    note saved with CRLF (a Windows editor, or one note_io preserved as it was)
    had frontmatter to two tools and none to the other two - and merge_notes.py,
    which passes note_io's read straight to export_okf's parser, lost that
    note's fields in the merge. Its own tests hit this on Windows, where
    write_text() saves the fixtures with CRLF."""
    import export_okf
    import vault_health
    import vault_scan
    import vault_stats

    results = {
        "vault_health": vault_health.FRONTMATTER_RE.match(CRLF_FENCE),
        "vault_stats": vault_stats.FRONTMATTER.match(CRLF_FENCE),
        "export_okf": export_okf.FM_RE.match(CRLF_FENCE),
        "vault_scan": vault_scan.FRONTMATTER_RE.match(CRLF_FENCE),
    }
    disagreed = [n for n, m in results.items() if not m]
    assert not disagreed, f"{disagreed} do not see the frontmatter of a CRLF note"
    for name, m in results.items():
        assert m.group(1).splitlines() == ["type: note", "tags: [a]"], (
            f"{name} captured {m.group(1)!r}"
        )

    fm, body, malformed = export_okf.parse_note(CRLF_FENCE)
    assert (fm, malformed) == ({"type": "note", "tags": ["a"]}, False)
    assert body == "\r\nbody\r\n", "the body keeps its line endings byte-exact"
    fm_text, body = vault_scan.split_frontmatter(CRLF_FENCE)
    assert fm_text.splitlines() == ["type: note", "tags: [a]"] and body == "\r\nbody\r\n"


def test_parse_note_skips_a_bom_like_the_canonical_parser():
    """export_okf reads with utf-8-sig, but merge_notes hands parse_note the
    byte-exact text note_io returns, BOM included; the BOM then hid the whole
    frontmatter and the merge carried the retired note's values over as the
    canonical note's own (test_merge_notes pins the end-to-end case)."""
    import export_okf

    fm, body, malformed = export_okf.parse_note("\ufeff---\ntype: note\n---\n\nbody\n")
    assert (fm, malformed) == ({"type": "note"}, False), "a BOM hid the frontmatter"
    assert body == "\nbody\n"


def test_the_canonical_parser_handles_the_awkward_cases():
    from vault_scan import split_frontmatter

    fm, body = split_frontmatter("---\ntype: note\n---\n\nbody\n")
    assert fm == "type: note" and body.strip() == "body"

    fm, _ = split_frontmatter("﻿---\ntype: note\n---\n\nbody\n")
    assert fm == "type: note", "a BOM hid the frontmatter"

    fm, body = split_frontmatter("no frontmatter here\n")
    assert fm == "" and body == "no frontmatter here\n", "must not raise on a bare note"


# --- B20 -------------------------------------------------------------------

def _build(cwd=None):
    return subprocess.run(
        [BASH, str(REPO_ROOT / "scripts" / "build.sh"), "--platform", "hermes"],
        cwd=cwd or REPO_ROOT, capture_output=True, text=True, check=False,
    )


def test_a_misspelled_exclude_platform_fails_the_build():
    bad = REPO_ROOT / "commands" / "zz-test-bad-exclude.md"
    bad.write_text(
        "---\ndescription: temporary fixture\nexclude: [codex, agentskills]\n---\n\nbody\n",
        encoding="utf-8",
    )
    try:
        result = _build()
        assert result.returncode != 0, (
            "a command excluding 'codex' and 'agentskills' built cleanly. Both are "
            "plausible shortenings of real platform names, and neither matches, so "
            "the command shipped to every platform it meant to skip."
        )
        assert "unknown platform" in result.stderr
        assert "codex-cli" in result.stderr, "the error should name the valid platforms"
    finally:
        bad.unlink(missing_ok=True)


def test_the_real_exclude_list_still_builds():
    """Guards against a validator so strict it rejects the one real user."""
    result = _build()
    assert result.returncode == 0, result.stderr


# --- B40 -------------------------------------------------------------------

def test_note_keys_are_posix_separated():
    src = (REPO_ROOT / "scripts" / "vault_health.py").read_text(encoding="utf-8")
    assert "rel = md.relative_to(vault).as_posix()" in src, (
        "note keys use str(Path). On Windows that is backslash-separated, so every "
        'rel.split("/") below sees no separator, top_folder becomes "", and every '
        "note under Daily/, Journal/ or Private/ is reported as an orphan."
    )
    assert "rel = str(md.relative_to(vault))" not in src


def test_the_split_logic_this_protects_still_works():
    """The consumer of that key, so the fix is not just cosmetic."""
    from pathlib import PureWindowsPath

    w = PureWindowsPath("Daily/2026-01-01.md")
    assert str(w).split("/")[0] != "Daily", "sanity: this is the broken behaviour"
    assert w.as_posix().split("/")[0] == "Daily"


# --- B35 -------------------------------------------------------------------

def test_unattended_hooks_do_not_log_to_a_fixed_shared_tmp_path():
    for name in ("obsidian-bg-agent.sh", "obsidian-hermes-session-end.sh"):
        src = (REPO_ROOT / "hooks" / name).read_text(encoding="utf-8")
        assert not re.search(r">>\s*/tmp/obsidian-[a-z-]+\.log", src), (
            f"{name} appends to a fixed name in the shared /tmp. It is world-readable "
            "under a default umask, and the path is predictable enough to pre-create "
            "as a symlink."
        )
        assert "id -u" in src, f"{name} log path is not per-user"
        assert "umask 077" in src, f"{name} does not restrict the log's mode"
