"""The eval harness must measure what its labels claim (stress-test fix 10/24).

Before: --mode lexical silently scored the fused blend whenever a semantic index
existed, --mode hybrid fed an already-fused ranking into fusion (semantic counted
twice, inflating hybrid enough to flip the June ship decision), and --generate
silently overwrote the baseline cases file mid-experiment. These tests pin the
straightened ruler without needing Ollama.
"""

from __future__ import annotations

import importlib
import json
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


# --- default mode must say whether it really fused (#386) ---------------------

def _default_run(vault, monkeypatch, tmp_path, capsys, *, index=True, embed=None):
    """One --mode default --json run over a two-word and a one-word question."""
    if index:
        (vault / vault_ops._SEMANTIC_INDEX_FILE).write_text(json.dumps({
            "model": "fake", "format": 2,
            "notes": {"note.md": {"title": "note", "vecs": [[1.0, 0.0]]}},
        }), encoding="utf-8")
    monkeypatch.setattr(vault_ops, "_SEMANTIC_ENABLED", True)
    embed = embed or (lambda q, **kw: [1.0, 0.0])
    monkeypatch.setattr(vault_ops, "_embed_query", embed)
    cases = tmp_path / "cases.jsonl"
    cases.write_text(
        '{"q": "zebra facts", "gold": ["note.md"]}\n{"q": "zebra", "gold": ["note.md"]}\n',
        encoding="utf-8")
    fuse_before = vault_ops._semantic_fuse
    code = rev.evaluate(cases, as_json=True, mode="default")
    # The tally wraps two vault_ops functions for the run and must put them back.
    assert vault_ops._semantic_fuse is fuse_before
    assert vault_ops._embed_query is embed
    return code, capsys.readouterr()


def test_default_mode_counts_fused_and_skipped(vault, monkeypatch, tmp_path, capsys):
    code, io = _default_run(vault, monkeypatch, tmp_path, capsys)
    assert code == 0, io.err
    report = json.loads(io.out)
    assert report["summary"]["fusion"] == {
        "fused": 1, "skipped": 1, "fallback": 0,
        "skipped_reasons": {"single-term query": 1},
    }
    assert [c["fusion"] for c in report["cases"]] == ["fused", "skipped"]


def test_default_mode_refuses_a_row_that_fell_back(vault, monkeypatch, tmp_path, capsys):
    def slow_embedder(q, **kw):
        raise TimeoutError("timed out")

    code, io = _default_run(vault, monkeypatch, tmp_path, capsys, embed=slow_embedder)
    assert code == 1
    assert io.out == ""  # no scores under the "lexical + semantic RRF" label
    assert "1 of 2 queries fell back" in io.err
    assert "1 skipped by design" in io.err  # the one-word case is not a failure
    assert "TimeoutError: timed out" in io.err
    assert "OBSIDIAN_EMBED_QUERY_TIMEOUT" in io.err


def test_default_mode_without_an_index_is_skipped_not_failed(vault, monkeypatch,
                                                             tmp_path, capsys):
    code, io = _default_run(vault, monkeypatch, tmp_path, capsys, index=False)
    assert code == 0, io.err
    assert json.loads(io.out)["summary"]["fusion"] == {
        "fused": 0, "skipped": 2, "fallback": 0,
        "skipped_reasons": {"no semantic index": 1, "single-term query": 1},
    }


def test_other_modes_carry_no_fusion_counts(vault, tmp_path, capsys):
    cases = tmp_path / "cases.jsonl"
    cases.write_text('{"q": "zebra facts", "gold": ["note.md"]}\n', encoding="utf-8")
    assert rev.evaluate(cases, as_json=True, mode="lexical") == 0
    report = json.loads(capsys.readouterr().out)
    assert "fusion" not in report["summary"]
    assert "fusion" not in report["cases"][0]


def test_query_embedding_timeout_follows_the_env(monkeypatch):
    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"embedding": [1.0]}'

    def fake_urlopen(req, timeout=None):
        seen["timeout"] = timeout
        return FakeResponse()

    try:
        # The context puts the environment back before the last reload, so the
        # module ends up built from the same environment it started with.
        with monkeypatch.context() as patch:
            patch.delenv("OBSIDIAN_EMBED_QUERY_TIMEOUT", raising=False)
            mod = importlib.reload(vault_ops)
            patch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
            assert mod._embed_query("zebra facts") == [1.0]
            assert seen["timeout"] == 10

            patch.setenv("OBSIDIAN_EMBED_QUERY_TIMEOUT", "45")
            mod = importlib.reload(vault_ops)
            assert mod._embed_query("zebra facts") == [1.0]
            assert seen["timeout"] == 45
    finally:
        importlib.reload(vault_ops)
