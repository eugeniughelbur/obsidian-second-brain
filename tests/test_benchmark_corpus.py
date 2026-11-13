"""A benchmark that grades itself wrong is worse than no benchmark.

The first version of the generator wrote "<title> is <gloss>." into each
canonical note, and the gloss is exactly the text of that note's paraphrase
query. So every paraphrase query appeared verbatim inside its own answer, and
pure lexical search scored 83% on a set specifically designed to defeat lexical
search. It looked like a strong result. It was the answer key.

That is the failure mode these tests exist for: not "does the generator run"
but "does the corpus actually measure the thing it claims to". So they check
that queries do not leak into their answers, that the intended difficulty is
really present, and that two people running this get the same corpus, without
which no two numbers are comparable.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "eval"))

import corpus  # noqa: E402


@pytest.fixture(scope="module")
def built():
    return corpus.build(300, 20260726), corpus.cases()


# --- reproducibility --------------------------------------------------------

def test_two_runs_produce_the_same_corpus():
    """Without this, no two people's numbers mean the same thing."""
    a, b = corpus.build(300, 20260726), corpus.build(300, 20260726)
    assert a == b
    assert corpus.manifest(a, corpus.cases()) == corpus.manifest(b, corpus.cases())


def test_a_different_seed_produces_a_different_corpus():
    """Proves the seed is actually wired up, not decorative."""
    a = corpus.build(300, 20260726)
    b = corpus.build(300, 1)
    assert a != b


def test_the_writer_round_trips(tmp_path):
    rc = corpus.main(["corpus.py", "--out", str(tmp_path), "--notes", "80"])
    assert rc == 0
    on_disk = {
        p.relative_to(tmp_path).as_posix(): p.read_text(encoding="utf-8")
        for p in tmp_path.rglob("*.md")
    }
    assert on_disk == corpus.build(80, 20260726)


# --- the integrity of the measurement ---------------------------------------

def test_no_paraphrase_query_appears_inside_its_own_answer(built):
    """The exact bug that made this benchmark score itself 83%."""
    files, sets = built
    offenders = []
    for c in sets["paraphrase"]:
        gold = files[c["gold"][0]].lower()
        if c["q"].lower() in gold:
            offenders.append(c["title"])
    assert not offenders, (
        f"the paraphrase query is verbatim inside the note it is supposed to find, "
        f"for {offenders}. Lexical search will 'solve' those cases by copying the "
        "answer key, and the set stops measuring paraphrase at all."
    )


def test_paraphrase_queries_barely_overlap_their_answers(built):
    """A little shared vocabulary is natural language; a lot is a leak."""
    files, sets = built
    bad = []
    for c in sets["paraphrase"]:
        gold = files[c["gold"][0]].lower()
        words = [w for w in c["q"].lower().split() if len(w) > 4]
        shared = sum(1 for w in words if w in gold)
        if words and shared / len(words) > 0.5:
            bad.append(f"{c['title']} ({shared}/{len(words)})")
    assert not bad, f"over half the query's content words are in the answer: {bad}"


def test_every_topic_has_derivatives_that_outweigh_the_canonical_note(built):
    """The designed difficulty. Without it the benchmark is trivially solvable."""
    files, _ = built
    for t in corpus.TOPICS:
        gold_rel = f"{corpus.FOLDER[t['kind']]}/{t['title']}.md"
        gold_hits = files[gold_rel].lower().count(t["term"])
        rivals = [
            rel for rel, body in files.items()
            if rel != gold_rel and body.lower().count(t["term"]) > gold_hits
        ]
        assert len(rivals) >= 3, (
            f"{t['title']}: only {len(rivals)} note(s) mention '{t['term']}' more "
            "often than the canonical note. Term-frequency ranking would find the "
            "right answer by accident, so this topic measures nothing."
        )


def test_the_gold_note_for_every_case_exists(built):
    files, sets = built
    for name, rows in sets.items():
        for c in rows:
            for g in c["gold"]:
                assert g in files, f"{name}: case '{c['title']}' points at a missing note {g}"


def test_the_three_sets_cover_every_topic(built):
    _, sets = built
    n = len(corpus.TOPICS)
    assert len(sets["keyword"]) == n
    assert len(sets["paraphrase"]) == n
    assert len(sets["multilingual"]) == 2 * n, "expected one Spanish and one Russian per topic"


def test_multilingual_queries_are_not_secretly_english(built):
    """A 'Russian' query written in English would make the set meaningless."""
    _, sets = built
    for c in sets["multilingual"]:
        cyrillic = any("Ѐ" <= ch <= "ӿ" for ch in c["q"])
        accented_or_spanish = any(w in c["q"].lower() for w in
                                  ("la ", "el ", "los ", "para", "que", "como", "de "))
        assert cyrillic or accented_or_spanish, f"not obviously ES or RU: {c['q'][:40]}"


# --- no real content --------------------------------------------------------

def test_the_corpus_is_marked_synthetic(built):
    files, _ = built
    missing = [r for r, b in files.items() if "synthetic: true" not in b]
    assert not missing, (
        f"{len(missing)} generated note(s) are not marked synthetic. Anyone who "
        "points a tool at this corpus must be able to tell it is not real."
    )


def test_the_generator_carries_no_real_vault_paths():
    """Guards the reason the real case files are gitignored in the first place."""
    src = (REPO_ROOT / "scripts" / "eval" / "corpus.py").read_text(encoding="utf-8")
    # The author-credit header (scripts/stamp_credit.py) names the author on
    # purpose; it is attribution, not vault data, so it is left out of the scan.
    credit = ("# SPDX-", "# Author:", "# Questions or consulting:")
    src = "\n".join(ln for ln in src.splitlines() if not ln.startswith(credit))
    for marker in ("/Users/", "Eugeniu", "obsinian", "singlegrain"):
        assert marker not in src, f"generator source contains {marker!r}"


def test_it_runs_as_a_command():
    r = subprocess.run([sys.executable, "scripts/eval/corpus.py", "--manifest"],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "sha256" in r.stdout


def test_case_files_are_valid_jsonl(tmp_path):
    corpus.main(["corpus.py", "--out", str(tmp_path), "--notes", "80"])
    for f in (tmp_path / "_cases").glob("*.jsonl"):
        rows = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
        assert rows, f"{f.name} is empty"
        for r in rows:
            assert r["q"] and r["gold"], f"{f.name} has a case with no query or no gold"
