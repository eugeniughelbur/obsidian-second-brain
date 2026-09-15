"""The setup script builds both documented layouts: --style wiki|obsidian (#283).

The README and references/vault-schema.md described a wiki-style layout that no
setup path could create: every preset made Daily/, People/ and the rest, and the
only write_bases call hardcoded style="obsidian". These pin the flag's contract:
obsidian stays the default and builds what it built before; wiki builds the wiki
layout and nothing from the Obsidian-style tree; either vault passes its own
health check; and the wiki paths cannot drift from references/folder-map.md.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import bootstrap_vault as bv  # noqa: E402


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


def _boot(vault: Path, *extra: str) -> subprocess.CompletedProcess:
    return _run("bootstrap_vault.py", "--path", str(vault), "--name", "Test User", *extra)


def _exists_exact(root: Path, rel: str) -> bool:
    """Case-sensitive existence check. On macOS `Path("Templates").exists()` is
    true when only `templates/` exists, which would hide exactly the leak these
    tests look for."""
    here = root
    for part in rel.split("/"):
        if not here.is_dir() or part not in {p.name for p in here.iterdir()}:
            return False
        here = here / part
    return True


def _tree(vault: Path) -> dict:
    return {
        p.relative_to(vault).as_posix(): (p.read_bytes() if p.is_file() else None)
        for p in sorted(vault.rglob("*"))
    }


def test_obsidian_is_the_default(tmp_path):
    """No flag and --style obsidian must build byte-identical vaults."""
    implicit, explicit = tmp_path / "implicit", tmp_path / "explicit"
    assert _boot(implicit).returncode == 0
    assert _boot(explicit, "--style", "obsidian").returncode == 0
    a, b = _tree(implicit), _tree(explicit)
    assert a.keys() == b.keys()
    assert [k for k in a if a[k] != b[k]] == []


@pytest.mark.parametrize("preset", sorted(bv.PRESETS))
def test_wiki_style_builds_only_the_wiki_layout(tmp_path, preset):
    vault = tmp_path / "vault"
    boot = _boot(vault, "--preset", preset, "--style", "wiki")
    assert boot.returncode == 0, boot.stderr

    leaked = [f for f in bv.PRESETS[preset]["folders"] if f != "_trash" and _exists_exact(vault, f)]
    assert leaked == [], f"wiki-style vault created Obsidian-style folders: {leaked}"

    missing = [
        path for f in bv.PRESETS[preset]["folders"]
        if (path := bv.resolve_folder(f, "wiki")) and not _exists_exact(vault, path)
    ]
    assert missing == [], f"preset folders with a wiki-style home were not created: {missing}"

    claude_md = (vault / "_CLAUDE.md").read_text(encoding="utf-8")
    assert "- **Vault style:** wiki" in claude_md
    for base in (vault / "Bases").glob("*.base"):
        text = base.read_text(encoding="utf-8")
        assert 'inFolder("wiki/' in text, f"{base.name} is not stamped for the wiki layout"


INSPECTION_CASES = [
    pytest.param(
        preset, style,
        marks=pytest.mark.xfail(
            strict=True,
            reason="Pre-existing, not introduced by --style: the researcher preset seeds "
                   "Reading Queue/_Queue.md with no incoming link, so vault_health reports "
                   "an orphan. A wiki-style vault does not create that folder.",
        ) if (preset, style) == ("researcher", "obsidian") else (),
    )
    for preset in sorted(bv.PRESETS)
    for style in bv.STYLES
]


@pytest.mark.parametrize(("preset", "style"), INSPECTION_CASES)
def test_every_style_passes_its_own_inspection(tmp_path, preset, style):
    """The showroom rule, for every preset in both layouts: zero health findings,
    a clean freshness lint, and a folder map that matches the disk."""
    vault = tmp_path / "vault"
    boot = _boot(vault, "--preset", preset, "--style", style)
    assert boot.returncode == 0, boot.stderr

    health = _run("vault_health.py", "--path", str(vault), "--json")
    assert health.returncode == 0, health.stderr
    payload = json.loads(health.stdout[health.stdout.find("{"):])
    assert payload["total_issues"] == 0, payload["issues"]

    lint = _run("freshness_lint.py", "--path", str(vault), "--json")
    findings = json.loads(lint.stdout[lint.stdout.find("{"):])
    assert findings["errors"] == 0 and findings["warnings"] == 0, findings["findings"]

    claude_md = (vault / "_CLAUDE.md").read_text(encoding="utf-8")
    listed = re.findall(r"^\|\s*`([^`]+)`\s*\|", claude_md, flags=re.MULTILINE)
    assert listed, "folder map table not found in _CLAUDE.md"
    assert [p for p in listed if not _exists_exact(vault, p.rstrip("/"))] == []
    # Only the people route is checked: the executive, creator and researcher
    # manuals already sent dev work to a Dev Logs/ they never create, before #283.
    people_route = re.search(r"New people mentioned → ([^ ]+)/", claude_md)
    assert people_route and _exists_exact(vault, people_route.group(1)), (
        "_CLAUDE.md routes new people to a folder the vault does not have"
    )


@pytest.mark.parametrize("style", bv.STYLES)
@pytest.mark.parametrize("preset", ["builder", "creator"])
def test_builder_and_creator_create_the_people_folder(tmp_path, preset, style):
    """Their generated _CLAUDE.md says new people go to People/ (or wiki/entities/),
    and until #283 neither preset created that folder."""
    vault = tmp_path / "vault"
    assert _boot(vault, "--preset", preset, "--style", style).returncode == 0
    assert _exists_exact(vault, bv.resolve_folder("People", style))


def _folder_map_rows() -> dict[str, set[str]]:
    """Obsidian-style folder name -> the wiki-style defaults folder-map.md gives it."""
    text = (REPO_ROOT / "references" / "folder-map.md").read_text(encoding="utf-8")
    rows: dict[str, set[str]] = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 3 or not cells[1].startswith("`"):
            continue
        wiki = re.findall(r"`([^`]+)`", cells[1])[0].rstrip("/")
        for name in re.findall(r"`([^`]+)`", cells[2]):
            rows.setdefault(name.rstrip("/"), set()).add(wiki)
    return rows


def test_wiki_paths_follow_the_folder_map():
    rows = _folder_map_rows()
    assert rows, "could not read the folder map table"
    wiki_defaults = set().union(*rows.values())
    for name, path in bv.WIKI_PATHS.items():
        if name in rows:
            assert path in rows[name], f"{name} -> {path}, but folder-map.md says {sorted(rows[name])}"
        if path not in ("templates", "_trash"):
            assert path in wiki_defaults, f"{path} is not a wiki-style default in folder-map.md"
