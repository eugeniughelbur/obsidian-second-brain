"""A source whose preamble says it is unverified, with no `source_quality`, warns (#258).

A correction that lives only in prose is invisible to every check that reads
fields. This check makes that state visible. The properties worth pinning
hardest are the negative ones: a labelled source, a source that never uses the
words, and the words inside a code block or deep in a long capture stay silent.
All fixtures are synthetic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import vault_health as vh  # noqa: E402


def _source(vault: Path, name: str, body: str, quality: str | None = None, ntype: str = "source") -> str:
    rel = f"raw/articles/{name}.md"
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = f"source_quality: {quality}\n" if quality is not None else ""
    path.write_text(
        f"---\ntype: {ntype}\ndate: 2026-10-27\ntags: [source]\n{extra}ai-first: true\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return rel


@pytest.fixture()
def vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    return v


def _findings(vault: Path):
    return vh.check_source_quality_unlabelled(vh.load_vault(vault), vault)


def test_unlabelled_source_that_calls_itself_unverified_warns(vault):
    rel = _source(vault, "thread", "Source: forum thread. Unverified, no byline.\n\ncaptured text")
    found = _findings(vault)
    assert [f["type"] for f in found] == ["source_quality_unlabelled"]
    assert found[0]["severity"] == "warning"
    assert found[0]["files"] == [rel]
    assert "Unverified" in found[0]["message"]


@pytest.mark.parametrize("phrase", [
    "not verified", "unconfirmed", "speculative", "Provenance unknown",
    "Provenance: unknown", "provenance is unknown",
])
def test_each_marker_is_recognised(vault, phrase):
    _source(vault, "thread", f"Note: {phrase}.\n\ncaptured text")
    found = _findings(vault)
    assert [f["type"] for f in found] == ["source_quality_unlabelled"]
    assert f'"{phrase}"' in found[0]["message"]


def test_untitled_and_unknown_alone_are_not_markers(vault):
    _source(vault, "plain", "Untitled draft. Author unknown. Undated.\n\ntext")
    assert _findings(vault) == []


def test_a_labelled_source_is_silent(vault):
    _source(vault, "thread", "Unverified, no byline.", quality="speculation")
    _source(vault, "other", "Unverified, no byline.", quality="medium")
    assert _findings(vault) == []


@pytest.mark.parametrize("value", ["typo", '""', "[speculation]"])
def test_a_present_but_unrecognised_label_is_not_reported_as_missing(vault, value):
    _source(vault, "thread", "Unverified, no byline.", quality=value)
    assert _findings(vault) == []


def test_a_source_that_never_uses_the_words_is_silent(vault):
    _source(vault, "plain", "Source: https://example.org/post by A. Author, 2026-09-01.\n\ntext")
    assert _findings(vault) == []


def test_summary_and_not_verbatim_are_not_markers(vault):
    # The spec says these do not by themselves lower the grade.
    _source(vault, "digest", "Summary, not verbatim. Derived from the talk.\n\ntext")
    assert _findings(vault) == []


def test_the_word_inside_a_code_block_is_silent(vault):
    _source(vault, "code", "```\nstatus = 'unverified'\n```\n\ntext")
    assert _findings(vault) == []


def test_a_long_code_block_on_top_uses_up_the_window(vault):
    code = "\n".join(f"x{i} = {i}" for i in range(30))
    _source(vault, "code_top", f"```\n{code}\n```\nthis claim is unverified")
    assert _findings(vault) == []


def test_inline_code_is_silent(vault):
    _source(vault, "inline", "The badge reads `unverified` on the platform.\n\ntext")
    assert _findings(vault) == []


def test_the_word_deep_in_a_long_capture_is_silent(vault):
    body = "\n".join(f"line {i}" for i in range(40)) + "\nthis claim is unverified"
    _source(vault, "long", body)
    assert _findings(vault) == []


def test_a_non_source_note_is_out_of_scope(vault):
    _source(vault, "idea", "Speculative idea for later.", ntype="concept")
    assert _findings(vault) == []


def test_silent_policy_mutes_it(vault):
    _source(vault, "thread", "Unverified, no byline.")
    (vault / ".vault-config.json").write_text(json.dumps({"source_quality_policy": "silent"}), encoding="utf-8")
    assert _findings(vault) == []


def test_registered_in_the_health_report(vault):
    _source(vault, "thread", "Unverified, no byline.")
    report = vh.run_health_check(vault)
    assert report["counts"]["Source quality (unlabelled)"] == 1
    assert [i["type"] for i in report["issues"] if i["type"].startswith("source_quality")] == [
        "source_quality_unlabelled"]
