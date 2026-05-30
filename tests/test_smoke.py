"""Smoke tests for the two highest-risk subsystems: the adapter build pipeline
and the vault health checker. Both run the real scripts via subprocess and only
depend on the Python standard library, so CI needs nothing beyond pytest.

Adapted from the test added by the bmassenz fork (the only fork that shipped
any automated test). See FORK_INSIGHTS.md items #47/#48.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _json_from_stdout(stdout: str) -> dict:
    """vault_health.py prints a couple of human-readable lines before the JSON
    payload even in --json mode. Scan for the first line that opens the object."""
    lines = stdout.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "{":
            return json.loads("\n".join(lines[index:]))
    raise AssertionError(f"JSON payload not found in stdout:\n{stdout}")


def test_codex_cli_build_generates_expected_files():
    """The codex-cli adapter must emit the AGENTS.md dispatcher and the command
    bodies. This guards the adapter pipeline that every command change depends on."""
    result = subprocess.run(
        ["bash", "scripts/build.sh", "--platform", "codex-cli"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (REPO_ROOT / "dist/codex-cli/AGENTS.md").is_file()
    assert (REPO_ROOT / "dist/codex-cli/.codex/commands/obsidian-save.md").is_file()


def test_vault_health_json_reports_clean_linked_vault(tmp_path):
    """A minimal two-note vault with reciprocal wikilinks should report zero
    issues: no orphans, no broken links, no missing frontmatter."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Home.md").write_text(
        "# Home\n\nSee [[Project Alpha]].\n",
        encoding="utf-8",
    )
    (vault / "Project Alpha.md").write_text(
        "---\n"
        "type: project\n"
        "aliases:\n"
        "  - Project Alpha\n"
        "---\n"
        "# Project Alpha\n\nBack to [[Home]].\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "scripts/vault_health.py", "--path", str(vault), "--json"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = _json_from_stdout(result.stdout)
    assert payload["total_notes"] == 2
    assert payload["total_issues"] == 0
    assert payload["counts"]["Broken links"] == 0
    assert payload["counts"]["Orphans"] == 0
