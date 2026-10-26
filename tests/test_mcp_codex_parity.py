"""Codex/MCP parity regressions found against a real-world vault. Fixture
names and facts here are synthetic.

These tests cover capabilities direct-filesystem Claude already had but MCP-only
clients lacked: non-duplicating AI preambles, canonical paths, complete reads,
safe exact edits, Inbox graduation, documented validation exceptions, and alias
resolution.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "integrations" / "obsidian-mcp-server"))


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(root))
    import vault_ops
    importlib.reload(vault_ops)
    return root, vault_ops


def test_save_collapses_repeated_legacy_preambles(vault):
    root, ops = vault
    result = ops.save_note(
        "Contact",
        "## For future Claude\n\n## For future Claude\n\n"
        "This contact may help with the launch plan. Verify availability.\n\n"
        "## Details\n\nBody.",
    )
    text = (root / result["saved"]).read_text(encoding="utf-8")
    assert text.count("## For future agent") == 1
    assert "For future Claude" not in text
    assert "Verify availability" in text


def test_save_supports_canonical_explicit_path(vault):
    root, ops = vault
    result = ops.save_note(
        "Alex Rivera",
        "Potential launch advisor. Availability is not confirmed.",
        note_type="person",
        path="wiki/entities/Alex Rivera.md",
    )
    assert result["saved"] == "wiki/entities/Alex Rivera.md"
    assert (root / result["saved"]).is_file()
    assert not (root / "Inbox").exists()


def test_save_explicit_path_guards(vault):
    _, ops = vault
    assert ops.save_note("x", "valid summary", path="../escape.md").get("error")
    assert ops.save_note("x", "valid summary", path="raw/escape.md").get("error")
    assert ops.save_note("x", "valid summary", path="wiki/no-extension").get("error")


def test_read_note_paginates_to_eof(vault):
    root, ops = vault
    payload = "a" * 20_000 + "TAIL"
    (root / "large.md").write_text(payload, encoding="utf-8")
    first = ops.read_note("large.md")
    assert first["truncated"] is True
    assert first["next_offset"] == 20_000
    second = ops.read_note("large.md", offset=first["next_offset"])
    assert second["content"] == "TAIL"
    assert second["truncated"] is False and second["next_offset"] is None


def _valid_note(preamble: str) -> str:
    return (
        "---\ntype: note\ndate: 2026-08-12\ntags: [note]\nai-first: true\n---\n\n"
        + preamble
    )


def test_validator_accepts_generic_and_legacy_but_rejects_empty_duplicates(vault):
    root, ops = vault
    (root / "generic.md").write_text(
        _valid_note("## For future agent\nUseful summary.\n"), encoding="utf-8"
    )
    (root / "legacy.md").write_text(
        _valid_note("## For future agent\nUseful legacy summary.\n"), encoding="utf-8"
    )
    (root / "broken.md").write_text(
        _valid_note("## For future agent\n\n## For future agent\n\n## Details\n"),
        encoding="utf-8",
    )
    assert ops.validate_note("generic.md")["ok"]
    assert ops.validate_note("legacy.md")["ok"]
    issues = " ".join(ops.validate_note("broken.md")["issues"])
    assert "duplicate" in issues and "empty" in issues


def test_validator_allows_embedded_source_preambles_in_a_bundle(vault):
    root, ops = vault
    (root / "bundle.md").write_text(
        _valid_note(
            "## For future agent\nOuter bundle summary.\n\n"
            "## Embedded note A\n\n## For future Claude\nEmbedded summary A.\n\n"
            "## Embedded note B\n\n## For future agent\nEmbedded summary B.\n"
        ),
        encoding="utf-8",
    )
    assert ops.validate_note("bundle.md")["ok"]


def test_validator_honours_board_exception(vault):
    root, ops = vault
    (root / "boards").mkdir()
    (root / "boards" / "Personal.md").write_text(
        "---\nkanban-plugin: board\n---\n\n## Waiting\n- [ ] reply\n",
        encoding="utf-8",
    )
    result = ops.validate_note("boards/Personal.md")
    assert result["ok"] and result["exempt"]


def test_validator_resolves_scalar_inline_and_block_aliases(vault):
    root, ops = vault
    (root / "people").mkdir()
    (root / "people" / "dated.md").write_text(
        _valid_note(
            "aliases:\n"  # body text does not count; frontmatter aliases below
        ), encoding="utf-8"
    )
    # Three actual entity notes exercise every supported YAML spelling.
    for name, alias_line in (
        ("one", "aliases: Alex Rivera"),
        ("two", "aliases: [Big Boss, El Jefe]"),
        ("three", "aliases:\n  - Deep Name"),
    ):
        (root / "people" / f"{name}.md").write_text(
            "---\ntype: person\ndate: 2026-08-12\ntags: [person]\n"
            f"{alias_line}\nai-first: true\n---\n\n"
            "## For future agent\nUseful summary.\n",
            encoding="utf-8",
        )
    (root / "links.md").write_text(
        _valid_note(
            "## For future agent\nLinks [[Alex Rivera]], [[Big Boss]], "
            "[[El Jefe]], and [[Deep Name]].\n"
        ), encoding="utf-8"
    )
    assert ops.validate_note("links.md")["ok"]


def test_replace_text_requires_one_exact_anchor(vault):
    root, ops = vault
    note = root / "note.md"
    note.write_text("before UNIQUE after\n", encoding="utf-8")
    assert ops.replace_text("note.md", "UNIQUE", "fixed")["replacements"] == 1
    assert note.read_text(encoding="utf-8") == "before fixed after\n"
    note.write_text("same same\n", encoding="utf-8")
    assert ops.replace_text("note.md", "same", "x").get("error")
    assert note.read_text(encoding="utf-8") == "same same\n"


def test_move_note_graduates_inbox_without_overwrite(vault):
    root, ops = vault
    (root / "Inbox").mkdir()
    src = root / "Inbox" / "capture.md"
    src.write_text("body\n", encoding="utf-8")
    result = ops.move_note("Inbox/capture.md", "wiki/entities/Contact.md")
    assert result["destination"] == "wiki/entities/Contact.md"
    assert not src.exists()
    assert (root / "wiki/entities/Contact.md").read_text(encoding="utf-8") == "body\n"
    (root / "Inbox" / "second.md").write_text("second\n", encoding="utf-8")
    assert ops.move_note("Inbox/second.md", "wiki/entities/Contact.md").get("error")


def test_move_note_does_not_overwrite_on_a_destination_race(vault, monkeypatch):
    root, ops = vault
    (root / "Inbox").mkdir()
    src = root / "Inbox" / "capture.md"
    src.write_text("precious source\n", encoding="utf-8")
    dst = root / "wiki/entities/Contact.md"
    real_open = ops.os.open

    def raced_open(path, flags, *args):
        # Another writer creates the destination after the exists() preflight
        # and before move_note's own create.
        if Path(path) == dst and flags & ops.os.O_EXCL:
            dst.write_text("other writer\n", encoding="utf-8")
        return real_open(path, flags, *args)

    monkeypatch.setattr(ops.os, "open", raced_open)
    result = ops.move_note("Inbox/capture.md", "wiki/entities/Contact.md")
    assert result.get("error")
    assert src.read_text(encoding="utf-8") == "precious source\n"
    assert dst.read_text(encoding="utf-8") == "other writer\n"


def test_move_note_never_puts_source_and_destination_on_one_inode(vault, monkeypatch):
    """#324: a hard link made source and destination one file for a moment.

    Cloud sync clients (OneDrive, Dropbox, iCloud) track files by identity; on
    OneDrive that window left two notes with swapped contents. No sync client
    runs here, so this pins the mechanism: the destination must have its own
    inode before the source is removed.
    """
    root, ops = vault
    (root / "Inbox").mkdir()
    src = root / "Inbox" / "capture.md"
    body = b"---\r\ntype: note\r\n---\r\n\xef\xbb\xbf caf\xc3\xa9\r\n"
    src.write_bytes(body)
    dst = root / "wiki/entities/Contact.md"
    seen = []
    real_unlink = Path.unlink

    def checked_unlink(self, *args, **kwargs):
        if self == src:
            seen.append((src.stat().st_ino, dst.stat().st_ino, src.stat().st_nlink))
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", checked_unlink)
    result = ops.move_note("Inbox/capture.md", "wiki/entities/Contact.md")
    assert result.get("moved") == "Inbox/capture.md", result
    assert len(seen) == 1, seen
    src_ino, dst_ino, src_links = seen[0]
    assert src_ino != dst_ino, "destination shared the source inode when the source was removed"
    assert src_links == 1, "source had a second hard link when it was removed"
    assert not src.exists()
    assert dst.read_bytes() == body
    assert dst.stat().st_nlink == 1


def test_move_note_keeps_an_edit_made_to_the_source_mid_move(vault, monkeypatch):
    root, ops = vault
    (root / "Inbox").mkdir()
    src = root / "Inbox" / "capture.md"
    src.write_text("first\n", encoding="utf-8")
    dst = root / "wiki/entities/Contact.md"
    real_open = ops.os.open

    def editing_open(path, flags, *args):
        # The editor saves the source after move_note has read it.
        if Path(path) == dst and flags & ops.os.O_EXCL:
            with src.open("a", encoding="utf-8") as fh:
                fh.write("typed during the move\n")
        return real_open(path, flags, *args)

    monkeypatch.setattr(ops.os, "open", editing_open)
    result = ops.move_note("Inbox/capture.md", "wiki/entities/Contact.md")
    assert result.get("error"), result
    assert src.read_text(encoding="utf-8") == "first\ntyped during the move\n"
    assert not dst.exists()


def test_move_note_reports_an_unreadable_source_instead_of_raising(vault, monkeypatch):
    root, ops = vault
    (root / "Inbox").mkdir()
    src = root / "Inbox" / "capture.md"
    src.write_text("locked\n", encoding="utf-8")
    real_read = Path.read_bytes

    def locked_read(self):
        if self == src:
            raise PermissionError("locked by another process")
        return real_read(self)

    monkeypatch.setattr(Path, "read_bytes", locked_read)
    result = ops.move_note("Inbox/capture.md", "wiki/entities/Contact.md")
    assert "could not read source" in result.get("error", ""), result
    assert src.exists()
    assert not (root / "wiki/entities/Contact.md").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="Windows does not let another writer replace a file this process holds open")
def test_move_note_cleanup_never_removes_a_destination_it_did_not_create(vault, monkeypatch):
    """A failed move removes its own half-made copy, not a file that replaced it.

    On ext4 the replacing file gets the freed inode number at once, so the
    check only holds while move_note still has its own descriptor open.
    """
    root, ops = vault
    (root / "Inbox").mkdir()
    src = root / "Inbox" / "capture.md"
    src.write_text("mine\n", encoding="utf-8")
    dst = root / "wiki/entities/Contact.md"
    real_read = Path.read_bytes
    calls = []

    def racing_read(self):
        data = real_read(self)
        if self == src:
            calls.append(1)
            if len(calls) == 2:
                # The pre-unlink re-read: another writer swaps in its own
                # destination and the source has changed, so the move fails.
                dst.unlink()
                dst.write_text("other writer\n", encoding="utf-8")
                return b"changed\n"
        return data

    monkeypatch.setattr(Path, "read_bytes", racing_read)
    result = ops.move_note("Inbox/capture.md", "wiki/entities/Contact.md")
    assert result.get("error"), result
    assert src.read_text(encoding="utf-8") == "mine\n"
    assert dst.read_text(encoding="utf-8") == "other writer\n"


def test_move_note_returns_an_error_when_the_destination_write_fails(vault, monkeypatch):
    root, ops = vault
    (root / "Inbox").mkdir()
    src = root / "Inbox" / "capture.md"
    src.write_text("keep me\n", encoding="utf-8")

    def full_disk(_fd, _data):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(ops.os, "write", full_disk)
    result = ops.move_note("Inbox/capture.md", "wiki/entities/Contact.md")
    assert "No space left" in result.get("error", ""), result
    assert src.read_text(encoding="utf-8") == "keep me\n"
    assert not (root / "wiki/entities/Contact.md").exists()


def test_move_note_leaves_a_copy_it_cannot_identify(vault, monkeypatch):
    """An inode of 0 (some network shares) cannot prove the copy is ours."""
    root, ops = vault
    (root / "Inbox").mkdir()
    src = root / "Inbox" / "capture.md"
    src.write_text("first\n", encoding="utf-8")
    real_open, real_fstat = ops.os.open, ops.os.fstat

    def editing_open(path, flags, *args):
        if flags & ops.os.O_EXCL:
            with src.open("a", encoding="utf-8") as fh:
                fh.write("edit\n")
        return real_open(path, flags, *args)

    class NoInode:
        def __init__(self, st):
            self._st = st
            self.st_ino = 0

        def __getattr__(self, name):
            return getattr(self._st, name)

    dst = root / "wiki/entities/Contact.md"
    real_stat = ops.os.stat

    def stat_without_inode(path, *args, **kwargs):
        st = real_stat(path, *args, **kwargs)
        return NoInode(st) if Path(path) == dst else st

    monkeypatch.setattr(ops.os, "open", editing_open)
    monkeypatch.setattr(ops.os, "fstat", lambda fd: NoInode(real_fstat(fd)))
    monkeypatch.setattr(ops.os, "stat", stat_without_inode)
    result = ops.move_note("Inbox/capture.md", "wiki/entities/Contact.md")
    assert result.get("error"), result
    assert src.read_text(encoding="utf-8") == "first\nedit\n"
    assert dst.exists()


def test_move_note_fails_instead_of_spinning_when_a_write_makes_no_progress(vault, monkeypatch):
    root, ops = vault
    (root / "Inbox").mkdir()
    src = root / "Inbox" / "capture.md"
    src.write_text("keep me\n", encoding="utf-8")
    monkeypatch.setattr(ops.os, "write", lambda _fd, _data: 0)
    result = ops.move_note("Inbox/capture.md", "wiki/entities/Contact.md")
    assert "accepted no bytes" in result.get("error", ""), result
    assert src.read_text(encoding="utf-8") == "keep me\n"
    assert not (root / "wiki/entities/Contact.md").exists()


@pytest.mark.parametrize(
    "destination",
    ["wiki/Contact.md/note.md", "wiki/Contact.md/sub/note.md"],
    ids=["parent-is-a-file", "ancestor-is-a-file"],
)
def test_move_note_returns_an_error_when_a_destination_parent_is_a_file(vault, destination):
    root, ops = vault
    (root / "Inbox").mkdir()
    src = root / "Inbox" / "capture.md"
    src.write_text("keep me\n", encoding="utf-8")
    (root / "wiki").mkdir()
    (root / "wiki" / "Contact.md").write_text("a note, not a folder\n", encoding="utf-8")
    result = ops.move_note("Inbox/capture.md", destination)
    assert "could not create the destination folder" in result.get("error", ""), result
    assert src.read_text(encoding="utf-8") == "keep me\n"
    assert (root / "wiki" / "Contact.md").read_text(encoding="utf-8") == "a note, not a folder\n"


@pytest.mark.parametrize(
    "path",
    ["wiki/Contact.md/note.md", "wiki/Contact.md/sub/note.md"],
    ids=["parent-is-a-file", "ancestor-is-a-file"],
)
def test_save_note_returns_an_error_when_a_target_parent_is_a_file(vault, path):
    root, ops = vault
    (root / "wiki").mkdir()
    (root / "wiki" / "Contact.md").write_text("a note, not a folder\n", encoding="utf-8")
    result = ops.save_note("x", "valid summary", path=path)
    assert "could not create the note folder" in result.get("error", ""), result
    assert (root / "wiki" / "Contact.md").read_text(encoding="utf-8") == "a note, not a folder\n"
    assert sorted(p.name for p in (root / "wiki").iterdir()) == ["Contact.md"], "nothing else was written"
