"""Byte-safety tests for the two scripts that rewrite vault notes in place.

heal_links and triage_links must never corrupt what they touch: a non-UTF-8 note
is skipped byte-identical, CRLF line endings survive a rewrite, and a UTF-8 BOM
survives a rewrite. Guards the note_io.py contract (stress-test fix 1,
confirmed findings: encoding corruption via errors="replace" + write_text).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

LATIN1_NOTE = b"---\ntags: [test]\n---\n\ncaf\xe9 mentions [[Real Note]]\n"


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


def _make_heal_vault(tmp_path: Path) -> Path:
    """Three notes with healable Title-case links to kebab-case files, one note
    per encoding hazard so each file gets its own independent fix."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "real-note.md").write_text("# Real\n", encoding="utf-8")
    (vault / "second-note.md").write_text("# Second\n", encoding="utf-8")
    (vault / "third-note.md").write_text("# Third\n", encoding="utf-8")
    (vault / "latin1.md").write_bytes(LATIN1_NOTE)
    (vault / "crlf.md").write_bytes(b"line one\r\nsee [[Second Note]]\r\nlast line\r\n")
    (vault / "bom.md").write_bytes(b"\xef\xbb\xbfintro\nsee [[Third Note]]\n")
    return vault


def test_heal_batch_skips_non_utf8_byte_identical(tmp_path):
    vault = _make_heal_vault(tmp_path)
    result = _run("heal_links.py", "--path", str(vault), "--batch")

    assert result.returncode == 0, result.stderr
    assert "SKIPPED (not valid UTF-8" in result.stdout
    # The unreadable note is untouched, down to the last byte.
    assert (vault / "latin1.md").read_bytes() == LATIN1_NOTE


def test_heal_batch_preserves_crlf_line_endings(tmp_path):
    vault = _make_heal_vault(tmp_path)
    result = _run("heal_links.py", "--path", str(vault), "--batch")

    assert result.returncode == 0, result.stderr
    healed = (vault / "crlf.md").read_bytes()
    assert b"[[second-note|Second Note]]" in healed
    # Every newline in the file is still a CRLF: healing one link must not
    # silently rewrite the file's line endings.
    assert healed.count(b"\n") == healed.count(b"\r\n")


def test_heal_batch_preserves_utf8_bom(tmp_path):
    vault = _make_heal_vault(tmp_path)
    result = _run("heal_links.py", "--path", str(vault), "--batch")

    assert result.returncode == 0, result.stderr
    healed = (vault / "bom.md").read_bytes()
    assert healed.startswith(b"\xef\xbb\xbf")
    assert b"[[third-note|Third Note]]" in healed


def test_heal_loop_skips_non_utf8_without_spinning(tmp_path):
    """--apply picks one fix per pass; a non-UTF-8 file must be skipped and
    remembered, not retried forever."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "real-note.md").write_text("# Real\n", encoding="utf-8")
    (vault / "latin1.md").write_bytes(LATIN1_NOTE)
    result = _run("heal_links.py", "--path", str(vault), "--apply", "--max", "5")

    assert result.returncode == 0, result.stderr
    assert "SKIPPED (not valid UTF-8" in result.stdout
    assert result.stdout.count("SKIPPED") == 1
    assert (vault / "latin1.md").read_bytes() == LATIN1_NOTE


def test_triage_apply_delete_is_byte_safe(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    latin1 = b"---\ntags: [test]\n---\n\ncaf\xe9 junk [[Zzz Junk]]\n"
    (vault / "latin1.md").write_bytes(latin1)
    (vault / "crlf.md").write_bytes(b"top\r\njunk [[Yyy Junk]] here\r\n")
    verdicts = tmp_path / "verdicts.txt"
    verdicts.write_text("DELETE [[Zzz Junk]]\nDELETE [[Yyy Junk]]\n", encoding="utf-8")

    result = _run(
        "triage_links.py", "--path", str(vault), "--apply", "--from", str(verdicts)
    )

    assert result.returncode == 0, result.stderr
    # Non-UTF-8 note: skipped, byte-identical, and reported.
    assert "SKIPPED (not valid UTF-8" in result.stdout
    assert (vault / "latin1.md").read_bytes() == latin1
    # UTF-8 note: link unwrapped, CRLF endings intact.
    edited = (vault / "crlf.md").read_bytes()
    assert b"[[Yyy Junk]]" not in edited
    assert b"junk Yyy Junk here" in edited
    assert edited.count(b"\n") == edited.count(b"\r\n")
