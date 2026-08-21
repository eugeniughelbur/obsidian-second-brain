"""Behavior eval must actually score answers, not just retrieval - and a null
or negative result must survive to the report, not get silently dropped.

Mirrors the mocking pattern in test_eval_ruler.py: monkeypatch the LLM call
sites so these tests run with zero network access and no API key present in
the environment.
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
# The issue's target mix is fact 15% / decision 15% / relationship 15% /
# synthesis 30% / contradiction 25%. Twelve fixed topics make an exact match
# impossible without either dropping the unconditional fact row (explicitly
# disallowed) or inflating the corpus far beyond what 12 topics can support
# in good faith - so this checks direction and rough proportion, not an exact
# hit: fact must no longer dominate, and synthesis+contradiction together
# must be the majority of the set (they were 24% before this fix).
TARGET_MIX = {"fact": 0.15, "decision": 0.15, "relationship": 0.15,
              "synthesis": 0.30, "contradiction": 0.25}
MIX_TOLERANCE = 0.10


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


def test_fact_no_longer_dominates_the_mix():
    """The exact bug the issue reported: fact was ~48% of 25 cases."""
    mix = corpus.category_mix()
    assert mix["fact"] < 0.30, f"fact is still the dominant category: {mix}"


def test_synthesis_and_contradiction_are_the_majority_of_the_mix():
    mix = corpus.category_mix()
    assert mix["synthesis"] + mix["contradiction"] > 0.5, (
        f"synthesis+contradiction should now outweigh the single-note categories: {mix}"
    )


def test_category_mix_is_within_tolerance_of_the_target():
    mix = corpus.category_mix()
    offenders = {
        cat: (mix[cat], TARGET_MIX[cat])
        for cat in TARGET_MIX
        if abs(mix[cat] - TARGET_MIX[cat]) > MIX_TOLERANCE
    }
    assert not offenders, f"category mix drifted too far from target: {offenders}"


def test_category_mix_reports_all_categories_and_sums_to_one():
    mix = corpus.category_mix()
    assert set(mix) == VALID_CATEGORIES
    assert abs(sum(mix.values()) - 1.0) < 0.01


def test_category_mix_on_empty_input_does_not_raise():
    assert corpus.category_mix([]) == {}


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


def test_manifest_is_stable_when_nothing_changes():
    files = corpus.build(80, 20260726)
    sets = corpus.cases()
    sets["behavior"] = corpus.behavior_cases()
    assert corpus.manifest(files, sets) == corpus.manifest(dict(files), dict(sets))


def test_contradiction_cases_have_a_reconciling_answer_key():
    """The daily-log injection must actually create the conflict the case grades on."""
    contradiction_cases = [c for c in corpus.behavior_cases() if c["category"] == "contradiction"]
    assert len(contradiction_cases) >= len(corpus.CONTRADICTIONS)
    for term, c in corpus.CONTRADICTIONS.items():
        assert c["early"] != c["late"], f"{term}: contradiction pair is not actually conflicting"
        assert c["answer_key"], f"{term}: no reconciling answer_key"


# --------------------------------------------------------------------------- #
# Startup guard: answer model and judge model must differ
# --------------------------------------------------------------------------- #
def test_guard_raises_when_provider_and_model_are_identical():
    with pytest.raises(SystemExit):
        bev._require_distinct_provider_and_model("gpt", "gpt-4o-mini", "gpt", "gpt-4o-mini")


def test_guard_passes_when_models_differ():
    bev._require_distinct_provider_and_model("grok", "grok-4.5", "gpt", "gpt-4o-mini")


def test_guard_passes_when_providers_differ_even_with_the_same_model_string():
    """Providers are hardcoded distinct today (grok answers, gpt judges), so this
    documents that the guard compares the full provider+model pair, not the
    model string alone."""
    bev._require_distinct_provider_and_model("grok", "same-name", "gpt", "same-name")


def test_evaluate_enforces_the_guard_before_running_any_case(vault_env_only, monkeypatch):
    """A misconfigured evaluate() call must fail before touching a single case,
    not after burning through the whole run."""
    calls = []
    monkeypatch.setattr(bev, "_answer_with_vault", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(bev, "_answer_without_vault", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(bev, "_default_answer_model", lambda: "same-model")
    monkeypatch.setattr(bev, "_default_judge_model", lambda: "same-model")
    # Simulate the fully-misconfigured case (both provider AND model coincide) -
    # today's hardcoded ANSWER_PROVIDER/JUDGE_PROVIDER constants make a real
    # collision impossible through the CLI, but the guard must still catch it
    # if that ever changes, and evaluate() must consult it before any case runs.
    monkeypatch.setattr(bev, "JUDGE_PROVIDER", bev.ANSWER_PROVIDER)

    cases_path = vault_env_only / "cases.jsonl"
    cases_path.write_text(
        json.dumps({"q": "q", "gold": ["topic.md"], "title": "t",
                    "category": "fact", "answer_key": "k"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        bev.evaluate(cases_path, as_json=True)
    assert not calls, "no case should be attempted once the guard fails"


# --------------------------------------------------------------------------- #
# judge response parsing (research.lib.gpt only - never grok)
# --------------------------------------------------------------------------- #
def test_judge_parses_well_formed_json(monkeypatch):
    class FakeGpt:
        @staticmethod
        def call(prompt, *, command, model=None, max_output_tokens=200):
            return {"text": '{"score_a": 4, "score_b": 2, "reasoning": "A is correct"}'}

    monkeypatch.setitem(sys.modules, "research.lib.gpt", FakeGpt)
    result = bev._judge("q", "key", "answer a", "answer b")
    assert result == {"score_a": 4, "score_b": 2, "reasoning": "A is correct"}


def test_judge_handles_json_wrapped_in_prose(monkeypatch):
    class FakeGpt:
        @staticmethod
        def call(prompt, *, command, model=None, max_output_tokens=200):
            return {"text": 'Sure, here it is:\n{"score_a": 3, "score_b": 3, "reasoning": "tie"}\nDone.'}

    monkeypatch.setitem(sys.modules, "research.lib.gpt", FakeGpt)
    result = bev._judge("q", "key", "answer a", "answer b")
    assert result == {"score_a": 3, "score_b": 3, "reasoning": "tie"}


def test_judge_returns_none_on_malformed_json(monkeypatch):
    class FakeGpt:
        @staticmethod
        def call(prompt, *, command, model=None, max_output_tokens=200):
            return {"text": "I cannot comply with strict JSON right now."}

    monkeypatch.setitem(sys.modules, "research.lib.gpt", FakeGpt)
    result = bev._judge("q", "key", "answer a", "answer b")
    assert result is None


def test_judge_returns_none_when_score_fields_missing(monkeypatch):
    class FakeGpt:
        @staticmethod
        def call(prompt, *, command, model=None, max_output_tokens=200):
            return {"text": '{"verdict": "A wins"}'}

    monkeypatch.setitem(sys.modules, "research.lib.gpt", FakeGpt)
    result = bev._judge("q", "key", "answer a", "answer b")
    assert result is None


def test_judge_call_failure_does_not_raise(monkeypatch):
    class FakeGpt:
        @staticmethod
        def call(prompt, *, command, model=None, max_output_tokens=200):
            raise RuntimeError("network down")

    monkeypatch.setitem(sys.modules, "research.lib.gpt", FakeGpt)
    result = bev._judge("q", "key", "answer a", "answer b")
    assert result is None


def test_judge_missing_key_propagates_as_system_exit(monkeypatch):
    """A missing OPENAI_API_KEY must exit cleanly, not be swallowed into an
    'unjudged' case - that would silently mask a configuration error as noise."""
    class FakeGpt:
        @staticmethod
        def call(prompt, *, command, model=None, max_output_tokens=200):
            raise SystemExit("OPENAI_API_KEY not configured")

    monkeypatch.setitem(sys.modules, "research.lib.gpt", FakeGpt)
    with pytest.raises(SystemExit):
        bev._judge("q", "key", "answer a", "answer b")


# --------------------------------------------------------------------------- #
# _ab_order: reproducible, not re-randomized per run
# --------------------------------------------------------------------------- #
def test_ab_order_is_reproducible_across_calls():
    for i in range(10):
        assert bev._ab_order(i) == bev._ab_order(i)


def test_ab_order_is_reproducible_in_a_fresh_process():
    """Same seeding strategy must hold across separate interpreter runs, not
    just within one - it's derived from a fixed hash of the index, not process
    state, but this pins that assumption directly."""
    import hashlib

    for i in range(10):
        digest = hashlib.sha256(f"behavior-eval-ab-{i}".encode()).hexdigest()
        expected = int(digest[:8], 16) % 2 == 0
        assert bev._ab_order(i) == expected


def test_ab_order_is_not_constant():
    orders = {bev._ab_order(i) for i in range(20)}
    assert orders == {True, False}, "labeling never varies - position bias would go unnoticed"


# --------------------------------------------------------------------------- #
# End-to-end evaluate() with everything mocked
# --------------------------------------------------------------------------- #
@pytest.fixture()
def vault_env_only(tmp_path, monkeypatch):
    """A vault directory + env var, with no API keys set anywhere - the
    'zero network access, no key present' boundary the whole suite runs under."""
    v = tmp_path / "vault"
    v.mkdir(parents=True)
    (v / "topic.md").write_text(
        "---\ntype: concept\n---\n\nCanonical fact about the topic.\n", encoding="utf-8"
    )
    monkeypatch.setenv(vault_ops._VAULT_ENV, str(v))
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
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


def test_evaluate_reports_a_positive_delta(vault_env_only, cases_file, monkeypatch, capsys):
    monkeypatch.setattr(bev, "_answer_with_vault", lambda q, model=None: "correct, matches the fact")
    monkeypatch.setattr(bev, "_answer_without_vault", lambda q, model=None: "I don't know")

    def fake_judge(q, key, a, b, model=None):
        return {"score_a": 5 if a == "correct, matches the fact" else 1,
                "score_b": 5 if b == "correct, matches the fact" else 1,
                "reasoning": "matches known facts"}

    monkeypatch.setattr(bev, "_judge", fake_judge)
    rc = bev.evaluate(cases_file, as_json=True, answer_model="grok-4.5", judge_model="gpt-4o-mini")
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["summary"]["judged"] == 2
    assert out["summary"]["overall_delta"] == 4.0
    assert out["summary"]["regressions"] == 0
    assert "overall_delta" in out["summary"]
    assert "by_category" in out["summary"]
    assert isinstance(out["regressions"], list)


def test_evaluate_reports_regressions_without_truncation(vault_env_only, cases_file, monkeypatch, capsys):
    monkeypatch.setattr(bev, "_answer_with_vault", lambda q, model=None: "vault-on")
    monkeypatch.setattr(bev, "_answer_without_vault", lambda q, model=None: "vault-off")

    def fake_judge(q, key, a, b, model=None):
        # vault-on always scores lower than vault-off - a regression on every case
        return {"score_a": 1 if a == "vault-on" else 5,
                "score_b": 1 if b == "vault-on" else 5,
                "reasoning": "vault answer worse"}

    monkeypatch.setattr(bev, "_judge", fake_judge)
    rc = bev.evaluate(cases_file, as_json=True, answer_model="grok-4.5", judge_model="gpt-4o-mini")
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["summary"]["regressions"] == 2
    assert len(out["regressions"]) == 2, "regressions bucket must never be truncated"
    assert out["summary"]["overall_delta"] < 0


def test_evaluate_does_not_crash_on_zero_delta(vault_env_only, cases_file, monkeypatch, capsys):
    monkeypatch.setattr(bev, "_answer_with_vault", lambda q, model=None: "same")
    monkeypatch.setattr(bev, "_answer_without_vault", lambda q, model=None: "same")
    monkeypatch.setattr(bev, "_judge",
                         lambda q, key, a, b, model=None: {"score_a": 3, "score_b": 3, "reasoning": "tie"})
    rc = bev.evaluate(cases_file, as_json=True, answer_model="grok-4.5", judge_model="gpt-4o-mini")
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["summary"]["overall_delta"] == 0.0


def test_evaluate_excludes_unjudged_cases_from_delta_but_reports_them(vault_env_only, cases_file, monkeypatch, capsys):
    monkeypatch.setattr(bev, "_answer_with_vault", lambda q, model=None: "vault-on")
    monkeypatch.setattr(bev, "_answer_without_vault", lambda q, model=None: "vault-off")
    monkeypatch.setattr(bev, "_judge", lambda q, key, a, b, model=None: None)  # every judge call fails
    rc = bev.evaluate(cases_file, as_json=True, answer_model="grok-4.5", judge_model="gpt-4o-mini")
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["summary"]["judged"] == 0
    assert out["summary"]["unjudged"] == 2
    assert out["summary"]["overall_delta"] is None


def test_evaluate_refuses_missing_cases_file(tmp_path):
    rc = bev.evaluate(tmp_path / "nope.jsonl", as_json=False)
    assert rc == 1


def test_generate_writes_the_requested_number_of_cases(tmp_path):
    p = tmp_path / "cases.jsonl"
    rc = bev.generate(10, p)
    assert rc == 0
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 10
    for r in rows:
        assert REQUIRED_FIELDS <= set(r)


def test_generate_refuses_to_overwrite_without_force(tmp_path):
    p = tmp_path / "cases.jsonl"
    p.write_text('{"q": "old"}\n', encoding="utf-8")
    import subprocess

    result = subprocess.run(
        [sys.executable, "scripts/eval/behavior_eval.py", "--generate", "5", "--cases", str(p)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "Refusing to overwrite" in result.stderr
    assert p.read_text(encoding="utf-8") == '{"q": "old"}\n'
