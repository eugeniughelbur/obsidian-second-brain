"""vault_health user-config excludes: `<vault>/.vault-config.json` extends the
built-in EXCLUDE_DIRS per-vault. These run the real script via subprocess so the
whole load-config -> scan path is exercised, and each positive test fails on the
pre-config code (which had no way to skip a user directory).

Reimplemented from the withdrawn PR #140 by @Rongles-World.
"""

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


def _write_config(vault: Path, config: dict) -> None:
    (vault / ".vault-config.json").write_text(json.dumps(config), encoding="utf-8")


def test_user_exclude_dirs_suppress_orphans(tmp_path):
    """A dir named in `exclude-dirs` is dropped from the scan, so its notes never
    surface as orphans. Without the config the note is a textbook orphan."""
    vault = tmp_path / "vault"
    (vault / "MyCardPool").mkdir(parents=True)
    (vault / "MyCardPool" / "note.md").write_text("# isolated note\n", encoding="utf-8")

    _write_config(vault, {"exclude-dirs": ["MyCardPool"]})

    orphans = {i["files"][0] for i in _health(vault).get("issues", []) if i["type"] == "orphan"}
    assert "MyCardPool/note.md" not in orphans


def test_user_exclude_paths_suppress_all_issue_types(tmp_path):
    """A prefix in `exclude-paths` suppresses every issue type under that path -
    here a note with no frontmatter that would otherwise be flagged."""
    vault = tmp_path / "vault"
    (vault / "Archive" / "Backup").mkdir(parents=True)
    (vault / "Archive" / "Backup" / "old.md").write_text("no frontmatter\n", encoding="utf-8")

    _write_config(vault, {"exclude-paths": ["Archive/Backup"]})

    issues = _health(vault).get("issues", [])
    flagged = [i for i in issues if i["files"] and "Archive/Backup" in i["files"][0]]
    assert flagged == [], flagged


def test_hardcoded_excludes_still_apply_with_config_present(tmp_path):
    """A user config must never weaken the built-in EXCLUDE_DIRS: `.obsidian` and
    friends stay excluded even when a (narrower) config is loaded."""
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / ".obsidian" / "workspace.md").write_text("plugin state\n", encoding="utf-8")
    (vault / "real.md").write_text("# real note\n", encoding="utf-8")

    _write_config(vault, {"exclude-dirs": ["Something-Else"]})

    files = {i["files"][0] for i in _health(vault).get("issues", []) if i["files"]}
    assert not any(".obsidian" in f for f in files)


def test_missing_config_is_silently_ignored(tmp_path):
    """No `.vault-config.json` -> identical to prior behavior, never a crash."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "solo.md").write_text("# solo\n", encoding="utf-8")

    payload = _health(vault)
    assert isinstance(payload, dict)
    assert "issues" in payload


def test_malformed_config_is_silently_ignored(tmp_path):
    """Malformed JSON -> ignored, scan still completes normally."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "ok.md").write_text("# ok\n", encoding="utf-8")
    (vault / ".vault-config.json").write_text("{not valid json", encoding="utf-8")

    payload = _health(vault)
    assert isinstance(payload, dict)
    assert "issues" in payload
