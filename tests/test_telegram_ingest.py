"""Runtime tests for the Telegram journal ingest's vault-write core.

The audit's completeness critic flagged this surface as never runtime-tested.
Driving it live against scratch vaults found a real bug: the bot hardcoded
wiki-style folders (the class #117 swept from commands, but the Python
integration was never covered), so an Obsidian-style vault would get a
parallel wiki/ tree forked into it.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "integrations" / "telegram-journal"))

import telegram_journal as tj  # noqa: E402

WHEN = datetime.datetime(2026, 7, 11, 14, 30)


def test_wiki_style_vault_routes_to_wiki_daily(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "wiki").mkdir(parents=True)
    monkeypatch.setattr(tj, "VAULT", vault)
    assert tj.daily_note(WHEN) == vault / "wiki/daily" / "2026-07-11.md"


def test_obsidian_style_vault_routes_to_Daily(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "Daily").mkdir(parents=True)
    (vault / "People").mkdir()
    monkeypatch.setattr(tj, "VAULT", vault)
    assert tj.daily_note(WHEN) == vault / "Daily" / "2026-07-11.md"
    assert tj._folder("entities") == "People"


def test_append_under_never_duplicates_headers(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "Daily").mkdir(parents=True)
    monkeypatch.setattr(tj, "VAULT", vault)
    note = tj.daily_note(WHEN)
    tj.ensure_daily(note, WHEN)
    tj.append_under(note, "## Journal", "- 14:30 first entry", WHEN)
    tj.append_under(note, "## Journal", "- 14:31 second entry", WHEN)
    body = note.read_text(encoding="utf-8")
    assert "first entry" in body and "second entry" in body
    assert body.count("## Journal") == 1


def test_remove_block_supports_the_move_flow(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "Daily").mkdir(parents=True)
    monkeypatch.setattr(tj, "VAULT", vault)
    note = tj.daily_note(WHEN)
    tj.ensure_daily(note, WHEN)
    tj.append_under(note, "## Journal", "- 14:30 movable entry", WHEN)
    tj.remove_block(note, "- 14:30 movable entry")
    assert "movable entry" not in note.read_text(encoding="utf-8")
