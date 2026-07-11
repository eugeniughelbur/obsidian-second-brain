"""export_okf must translate faithfully or say it failed - never guess quietly.

Pins the six root causes behind the stress test's 12 export findings (fix 5/24):
pyyaml missing from the project env, capital Templates/ leaking, malformed YAML
silently mislabeled with the folder name (and prose dropped), dotted titles
losing their links (#93 regression), asset links degrading to plain text, and
the vault's own index.md being exported then clobbered by the bundle index.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_export(vault: Path) -> subprocess.CompletedProcess:
    # sys.executable = the project venv: this invocation is itself the pyyaml
    # regression test (the script used to work only via its PEP-723 header).
    return subprocess.run(
        [sys.executable, "scripts/export_okf.py", "--path", str(vault)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "Concepts").mkdir(parents=True)
    (vault / "Weird").mkdir()
    (vault / "Templates").mkdir()
    (vault / "Attachments").mkdir()
    (vault / "index.md").write_text("# MY NAV FILE\n", encoding="utf-8")
    (vault / "Templates" / "Daily Note.md").write_text("<% tp.date %>\n", encoding="utf-8")
    (vault / "Attachments" / "file.pdf").write_bytes(b"%PDF-1.4 fake")
    (vault / "Concepts" / "release v2.4 notes.md").write_text(
        "---\ntype: concept\ndate: 2026-07-11\ntags: [concept]\n---\n\nDotted title note.\n",
        encoding="utf-8",
    )
    (vault / "Weird" / "broken.md").write_text(
        "---\ntitle: [unclosed\n---\n\nPrecious prose that must survive.\n",
        encoding="utf-8",
    )
    (vault / "linker.md").write_text(
        "---\ntype: note\ndate: 2026-07-11\ntags: [note]\n---\n\n"
        "dotted [[release v2.4 notes]] here\n"
        "asset [[Attachments/file.pdf]] here\n"
        "missing [[No Such Note]] here\n",
        encoding="utf-8",
    )
    return vault


def test_export_runs_under_project_python_and_skips_templates(tmp_path):
    vault = _make_vault(tmp_path)
    result = _run_export(vault)

    assert result.returncode == 0, result.stderr
    out = vault / "_export" / "okf"
    assert out.is_dir()
    # Capital Templates/ used to leak (skip-list compared case-sensitively).
    assert not (out / "Templates").exists()


def test_malformed_yaml_warns_and_never_guesses(tmp_path):
    vault = _make_vault(tmp_path)
    result = _run_export(vault)

    assert result.returncode == 0, result.stderr
    assert "WARNING" in result.stderr and "broken.md" in result.stderr
    exported = (vault / "_export" / "okf" / "Weird" / "broken.md").read_text(encoding="utf-8")
    # Folder-name inference on a parse failure would say "type: weird".
    assert "type: note" in exported
    assert "type: weird" not in exported
    assert "Precious prose that must survive." in exported


def test_dotted_title_keeps_its_link(tmp_path):
    vault = _make_vault(tmp_path)
    result = _run_export(vault)

    assert result.returncode == 0, result.stderr
    linker = (vault / "_export" / "okf" / "linker.md").read_text(encoding="utf-8")
    assert "[release v2.4 notes](<Concepts/release v2.4 notes.md>)" in linker


def test_asset_link_survives_and_missing_note_degrades(tmp_path):
    vault = _make_vault(tmp_path)
    result = _run_export(vault)

    assert result.returncode == 0, result.stderr
    linker = (vault / "_export" / "okf" / "linker.md").read_text(encoding="utf-8")
    assert "[Attachments/file.pdf](Attachments/file.pdf)" in linker
    # Only links to notes that truly don't exist degrade to plain text.
    assert "missing No Such Note here" in linker


def test_vault_index_is_not_a_concept_doc(tmp_path):
    vault = _make_vault(tmp_path)
    result = _run_export(vault)

    assert result.returncode == 0, result.stderr
    bundle_index = (vault / "_export" / "okf" / "index.md").read_text(encoding="utf-8")
    assert 'okf_version: "0.1"' in bundle_index
    assert "MY NAV FILE" not in bundle_index
    # 3 real notes (dotted, broken, linker); the vault index must not be counted.
    assert "3 concept docs" in result.stdout
