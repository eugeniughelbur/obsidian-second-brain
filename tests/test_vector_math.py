"""Vector math used to rank every semantic search result (issue #164).

_cosine/_dot in vault_ops.py and cosine() in scripts/eval/semantic_search.py
each guard `len(a) != len(b)` before summing with zip(), so a length
mismatch already returns 0.0 rather than silently scoring a truncated
partial dot product. zip(..., strict=True) turns that guard into an
enforced invariant: if a future edit ever removes the length check, the
zip raises instead of quietly resuming the old failure mode (a plausible-
looking but wrong similarity score) - see the issue for how bad that
failure mode is: nothing in the output distinguishes a genuinely weak
match from a comparison that silently dropped half its dimensions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "integrations" / "obsidian-mcp-server"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "eval"))

import vault_ops  # noqa: E402
import semantic_search as ss  # noqa: E402


@pytest.mark.parametrize(
    "fn",
    [vault_ops._cosine, vault_ops._dot, ss.cosine],
    ids=["vault_ops._cosine", "vault_ops._dot", "semantic_search.cosine"],
)
def test_mismatched_length_returns_zero_not_a_partial_score(fn):
    """A 3-dim and a 5-dim vector must never be scored via a truncated zip."""
    a = [1.0, 1.0, 1.0]
    b = [1.0, 1.0, 1.0, 1.0, 1.0]
    assert fn(a, b) == 0.0
    assert fn(b, a) == 0.0


@pytest.mark.parametrize(
    "fn",
    [vault_ops._cosine, vault_ops._dot, ss.cosine],
    ids=["vault_ops._cosine", "vault_ops._dot", "semantic_search.cosine"],
)
def test_equal_length_vectors_still_score_normally(fn):
    """strict=True must not change behaviour for the normal, matching case."""
    identical = [1.0, 0.0, 0.0]
    assert fn(identical, identical) == pytest.approx(1.0)

    orthogonal_a = [1.0, 0.0]
    orthogonal_b = [0.0, 1.0]
    assert fn(orthogonal_a, orthogonal_b) == pytest.approx(0.0)


def test_empty_vectors_return_zero():
    assert vault_ops._cosine([], []) == 0.0
    assert ss.cosine([], []) == 0.0
