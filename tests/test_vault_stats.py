"""vault_stats: a count is only as honest as its denominator.

Pins the four census sins from the stress test (fix 6/24): .git/_export
markdown counted as vault notes (stats doubled after every OKF export),
tab-indented nested YAML keys leaking to top level and flipping type counts,
non-UTF-8 notes silently dropped from every count with no footnote, and the
odd-one-out CLI (--vault only, --path rejected).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/vault_stats.py", *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _json_of(result: subprocess.CompletedProcess) -> dict:
    return json.loads(result.stdout[result.stdout.find("{"):])


def test_git_and_export_folders_are_not_counted(tmp_path):
    vault = tmp_path / "vault"
    (vault / ".git").mkdir(parents=True)
    (vault / "_export" / "okf").mkdir(parents=True)
    (vault / "note.md").write_text("---\ntype: concept\n---\nbody\n", encoding="utf-8")
    (vault / ".git" / "junk.md").write_text("---\ntype: junk\n---\n", encoding="utf-8")
    (vault / "_export" / "okf" / "note.md").write_text(
        "---\ntype: concept\n---\nexported copy\n", encoding="utf-8"
    )

    result = _run("--path", str(vault), "--json")
    assert result.returncode == 0, result.stderr
    stats = _json_of(result)
    # One real note; the exported copy and .git junk must not inflate anything.
    assert stats["total_notes"] == 1
    assert stats["by_type"] == {"concept": 1}


def test_tab_indented_nested_keys_do_not_leak(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "proj.md").write_text(
        "---\ntype: project\nstatus: active\nmeta:\n\tstatus: archived\n\ttype: person\n---\nbody\n",
        encoding="utf-8",
    )

    result = _run("--path", str(vault), "--json")
    assert result.returncode == 0, result.stderr
    stats = _json_of(result)
    assert stats["by_type"] == {"project": 1}
    assert stats["projects"]["by_status"] == {"active": 1}


def test_unreadable_notes_are_footnoted_not_hidden(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "good.md").write_text("---\ntype: concept\n---\nbody\n", encoding="utf-8")
    (vault / "bad.md").write_bytes(b"---\ntype: concept\n---\ncaf\xe9\n")

    result = _run("--path", str(vault), "--json")
    assert result.returncode == 0, result.stderr
    assert "skipped unreadable note" in result.stderr and "bad.md" in result.stderr
    stats = _json_of(result)
    assert stats["total_notes"] == 1
    assert stats["skipped_unreadable"] == 1

    # The human-readable block carries the footnote too.
    block = _run("--path", str(vault), "--print-only")
    assert "1 unreadable file(s) skipped" in block.stdout


def test_path_flag_matches_sibling_scripts(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("---\ntype: concept\n---\nbody\n", encoding="utf-8")

    for flag in ("--path", "--vault"):
        result = _run(flag, str(vault), "--json")
        assert result.returncode == 0, (flag, result.stderr)
        assert _json_of(result)["total_notes"] == 1
