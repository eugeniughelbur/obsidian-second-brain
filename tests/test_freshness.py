"""Freshness: "current" is part of the question (stress-test fix 15/24).

The audit's flagship failure: "who is my CURRENT employer" ranked a declined
April offer above the real employer. Ranking now reads two honest signals the
fusion ignored: a note's own stale status (superseded/declined/parked...) fades
it always, and recency reorders when the query asks about the present.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "integrations" / "obsidian-mcp-server"))

import vault_ops  # noqa: E402


def test_current_intent_band_is_much_stronger():
    fresh_gentle = vault_ops._freshness_weight(0, current_intent=False)
    old_gentle = vault_ops._freshness_weight(730, current_intent=False)
    fresh_strong = vault_ops._freshness_weight(0, current_intent=True)
    old_strong = vault_ops._freshness_weight(730, current_intent=True)
    # Gentle band barely moves (evergreen notes unharmed)...
    assert 0.9 <= old_gentle < fresh_gentle <= 1.0
    # ...the current-intent band actually bites.
    assert old_strong < 0.65 < fresh_strong


def test_stale_status_steps_back_in_rerank(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "old-decision.md").write_text(
        "---\ntype: decision-record\ndate: 2026-05-01\nstatus: superseded\n---\nbody\n",
        encoding="utf-8",
    )
    (vault / "current-note.md").write_text(
        "---\ntype: concept\ndate: 2026-07-01\nstatus: active\n---\nbody\n",
        encoding="utf-8",
    )
    results = [{"path": "old-decision.md", "title": "old"},
               {"path": "current-note.md", "title": "new"}]

    out = vault_ops._freshness_rerank(results, vault, current_intent=False)
    assert out[0]["path"] == "current-note.md", "superseded must lose the near-tie"


def test_recency_reorders_only_with_current_intent(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "stale.md").write_text(
        "---\ntype: project\ndate: 2025-01-01\nstatus: active\n---\nbody\n",
        encoding="utf-8",
    )
    (vault / "fresh.md").write_text(
        "---\ntype: entity\ndate: 2026-07-10\nstatus: active\n---\nbody\n",
        encoding="utf-8",
    )
    results = [{"path": "stale.md", "title": "s"}, {"path": "fresh.md", "title": "f"}]

    plain = vault_ops._freshness_rerank(list(results), vault, current_intent=False)
    assert plain[0]["path"] == "stale.md", "no current intent: rank order stands"

    current = vault_ops._freshness_rerank(list(results), vault, current_intent=True)
    assert current[0]["path"] == "fresh.md", "current intent: the old map loses"


def test_note_age_prefers_updated_over_date(tmp_path):
    md = tmp_path / "n.md"
    md.write_text("---\ndate: 2020-01-01\nupdated: 2026-07-01\n---\n", encoding="utf-8")
    age = vault_ops._note_age_days(md.read_text(encoding="utf-8"), md)
    assert age < 365, "updated: must win over the ancient date:"


def test_search_detects_current_intent_tokens(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "a.md").write_text("---\ntype: note\n---\nemployer facts\n", encoding="utf-8")
    monkeypatch.setenv(vault_ops._VAULT_ENV, str(vault))
    seen = {}
    monkeypatch.setattr(vault_ops, "_freshness_rerank",
                        lambda res, v, ci: seen.setdefault("ci", ci) or res)
    monkeypatch.setattr(vault_ops, "_semantic_fuse", lambda *a, **k: [{"path": "a.md"}])
    vault_ops.search("who is my current employer", limit=5)
    assert seen["ci"] is True
