"""The front door must not eat luggage (stress-test fix 23/24).

The audit's newcomer walk found bootstrap silently overwriting a hand-made
Home.md and _CLAUDE.md (verified data loss), the README's first command
pointing at a file that did not exist, and installers that each did half the
job. These pin the bootstrap guard and keep the installer scripts parseable
and cross-referenced.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _bootstrap(vault: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/bootstrap_vault.py", "--path", str(vault),
         "--name", "Test User", *extra],
        cwd=REPO_ROOT, check=False, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def test_bootstrap_never_overwrites_user_files(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Home.md").write_text("# MY precious dashboard\n", encoding="utf-8")
    (vault / "_CLAUDE.md").write_text("# MY manual\n", encoding="utf-8")

    result = _bootstrap(vault)
    assert result.returncode == 0, result.stderr
    assert (vault / "Home.md").read_text(encoding="utf-8") == "# MY precious dashboard\n"
    assert (vault / "_CLAUDE.md").read_text(encoding="utf-8") == "# MY manual\n"
    assert "kept existing" in result.stdout


def test_bootstrap_force_overwrites_when_asked(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Home.md").write_text("# old\n", encoding="utf-8")

    result = _bootstrap(vault, "--force")
    assert result.returncode == 0, result.stderr
    assert (vault / "Home.md").read_text(encoding="utf-8") != "# old\n"


def test_installer_scripts_parse_and_crossreference():
    for script in ("install.sh", "scripts/setup.sh", "scripts/quick-install.sh"):
        r = subprocess.run(["bash", "-n", str(REPO_ROOT / script)],
                           capture_output=True, text=True)
        assert r.returncode == 0, f"{script}: {r.stderr}"
    # The README's one-liner must point at a file that exists.
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "scripts/quick-install.sh" in readme
    assert (REPO_ROOT / "scripts" / "quick-install.sh").exists()
