"""Freshness: "current" is part of the question (stress-test fix 15/24).

The audit's flagship failure: a "what is CURRENT now" query ranked a superseded,
since-declined note above the one that still holds. Ranking now reads two honest signals the
fusion ignored: a note's own stale status (superseded/declined/parked...) fades
it always, and recency reorders when the query asks about the present.
"""

from __future__ import annotations

import sys
from pathlib import Path

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


def _three_note_vault(tmp_path):
    """The #408 repro: two notes carry the edge inside `relations:`, one carries
    only a stale `status:`. The middle note matches the query most, so without
    the edge it wins on terms alone."""
    vault = tmp_path / "vault"
    (vault / "decisions").mkdir(parents=True)
    (vault / "decisions" / "old.md").write_text(
        "---\ntype: decision\ndate: 2026-05-01\n"
        'relations:\n  superseded_by: ["[[new]]"]\nai-first: true\n---\n'
        "fixed fee 14500 fixed fee 14500 fixed fee 14500\n",
        encoding="utf-8",
    )
    (vault / "decisions" / "new.md").write_text(
        "---\ntype: decision\ndate: 2026-11-01\n"
        'relations:\n  supersedes: ["[[old]]"]\nai-first: true\n---\n'
        "fixed fee 16000\n",
        encoding="utf-8",
    )
    (vault / "decisions" / "old2.md").write_text(
        "---\ntype: decision\ndate: 2026-05-01\nstatus: superseded\nai-first: true\n---\n"
        "fixed fee 14500\n",
        encoding="utf-8",
    )
    return vault


def test_relations_superseded_by_steps_back(tmp_path):
    """#408: a note saying `relations.superseded_by` is as stale as one whose
    `status:` says superseded, and must not outrank the note that replaced it."""
    vault = _three_note_vault(tmp_path)
    results = [{"path": "decisions/old.md", "title": "old"},
               {"path": "decisions/new.md", "title": "new"},
               {"path": "decisions/old2.md", "title": "old2"}]

    out = vault_ops._freshness_rerank(results, vault, current_intent=False)
    order = [r["path"] for r in out]
    assert order.index("decisions/new.md") < order.index("decisions/old.md"), order
    # The relation-free stale note fades exactly as it did before the change:
    # both stale shapes land behind the note that still holds.
    assert order[0] == "decisions/new.md", order


def test_relations_supersedes_reverse_edge(tmp_path):
    """The forward edge inside `relations:` fades its target, like the legacy
    top-level scalar already did: the old note's status was never updated."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "adr-1.md").write_text(
        "---\ntype: adr\nstatus: accepted\n---\n"
        "caching caching caching caching caching caching layer\n", encoding="utf-8",
    )
    (vault / "adr-2.md").write_text(
        "---\ntype: adr\nstatus: accepted\n"
        'relations:\n  supersedes: ["[[adr-1]]"]\n---\ncaching layer\n', encoding="utf-8",
    )
    results = [{"path": "adr-1.md", "title": "adr-1"},
               {"path": "adr-2.md", "title": "adr-2"}]

    out = vault_ops._freshness_rerank(results, vault, current_intent=False)
    assert [r["path"] for r in out] == ["adr-2.md", "adr-1.md"]


def test_supersession_edges_reads_every_documented_shape():
    """The shapes `references/ai-first-rules.md` Rule 6 documents, plus the
    legacy scalars, all produce the same edge."""
    def read(fm: str):
        return vault_ops._supersession_edges(f"---\n{fm}\n---\n\nbody\n")

    # Inline array inside the block (the rule's own example).
    assert read('relations:\n  superseded_by: ["[[new]]"]') == (set(), {"new"})
    # List form, with a vault-relative path; resolves by note stem.
    assert read("relations:\n  supersedes:\n    - \"[[Knowledge/ADR-006 - Use Redis]]\"") == (
        {"adr-006 - use redis"}, set(),
    )
    # Legacy top-level scalars.
    assert read('superseded_by: "[[New]]"') == (set(), {"new"})
    # Inline mapping on one line.
    assert read('relations: {supersedes: ["[[old]]"], depends_on: ["[[x]]"]}') == ({"old"}, set())
    # Both directions in one note.
    assert read('relations:\n  supersedes: ["[[a]]"]\n  superseded_by: ["[[b]]"]') == (
        {"a"}, {"b"},
    )
    # A wikilink alias/heading suffix resolves to the note, not the fragment.
    assert read('relations:\n  superseded_by: ["[[new#Summary|the new one]]"]') == (set(), {"new"})


def test_supersession_edges_ignores_body_prose():
    """Only frontmatter is a claim. A note that merely talks about being
    superseded must not fade itself."""
    text = (
        "---\ntype: note\ntags: [note]\n---\n\n"
        "## For future agent\n\nThis note mentions relations.superseded_by: [\"[[x]]\"] "
        "in prose and supersedes: [[y]] as an example.\n"
    )
    assert vault_ops._supersession_edges(text) == (set(), set())


def test_supersession_edges_tolerates_no_frontmatter():
    assert vault_ops._supersession_edges("plain body, supersedes: [[x]]\n") == (set(), set())


def test_search_ranks_relations_superseded_note_last(tmp_path, monkeypatch):
    """End to end through `search()` with the semantic arm forced off, which is
    the path the issue reported (`OBSIDIAN_SEARCH_SEMANTIC=0`)."""
    vault = _three_note_vault(tmp_path)
    monkeypatch.setenv(vault_ops._VAULT_ENV, str(vault))

    results = vault_ops.search("fixed fee decision", limit=5, semantic=False)
    order = [r["path"] for r in results]
    assert set(order) == {"decisions/old.md", "decisions/new.md", "decisions/old2.md"}, order
    assert order[0] == "decisions/new.md", order
    assert order[-1] == "decisions/old.md", order


def test_search_detects_current_intent_tokens(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "a.md").write_text("---\ntype: note\n---\ncurrent provider facts\n", encoding="utf-8")
    monkeypatch.setenv(vault_ops._VAULT_ENV, str(vault))
    seen = {}
    monkeypatch.setattr(vault_ops, "_freshness_rerank",
                        lambda res, v, ci: seen.setdefault("ci", ci) or res)
    monkeypatch.setattr(vault_ops, "_semantic_fuse", lambda *a, **k: [{"path": "a.md"}])
    vault_ops.search("what is the current provider", limit=5)
    assert seen["ci"] is True
