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
    assert 'okf_version: "0.2"' in bundle_index
    assert "MY NAV FILE" not in bundle_index
    # 3 real notes (dotted, broken, linker); the vault index must not be counted.
    assert "3 concept docs" in result.stdout


# --- OKF v0.2 (supersedes v0.1; #213) ----------------------------------------

def _v02_vault(tmp_path: Path) -> Path:
    """A vault carrying exactly the frontmatter v0.2's new fields map from."""
    vault = tmp_path / "vault"
    (vault / "Knowledge").mkdir(parents=True)
    (vault / "Knowledge" / "Cited.md").write_text(
        "---\ntype: concept\ndate: 2026-07-11\ntags: [concept]\n---\n\nA cited concept.\n",
        encoding="utf-8",
    )
    (vault / "Knowledge" / "Decision.md").write_text(
        "---\ntype: decision\ndate: 2026-07-12\ntags: [decision]\n"
        'sources: ["[[Cited]]", "https://example.test/report", "[[Nowhere At All]]"]\n---\n\n'
        "We chose the thing.\n",
        encoding="utf-8",
    )
    (vault / "Knowledge" / "Retired.md").write_text(
        "---\ntype: redirect\ndate: 2026-07-13\ntags: [redirect]\n"
        'redirects_to: "[[Cited]]"\n---\n\nMerged into [[Cited]].\n',
        encoding="utf-8",
    )
    (vault / "Knowledge" / "Withdrawn.md").write_text(
        "---\ntype: concept\ndate: 2026-07-14\ntags: [concept]\nstatus: superseded\n---\n\nOld view.\n",
        encoding="utf-8",
    )
    (vault / "Knowledge" / "Shipped.md").write_text(
        "---\ntype: project\ndate: 2026-07-15\ntags: [project]\nstatus: done\n---\n\nFinished work.\n",
        encoding="utf-8",
    )
    return vault


def _exported(vault: Path, rel: str) -> str:
    return (vault / "_export" / "okf" / rel).read_text(encoding="utf-8")


def test_production_time_is_generated_not_a_bare_timestamp(tmp_path):
    """v0.2's first breaking change. A bundle stamped 0.2 that still writes
    `timestamp:` is emitting v0.1 under a v0.2 label."""
    vault = _v02_vault(tmp_path)
    assert _run_export(vault).returncode == 0
    note = _exported(vault, "Knowledge/Cited.md")
    assert "generated:" in note
    assert "  by: obsidian-second-brain" in note
    assert "  at: 2026-07-11T00:00:00Z" in note
    assert "\ntimestamp:" not in note, "the superseded v0.1 field is still being written"


def test_sources_move_to_frontmatter_and_resolve_like_body_links(tmp_path):
    """v0.2's second breaking change: provenance leaves the body. A wikilinked
    source has to land on the same bundle path the body link does, or the
    citation and the link disagree about which file is meant."""
    vault = _v02_vault(tmp_path)
    assert _run_export(vault).returncode == 0
    note = _exported(vault, "Knowledge/Decision.md")
    assert "sources:" in note
    assert "  - resource: Cited.md" in note, "a wikilinked source did not resolve to its note"
    # yaml_val quotes a scalar carrying a colon; either spelling is valid YAML.
    assert "https://example.test/report" in note
    assert "Nowhere At All" not in note, (
        "an unresolvable source was exported as a dangling resource; OKF requires "
        "a real resource per entry"
    )


def test_a_note_with_no_sources_gets_no_sources_key(tmp_path):
    vault = _v02_vault(tmp_path)
    assert _run_export(vault).returncode == 0
    assert "sources:" not in _exported(vault, "Knowledge/Cited.md")


def test_only_withdrawn_knowledge_exports_as_deprecated(tmp_path):
    """`done` is the trap. A finished project is completed knowledge, not
    withdrawn knowledge, and exporting it as deprecated tells every downstream
    consumer to discount a true record."""
    vault = _v02_vault(tmp_path)
    assert _run_export(vault).returncode == 0
    assert "status: deprecated" in _exported(vault, "Knowledge/Retired.md"), (
        "a note retired by a merge is deprecated by construction"
    )
    assert "status: deprecated" in _exported(vault, "Knowledge/Withdrawn.md")
    shipped = _exported(vault, "Knowledge/Shipped.md")
    assert "status:" not in shipped, (
        "a completed project was exported with a lifecycle status it never stated"
    )
    assert "status:" not in _exported(vault, "Knowledge/Cited.md"), (
        "a plain note gained a status; stable is the spec default and silence says it"
    )


def test_a_title_that_looks_like_a_date_or_number_stays_text(tmp_path):
    """A daily note named 2026-01-05.md has no title of its own, so the file
    name is used. Written bare, YAML read it back as a date, and a note headed
    `# No` or `# 2026` came back as False or an integer. OKF `title` is text."""
    import yaml

    vault = tmp_path / "vault"
    (vault / "Daily").mkdir(parents=True)
    (vault / "Daily" / "2026-01-05.md").write_text(
        "---\ntype: daily\ndate: 2026-01-05\n---\n\nWent for a run.\n", encoding="utf-8"
    )
    (vault / "No.md").write_text("---\ntype: concept\ntags: ['2026']\n---\n# No\n\nText.\n", encoding="utf-8")
    # A typo'd daily note: not a real date, so YAML raises instead of loading it.
    (vault / "Daily" / "2026-02-30.md").write_text("Typo day.\n", encoding="utf-8")
    assert _run_export(vault).returncode == 0

    def front(rel):
        text = (vault / "_export" / "okf" / rel).read_text(encoding="utf-8")
        return yaml.safe_load(text.split("---\n")[1])

    assert front("Daily/2026-01-05.md")["title"] == "2026-01-05"
    assert front("Daily/2026-02-30.md")["title"] == "2026-02-30"
    assert front("No.md")["title"] == "No"
    assert front("No.md")["tags"] == ["2026"]
