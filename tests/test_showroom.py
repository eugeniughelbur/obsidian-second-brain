"""The showroom rule: a fresh install must pass its own inspection.

Before stress-test fix 9/24, `bootstrap_vault.py` followed by `vault_health.py`
reported 19 issues on a brand-new untouched vault (17 empty scaffold folders, a
dangling Home.md wikilink, an orphaned seeded note). Plus four toolbox paper
cuts pinned here: triage's TypeError on a missing --from, sweep_non_ascii's
broken --help, its silent skip of unreadable files, and its habit of rewriting
dashes inside wikilinks (breaking the link).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, f"scripts/{script}", *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_fresh_bootstrap_passes_its_own_health_check(tmp_path):
    vault = tmp_path / "vault"
    boot = _run("bootstrap_vault.py", "--path", str(vault), "--name", "Test User")
    assert boot.returncode == 0, boot.stderr

    health = _run("vault_health.py", "--path", str(vault), "--json")
    assert health.returncode == 0, health.stderr
    payload = json.loads(health.stdout[health.stdout.find("{"):])
    assert payload["total_issues"] == 0, payload["issues"]


def test_fresh_bootstrap_passes_freshness_lint(tmp_path):
    """Same showroom rule, second inspector: a brand-new vault must also be
    freshness-clean. The Kanban settings footer on every seeded board rang
    FRESH-3 out of the box (2 errors on the default preset)."""
    vault = tmp_path / "vault"
    boot = _run("bootstrap_vault.py", "--path", str(vault), "--name", "Test User")
    assert boot.returncode == 0, boot.stderr

    lint = _run("freshness_lint.py", "--path", str(vault), "--json")
    payload = json.loads(lint.stdout[lint.stdout.find("{"):])
    assert payload["errors"] == 0 and payload["warnings"] == 0, payload["findings"]
    assert lint.returncode == 0, lint.stderr


def _expected_default_folders():
    """The folder set the default preset is contracted to create, constructed
    independently of the map-rendering code under test: the preset's base list
    plus the runtime Side Biz extension bootstrap() appends."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        from bootstrap_vault import PRESETS
    finally:
        sys.path.remove(str(REPO_ROOT / "scripts"))
    return set(PRESETS["default"]["folders"]) | {
        "Side Biz/Deals/Location1", "Side Biz/Deals/Location2",
    }


def _assert_map_matches_vault(vault):
    """Both directions: every path the _CLAUDE.md folder map lists exists on
    disk, and every folder bootstrap is contracted to create is listed. The
    one-directional form (listed -> exists) could never catch a created-but-
    never-listed folder - the exact Side Biz defect this guards against."""
    claude_md = (vault / "_CLAUDE.md").read_text(encoding="utf-8")
    listed = re.findall(r"^\|\s*`([^`]+)`\s*\|", claude_md, flags=re.MULTILINE)
    assert listed, "folder map table not found in _CLAUDE.md"
    missing = [p for p in listed if not (vault / p.rstrip("/")).exists()]
    assert not missing, f"folder map lists paths bootstrap never created: {missing}"
    unlisted = [f for f in _expected_default_folders() if f"`{f}/`" not in claude_md]
    assert not unlisted, f"folders bootstrap created but the map omits: {unlisted}"


def test_folder_map_matches_what_bootstrap_created(tmp_path):
    """_CLAUDE.md's folder map is the agent's ground truth for what is where.
    The default preset used to list a `Jobs/Work.md` that was never written
    and omit the `Side Biz/` tree it did create."""
    vault = tmp_path / "vault"
    boot = _run("bootstrap_vault.py", "--path", str(vault), "--name", "Test User")
    assert boot.returncode == 0, boot.stderr
    _assert_map_matches_vault(vault)


def test_folder_map_matches_in_assistant_mode(tmp_path):
    """Assistant mode renders the map through claude_md_assistant, which had
    the same preset-only folder source - both builders must document the
    folders actually created."""
    vault = tmp_path / "vault"
    boot = _run("bootstrap_vault.py", "--path", str(vault), "--name", "Operator",
                "--mode", "assistant", "--subject", "Subject Person")
    assert boot.returncode == 0, boot.stderr
    _assert_map_matches_vault(vault)


def test_triage_apply_without_from_errors_cleanly(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("# n\n", encoding="utf-8")
    result = _run("triage_links.py", "--path", str(vault), "--apply")

    assert result.returncode == 2
    assert "--from" in result.stderr and "required" in result.stderr
    assert "Traceback" not in result.stderr


def test_sweep_help_prints_usage_not_a_scan(tmp_path):
    result = _run("sweep_non_ascii.py", "--help")
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()
    assert "would" not in result.stdout  # no dry-run scan output


def test_sweep_warns_on_unreadable_files(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"caf\xe9 \xe2\x80 broken bytes")
    result = _run("sweep_non_ascii.py", str(bad))

    assert result.returncode == 0
    assert "unreadable" in result.stderr and "bad.md" in result.stderr
    assert "unreadable and NOT checked" in result.stdout


def test_sweep_preserves_wikilink_interiors(tmp_path):
    note = tmp_path / "note.md"
    # em-dash INSIDE a wikilink is a filename character; the one in prose is
    # typography and must still be fixed.
    note.write_text(
        "prose dash \u2014 here, link [[Call \u2014 script]] stays\n",
        encoding="utf-8",
    )
    result = _run("sweep_non_ascii.py", "--apply", str(note))

    assert result.returncode == 0, result.stderr
    fixed = note.read_text(encoding="utf-8")
    assert "prose dash - here" in fixed
    assert "[[Call \u2014 script]]" in fixed


def test_wanted_note_with_brackets_is_annotated(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "linker.md").write_text("see [[note [draft]]]\n", encoding="utf-8")

    health = _run("vault_health.py", "--path", str(vault), "--json")
    assert health.returncode == 0, health.stderr
    payload = json.loads(health.stdout[health.stdout.find("{"):])
    wanted = [i for i in payload["issues"] if i["type"] == "wanted_note"]
    assert wanted and "capture may be truncated" in wanted[0]["message"]
