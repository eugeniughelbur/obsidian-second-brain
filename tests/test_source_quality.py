"""`source_quality` warns when knowledge rests only on speculation-grade sources (#258).

The field is written on the raw note at capture and consumed here. It is not a
verdict on truth and not a retention measure (that is `capture_scope`, #194).
The check has one job: a concept or synthesis note whose every cited source is
`speculation` gets a warning. The property worth pinning hardest is the
negative one - a vault written before the field existed must stay silent.
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


def _source(vault: Path, name: str, quality: str | None, scope: str | None = "full-local") -> str:
    rel = f"raw/articles/{name}.md"
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = ""
    if quality is not None:
        extra += f"source_quality: {quality}\n"
    if scope:
        extra += f"capture_scope: {scope}\n"
    path.write_text(
        f"---\ntype: source\ndate: 2026-09-20\ntags: [source]\n{extra}ai-first: true\n---\n\n"
        + "captured text " * 10,
        encoding="utf-8",
    )
    return rel


def _note(vault: Path, name: str, links: list[str], ntype: str = "concept") -> str:
    rel = f"Knowledge/{name}.md"
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    body = " ".join(f"[[{link}]]" for link in links)
    path.write_text(
        f"---\ntype: {ntype}\ndate: 2026-09-20\ntags: [{ntype}]\nai-first: true\n---\n\n"
        f"## For future agent\nsummary\n\n{body}\n",
        encoding="utf-8",
    )
    return rel


@pytest.fixture()
def vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    return v


def _findings(vault: Path):
    return vh.check_source_quality(vh.load_vault(vault), vault)


def test_note_citing_only_speculation_sources_warns(vault):
    _source(vault, "thin", "speculation")
    note = _note(vault, "Claim", ["thin"])
    found = _findings(vault)
    assert [f["type"] for f in found] == ["source_quality"]
    assert found[0]["severity"] == "warning"
    assert found[0]["files"][0] == note


def test_every_cited_source_must_be_speculation(vault):
    _source(vault, "thin", "speculation")
    _source(vault, "solid", "medium")
    _note(vault, "Claim", ["thin", "solid"])
    assert _findings(vault) == []


def test_unlabelled_source_is_unjudged_not_speculative(vault):
    """A vault written before the field existed must stay silent."""
    _source(vault, "thin", "speculation")
    _source(vault, "old", None)
    _note(vault, "Mixed", ["thin", "old"])
    _note(vault, "OnlyOld", ["old"])
    assert _findings(vault) == []


def test_unrecognised_value_is_ignored(vault):
    _source(vault, "odd", "Speculative-ish")
    _note(vault, "Claim", ["odd"])
    assert _findings(vault) == []


def test_source_quality_is_independent_of_capture_scope(vault):
    """Same quality, different retention: both are reported, neither implies the other."""
    _source(vault, "thin-full", "speculation", scope="full-local")
    _source(vault, "thin-url", "speculation", scope="url-only")
    _note(vault, "A", ["thin-full"])
    _note(vault, "B", ["thin-url"])
    flagged = {f["files"][0] for f in _findings(vault)}
    assert flagged == {"Knowledge/A.md", "Knowledge/B.md"}
    payload = vh.check_source_payload(vh.load_vault(vault), vault)
    assert {f["files"][0] for f in payload if f["severity"] == "warning"} == {"raw/articles/thin-url.md"}


def test_a_source_citing_a_source_is_not_active_knowledge(vault):
    _source(vault, "thin", "speculation")
    path = vault / "raw/articles/digest.md"
    path.write_text(
        "---\ntype: source\ndate: 2026-09-20\ntags: [source]\nsource_quality: speculation\n"
        "ai-first: true\n---\n\n[[thin]] " + "text " * 20,
        encoding="utf-8",
    )
    assert _findings(vault) == []


def test_uncited_speculation_source_is_quiet(vault):
    """raw/ stays cheap: capturing a thin source and never compiling it costs nothing."""
    _source(vault, "thin", "speculation")
    assert _findings(vault) == []


@pytest.mark.parametrize("config", [None, "{not json", "[]", '{"source_quality_policy": 3}',
                                    '{"source_quality_policy": "strict"}',
                                    '{"source_quality_policy": "warn"}'])
def test_policy_defaults_to_warn(vault, config):
    if config is not None:
        (vault / ".vault-config.json").write_text(config, encoding="utf-8")
    assert vh.load_source_quality_policy(vault) == "warn"


def test_silent_policy_mutes_the_warning(vault):
    _source(vault, "thin", "speculation")
    _note(vault, "Claim", ["thin"])
    (vault / ".vault-config.json").write_text(
        json.dumps({"source_quality_policy": "silent"}), encoding="utf-8")
    assert vh.load_source_quality_policy(vault) == "silent"
    assert _findings(vault) == []


def test_reported_in_the_health_run(vault):
    _source(vault, "thin", "speculation")
    _note(vault, "Claim", ["thin"])
    result = vh.run_health_check(vault)
    assert result["counts"]["Source quality"] == 1


def test_activity_notes_do_not_ring(vault):
    """A daily note, a log and the index mention every capture. They record that
    a source arrived; they are not knowledge resting on it."""
    _source(vault, "thin", "speculation")
    _note(vault, "2026-09-20", ["thin"], ntype="daily")
    _note(vault, "log-entry", ["thin"], ntype="log")
    (vault / "index.md").write_text("- [[thin]]\n", encoding="utf-8")
    assert _findings(vault) == []


def test_template_comment_is_not_part_of_the_value(vault):
    rel = "raw/articles/inl.md"
    (vault / rel).parent.mkdir(parents=True)
    (vault / rel).write_text(
        "---\ntype: source\nsource_quality: speculation   # high | medium | speculation\n"
        "ai-first: true\n---\n\n" + "captured text " * 10, encoding="utf-8")
    _note(vault, "Claim", ["inl"])
    assert [f["files"][0] for f in _findings(vault)] == ["Knowledge/Claim.md"]
