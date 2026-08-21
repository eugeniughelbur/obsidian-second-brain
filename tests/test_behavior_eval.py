"""Behavior eval must actually score answers, not just retrieval - and a null
or negative result must survive to the report, not get silently dropped.

Mirrors the mocking pattern in test_eval_ruler.py: monkeypatch grok.call so
these tests run without XAI_API_KEY or network access.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "integrations" / "obsidian-mcp-server"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "eval"))

import behavior_eval as bev  # noqa: E402
import corpus  # noqa: E402
import vault_ops  # noqa: E402

# --------------------------------------------------------------------------- #
# corpus.behavior_cases()
# --------------------------------------------------------------------------- #
REQUIRED_FIELDS = {"q", "gold", "title", "category", "answer_key"}
VALID_CATEGORIES = {"fact", "decision", "relationship", "synthesis", "contradiction"}


def test_behavior_cases_are_deterministic():
    a, b = corpus.behavior_cases(), corpus.behavior_cases()
    assert a == b


def test_every_behavior_case_has_required_fields():
    for c in corpus.behavior_cases():
        missing = REQUIRED_FIELDS - set(c)
        assert not missing, f"case {c.get('title')!r} missing {missing}"
        assert c["q"] and c["answer_key"] and c["gold"]


def test_every_category_is_one_of_the_five_defined_types():
    cats = {c["category"] for c in corpus.behavior_cases()}
    assert cats <= VALID_CATEGORIES
    # all five must actually appear, or the eval isn't exercising what it claims
    assert cats == VALID_CATEGORIES


def test_gold_notes_referenced_by_behavior_cases_exist_in_the_corpus():
    files = corpus.build(300, 20260726)
    for c in corpus.behavior_cases():
        for g in c["gold"]:
            assert g in files, f"{c['title']}: missing gold note {g}"


def test_manifest_changes_when_behavior_cases_are_included():
    files = corpus.build(80, 20260726)
    sets = corpus.cases()
    without = corpus.manifest(files, sets)
    sets_with = dict(sets)
    sets_with["behavior"] = corpus.behavior_cases()
    with_behavior = corpus.manifest(files, sets_with)
    assert without != with_behavior


def test_contradiction_cases_have_a_reconciling_answer_key():
    """The daily-log injection must actually create the conflict the case grades on."""
    contradiction_cases = [c for c in corpus.behavior_cases() if c["category"] == "contradiction"]
    assert len(contradiction_cases) == len(corpus.CONTRADICTIONS)
    for term, c in corpus.CONTRADICTIONS.items():
        assert c["early"] != c["late"], f"{term}: contradiction pair is not actually conflicting"
        assert c["answer_key"], f"{term}: no reconciling answer_key"


# --------------------------------------------------------------------------- #
# _ab_order: reproducible, not re-randomized per run
# --------------------------------------------------------------------------- #
def test_ab_order_is_reproducible_across_calls():
    for i in range(10):
        assert bev._ab_order(i) == bev._ab_order(i)


def test_ab_order_is_not_constant():
    orders = {bev._ab_order(i) for i in range(20)}
    assert orders == {True, False}, "labeling never varies - position bias would go unnoticed"


# --------------------------------------------------------------------------- #
# judge response parsing
# --------------------------------------------------------------------------- #
def test_judge_parses_well_formed_json(monkeypatch):
    class FakeGrok:
        @staticmethod
        def call(prompt, *, command, max_output_tokens=200):
            return {"text": '{"score_a": 4, "score_b": 2, "reasoning": "A is correct"}'}

    monkeypatch.setitem(sys.modules, "research.lib.grok", FakeGrok)
    result = bev._judge("q", "key", "answer a", "answer b")
    assert result == {"score_a": 4, "score_b": 2, "reasoning": "A is correct"}


def test_judge_handles_json_wrapped_in_prose(monkeypatch):
    class FakeGrok:
        @staticmethod
        def call(prompt, *, command, max_output_tokens=200):
            return {"text": 'Sure, here it is:\n{"score_a": 3, "score_b": 3, "reasoning": "tie"}\nDone.'}

    monkeypatch.setitem(sys.modules, "research.lib.grok", FakeGrok)
    result = bev._judge("q", "key", "answer a", "answer b")
    assert result == {"score_a": 3, "score_b": 3, "reasoning": "tie"}


def test_judge_returns_none_on_malformed_json(monkeypatch, capsys):
    class FakeGrok:
        @staticmethod
        def call(prompt, *, command, max_output_tokens=200):
            return {"text": "I cannot comply with strict JSON right now."}

    monkeypatch.setitem(sys.modules, "research.lib.grok", FakeGrok)
    result = bev._judge("q", "key", "answer a", "answer b")
    assert result is None


def test_judge_returns_none_when_score_fields_missing(monkeypatch):
    class FakeGrok:
        @staticmethod
        def call(prompt, *, command, max_output_tokens=200):
            return {"text": '{"verdict": "A wins"}'}

    monkeypatch.setitem(sys.modules, "research.lib.grok", FakeGrok)
    result = bev._judge("q", "key", "answer a", "answer b")
    assert result is None


def test_judge_call_failure_does_not_raise(monkeypatch):
    class FakeGrok:
        @staticmethod
        def call(prompt, *, command, max_output_tokens=200):
            raise RuntimeError("network down")

    monkeypatch.setitem(sys.modules, "research.lib.grok", FakeGrok)
    result = bev._judge("q", "key", "answer a", "answer b")
    assert result is None


# --------------------------------------------------------------------------- #
# End-to-end evaluate() with everything mocked
# --------------------------------------------------------------------------- #
@pytest.fixture()
def vault(tmp_path, monkeypatch):
    v = tmp_path / "vault"
    v.mkdir(parents=True)
    (v / "topic.md").write_text(
        "---\ntype: concept\n---\n\nCanonical fact about the topic.\n", encoding="utf-8"
    )
    monkeypatch.setenv(vault_ops._VAULT_ENV, str(v))
    return v


@pytest.fixture()
def cases_file(tmp_path):
    rows = [
        {"q": "What is the topic?", "gold": ["topic.md"], "title": "Topic",
         "category": "fact", "answer_key": "Canonical fact about the topic."},
        {"q": "What is the other topic?", "gold": ["topic.md"], "title": "Topic 2",
         "category": "decision", "answer_key": "Canonical fact about the topic."},
    ]
    p = tmp_path / "cases.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def test_evaluate_reports_a_positive_delta(vault, cases_file, monkeypatch, capsys):
    monkeypatch.setattr(bev, "_answer_with_vault", lambda q: "correct, matches the fact")
    monkeypatch.setattr(bev, "_answer_without_vault", lambda q: "I don't know")

    def fake_judge(q, key, a, b):
        # whichever of a/b is the "correct" text scores 5, the other 1
        return {"score_a": 5 if a == "correct, matches the fact" else 1,
                "score_b": 5 if b == "correct, matches the fact" else 1,
                "reasoning": "matches known facts"}

    monkeypatch.setattr(bev, "_judge", fake_judge)
    rc = bev.evaluate(cases_file, as_json=True)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["summary"]["judged"] == 2
    assert out["summary"]["overall_delta"] == 4.0
    assert out["summary"]["regressions"] == 0


def test_evaluate_reports_regressions_without_truncation(vault, cases_file, monkeypatch, capsys):
    monkeypatch.setattr(bev, "_answer_with_vault", lambda q: "vault-on")
    monkeypatch.setattr(bev, "_answer_without_vault", lambda q: "vault-off")

    def fake_judge(q, key, a, b):
        # vault-on always scores lower than vault-off - a regression on every case
        return {"score_a": 1 if a == "vault-on" else 5,
                "score_b": 1 if b == "vault-on" else 5,
                "reasoning": "vault answer worse"}

    monkeypatch.setattr(bev, "_judge", fake_judge)
    rc = bev.evaluate(cases_file, as_json=True)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["summary"]["regressions"] == 2
    assert len(out["regressions"]) == 2, "regressions bucket must never be truncated"
    assert out["summary"]["overall_delta"] < 0


def test_evaluate_does_not_crash_on_zero_delta(vault, cases_file, monkeypatch, capsys):
    monkeypatch.setattr(bev, "_answer_with_vault", lambda q: "same")
    monkeypatch.setattr(bev, "_answer_without_vault", lambda q: "same")
    monkeypatch.setattr(bev, "_judge", lambda q, key, a, b: {"score_a": 3, "score_b": 3, "reasoning": "tie"})
    rc = bev.evaluate(cases_file, as_json=True)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["summary"]["overall_delta"] == 0.0


def test_evaluate_excludes_unjudged_cases_from_delta_but_reports_them(vault, cases_file, monkeypatch, capsys):
    monkeypatch.setattr(bev, "_answer_with_vault", lambda q: "vault-on")
    monkeypatch.setattr(bev, "_answer_without_vault", lambda q: "vault-off")
    monkeypatch.setattr(bev, "_judge", lambda q, key, a, b: None)  # every judge call fails
    rc = bev.evaluate(cases_file, as_json=True)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["summary"]["judged"] == 0
    assert out["summary"]["unjudged"] == 2
    assert out["summary"]["overall_delta"] is None


def test_evaluate_refuses_missing_cases_file(tmp_path):
    rc = bev.evaluate(tmp_path / "nope.jsonl", as_json=False)
    assert rc == 1


def test_generate_refuses_to_overwrite_without_force(tmp_path):
    p = tmp_path / "cases.jsonl"
    p.write_text('{"q": "old"}\n', encoding="utf-8")
    import subprocess

    result = subprocess.run(
        [sys.executable, "scripts/eval/behavior_eval.py", "--generate", "--cases", str(p)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "Refusing to overwrite" in result.stderr
    assert p.read_text(encoding="utf-8") == '{"q": "old"}\n'
