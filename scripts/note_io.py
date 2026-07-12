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
"""
import os
import stat as stat_mod
import tempfile
from pathlib import Path


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
        keep_mode = stat_mod.S_IMODE(os.stat(path).st_mode)
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
            os.chmod(tmp, keep_mode)
        os.replace(tmp, path)
    except BaseException:
        # Interrupted or failed before the rename: the original is untouched. Drop
        # the temp so a half-written file never lingers in the vault, then re-raise.
        # BaseException (not Exception) so a Ctrl-C mid-write still cleans up.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
