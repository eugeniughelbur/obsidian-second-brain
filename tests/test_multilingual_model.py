"""Multilingual model swap + model-mix guards (stress-test fix 16/24).

Russian queries scored 0% in every mode: the embedding model was the
bottleneck. The default is a multilingual model now, and two latent bugs that
would silently mix vector spaces are guarded: the build cache invalidates on a
model change, and queries always embed with the INDEX's model.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "integrations" / "obsidian-mcp-server"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "eval"))

import vault_ops  # noqa: E402
import semantic_search as ss  # noqa: E402


def test_default_model_is_multilingual():
    assert ss.EMBED_MODEL == "bge-m3"
    assert vault_ops._EMBED_MODEL == "bge-m3"


def test_build_cache_invalidates_on_model_change(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "a.md").write_text("---\ntype: note\n---\n\nsome prose\n", encoding="utf-8")
    monkeypatch.setattr(ss, "embed", lambda t, retries=None, model=None: [1.0, 0.0])

    ss.build_index(vault, verbose=False)
    embeds = []
    monkeypatch.setattr(ss, "embed",
                        lambda t, retries=None, model=None: embeds.append(t) or [0.0, 1.0])

    # Same model: cache reused, nothing re-embedded.
    ss.build_index(vault, verbose=False)
    assert embeds == []

    # Model changed on disk: every cached vector is in the wrong space.
    idx = vault / ss.INDEX_FILE
    d = json.loads(idx.read_text())
    d["model"] = "some-old-model"
    idx.write_text(json.dumps(d))
    ss.build_index(vault, verbose=False)
    assert embeds, "a model change must force a full re-embed"


def test_fuse_embeds_query_with_index_model(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    index = {"model": "index-model-x", "format": 2,
             "notes": {"a.md": {"title": "a", "vecs": [[1.0, 0.0]]}}}
    (vault / vault_ops._SEMANTIC_INDEX_FILE).write_text(json.dumps(index), encoding="utf-8")

    seen = {}

    def spy(text, model=None):
        seen["model"] = model
        return [1.0, 0.0]

    monkeypatch.setattr(vault_ops, "_embed_query", spy)
    vault_ops._semantic_fuse("some multi word query", [], vault, 5, enabled=True)
    assert seen["model"] == "index-model-x"


def test_eval_semantic_search_uses_index_model(monkeypatch):
    seen = {}

    def spy(text, retries=None, model=None):
        seen["model"] = model
        return [1.0, 0.0]

    monkeypatch.setattr(ss, "embed", spy)
    index = {"model": "index-model-y", "format": 2,
             "notes": {"a.md": {"title": "a", "vecs": [[1.0, 0.0]]}}}
    ss.semantic_search("query words", index, limit=3)
    assert seen["model"] == "index-model-y"
