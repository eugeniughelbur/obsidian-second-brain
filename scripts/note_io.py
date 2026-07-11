"""note_io.py - byte-exact read/write for scripts that rewrite vault notes in place.

Scripts that only READ a note may decode forgivingly (errors="replace"); a lossy
copy that dies in memory hurts nobody. A script that reads, edits, and WRITES BACK
must never do that: every undecodable byte would be saved to disk as a permanent
U+FFFD, and the text-mode round-trip would silently rewrite CRLF line endings.

Rule enforced here: strict UTF-8 in, byte-exact UTF-8 out, and a file we cannot
decode losslessly is never rewritten at all.
"""
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
    """Write text back as UTF-8 bytes, with no newline translation."""
    path.write_bytes(text.encode("utf-8"))
