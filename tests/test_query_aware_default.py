"""The shipped search default is query-aware now (stress-test fix 11/24).

Single exact tokens (acronyms, bare names) dispatch to pure lexical - embeddings
of a bare token are near-meaningless and fusion demoted exact hits (OKF: lexical
rank 2 -> fused rank 5 in the audit). Multi-word queries keep the fusion, but
semantic votes now outweigh lexical ones (w=3.0, winner of the measured sweep on
paraphrase + keyword case sets with the straightened ruler from fix 10).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "integrations" / "obsidian-mcp-server"))

import vault_ops  # noqa: E402


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    v = tmp_path / "vault"
    v.mkdir()
    (v / "zebra-facts.md").write_text("---\ntype: note\n---\n\nzebra stripes galore\n",
                                      encoding="utf-8")
    monkeypatch.setenv(vault_ops._VAULT_ENV, str(v))
    return v


def test_single_token_query_dispatches_to_lexical(vault, monkeypatch):
    seen = {}

    def spy(query, lexical, v, limit, enabled=None):
        seen["enabled"] = enabled
        return None

    monkeypatch.setattr(vault_ops, "_semantic_fuse", spy)
    vault_ops.search("zebra", limit=5)
    assert seen["enabled"] is False, "bare-token lookup must not be diluted by fusion"


def test_multi_word_query_keeps_fusion(vault, monkeypatch):
    seen = {}

    def spy(query, lexical, v, limit, enabled=None):
        seen["enabled"] = enabled
        return None

    monkeypatch.setattr(vault_ops, "_semantic_fuse", spy)
    vault_ops.search("zebra stripes galore", limit=5)
    assert seen["enabled"] is None, "multi-word queries follow the env default (fusion on)"


def test_explicit_semantic_true_overrides_dispatch(vault, monkeypatch):
    seen = {}

    def spy(query, lexical, v, limit, enabled=None):
        seen["enabled"] = enabled
        return None

    monkeypatch.setattr(vault_ops, "_semantic_fuse", spy)
    vault_ops.search("zebra", limit=5, semantic=True)
    assert seen["enabled"] is True, "an explicit caller choice always wins over dispatch"


def test_semantic_votes_outweigh_lexical_in_fusion(vault, monkeypatch):
    """a.md wins lexically, b.md wins semantically; with w=3 the semantic
    winner must come out on top of the fused ranking."""
    index = {
        "model": "fake",
        "notes": {
            "a.md": {"title": "a", "vec": [0.6, 0.8]},
            "b.md": {"title": "b", "vec": [1.0, 0.0]},
        },
    }
    (vault / vault_ops._SEMANTIC_INDEX_FILE).write_text(json.dumps(index), encoding="utf-8")
    monkeypatch.setattr(vault_ops, "_embed_query", lambda q: [1.0, 0.0])

    # b.md sits at lexical rank 3: flat 1:1 fusion would keep a.md on top
    # (verified against the old code); semantic-weighted fusion must not.
    lexical = [
        {"path": "a.md", "title": "a", "snippet": ""},
        {"path": "c.md", "title": "c", "snippet": ""},
        {"path": "b.md", "title": "b", "snippet": ""},
    ]
    fused = vault_ops._semantic_fuse("some multi word query", lexical, vault, 5,
                                     enabled=True)
    assert fused is not None
    assert fused[0]["path"] == "b.md", fused
