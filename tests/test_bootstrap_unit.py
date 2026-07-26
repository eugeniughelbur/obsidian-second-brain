"""In-process unit tests for bootstrap_vault, the file that creates a user's vault.

1,280 lines and, until now, exercised only as a black box: test_front_door and
test_showroom shell out and check file side effects. That is real coverage, but
it means nobody could test a single function, and the reason was one line -
write() read a module-level FORCE global that main() mutated, so a fresh
subprocess was the only way to reset it between scenarios.

write() is the funnel every template, board and note write passes through, and
its whole job is refusing to clobber a user's existing file. That deserved a
direct test.

The pure functions below needed no refactor at all. They were always testable;
nothing had called them from a test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import bootstrap_vault as bv  # noqa: E402

# --- S19: write() ----------------------------------------------------------

def test_write_creates_a_missing_file(tmp_path):
    target = tmp_path / "sub" / "Home.md"
    bv.write(target, "hello", force=False)
    assert target.read_text(encoding="utf-8") == "hello\n"


def test_write_refuses_to_clobber_without_force(tmp_path):
    """The guarantee that makes bootstrap safe to re-run on a real vault."""
    target = tmp_path / "Home.md"
    target.write_text("MY HAND WRITTEN NOTE\n", encoding="utf-8")

    bv.write(target, "generated boilerplate", force=False)

    assert target.read_text(encoding="utf-8") == "MY HAND WRITTEN NOTE\n", (
        "bootstrap overwrote a file the user already had. Running setup on a "
        "non-empty vault would be data loss, not setup."
    )


def test_write_overwrites_when_forced(tmp_path):
    target = tmp_path / "Home.md"
    target.write_text("old\n", encoding="utf-8")
    bv.write(target, "new", force=True)
    assert target.read_text(encoding="utf-8") == "new\n"


def test_write_falls_back_to_the_module_global(monkeypatch, tmp_path):
    """Existing call sites pass no `force`, so the default must still work."""
    target = tmp_path / "Home.md"
    target.write_text("original\n", encoding="utf-8")

    monkeypatch.setattr(bv, "FORCE", False)
    bv.write(target, "replacement")
    assert target.read_text(encoding="utf-8") == "original\n"

    monkeypatch.setattr(bv, "FORCE", True)
    bv.write(target, "replacement")
    assert target.read_text(encoding="utf-8") == "replacement\n"


# --- S21: Board ------------------------------------------------------------

def test_boards_are_readable_by_name_and_still_unpack():
    """Named access for the three sites that read b[0]; unpacking for the fourth."""
    board = bv.Board("Engineering", ["Backlog", "Done"])
    assert board.name == "Engineering"
    assert board.columns == ["Backlog", "Done"]

    name, columns = board  # the destructuring call site must keep working
    assert name == "Engineering" and columns == ["Backlog", "Done"]


def test_every_preset_board_is_a_named_board():
    for key, preset in bv.PRESETS.items():
        for b in preset.get("boards", []):
            assert isinstance(b, bv.Board), (
                f"preset {key!r} declares a bare tuple; the three sites that read "
                "b.name would break silently on a reorder"
            )


# --- pure functions that were always testable ------------------------------

@pytest.mark.parametrize("fn", ["render_kanban", "folder_map_table"])
def test_pure_renderers_return_strings(fn):
    """Both take a list and return a string; neither needed a refactor to test."""
    out = getattr(bv, fn)(["A", "B"])
    assert isinstance(out, str) and out.strip()


def test_render_home_is_pure_and_does_not_write(tmp_path):
    """Takes seven arguments off the CLI args and touches no disk (S22).

    Worth a direct test precisely because the parameter sprawl makes it look
    like it might.
    """
    before = list(tmp_path.iterdir())
    out = bv.render_home(
        name="Test User", preset_key="builder", preset=bv.PRESETS["builder"],
        jobs=["Work"], mode="wiki",
    )
    assert isinstance(out, str) and "Test User" in out
    assert list(tmp_path.iterdir()) == before, "a renderer wrote to disk"


def test_render_kanban_includes_every_column():
    out = bv.render_kanban(["Backlog", "In Progress", "Done"])
    for col in ("Backlog", "In Progress", "Done"):
        assert col in out
