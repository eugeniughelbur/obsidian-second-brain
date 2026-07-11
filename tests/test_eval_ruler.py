"""The eval harness must measure what its labels claim (stress-test fix 10/24).

Before: --mode lexical silently scored the fused blend whenever a semantic index
existed, --mode hybrid fed an already-fused ranking into fusion (semantic counted
twice, inflating hybrid enough to flip the June ship decision), and --generate
silently overwrote the baseline cases file mid-experiment. These tests pin the
straightened ruler without needing Ollama.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "integrations" / "obsidian-mcp-server"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "eval"))

import vault_ops  # noqa: E402
import retrieval_eval as rev  # noqa: E402


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    v = tmp_path / "vault"
    v.mkdir()
    (v / "note.md").write_text("---\ntype: note\n---\n\nzebra facts live here\n",
                               encoding="utf-8")
    monkeypatch.setenv(vault_ops._VAULT_ENV, str(v))
    return v


def test_semantic_false_never_touches_fusion(vault, monkeypatch):
    calls = []
    monkeypatch.setattr(vault_ops, "_semantic_fuse",
                        lambda *a, **k: calls.append(k.get("enabled")) or None)
    results = vault_ops.search("zebra", limit=5, semantic=False)
    assert results and results[0]["path"] == "note.md"
    assert calls == [False] or calls == []  # fusion disabled for this call


def test_semantic_toggle_reaches_fuse(vault, monkeypatch):
    seen = {}
    real = vault_ops._semantic_fuse

    def spy(query, lexical, v, limit, enabled=None):
        seen["enabled"] = enabled
        return real(query, lexical, v, limit, enabled=enabled)

    monkeypatch.setattr(vault_ops, "_semantic_fuse", spy)
    vault_ops.search("zebra", limit=5, semantic=False)
    assert seen["enabled"] is False
    vault_ops.search("zebra", limit=5)
    assert seen["enabled"] is None  # shipped default follows the env


def test_lexical_mode_is_pure(vault, monkeypatch):
    recorded = {}

    def fake_search(q, *, limit, semantic=None):
        recorded["semantic"] = semantic
        return []

    monkeypatch.setattr(rev.vault_ops, "search", fake_search)
    label, fn = rev._searcher("lexical")
    fn("anything")
    assert recorded["semantic"] is False
    assert "pure lexical" in label


def test_default_mode_measures_shipped_behavior(vault, monkeypatch):
    recorded = {}

    def fake_search(q, *, limit, semantic=None):
        recorded["semantic"] = semantic
        return []

    monkeypatch.setattr(rev.vault_ops, "search", fake_search)
    label, fn = rev._searcher("default")
    fn("anything")
    assert recorded["semantic"] is None
    assert "shipped default" in label


def test_hybrid_feeds_a_pure_lexical_arm(vault, monkeypatch):
    recorded = {}

    class FakeSS:
        EMBED_MODEL = "fake-model"

        @staticmethod
        def ollama_available():
            return True

        @staticmethod
        def load_index(v):
            return {"model": "fake-model"}

        @staticmethod
        def hybrid_search(q, index, lexical, limit):
            recorded["lexical_arm"] = lexical
            return []

    def fake_search(q, *, limit, semantic=None):
        recorded["semantic"] = semantic
        return [{"path": "note.md", "title": "note"}]

    monkeypatch.setitem(sys.modules, "semantic_search", FakeSS)
    monkeypatch.setattr(rev.vault_ops, "search", fake_search)
    label, fn = rev._searcher("hybrid")
    fn("anything")
    # The arm handed to fusion must be the PURE lexical ranking.
    assert recorded["semantic"] is False
    assert recorded["lexical_arm"] == [{"path": "note.md", "title": "note"}]
    assert "single RRF" in label


def test_generate_refuses_to_overwrite_baseline(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "topic.md").write_text(
        "---\ntype: concept\n---\n\n" + ("This body describes retention emails "
        "for tour operators in the south of Spain in enough detail. " * 10),
        encoding="utf-8",
    )
    cases = tmp_path / "cases.jsonl"
    cases.write_text('{"q": "old question", "gold": ["topic.md"]}\n', encoding="utf-8")

    env = {"OBSIDIAN_VAULT_PATH": str(vault), "PATH": "/usr/bin:/bin"}
    cmd = [sys.executable, "scripts/eval/retrieval_eval.py",
           "--generate", "1", "--cases", str(cases)]
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", env=env)
    assert result.returncode == 1
    assert "Refusing to overwrite" in result.stderr
    assert "old question" in cases.read_text(encoding="utf-8")

    forced = subprocess.run(cmd + ["--force"], cwd=REPO_ROOT, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", env=env)
    assert forced.returncode == 0, forced.stderr
    assert "old question" not in cases.read_text(encoding="utf-8")


def test_multi_gold_scoring_matches_any(vault):
    results = [{"path": "a.md"}, {"path": "b.md"}, {"path": "c.md"}]
    assert rev._rank_of_gold(results, ["zzz.md", "b.md"]) == 2
    assert rev._rank_of_gold(results, ["zzz.md"]) == 0
