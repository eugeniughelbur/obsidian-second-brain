"""One ghost must never kill the scan.

rglob("*.md") matches names, not files: a dangling symlink or a directory named
*.md used to raise FileNotFoundError/IsADirectoryError inside vault_health's
load_vault (shared by heal_links and triage_links) and export_okf's collector,
aborting the whole run (stress-test fix 2/24). These tests pin the guard.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

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


def _make_ghost_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "real-note.md").write_text(
        "---\ntags: [test]\n---\n\nA real note linking [[real-note]].\n",
        encoding="utf-8",
    )
    # Ghost 1: symlink whose target (outside the vault) no longer exists.
    (vault / "orphan-link.md").symlink_to(tmp_path / "outside" / "was-deleted.md")
    # Ghost 2: a directory whose name matches *.md.
    (vault / "notes.md").mkdir()
    return vault


def test_vault_health_survives_ghosts(tmp_path):
    vault = _make_ghost_vault(tmp_path)
    result = _run("vault_health.py", "--path", str(vault), "--json")

    assert result.returncode == 0, result.stderr
    # The report must still be produced and must include the real note.
    payload_start = result.stdout.find("{")
    assert payload_start != -1, f"no JSON payload in stdout:\n{result.stdout}"
    payload = json.loads(result.stdout[payload_start:])
    assert payload["total_notes"] >= 1


def test_heal_links_survives_ghosts(tmp_path):
    vault = _make_ghost_vault(tmp_path)
    result = _run("heal_links.py", "--path", str(vault), "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "DRY RUN" in result.stdout


def test_triage_links_apply_survives_ghosts(tmp_path):
    vault = _make_ghost_vault(tmp_path)
    verdicts = tmp_path / "verdicts.txt"
    verdicts.write_text("DELETE [[nothing-here]]\n", encoding="utf-8")
    result = _run(
        "triage_links.py", "--path", str(vault), "--apply", "--from", str(verdicts)
    )
    assert result.returncode == 0, result.stderr


def test_export_okf_survives_ghosts(tmp_path):
    if importlib.util.find_spec("yaml") is None:
        pytest.skip("pyyaml not installed in the test env (tracked as stress-test fix 5)")
    vault = _make_ghost_vault(tmp_path)
    result = _run("export_okf.py", "--path", str(vault))
    assert result.returncode == 0, result.stderr
