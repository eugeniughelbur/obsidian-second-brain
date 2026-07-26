"""Fences for six defects that reach a real user.

  B30 heal_links --apply counted a fix that changed nothing, then tripped its
      own no-progress guard and abandoned every remaining safe fix
  B31 a podcast feed controlled the fetch target, so it could reach localhost,
      a dev server, or a cloud metadata endpoint - and the body was then
      summarized by an LLM and written into the vault
  B22 the bytecode cleanup was cwd-relative, so invoking build.sh by absolute
      path (which the vault updater does) shipped .pyc files into the vault
  B18 SKILL.md called the ASCII hyphen an em dash, so an agent following it
      literally produced filenames that no wikilink can resolve
  B33 the documented set_fields example was a silent soft-delete
  B34 one failing case aborted the entire retrieval eval
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "integrations" / "obsidian-mcp-server"))


# --- B31 -------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://localhost:11434/api/tags",
    "http://127.0.0.1:8002/internal",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/admin",
    "http://192.168.1.1/",
    "file:///etc/passwd",
])
def test_feed_supplied_urls_pointing_inward_are_refused(url):
    from research.lib.podcast import safe_fetch_url
    assert safe_fetch_url(url) is not None, (
        f"{url} was accepted. A podcast feed supplies these verbatim, so this is "
        "reachable from a normal-looking podcasts.apple.com link."
    )


def test_ordinary_public_urls_still_work():
    """Guards against a guard so broad it breaks the feature."""
    from research.lib.podcast import safe_fetch_url
    assert safe_fetch_url("https://example.com/transcript.vtt") is None


def test_both_fetch_sites_call_the_guard():
    src = (REPO_ROOT / "scripts" / "research" / "lib" / "podcast.py").read_text(encoding="utf-8")
    assert src.count("safe_fetch_url(") >= 3, (
        "the guard exists but is not called at both the transcript and audio "
        "fetch sites (plus the redirect re-check)"
    )
    assert "allow_redirects=False" in src, (
        "an allowed host can still 302 the request inward"
    )


# --- B22 -------------------------------------------------------------------

def test_bytecode_cleanup_is_anchored_to_the_repo_not_the_cwd():
    src = (REPO_ROOT / "scripts" / "build.sh").read_text(encoding="utf-8")
    assert 'find "$REPO_ROOT/dist"' in src, (
        "the cleanup uses a cwd-relative path. scripts/update-vault-integration.sh "
        "calls build.sh by absolute path with no cd, so it silently matched nothing "
        "and the bytecode was copied into the user's vault"
    )
    assert "find dist -name" not in src


def test_a_build_from_a_foreign_cwd_ships_no_bytecode(tmp_path):
    subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "build.sh"), "--platform", "hermes"],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    stray = list((REPO_ROOT / "dist" / "hermes").rglob("*.pyc"))
    stray += [p for p in (REPO_ROOT / "dist" / "hermes").rglob("__pycache__") if p.is_dir()]
    assert not stray, f"bytecode shipped when built from another directory: {stray[:5]}"


# --- B18 -------------------------------------------------------------------

def test_skill_md_does_not_call_the_hyphen_an_em_dash():
    src = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "(em dash)" not in src, (
        "SKILL.md labels the ASCII hyphen an em dash. An agent following it "
        "literally writes a filename no wikilink can resolve, and the write-time "
        "validator only checks content, not filenames"
    )
    assert "Never an em dash" in src


# --- B33 -------------------------------------------------------------------

def test_update_note_reports_a_retrieval_affecting_status(tmp_path, monkeypatch):
    v = tmp_path / "vault"
    v.mkdir()
    (v / "n.md").write_text("---\ntype: note\n---\n\nbody\n", encoding="utf-8")
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(v))
    import importlib

    import vault_ops
    importlib.reload(vault_ops)

    quiet = vault_ops.update_note("n.md", set_fields={"owner": "alex"})
    assert "faded" not in quiet, "an ordinary field should not warn"

    faded = vault_ops.update_note("n.md", set_fields={"status": "done"})
    assert "faded" in faded, (
        "setting a stale status de-ranks the note in every future search and said "
        "nothing about it, which is closer to archiving than to labelling"
    )


def test_the_documented_example_is_not_a_soft_delete():
    src = (REPO_ROOT / "integrations" / "obsidian-mcp-server" / "server.py").read_text(encoding="utf-8")
    assert '{"status": "done"}' not in src, (
        "the tool's own example told the agent to set a status that fades the note"
    )


# --- B34 -------------------------------------------------------------------

def test_one_failing_eval_case_does_not_abort_the_run():
    src = (REPO_ROOT / "scripts" / "eval" / "retrieval_eval.py").read_text(encoding="utf-8")
    # There are two `for c in cases:` loops; the one that matters is the scoring
    # loop, identified by the search_fn call rather than by being first.
    idx = src.index("search_fn(c[")
    window = src[max(0, idx - 400):idx + 200]
    assert "try:" in window and "except Exception" in window, (
        "the eval loop has no guard, so one failing case discards every case "
        "already scored - and in semantic mode a slow backend can burn ten "
        "minutes on the retry ladder before it raises"
    )


# --- B30 -------------------------------------------------------------------

def test_heal_links_does_not_count_a_rewrite_that_changed_nothing():
    src = (REPO_ROOT / "scripts" / "heal_links.py").read_text(encoding="utf-8")
    assert "text, _ = _rewrite(" not in src, (
        "apply_loop discards the replacement count, so an anchored or aliased "
        "link reports a fix, writes identical bytes, then trips the no-progress "
        "guard and abandons the remaining safe fixes"
    )
    assert "if n == 0:" in src
