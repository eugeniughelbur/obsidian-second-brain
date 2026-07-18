"""vault_health user-config excludes: .vault-config.json loads and gates skips."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _health(vault: Path) -> dict:
    result = subprocess.run(
        [sys.executable, "scripts/vault_health.py", "--path", str(vault), "--json"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout[result.stdout.find("{"):])


def test_user_exclude_dirs_suppress_orphans(tmp_path):
    """Dirs listed in .vault-config.json exclude-dirs must be skipped."""
    vault = tmp_path / "vault"
    (vault / "MyDistPool").mkdir(parents=True)
    (vault / "MyDistPool" / "note.md").write_text("# isolated note\n", encoding="utf-8")

    (vault / ".vault-config.json").write_text(
        json.dumps({"exclude-dirs": ["MyDistPool"]}),
        encoding="utf-8",
    )

    orphans = {i["files"][0] for i in _health(vault).get("issues", []) if i["type"] == "orphan"}
    assert "MyDistPool/note.md" not in orphans


def test_user_exclude_paths_suppress_frontmatter_gap(tmp_path):
    """Path prefixes in exclude-paths must suppress all issue types."""
    vault = tmp_path / "vault"
    (vault / "Archive" / "Backup").mkdir(parents=True)
    (vault / "Archive" / "Backup" / "old.md").write_text("no frontmatter here\n", encoding="utf-8")

    (vault / ".vault-config.json").write_text(
        json.dumps({"exclude-paths": ["Archive/Backup"]}),
        encoding="utf-8",
    )

    issues = _health(vault).get("issues", [])
    fm_issues = [i for i in issues if i["type"] == "missing_frontmatter" and "Archive/Backup" in i["files"][0]]
    assert fm_issues == [], fm_issues


def test_missing_config_is_silently_ignored(tmp_path):
    """No .vault-config.json → behaves exactly as before (no crash)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "solo.md").write_text("# solo\n", encoding="utf-8")

    payload = _health(vault)
    assert isinstance(payload, dict)
    assert "issues" in payload


def test_malformed_config_is_silently_ignored(tmp_path):
    """Malformed JSON in .vault-config.json → no crash, behaves as before."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "ok.md").write_text("# ok\n", encoding="utf-8")
    (vault / ".vault-config.json").write_text("{not valid json", encoding="utf-8")

    payload = _health(vault)
    assert isinstance(payload, dict)
