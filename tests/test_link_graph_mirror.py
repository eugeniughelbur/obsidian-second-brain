"""link_graph must actually mirror vault_health - drift fails loudly here.

The docstring always claimed "mirrors vault_health's link handling"; the audit
found the two disagreed in both directions on the same vault (528 vs 187 broken
links on the 3,000-note fixture). These tests pin the fixed behavior and, most
importantly, pin the two tools' counts to each other (stress-test fix 7/24).
"""

from __future__ import annotations

import json
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


def _graph(vault: Path) -> dict:
    result = _run("link_graph.py", "--path", str(vault))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_space_vs_hyphen_is_not_an_edge(tmp_path):
    """Obsidian does not resolve [[Foo Bar Baz]] to foo-bar-baz.md; a phantom
    edge here hides a genuinely broken link."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "foo-bar-baz.md").write_text("# t\n", encoding="utf-8")
    (vault / "linker.md").write_text("see [[Foo Bar Baz]]\n", encoding="utf-8")

    g = _graph(vault)
    assert g["stats"]["edge_count"] == 0
    assert g["stats"]["dangling_link_count"] == 1


def test_em_dash_unification_still_resolves(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "A \u2014 B.md").write_text("# t\n", encoding="utf-8")
    (vault / "linker.md").write_text("see [[A - B]]\n", encoding="utf-8")

    g = _graph(vault)
    assert g["stats"]["edge_count"] == 1
    assert g["stats"]["dangling_link_count"] == 0


def test_path_qualified_link_hits_the_right_twin(tmp_path):
    vault = tmp_path / "vault"
    (vault / "Projects").mkdir(parents=True)
    (vault / "Archive").mkdir()
    (vault / "Projects" / "ProjectX.md").write_text("# live\n", encoding="utf-8")
    (vault / "Archive" / "ProjectX.md").write_text("# old\n", encoding="utf-8")
    (vault / "alpha.md").write_text("see [[Projects/ProjectX]]\n", encoding="utf-8")

    g = _graph(vault)
    targets = {e["to"] for e in g["edges"] if e["from"] == "alpha.md"}
    assert targets == {"Projects/ProjectX.md"}


def test_assets_folders_and_manual_are_not_dangling(tmp_path):
    vault = tmp_path / "vault"
    (vault / "Attachments").mkdir(parents=True)
    (vault / "Projects").mkdir()
    (vault / "Attachments" / "file.pdf").write_bytes(b"%PDF fake")
    (vault / "Attachments" / "image.png").write_bytes(b"\x89PNG fake")
    (vault / "Projects" / "real.md").write_text("# p\n", encoding="utf-8")
    (vault / "note.md").write_text(
        "asset [[Attachments/file.pdf]] embed ![[image.png]] folder [[Projects]]\n",
        encoding="utf-8",
    )
    (vault / "_CLAUDE.md").write_text(
        "manual demo: [[wikilinks]] and [[Related Project]]\n", encoding="utf-8"
    )

    g = _graph(vault)
    assert g["stats"]["dangling_link_count"] == 0


def test_capital_templates_not_in_orphans(tmp_path):
    vault = tmp_path / "vault"
    (vault / "Templates").mkdir(parents=True)
    (vault / "Templates" / "Daily Note.md").write_text("<% tp %>\n", encoding="utf-8")
    (vault / "note.md").write_text("# n\n", encoding="utf-8")

    g = _graph(vault)
    assert all("Templates" not in o for o in g["stats"]["orphans"])
    assert all("Templates" not in n["path"] for n in g["nodes"])


def test_counts_pinned_to_vault_health(tmp_path):
    """The drift alarm: on a vault exercising every disagreement the audit found,
    link_graph's dangling count must equal vault_health's wanted-note count."""
    vault = tmp_path / "vault"
    (vault / "Attachments").mkdir(parents=True)
    (vault / "Attachments" / "file.pdf").write_bytes(b"%PDF fake")
    (vault / "foo-bar-baz.md").write_text("# t\n", encoding="utf-8")
    (vault / "real-target.md").write_text("# t\n", encoding="utf-8")
    (vault / "linker.md").write_text(
        "broken-by-case [[Foo Bar Baz]]\n"
        "truly broken [[Nothing Here]]\n"
        "fine [[real-target]]\n"
        "asset [[Attachments/file.pdf]]\n",
        encoding="utf-8",
    )

    g = _graph(vault)

    health = _run("vault_health.py", "--path", str(vault), "--json")
    assert health.returncode == 0, health.stderr
    payload = json.loads(health.stdout[health.stdout.find("{"):])
    wanted = [i for i in payload["issues"] if i.get("type") == "wanted_note"]

    assert g["stats"]["dangling_link_count"] == len(wanted) == 2