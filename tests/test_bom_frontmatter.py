"""A leading UTF-8 BOM must not blind the frontmatter readers.

Editors (mostly on Windows) prepend U+FEFF to files. Every scanner that asks
"does the file start with ---" then answers no: vault_health reported healthy
notes as missing frontmatter and lost their aliases, vault_stats dropped them
from type counts, link_graph lost their type, and export_okf wrote a duplicate
frontmatter block. Fixed by reading with encoding="utf-8-sig" at all six read
sites (stress-test fix 4/24). Files on disk keep their BOM (fix 1's byte-exact
rule); only the readers stop being blind.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

BOM_NOTE = (
    "\ufeff---\n"
    "type: project\n"
    "date: 2026-07-11\n"
    "tags: [project]\n"
    "aliases:\n"
    "  - Bommy Project\n"
    "ai-first: true\n"
    "---\n\n"
    "## For future Claude\n\nA healthy note saved by a BOM-adding editor.\n"
)


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


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "bom-note.md").write_text(BOM_NOTE, encoding="utf-8")
    (vault / "linker.md").write_text(
        "---\ntags: [note]\n---\n\nsee [[Bommy Project]] and [[bom-note]]\n",
        encoding="utf-8",
    )
    return vault


def test_vault_health_sees_bom_frontmatter(tmp_path):
    vault = _make_vault(tmp_path)
    result = _run("vault_health.py", "--path", str(vault), "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout[result.stdout.find("{"):])
    # The BOM'd note has valid frontmatter and is linked via its alias: no issue
    # of any kind (missing frontmatter, wanted alias link) may mention it.
    complaints = [i for i in payload["issues"] if "bom-note" in i["message"]
                  or "Bommy Project" in i["message"]]
    assert complaints == [], complaints


def test_vault_stats_counts_bom_note_by_type(tmp_path):
    vault = _make_vault(tmp_path)
    result = _run("vault_stats.py", "--vault", str(vault), "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout[result.stdout.find("{"):])
    by_type = payload.get("by_type", {})
    assert by_type.get("project", 0) >= 1, payload


def test_link_graph_reads_bom_note_type(tmp_path):
    vault = _make_vault(tmp_path)
    result = _run("link_graph.py", "--path", str(vault))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout[result.stdout.find("{"):])
    bom_nodes = [n for n in payload["nodes"] if "bom-note" in n["path"]]
    assert bom_nodes and bom_nodes[0].get("type") == "project", bom_nodes
