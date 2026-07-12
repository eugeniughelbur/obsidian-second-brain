"""Byte-safety tests for the two scripts that rewrite vault notes in place.

heal_links and triage_links must never corrupt what they touch: a non-UTF-8 note
is skipped byte-identical, CRLF line endings survive a rewrite, and a UTF-8 BOM
survives a rewrite. Guards the note_io.py contract (stress-test fix 1,
confirmed findings: encoding corruption via errors="replace" + write_text).
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import note_io  # noqa: E402  (import after sys.path shim, matching sibling tests)

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


# --- write_exact is atomic: an interrupted rewrite never eats the original note ---
# (stress-test round 2: write_bytes truncated-then-streamed in place, so a crash or
# Ctrl-C mid-write could leave a real note truncated or empty with no backup.)

def _temp_leftovers(directory: Path) -> list[Path]:
    """The sibling temp files write_exact creates while swapping bytes in."""
    return [p for p in directory.iterdir() if p.name.endswith(".tmp")]


def test_write_exact_round_trips_bytes_and_leaves_no_temp(tmp_path):
    note = tmp_path / "note.md"
    original = b"line one\r\nsee [[x]]\r\nend\r\n"  # CRLF, to prove no translation
    note.write_bytes(original)

    note_io.write_exact(note, "﻿new body\nsecond line\n")

    # Exact bytes we asked for, including the BOM, and nothing was lost.
    assert note.read_bytes() == "﻿new body\nsecond line\n".encode("utf-8")
    # The temp file was renamed away, never left behind in the vault.
    assert _temp_leftovers(tmp_path) == []


def test_write_exact_keeps_original_when_rename_fails(tmp_path, monkeypatch):
    """If the final swap fails (disk full, crash, interrupt), the original note must
    survive byte-for-byte and no half-written temp may linger."""
    note = tmp_path / "note.md"
    original = b"# precious\n\nirreplaceable content\n"
    note.write_bytes(original)

    def boom(_src, _dst):
        raise OSError("simulated crash during the atomic swap")

    monkeypatch.setattr(note_io.os, "replace", boom)

    with pytest.raises(OSError):
        note_io.write_exact(note, "this must never reach disk")

    # The original is exactly as it was, and the temp file was cleaned up.
    assert note.read_bytes() == original
    assert _temp_leftovers(tmp_path) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits not meaningful on Windows")
def test_write_exact_preserves_permission_bits(tmp_path):
    note = tmp_path / "note.md"
    note.write_bytes(b"body\n")
    note.chmod(0o640)

    note_io.write_exact(note, "rewritten\n")

    # A rewrite must not quietly widen or narrow a note's mode (mkstemp defaults 0600).
    assert stat.S_IMODE(note.stat().st_mode) == 0o640


# --- triage CREATE stays inside the vault: a crafted link can't write anywhere else ---
# (stress-test round 2: the stub path was built straight from wikilink text, so a
# CREATE verdict on [[../../x]] or [[/abs/x]] escaped the vault or crashed the batch.)

def _make_triage_vault(tmp_path: Path, link_text: str) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text(f"# Note\n\nrefers to [[{link_text}]] here\n", encoding="utf-8")
    return vault


def test_triage_create_refuses_parent_traversal(tmp_path):
    vault = _make_triage_vault(tmp_path, "../../escaped/pwned")
    verdicts = tmp_path / "verdicts.txt"
    verdicts.write_text("CREATE [[../../escaped/pwned]]\n", encoding="utf-8")

    result = _run("triage_links.py", "--path", str(vault), "--apply", "--from", str(verdicts))

    assert result.returncode == 0, result.stderr
    assert "unsafe link path" in result.stdout
    # Nothing was written outside the vault, anywhere up the tree.
    assert not (tmp_path / "escaped").exists()
    assert not (tmp_path.parent / "escaped").exists()
    # And nothing bogus was created inside the stubs folder either.
    stubs = vault / "wiki" / "stubs"
    assert not stubs.exists() or list(stubs.glob("**/*.md")) == []


def test_triage_create_refuses_absolute_path(tmp_path):
    target = tmp_path / "outside_marker"
    vault = _make_triage_vault(tmp_path, f"{target}/pwned")
    verdicts = tmp_path / "verdicts.txt"
    verdicts.write_text(f"CREATE [[{target}/pwned]]\n", encoding="utf-8")

    result = _run("triage_links.py", "--path", str(vault), "--apply", "--from", str(verdicts))

    assert result.returncode == 0, result.stderr
    assert not (Path(f"{target}") / "pwned.md").exists()
    assert not target.exists()


def test_triage_create_still_makes_a_normal_stub(tmp_path):
    """The guard must not block legitimate stub creation."""
    vault = _make_triage_vault(tmp_path, "Legit Topic")
    verdicts = tmp_path / "verdicts.txt"
    verdicts.write_text("CREATE [[Legit Topic]]\n", encoding="utf-8")

    result = _run("triage_links.py", "--path", str(vault), "--apply", "--from", str(verdicts))

    assert result.returncode == 0, result.stderr
    stub = vault / "wiki" / "stubs" / "Legit Topic.md"
    assert stub.is_file()
    assert "type: stub" in stub.read_text(encoding="utf-8")
