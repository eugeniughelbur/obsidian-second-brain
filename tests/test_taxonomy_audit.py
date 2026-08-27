"""Taxonomy audit (#221's opt-in half): `_meta/taxonomy.md` -> tag findings.

Absence of the file must stay a true no-op (a fresh vault gets zero findings,
never a crash), a known synonym must resolve to its canonical tag unambiguously,
an unlisted tag must be flagged as informational rather than wrong, and a note
already on the canonical form must never be reported.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

TAXONOMY = """# Tag Taxonomy

## docker
- containerization
- containers

## llm
- large-language-model
- large-language-models
"""


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


def _issues(payload: dict, itype: str) -> list:
    return [i for i in payload["issues"] if i["type"] == itype]


def _write_note(vault: Path, name: str, tags: str) -> None:
    (vault / name).write_text(
        f"---\ntype: concept\ntags: [{tags}]\n---\n\n# {name}\n", encoding="utf-8",
    )


def test_no_taxonomy_file_is_a_true_no_op(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_note(vault, "note.md", "containerization")

    payload = _health(vault)
    assert _issues(payload, "tag_synonym") == []
    assert _issues(payload, "tag_not_in_taxonomy") == []


def test_known_synonym_is_flagged_with_its_canonical(tmp_path):
    vault = tmp_path / "vault"
    (vault / "_meta").mkdir(parents=True)
    (vault / "_meta" / "taxonomy.md").write_text(TAXONOMY, encoding="utf-8")
    _write_note(vault, "note.md", "containerization")

    synonyms = _issues(_health(vault), "tag_synonym")
    assert len(synonyms) == 1
    assert synonyms[0]["tag"] == "containerization"
    assert synonyms[0]["canonical"] == "docker"
    assert synonyms[0]["files"] == ["note.md"]


def test_tag_absent_from_taxonomy_is_informational_not_a_synonym_fold(tmp_path):
    vault = tmp_path / "vault"
    (vault / "_meta").mkdir(parents=True)
    (vault / "_meta" / "taxonomy.md").write_text(TAXONOMY, encoding="utf-8")
    _write_note(vault, "note.md", "banana")

    payload = _health(vault)
    unlisted = _issues(payload, "tag_not_in_taxonomy")
    assert len(unlisted) == 1
    assert unlisted[0]["tag"] == "banana"
    assert unlisted[0]["severity"] == "info"
    assert _issues(payload, "tag_synonym") == []


def test_canonical_tag_already_in_use_raises_no_issue(tmp_path):
    vault = tmp_path / "vault"
    (vault / "_meta").mkdir(parents=True)
    (vault / "_meta" / "taxonomy.md").write_text(TAXONOMY, encoding="utf-8")
    _write_note(vault, "note.md", "docker")

    payload = _health(vault)
    assert _issues(payload, "tag_synonym") == []
    assert _issues(payload, "tag_not_in_taxonomy") == []
