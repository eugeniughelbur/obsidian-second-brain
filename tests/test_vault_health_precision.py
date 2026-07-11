"""vault_health precision: the smoke alarm must neither miss fires nor cry wolf.

Pins the stress test's referee-level findings (fix 8/24): the orphan check's
substring blind spot (short stems hiding inside other links) and self-link
loophole, duplicate warnings inflated by shared AI-first boilerplate, and the
inline-alias parsing gap discovered during fix 4.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _health(vault: Path) -> dict:
    result = subprocess.run(
        [sys.executable, "scripts/vault_health.py", "--path", str(vault), "--json"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout[result.stdout.find("{"):])


def _issues(payload: dict, itype: str) -> list:
    return [i for i in payload["issues"] if i["type"] == itype]


def test_short_stem_orphan_is_flagged(tmp_path):
    """'ai' used to hide inside 'detail' via substring matching and never ring."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "ai.md").write_text("# about ai\n", encoding="utf-8")
    (vault / "other.md").write_text("see [[detail]]\n", encoding="utf-8")

    orphans = {i["files"][0] for i in _issues(_health(vault), "orphan")}
    assert "ai.md" in orphans


def test_path_qualified_incoming_link_still_counts(tmp_path):
    """The legit case behind the old substring hack must keep working."""
    vault = tmp_path / "vault"
    (vault / "Projects").mkdir(parents=True)
    (vault / "Projects" / "target.md").write_text("# t\n", encoding="utf-8")
    (vault / "linker.md").write_text("see [[Projects/target]]\n", encoding="utf-8")

    orphans = {i["files"][0] for i in _issues(_health(vault), "orphan")}
    assert "Projects/target.md" not in orphans


def test_self_link_does_not_prevent_orphanhood(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "zephyr.md").write_text("me again: [[zephyr]]\n", encoding="utf-8")

    orphans = {i["files"][0] for i in _issues(_health(vault), "orphan")}
    assert "zephyr.md" in orphans


def test_same_title_different_content_is_not_a_duplicate_warning(tmp_path):
    """Shared frontmatter + '## For future Claude' boilerplate used to push two
    unrelated notes past the 0.6 similarity threshold."""
    vault = tmp_path / "vault"
    (vault / "Concepts").mkdir(parents=True)
    boiler = ("---\ntype: concept\ndate: 2026-07-11\ntags: [concept]\nai-first: true\n---\n\n"
              "## For future Claude\n\n")
    (vault / "Concepts" / "Google Ads.md").write_text(
        boiler + "Concept A is entirely about the Google Ads auction platform and bidding.\n",
        encoding="utf-8",
    )
    (vault / "Concepts" / "google-ads.md").write_text(
        boiler + "Concept B covers something different: retention emails for tour operators.\n",
        encoding="utf-8",
    )

    dups = _issues(_health(vault), "duplicate")
    assert dups, "same-title notes should still be grouped"
    assert all(d["severity"] == "info" for d in dups), dups


def test_true_duplicates_still_warn(tmp_path):
    vault = tmp_path / "vault"
    (vault / "A").mkdir(parents=True)
    (vault / "B").mkdir()
    body = "---\ntype: concept\n---\n\n## For future Claude\n\nIdentical body text here.\n"
    (vault / "A" / "Same Note.md").write_text(body, encoding="utf-8")
    (vault / "B" / "same-note.md").write_text(body, encoding="utf-8")

    dups = _issues(_health(vault), "duplicate")
    assert dups and dups[0]["severity"] == "warning", dups


def test_inline_aliases_resolve_links(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "person.md").write_text(
        "---\ntype: person\naliases: [Big Boss, El Jefe]\n---\n\n# person\n",
        encoding="utf-8",
    )
    (vault / "linker.md").write_text("met [[Big Boss]] and [[El Jefe]]\n", encoding="utf-8")

    wanted = _issues(_health(vault), "wanted_note")
    assert wanted == [], wanted
