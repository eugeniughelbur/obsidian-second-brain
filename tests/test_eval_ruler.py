"""The eval harness must measure what its labels claim (stress-test fix 10/24).

Before: --mode lexical silently scored the fused blend whenever a semantic index
existed, --mode hybrid fed an already-fused ranking into fusion (semantic counted
twice, inflating hybrid enough to flip the June ship decision), and --generate
silently overwrote the baseline cases file mid-experiment. These tests pin the
straightened ruler without needing Ollama.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "integrations" / "obsidian-mcp-server"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "eval"))

import retrieval_eval as rev  # noqa: E402
import vault_ops  # noqa: E402


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

    # **_ absorbs arguments search passes that this double does not assert on
    # (currently `scanned`, the already-walked path list the staleness check
    # reuses). Pinning the full signature here made a test double a second
    # definition of the production signature.
    def spy(query, lexical, v, limit, enabled=None, **_):
        seen["enabled"] = enabled
        return real(query, lexical, v, limit, enabled=enabled)

    monkeypatch.setattr(vault_ops, "_semantic_fuse", spy)
    vault_ops.search("zebra facts live", limit=5, semantic=False)
    assert seen["enabled"] is False
    # multi-word: the shipped default follows the env (single tokens dispatch
    # to lexical since fix 11/24 and are covered in test_query_aware_default)
    vault_ops.search("zebra facts live", limit=5)
    assert seen["enabled"] is None


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


def test_missing_semantic_index_reports_each_query_without_warning(vault, monkeypatch, capsys):
    monkeypatch.setattr(vault_ops, "_SEMANTIC_FALLBACK_WARNED", False)
    reasons = []

    for _ in range(2):
        assert vault_ops._semantic_fuse(
            "meaning query", [], vault, 5, enabled=True, on_fallback=reasons.append
        ) is None

    assert reasons == ["semantic index missing", "semantic index missing"]
    assert capsys.readouterr().err == ""


def test_disabled_semantic_search_reports_without_warning(vault, monkeypatch, capsys):
    monkeypatch.setattr(vault_ops, "_SEMANTIC_ENABLED", False)
    monkeypatch.setattr(vault_ops, "_SEMANTIC_FALLBACK_WARNED", False)
    reasons = []

    assert vault_ops._semantic_fuse(
        "meaning query", [], vault, 5, on_fallback=reasons.append
    ) is None

    assert reasons == ["disabled by configuration"]
    assert capsys.readouterr().err == ""


def test_live_search_reports_embedding_timeout_and_keeps_lexical_results(
    vault, monkeypatch, capsys
):
    (vault / vault_ops._SEMANTIC_INDEX_FILE).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        vault_ops,
        "_load_index_cached",
        lambda _path: {"notes": {"note.md": {"title": "note", "_unit": [[1.0, 0.0]]}}},
    )
    def timeout(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(vault_ops, "_embed_query", timeout)
    monkeypatch.setattr(vault_ops, "_SEMANTIC_FALLBACK_WARNED", False)
    reasons = []

    hits = vault_ops.search("zebra facts", on_semantic_fallback=reasons.append)

    assert hits and hits[0]["path"] == "note.md"
    assert reasons == ["embedding timed out"]
    assert "warning: semantic search fell back to lexical results (embedding timed out)" \
        in capsys.readouterr().err


def test_semantic_index_without_note_vectors_is_counted(vault, monkeypatch, capsys):
    (vault / vault_ops._SEMANTIC_INDEX_FILE).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        vault_ops, "_load_index_cached", lambda _path: {"notes": {"note.md": {}}}
    )
    monkeypatch.setattr(vault_ops, "_embed_query", lambda *a, **k: [1.0, 0.0])
    monkeypatch.setattr(vault_ops, "_SEMANTIC_FALLBACK_WARNED", False)
    reasons = []

    assert vault_ops._semantic_fuse(
        "meaning query", [], vault, 5, enabled=True, on_fallback=reasons.append
    ) is None

    assert reasons == ["semantic index has no usable vectors"]
    assert capsys.readouterr().err == ""


def test_default_eval_counts_semantic_fallbacks(tmp_path, monkeypatch, capsys):
    cases = tmp_path / "cases.jsonl"
    cases.write_text(
        '{"q":"first query","gold":["note.md"]}\n'
        '{"q":"second query","gold":["note.md"]}\n'
        '{"q":"third query","gold":["note.md"]}\n',
        encoding="utf-8",
    )

    def fake_search(query, *, limit, on_semantic_fallback=None):
        reason = {
            "first query": "semantic index missing",
            "second query": "disabled by configuration",
            "third query": "embedding timed out",
        }[query]
        on_semantic_fallback(reason)
        return [{"path": "note.md"}]

    monkeypatch.setattr(rev.vault_ops, "search", fake_search)
    assert rev.evaluate(cases, as_json=True, mode="default") == 0
    summary = __import__("json").loads(capsys.readouterr().out)["summary"]
    assert summary["semantic_fallbacks"] == {
        "queries": 3,
        "reasons": {
            "disabled by configuration": 1,
            "embedding timed out": 1,
            "semantic index missing": 1,
        },
    }


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
    if os.name == "nt":
        # Path.home() reads USERPROFILE on Windows (HOME is ignored) and raises
        # "Could not determine home directory" without it.
        env["USERPROFILE"] = str(tmp_path)
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
