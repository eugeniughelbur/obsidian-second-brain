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

    def fake_search(q, *, limit, semantic=None, with_scores=False):
        recorded["semantic"] = semantic
        recorded["with_scores"] = with_scores
        return []

    monkeypatch.setattr(rev.vault_ops, "search", fake_search)
    label, fn = rev._searcher("lexical")
    fn("anything")
    assert recorded["semantic"] is False
    # Raw scores ride along so "gold": null cases can be judged; ranking is unchanged.
    assert recorded["with_scores"] is True
    assert "pure lexical" in label


def test_default_mode_measures_shipped_behavior(vault, monkeypatch):
    recorded = {}

    def fake_search(q, *, limit, semantic=None, with_scores=False):
        recorded["semantic"] = semantic
        recorded["with_scores"] = with_scores
        return []

    monkeypatch.setattr(rev.vault_ops, "search", fake_search)
    label, fn = rev._searcher("default")
    fn("anything")
    assert recorded["semantic"] is None
    assert recorded["with_scores"] is True
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


def _reporting_search(reasons_by_query):
    def fake_search(query, *, limit, on_semantic_fallback=None, with_scores=False):
        reason = reasons_by_query[query]
        if reason:
            on_semantic_fallback(reason)
        return [{"path": "note.md"}]

    return fake_search


def test_default_eval_sorts_vault_ops_reasons_into_skipped(tmp_path, monkeypatch, capsys):
    # The reasons #389 reports when fusion was never attempted on purpose are
    # `skipped`, not `fallback`: the row is still what its label says.
    cases = tmp_path / "cases.jsonl"
    cases.write_text(
        '{"q":"first query","gold":["note.md"]}\n'
        '{"q":"second query","gold":["note.md"]}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(rev.vault_ops, "search", _reporting_search({
        "first query": "semantic index missing",
        "second query": "disabled by configuration",
    }))
    assert rev.evaluate(cases, as_json=True, mode="default") == 0
    summary = json.loads(capsys.readouterr().out)["summary"]
    assert summary["fusion"] == {
        "fused": 0, "skipped": 2, "fallback": 0,
        "skipped_reasons": {
            "disabled by configuration": 1,
            "semantic index missing": 1,
        },
    }


def test_default_eval_refuses_a_reported_semantic_fallback(tmp_path, monkeypatch, capsys):
    cases = tmp_path / "cases.jsonl"
    cases.write_text(
        '{"q":"first query","gold":["note.md"]}\n'
        '{"q":"second query","gold":["note.md"]}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(rev.vault_ops, "search", _reporting_search({
        "first query": "semantic index missing",
        "second query": "embedding timed out",
    }))
    assert rev.evaluate(cases, as_json=True, mode="default") == 1
    io = capsys.readouterr()
    assert io.out == ""
    assert "1 of 2 queries fell back" in io.err
    assert "1x embedding timed out" in io.err


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
    # The tally wraps _semantic_fuse for the run and must put it back.
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
    assert "1x embedding timed out" in io.err
    assert "OBSIDIAN_EMBED_QUERY_TIMEOUT" in io.err


def test_default_mode_without_an_index_is_skipped_not_failed(vault, monkeypatch,
                                                             tmp_path, capsys):
    code, io = _default_run(vault, monkeypatch, tmp_path, capsys, index=False)
    assert code == 0, io.err
    assert json.loads(io.out)["summary"]["fusion"] == {
        "fused": 0, "skipped": 2, "fallback": 0,
        "skipped_reasons": {"semantic index missing": 1, "single-term query": 1},
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

            # Read at import, so a bad value must not stop the module loading.
            for bad in ("soon", "0", "-3", "nan", "inf"):
                patch.setenv("OBSIDIAN_EMBED_QUERY_TIMEOUT", bad)
                assert importlib.reload(vault_ops)._EMBED_QUERY_TIMEOUT == 10
    finally:
        importlib.reload(vault_ops)


# --------------------------------------------------------------------------- #
# No-answer cases ("gold": null): questions the vault cannot answer. Before
# this support existed, a null gold crashed the harness with a TypeError.
# --------------------------------------------------------------------------- #
def _eval_json(tmp_path, monkeypatch, capsys, cases, fake, mode="lexical"):
    path = tmp_path / "cases.jsonl"
    path.write_text("".join(json.dumps(c) + "\n" for c in cases), encoding="utf-8")
    monkeypatch.setattr(rev.vault_ops, "search", fake)
    assert rev.evaluate(path, as_json=True, mode=mode) == 0
    return json.loads(capsys.readouterr().out)


def _lexical(score, path="other.md"):
    return [{"path": path, "score": score, "score_kind": "lexical"}]


def test_no_answer_case_fails_when_a_result_scores_above_the_line(
    tmp_path, monkeypatch, capsys
):
    def fake(q, *, limit, semantic=None, with_scores=False):
        return _lexical(20.0, "note.md") if q == "answerable" else _lexical(12.0)

    out = _eval_json(tmp_path, monkeypatch, capsys, [
        {"q": "answerable", "gold": ["note.md"]},
        {"q": "unanswerable", "gold": None},
    ], fake)

    # The no-answer case never counts toward recall or MRR.
    assert out["summary"]["cases"] == 1
    assert out["summary"]["recall_at"]["1"] == 1.0
    assert out["summary"]["no_answer"] == {
        "cases": 1, "thresholds": {"lexical": rev.NO_ANSWER_THRESHOLD},
        "passed": 0, "failed": 1, "judged": True,
    }
    assert out["no_answer_cases"][0]["top_hit"] == "other.md"
    assert out["no_answer_cases"][0]["max_score"] == 12.0


def test_no_answer_case_passes_at_the_line_or_with_no_results(
    tmp_path, monkeypatch, capsys
):
    def fake(q, *, limit, semantic=None, with_scores=False):
        return _lexical(rev.NO_ANSWER_THRESHOLD) if q == "weak" else []

    out = _eval_json(tmp_path, monkeypatch, capsys, [
        {"q": "weak", "gold": None},
        {"q": "empty", "gold": None},
    ], fake)

    assert [c["passed"] for c in out["no_answer_cases"]] == [True, True]


def test_no_answer_case_fails_when_search_crashes(tmp_path, monkeypatch, capsys):
    def fake(q, *, limit, semantic=None, with_scores=False):
        raise RuntimeError("backend down")

    out = _eval_json(tmp_path, monkeypatch, capsys, [{"q": "x", "gold": None}], fake)

    # An empty list from a crash is not search admitting "not found".
    assert out["no_answer_cases"][0]["passed"] is False


def test_default_mode_judges_no_answer_on_cosine_not_fused_score(
    tmp_path, monkeypatch, capsys
):
    # The fused RRF score is rank-derived, so 0.33 would sit under the 0.48
    # cosine line and pass. The cosine (0.60) is what must decide.
    def fake(q, *, limit, on_semantic_fallback=None, with_scores=False):
        return [
            {"path": "a.md", "score": 0.33, "score_kind": "fused", "semantic_score": 0.60},
            {"path": "b.md", "score": 0.30, "score_kind": "fused", "semantic_score": None},
        ]

    out = _eval_json(tmp_path, monkeypatch, capsys, [{"q": "x", "gold": None}], fake,
                     mode="default")

    case = out["no_answer_cases"][0]
    assert case["passed"] is False
    assert case["scale"] == "cosine"
    assert case["max_score"] == 0.6


def test_default_mode_refuses_a_row_when_a_no_answer_query_fell_back(
    tmp_path, monkeypatch, capsys
):
    # A no-answer query that fell back is judged on the lexical scale under a
    # fused label, so it must stop the row like a ranked query does.
    cases = tmp_path / "cases.jsonl"
    cases.write_text(
        '{"q":"first query","gold":["note.md"]}\n'
        '{"q":"second query","gold":null}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(rev.vault_ops, "search", _reporting_search({
        "first query": None,
        "second query": "embedding timed out",
    }))
    assert rev.evaluate(cases, as_json=True, mode="default") == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "1 of 2 queries fell back" in captured.err


def test_search_with_scores_keeps_the_lexical_score(vault):
    hits = vault_ops.search("zebra", semantic=False, with_scores=True)
    assert hits[0]["score"] > 0
    assert hits[0]["score_kind"] == "lexical"


def test_fused_search_with_scores_carries_the_cosine(vault, monkeypatch):
    (vault / vault_ops._SEMANTIC_INDEX_FILE).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        vault_ops, "_load_index_cached",
        lambda _path: {"notes": {"note.md": {"title": "note", "_unit": [[1.0, 0.0]]}}},
    )
    monkeypatch.setattr(vault_ops, "_embed_query", lambda *a, **k: [0.6, 0.8])

    hits = vault_ops.search("zebra facts", semantic=True, with_scores=True)

    assert hits[0]["score_kind"] == "fused"
    assert hits[0]["semantic_score"] == pytest.approx(0.6)


def test_guard_search_output_carries_no_scores_by_default(vault, monkeypatch):
    # Guard, passes before and after: the MCP output must stay score-free.
    lexical = vault_ops.search("zebra", semantic=False)
    assert lexical and not {"score", "score_kind"} & set(lexical[0])

    (vault / vault_ops._SEMANTIC_INDEX_FILE).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        vault_ops, "_load_index_cached",
        lambda _path: {"notes": {"note.md": {"title": "note", "_unit": [[1.0, 0.0]]}}},
    )
    monkeypatch.setattr(vault_ops, "_embed_query", lambda *a, **k: [0.6, 0.8])
    fused = vault_ops.search("zebra facts", semantic=True)
    assert fused and not {"score", "score_kind", "semantic_score"} & set(fused[0])
