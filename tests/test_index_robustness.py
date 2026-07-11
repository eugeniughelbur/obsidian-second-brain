"""Index robustness: weather gets retries, walls get split (fix 14/24).

Eleven real notes failed to embed on every build - deterministic token-window
overflows (a 1,066-char euro-table 500s while its halves embed fine), not
transient errors. The build now halves failing chunks adaptively, degrades to
an identity-only vector when even splitting fails, and reports coverage loudly
naming every degraded or dropped note.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "eval"))

import semantic_search as ss  # noqa: E402


def _fake_embed_maker(max_len: int):
    """An embedder with a hard wall: anything longer than max_len chars 500s."""
    calls = []

    def fake(text, retries=None):
        calls.append(len(text))
        if len(text) > max_len:
            raise RuntimeError("HTTP Error 500 (wall)")
        return [1.0, 0.0]

    return fake, calls


def test_adaptive_split_gets_through_the_wall(monkeypatch):
    fake, calls = _fake_embed_maker(max_len=700)
    monkeypatch.setattr(ss, "embed", fake)

    vecs = ss.embed_note_chunks("x" * 1200, header="H|")
    assert len(vecs) >= 2, "the wall chunk must be halved, not dropped"
    assert all(len(v) == 2 for v in vecs)


def test_split_floor_raises_for_unembeddable_content(monkeypatch):
    fake, _ = _fake_embed_maker(max_len=0)  # everything fails
    monkeypatch.setattr(ss, "embed", fake)
    with pytest.raises(Exception):
        ss.embed_note_chunks("y" * 1200, header="")


def test_build_degrades_to_identity_and_reports(tmp_path, monkeypatch, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "good.md").write_text("---\ntype: note\n---\n\nfine prose\n", encoding="utf-8")
    (vault / "cursed.md").write_text(
        "---\ntype: task\n---\n\nPOISON " * 60, encoding="utf-8"
    )

    def fake(text, retries=None):
        if "POISON" in text:
            raise RuntimeError("HTTP Error 500 (wall all the way down)")
        return [1.0, 0.0]

    monkeypatch.setattr(ss, "embed", fake)
    index = ss.build_index(vault, verbose=True)

    entry = index["notes"]["cursed.md"]
    assert entry.get("degraded") is True
    assert entry["vecs"], "identity-only vector must exist - findable by name"
    err = capsys.readouterr().err
    assert "coverage:" in err
    assert "degraded to identity-only] cursed.md" in err


def test_build_names_fully_dropped_notes(tmp_path, monkeypatch, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "doomed.md").write_text("---\ntype: note\n---\n\nbody\n", encoding="utf-8")

    def fake(text, retries=None):
        raise RuntimeError("HTTP Error 500 (always)")

    monkeypatch.setattr(ss, "embed", fake)
    index = ss.build_index(vault, verbose=True)

    assert "doomed.md" not in index["notes"]
    err = capsys.readouterr().err
    assert "DROPPED - not findable semantically] doomed.md" in err
