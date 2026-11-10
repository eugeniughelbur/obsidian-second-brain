# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""note_io.py - byte-exact read/write for scripts that rewrite vault notes in place.

Scripts that only READ a note may decode forgivingly (errors="replace"); a lossy
copy that dies in memory hurts nobody. A script that reads, edits, and WRITES BACK
must never do that: every undecodable byte would be saved to disk as a permanent
U+FFFD, and the text-mode round-trip would silently rewrite CRLF line endings.

Rule enforced here: strict UTF-8 in, byte-exact UTF-8 out, and a file we cannot
decode losslessly is never rewritten at all.

Writes are atomic. A note is rewritten by writing a sibling temp file and renaming
it over the target, so an interrupted write (Ctrl-C, a crash, a disk that fills
mid-write) can never leave a real note truncated or half-written. The original
survives untouched until one final same-filesystem rename swaps the new bytes in.

Atomic is not the same as safe from a concurrent writer (#217). Every caller here
reads a note, transforms the text, and writes it back, and the gap between the
read and the write is where a second writer's change is lost - silently, because
both writes succeed. A multi-adapter vault runs in exactly that shape: a Hermes
cron agent and a live session against one vault, plus LiveSync landing a third
device's edits as a local file change. `write_exact_if_unchanged` closes that by
checking, immediately before the rename, that the note still holds the bytes the
caller read. It refuses rather than overwrites. See NoteChangedError.
"""
import os
import stat as stat_mod
import tempfile
from pathlib import Path


class NoteChangedError(RuntimeError):
    """A note changed on disk between the caller's read and its write (#217).

    Carries `path` so a caller processing many notes can report which one it
    skipped and keep going. Raised, never swallowed: the whole point is that a
    lost update stops being silent.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        super().__init__(
            f"{self.path} changed on disk since it was read - refusing to overwrite. "
            "Another writer (a scheduled agent, a second session, or a sync client) "
            "edited it; re-read the note and redo the change."
        )


def read_exact(path: Path) -> str | None:
    """Decode the file as strict UTF-8, or return None if it is not valid UTF-8.

    Bytes are decoded directly, so CRLF line endings and a leading BOM survive in
    the returned text and round-trip unchanged through write_exact.
    """
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return None


def write_exact(path: Path, text: str) -> None:
    """Rewrite path with text as UTF-8 bytes, atomically and with no newline translation.

    The bytes go to a temp file in the same directory, so the closing os.replace is a
    same-filesystem rename (atomic on POSIX and Windows). If the write is interrupted
    or fails before that rename, the temp file is removed and the original note is left
    exactly as it was. The target's permission bits are carried over so a rewrite never
    quietly changes a note's mode.
    """
    data = text.encode("utf-8")
    directory = path.parent
    try:
        keep_mode = stat_mod.S_IMODE(Path(path).stat().st_mode)
    except OSError:
        keep_mode = None  # new file: let the umask decide, as write_bytes would have

    fd, tmp = tempfile.mkstemp(dir=directory, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass  # durability is best-effort; the atomic rename is not
        if keep_mode is not None:
            Path(tmp).chmod(keep_mode)
        Path(tmp).replace(path)
    except BaseException:
        # Interrupted or failed before the rename: the original is untouched. Drop
        # the temp so a half-written file never lingers in the vault, then re-raise.
        # BaseException (not Exception) so a Ctrl-C mid-write still cleans up.
        try:
            Path(tmp).unlink()
        except OSError:
            pass
        raise


def write_exact_if_unchanged(path: Path, text: str, expected: str | None) -> None:
    """write_exact, but only while the note still holds the bytes it was read with.

    `expected` is what read_exact returned for this path, or None when the caller
    means "this note must not exist yet". If the file on disk no longer matches,
    nothing is written and NoteChangedError is raised.

    What this does and does not buy. It does not make the read and the write one
    operation - a writer that lands between the comparison below and the rename
    a few microseconds later still wins. What it removes is the window that
    actually loses data here: the seconds or minutes an agent spends thinking
    between reading a note and writing it back, during which a cron agent, a
    second session, or a sync client rewrites the same file. A lock would not
    cover the last of those anyway, because a change replicated onto disk by a
    sync client participates in no lock this process could hold.

    The comparison is over bytes, not mtime: a same-size edit inside one
    timestamp tick is invisible to stat on a filesystem with coarse timestamps,
    and a synced vault is exactly where those turn up.
    """
    if expected is None:
        # "must not exist yet" is checked as absence, never as a read result:
        # read_exact returns None for a file that is not valid UTF-8 too, and
        # treating that as absent would let this clobber the one class of file
        # the module exists to refuse to rewrite.
        if path.exists():
            raise NoteChangedError(path)
    elif read_exact(path) != expected:
        raise NoteChangedError(path)
    write_exact(path, text)
