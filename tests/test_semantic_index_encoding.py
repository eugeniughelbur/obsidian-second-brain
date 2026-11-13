"""The semantic index is UTF-8 on disk, so it must be read as UTF-8 (#404).

`build_index()` writes the index with `ensure_ascii=False` and
`encoding="utf-8"` (#259), but both reads of it named no encoding, so on
Windows they decoded it with the ANSI code page. On a Chinese install (GBK)
that fails two different ways:

* `load_index()` raises UnicodeDecodeError, so `--query` and
  `/obsidian-retrieval-eval --mode semantic` produce nothing.
* `build_index()` swallows the same error in its cache read, so every build
  quietly re-embeds the whole vault ("N new, 0 cached") instead of reusing
  the vectors of unchanged notes.

`/obsidian-find` was not affected: the MCP server's own loader already reads
the index as UTF-8.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "eval"))

import semantic_search as ss  # noqa: E402


@pytest.fixture
def gbk_default(monkeypatch):
    """Emulate a Chinese Windows on every platform: text-mode file I/O that
    names no encoding gets GBK instead of UTF-8. read_text()/write_text()
    resolve a missing encoding to "locale" and then call Path.open(), so
    patching that one method covers them (same approach as the cp1252 fixture
    in test_research_cjk_and_models.py)."""
    real_open = Path.open

    def gbk_open(self, mode="r", buffering=-1, encoding=None, errors=None, newline=None):
        if "b" not in mode and encoding in (None, "locale"):
            encoding = "gbk"
        return real_open(self, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, "open", gbk_open)


# The index stores note paths and titles, so the title decides how a GBK read
# fails: the UTF-8 bytes of 笔记 hit an illegal GBK sequence (0xae, the byte in
# the report) and raise; those of 晨间习惯 happen to decode, as mojibake, so the
# note is silently missing from the index that was loaded.
CJK_TITLES = pytest.mark.parametrize("title", ["笔记", "晨间习惯"], ids=["raises", "mojibake"])


def _cjk_vault(tmp_path: Path, title: str) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / f"{title}.md").write_text(
        "---\ntype: note\n---\n\n记录每天早上的习惯。\n", encoding="utf-8"
    )
    (vault / "plain.md").write_text("---\ntype: note\n---\n\nplain prose\n", encoding="utf-8")
    return vault


def _fake_embed(monkeypatch) -> list[str]:
    calls: list[str] = []

    def fake(text, retries=None):
        calls.append(text)
        return [1.0, 0.0]

    monkeypatch.setattr(ss, "embed", fake)
    return calls


@CJK_TITLES
def test_load_index_reads_a_cjk_index_under_a_gbk_default(
    tmp_path, monkeypatch, gbk_default, title
):
    vault = _cjk_vault(tmp_path, title)
    _fake_embed(monkeypatch)
    ss.build_index(vault, verbose=False)

    index = ss.load_index(vault)

    assert f"{title}.md" in index["notes"]
    assert index["notes"][f"{title}.md"]["title"] == title


@CJK_TITLES
def test_rebuild_reuses_the_cache_under_a_gbk_default(
    tmp_path, monkeypatch, capsys, gbk_default, title
):
    vault = _cjk_vault(tmp_path, title)
    calls = _fake_embed(monkeypatch)
    ss.build_index(vault, verbose=False)
    first_build_calls = len(calls)
    assert first_build_calls > 0

    ss.build_index(vault, verbose=True)

    assert len(calls) == first_build_calls, "unchanged notes must not be re-embedded"
    assert "(0 new, 2 cached," in capsys.readouterr().err
