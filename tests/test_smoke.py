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


def test_substitution_check_passes_on_repo():
    """The repo source must be free of banned substitution characters in prose
    (the CI gate). Characters inside code fences/spans are allowed."""
    result = subprocess.run(
        [sys.executable, "scripts/sweep_non_ascii.py", "--check"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_substitution_check_flags_prose_em_dash(tmp_path):
    """--check must fail (exit 1) when a banned character appears in prose, and
    must NOT fail when it only appears inside an inline code span."""
    # Build the em-dash from its code point so this test's own source stays
    # ASCII (the CI gate scans .py files too); the written fixtures get the
    # real character.
    em = "\u2014"
    bad = tmp_path / "bad.md"
    bad.write_text(f"A prose line with an em{em}dash.\n", encoding="utf-8")
    flagged = subprocess.run(
        [sys.executable, "scripts/sweep_non_ascii.py", "--check", str(bad)],
        cwd=REPO_ROOT, check=False, capture_output=True, text=True,
    )
    assert flagged.returncode == 1, flagged.stdout

    ok = tmp_path / "ok.md"
    ok.write_text(f"A filename in code: `2026-01-01 {em} note.md` is fine.\n", encoding="utf-8")
    passed = subprocess.run(
        [sys.executable, "scripts/sweep_non_ascii.py", "--check", str(ok)],
        cwd=REPO_ROOT, check=False, capture_output=True, text=True,
    )
    assert passed.returncode == 0, passed.stdout


def test_health_normalizes_dashes_in_links(tmp_path):
    """Regression for #63: a wikilink written with a regular hyphen must resolve
    against a filename written with an em-dash (the #31 behavior). The non-ASCII
    sweep once rewrote _normalize_dashes()'s operands into ASCII hyphens, turning
    it into a no-op; this locks the behavior so an automated pass cannot silently
    undo it again. Em-dash built from its code point so this source stays ASCII."""
    em = "\u2014"
    (tmp_path / f"2026-05-22 {em} Learnings Review.md").write_text(
        "---\ntype: concept\n---\n# Learnings Review\n\nBack to [[Home]].\n",
        encoding="utf-8",
    )
    (tmp_path / "Home.md").write_text(
        "# Home\n\nSee [[2026-05-22 - Learnings Review]].\n", encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, "scripts/vault_health.py", "--path", str(tmp_path), "--json"],
        cwd=REPO_ROOT, check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"broken_link"' not in result.stdout, (
        "hyphen-written link to em-dash filename was flagged broken:\n" + result.stdout
    )


def _load_vault_ops():
    """Import the MCP connector's vault_ops module (pure stdlib, no mcp dep)."""
    import importlib

    mod_dir = REPO_ROOT / "integrations" / "obsidian-mcp-server"
    sys.path.insert(0, str(mod_dir))
    try:
        return importlib.import_module("vault_ops")
    finally:
        sys.path.remove(str(mod_dir))


def test_mcp_vault_ops_save_read_search_roundtrip(tmp_path, monkeypatch):
    """The MCP connector's core data tools must round-trip against a real vault:
    save_note writes an AI-first note (frontmatter + preamble + source: mcp marker)
    to Inbox/, read_note returns it, search finds it. Pure stdlib path - exercises
    the logic the MCP server wraps without needing the mcp package."""
    vault_ops = _load_vault_ops()
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))

    saved = vault_ops.save_note(
        "Hermes connector test",
        "A note about the Hermes agent reading the vault over MCP.",
        note_type="note",
        tags=["mcp", "hermes"],
    )
    rel = saved["saved"]
    assert rel.startswith("Inbox/")

    note = (vault / rel).read_text(encoding="utf-8")
    assert "ai-first: true" in note
    assert "source: mcp" in note
    assert "## For future Claude" in note

    read_back = vault_ops.read_note(rel)
    assert "Hermes agent" in read_back["content"]

    hits = vault_ops.search("hermes", limit=5)
    assert any(h["path"] == rel for h in hits)


def test_mcp_vault_ops_read_guards_path_escape(tmp_path, monkeypatch):
    """read_note must refuse paths that escape the vault root."""
    vault_ops = _load_vault_ops()
    vault = tmp_path / "vault"
    vault.mkdir()
    (tmp_path / "secret.md").write_text("outside the vault\n", encoding="utf-8")
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))

    assert vault_ops.read_note("../secret.md").get("error")


def test_mcp_vault_ops_skills_exclude_niche(monkeypatch):
    """list_skills exposes the real commands but never the niche/agent-only ones,
    and get_skill blocks the excluded set (the #60 contract)."""
    vault_ops = _load_vault_ops()
    names = {s["name"] for s in vault_ops.list_skills()}
    assert "obsidian-save" in names
    assert names.isdisjoint({"obsidian-health", "obsidian-challenge", "create-command"})
    assert vault_ops.get_skill("obsidian-health").get("error")
    assert "instructions" in vault_ops.get_skill("obsidian-save")


def test_architect_scan_emits_manifest(tmp_path):
    """architect_scan.py must produce a JSON manifest with the expected shape
    on a minimal project (no network, no install)."""
    proj = tmp_path / "proj"
    (proj / "src" / "billing").mkdir(parents=True)
    (proj / "src" / "billing" / "charge.py").write_text("def charge():\n    pass\n", encoding="utf-8")
    (proj / "pyproject.toml").write_text(
        '[project]\nname = "paymentbot"\ndependencies = ["requests"]\n', encoding="utf-8"
    )

    result = subprocess.run(
        [sys.executable, "scripts/architect_scan.py", "--path", str(proj)],
        cwd=REPO_ROOT, check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    data = _json_from_stdout(result.stdout)
    assert data["name"] == "paymentbot"
    assert data["kind"] == "python"
    assert any(m["name"] == "billing" for m in data["modules"])
    assert "requests" in data["dependencies"]
    assert any(lang["language"] == "Python" for lang in data["languages"])
