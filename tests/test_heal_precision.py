"""Precision tests for heal_links auto-fixes and triage deletes.

The healer's contract is "only certain matches are ever auto-applied". These pin
the three ways certainty used to leak (stress-test fix 3/24):
  1. ASCII-folding erased whole alphabets, so [[Ελλάδα]] / [[مرحبا]] / [[🚀🚀]]
     all slugged to "" and matched whichever single note also folded to nothing.
  2. Folding deleted meaningful symbols, so [[C++]] slugged to "c" and was
     confidently repointed to C.md.
  3. Rewrites and deletes edited [[links]] inside code fences that the counter
     never reported, so apply exceeded what dry-run promised.
Plus the win: honest slugs keep every alphabet, so Cyrillic Title-case links now
heal correctly instead of falling to the fuzzy guesser.
"""

from __future__ import annotations

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


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


def test_cyrillic_title_link_heals_to_kebab_file(tmp_path):
    vault = _vault(tmp_path)
    (vault / "привет-мир.md").write_text("# note\n", encoding="utf-8")
    (vault / "linker.md").write_text("see [[Привет Мир]]\n", encoding="utf-8")

    result = _run("heal_links.py", "--path", str(vault), "--batch")
    assert result.returncode == 0, result.stderr
    healed = (vault / "linker.md").read_text(encoding="utf-8")
    assert "[[привет-мир|Привет Мир]]" in healed


def test_foreign_alphabet_link_never_matches_unrelated_note(tmp_path):
    """Old slugify folded Ελλάδα, مرحبا and 🚀🚀 all to "" and repointed them to
    the single note whose title also folded to nothing."""
    vault = _vault(tmp_path)
    (vault / "привет-мир.md").write_text("# note\n", encoding="utf-8")
    original = "see [[Ελλάδα]] and [[مرحبا]] and [[🚀🚀]]\n"
    (vault / "linker.md").write_text(original, encoding="utf-8")

    result = _run("heal_links.py", "--path", str(vault), "--batch")
    assert result.returncode == 0, result.stderr
    assert (vault / "linker.md").read_text(encoding="utf-8") == original


def test_cpp_is_not_repointed_to_c(tmp_path):
    vault = _vault(tmp_path)
    (vault / "c.md").write_text("# the C language\n", encoding="utf-8")
    original = "comparing [[C++]] with C\n"
    (vault / "linker.md").write_text(original, encoding="utf-8")

    result = _run("heal_links.py", "--path", str(vault), "--batch")
    assert result.returncode == 0, result.stderr
    assert (vault / "linker.md").read_text(encoding="utf-8") == original


def test_heal_never_rewrites_inside_code(tmp_path):
    vault = _vault(tmp_path)
    (vault / "host-iptables-rules.md").write_text("# rules\n", encoding="utf-8")
    (vault / "linker.md").write_text(
        "prose [[Host iptables rules]]\n\n"
        "```bash\n# example: [[Host iptables rules]]\n```\n\n"
        "inline `[[Host iptables rules]]` stays\n",
        encoding="utf-8",
    )

    result = _run("heal_links.py", "--path", str(vault), "--batch")
    assert result.returncode == 0, result.stderr
    healed = (vault / "linker.md").read_text(encoding="utf-8")
    assert "prose [[host-iptables-rules|Host iptables rules]]" in healed
    assert "# example: [[Host iptables rules]]" in healed
    assert "`[[Host iptables rules]]`" in healed


def test_bracket_names_are_never_auto_touched(tmp_path):
    vault = _vault(tmp_path)
    (vault / "note-draft.md").write_text("# draft\n", encoding="utf-8")
    original = "see [[note [draft]]]\n"
    (vault / "linker.md").write_text(original, encoding="utf-8")

    result = _run("heal_links.py", "--path", str(vault), "--batch")
    assert result.returncode == 0, result.stderr
    assert (vault / "linker.md").read_text(encoding="utf-8") == original


def test_triage_delete_skips_code_occurrences(tmp_path):
    vault = _vault(tmp_path)
    (vault / "note.md").write_text(
        "prose [[Gone Note]] here\n\n```\nexample [[Gone Note]] in fence\n```\n",
        encoding="utf-8",
    )
    verdicts = tmp_path / "verdicts.txt"
    verdicts.write_text("DELETE [[Gone Note]]\n", encoding="utf-8")

    result = _run(
        "triage_links.py", "--path", str(vault), "--apply", "--from", str(verdicts)
    )
    assert result.returncode == 0, result.stderr
    edited = (vault / "note.md").read_text(encoding="utf-8")
    assert "prose Gone Note here" in edited
    assert "example [[Gone Note]] in fence" in edited
