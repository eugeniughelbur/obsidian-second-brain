"""Tests for the slim Claude Code + Codex toolkit.

Covers what both hosts depend on: skill files, config resolution, Korean
search, the Codex/Claude host config edits, bootstrap, and the validator hook
fed both Claude and Codex payloads.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import host_config  # noqa: E402
import vault_search  # noqa: E402
import youtube_transcript  # noqa: E402

SKILLS = ["obsidian-init", "obsidian-save", "obsidian-find", "obsidian-health", "obsidian-review"]
GOOD_NOTE = (
    "---\ntype: concept\ndate: 2026-11-11\ntags: [concept]\nai-first: true\n---\n\n"
    "## For future agent\n지식 관리에 대한 개념 노트.\n\n프로젝트를 정리하는 방법.\n"
)


# ---------------------------------------------------------------- skills

def _frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "missing frontmatter"
    out = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip().strip('"')
    return out


def test_exactly_the_five_skills_ship():
    assert sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir()) == sorted(SKILLS)
    assert not (ROOT / "commands").exists()
    assert not (ROOT / "adapters").exists()


@pytest.mark.parametrize("name", SKILLS)
def test_skill_frontmatter_is_portable(name):
    text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    fm = _frontmatter(text)
    assert fm.get("name") == name
    # Codex and Claude both read name + description; keep the description well
    # under the 1024-character cap and free of Claude-only frontmatter.
    assert 50 < len(fm["description"]) < 1024
    assert set(fm) == {"name", "description"}


@pytest.mark.parametrize("name", SKILLS)
def test_skill_body_has_no_platform_lockin(name):
    text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    placeholders = set(re.findall(r"\{\{([A-Z_]+)\}\}", text))
    # obsidian-init mentions the template's {{...}} syntax in prose.
    assert placeholders <= {"OSB_ROOT"}
    assert "{{OSB_ROOT}}/scripts/osb_env.py" in text, "skill must resolve the vault from config"
    for banned in ("CLAUDE_PLUGIN_ROOT", "SKILL_ROOT", "AskUserQuestion", "Task tool",
                   "grok", "Grok", "gemini", "Gemini", "perplexity", "Perplexity", "$ARGUMENTS"):
        assert banned not in text, f"{name} mentions {banned}"


# ---------------------------------------------------------------- config

def _run_env(tmp_path, env_extra):
    env = {**os.environ, "HOME": str(tmp_path), **env_extra}
    env.pop("OBSIDIAN_VAULT_PATH", None)
    env.update(env_extra)
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "osb_env.py")],
                          capture_output=True, text=True, env=env)


def test_osb_env_refuses_without_vault(tmp_path):
    r = _run_env(tmp_path, {})
    assert r.returncode == 2
    assert json.loads(r.stdout)["vault_ok"] is False


def test_osb_env_reads_config_file(tmp_path):
    vault = tmp_path / "v"
    vault.mkdir()
    host_config.write_env(vault, "ko", env_file=tmp_path / ".config/obsidian-second-brain/.env")
    r = _run_env(tmp_path, {})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["vault_path"] == str(vault) and out["language"] == "ko"


# ---------------------------------------------------------------- search

def _vault(tmp_path) -> Path:
    v = tmp_path / "vault"
    (v / "wiki" / "concepts").mkdir(parents=True)
    (v / "raw" / "articles").mkdir(parents=True)
    (v / "wiki" / "concepts" / "지식 관리.md").write_text(GOOD_NOTE, encoding="utf-8")
    (v / "raw" / "articles" / "긴 원문.md").write_text("지식 관리 " * 200, encoding="utf-8")
    (v / "wiki" / "concepts" / "Other.md").write_text("unrelated english note", encoding="utf-8")
    return v


def test_search_matches_korean_with_particles(tmp_path):
    v = _vault(tmp_path)
    hits = vault_search.search(v, "프로젝트는 어떻게 정리하지")
    assert hits and hits[0]["path"] == "wiki/concepts/지식 관리.md"


def test_search_ranks_wiki_above_raw_and_handles_nfd(tmp_path):
    v = _vault(tmp_path)
    nfd_query = unicodedata.normalize("NFD", "지식 관리")
    hits = vault_search.search(v, nfd_query)
    assert hits[0]["path"] == "wiki/concepts/지식 관리.md"
    assert any(h["path"].startswith("raw/") for h in hits)


# ---------------------------------------------------------------- youtube

@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=jNQXAC9IVRw",
    "https://youtu.be/jNQXAC9IVRw?t=3",
    "https://www.youtube.com/shorts/jNQXAC9IVRw",
    "jNQXAC9IVRw",
])
def test_youtube_video_id(url):
    assert youtube_transcript.video_id(url) == "jNQXAC9IVRw"


def test_youtube_rejects_non_youtube():
    assert youtube_transcript.video_id("https://example.com/watch") == ""


# ---------------------------------------------------------------- host config

def test_codex_toml_merge_is_idempotent_and_keeps_existing_roots(tmp_path):
    codex = tmp_path / ".codex"
    codex.mkdir()
    (codex / "config.toml").write_text(
        'model = "x"\n\n[sandbox_workspace_write]\nwritable_roots = [\n  "/a",\n]\n'
        "network_access = false\n\n[features]\nfoo = true\n", encoding="utf-8")
    vault = tmp_path / "vault"
    assert host_config.configure_codex(vault, codex_home=codex)
    first = (codex / "config.toml").read_text(encoding="utf-8")
    assert host_config.configure_codex(vault, codex_home=codex) == []
    assert (codex / "config.toml").read_text(encoding="utf-8") == first
    if sys.version_info >= (3, 11):
        import tomllib

        cfg = tomllib.loads(first)
        assert cfg["sandbox_workspace_write"]["writable_roots"] == ["/a", str(vault)]
        assert cfg["sandbox_workspace_write"]["network_access"] is True
        assert cfg["features"]["foo"] is True
    assert (codex / "config.toml.osb-bak").exists()


def test_codex_hooks_keep_foreign_hooks_and_index(tmp_path):
    codex = tmp_path / ".codex"
    codex.mkdir()
    foreign = {"matcher": "", "hooks": [{"type": "command", "command": "other-tool"}]}
    (codex / "hooks.json").write_text(json.dumps({"hooks": {"PostToolUse": [foreign]}}))
    host_config.configure_codex(tmp_path / "v", codex_home=codex)
    host_config.configure_codex(tmp_path / "v", codex_home=codex)
    groups = json.loads((codex / "hooks.json").read_text())["hooks"]["PostToolUse"]
    # The foreign hook stays at index 0, so Codex's stored trust for it holds.
    assert groups[0] == foreign
    assert len(groups) == 2 and "validate-ai-first.sh" in groups[1]["hooks"][0]["command"]


def test_claude_settings_drop_legacy_hooks(tmp_path):
    settings = tmp_path / "settings.json"
    legacy = "/x/.claude/skills/obsidian-second-brain/hooks/load_vault_context.sh"
    settings.write_text(json.dumps({"hooks": {
        "SessionStart": [{"hooks": [{"type": "command", "command": legacy}]}],
        "PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "keep-me"}]}],
    }, "env": {"OTHER": "1"}}))
    vault = tmp_path / "vault"
    host_config.configure_claude(vault, settings=settings)
    assert host_config.configure_claude(vault, settings=settings) is False
    data = json.loads(settings.read_text())
    assert "SessionStart" not in data["hooks"]
    assert data["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "keep-me"
    assert data["permissions"]["additionalDirectories"] == [str(vault)]
    assert data["env"] == {"OTHER": "1", "OBSIDIAN_VAULT_PATH": str(vault)}


# ---------------------------------------------------------------- bootstrap

def test_bootstrap_creates_layout_and_valid_owner_note(tmp_path):
    import bootstrap_vault

    vault = tmp_path / "Brain"
    created = bootstrap_vault.bootstrap(vault, "홍길동", "에이씨미", "CTO", "ko")
    for folder in ("raw/videos", "wiki/entities", "wiki/reviews", "Logs"):
        assert (vault / folder).is_dir()
    assert "wiki/entities/홍길동.md" in created
    profile = json.loads((vault / ".osb" / "profile.json").read_text(encoding="utf-8"))
    assert profile["company"] == "에이씨미" and profile["language"] == "ko"
    # Second run never overwrites.
    (vault / "wiki/entities/홍길동.md").write_text("edited", encoding="utf-8")
    bootstrap_vault.bootstrap(vault, "홍길동", "에이씨미", "CTO", "ko")
    assert (vault / "wiki/entities/홍길동.md").read_text(encoding="utf-8") == "edited"


# ---------------------------------------------------------------- validator hook

needs_jq = pytest.mark.skipif(not shutil.which("jq") or not shutil.which("bash"),
                              reason="validator needs bash and jq")


def _hook(payload: dict, vault: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "OBSIDIAN_VAULT_PATH": str(vault)}
    return subprocess.run(["bash", str(ROOT / "hooks" / "validate-ai-first.sh")],
                          input=json.dumps(payload), capture_output=True, text=True, env=env)


@needs_jq
def test_hook_validates_codex_apply_patch(tmp_path):
    v = tmp_path / "vault"
    (v / "wiki").mkdir(parents=True)
    (v / "wiki" / "bad.md").write_text("---\ntype: concept\n---\nno preamble\n", encoding="utf-8")
    (v / "wiki" / "좋은 노트.md").write_text(GOOD_NOTE, encoding="utf-8")
    patch = ("*** Begin Patch\n*** Add File: wiki/bad.md\n+x\n"
             "*** Update File: wiki/좋은 노트.md\n*** End Patch")
    r = _hook({"tool_name": "apply_patch", "cwd": str(v), "tool_input": {"command": patch}}, v)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert "bad.md" in out["hookSpecificOutput"]["additionalContext"]
    assert "좋은 노트" not in out["reason"]


@needs_jq
def test_hook_passes_good_korean_note_and_ignores_outside_vault(tmp_path):
    v = tmp_path / "vault"
    (v / "wiki").mkdir(parents=True)
    good = v / "wiki" / "좋은 노트.md"
    good.write_text(GOOD_NOTE, encoding="utf-8")
    r = _hook({"tool_name": "Write", "tool_input": {"file_path": str(good)}}, v)
    assert r.returncode == 0 and r.stdout.strip() == ""
    outside = tmp_path / "elsewhere.md"
    outside.write_text("no frontmatter", encoding="utf-8")
    r = _hook({"tool_name": "Write", "tool_input": {"file_path": str(outside)}}, v)
    assert r.returncode == 0 and r.stdout.strip() == ""


@needs_jq
def test_hook_skips_schema_files(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    for name in ("AGENTS.md", "CLAUDE.md", "index.md"):
        (v / name).write_text("# no frontmatter by design\n", encoding="utf-8")
        r = _hook({"tool_name": "Write", "tool_input": {"file_path": str(v / name)}}, v)
        assert r.stdout.strip() == "", name


# ---------------------------------------------------------------- installer

def test_installer_is_valid_bash_and_offers_both_hosts():
    script = ROOT / "scripts" / "quick-install.sh"
    if shutil.which("bash"):
        assert subprocess.run(["bash", "-n", str(script)]).returncode == 0
    text = script.read_text(encoding="utf-8")
    for needle in ("Claude Code", "Codex", "$HOME/Documents", "bootstrap_vault.py",
                   "obsidian-init", "requirements.txt"):
        assert needle in text


# ---------------------------------------------------------------- review fixes

def test_codex_merge_never_moves_or_rematches_foreign_hooks():
    legacy = {"type": "command", "command": "/x/obsidian-second-brain/hooks/load_vault_context.sh"}
    old_val = {"type": "command", "command": 'bash "/old/hooks/validate-ai-first.sh"'}
    foreign = {"type": "command", "command": "foreign"}
    hooks = {
        "SessionStart": [{"hooks": [legacy]}, {"hooks": [dict(foreign)]}],
        "PostToolUse": [
            {"matcher": "Write", "hooks": [dict(old_val), dict(foreign)]},
            {"matcher": "Bash", "hooks": [dict(foreign)]},
        ],
    }
    notes = host_config.merge_hooks_positional(hooks, "Write|Edit|apply_patch")
    # Nothing removed or moved; the legacy entry is reported, not deleted.
    assert hooks["SessionStart"][0]["hooks"] == [legacy]
    assert hooks["SessionStart"][1]["hooks"] == [foreign]
    assert any("legacy" in n for n in notes)
    mixed = hooks["PostToolUse"][0]
    assert mixed["matcher"] == "Write", "a shared group's matcher must not change"
    assert str(host_config.VALIDATOR) in mixed["hooks"][0]["command"]
    assert mixed["hooks"][1] == foreign
    assert len(hooks["PostToolUse"]) == 2, "no new group when a validator already exists"


def test_codex_merge_rematches_only_our_own_group():
    old_val = {"type": "command", "command": 'bash "/old/hooks/validate-ai-first.sh"'}
    hooks = {"PostToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "f"}]},
                             {"matcher": "Write", "hooks": [old_val]}]}
    host_config.merge_hooks_positional(hooks, "Write|Edit|apply_patch")
    assert hooks["PostToolUse"][0]["hooks"][0]["command"] == "f"
    assert hooks["PostToolUse"][1]["matcher"] == "Write|Edit|apply_patch"


def test_indented_codex_keys_are_updated_not_duplicated(tmp_path):
    text = '[sandbox_workspace_write]\n  writable_roots = ["/a"]\n  network_access = false\n'
    out = host_config.update_codex_toml(text, tmp_path)
    host_config._verify_codex_toml(out, tmp_path, tmp_path / "config.toml")
    assert out.count("writable_roots") == 1 and out.count("network_access") == 1


def test_unusual_codex_toml_is_refused_not_broken(tmp_path):
    codex = tmp_path / ".codex"
    codex.mkdir()
    original = "sandbox_workspace_write.network_access = false\n"
    (codex / "config.toml").write_text(original, encoding="utf-8")
    with pytest.raises(SystemExit):
        host_config.configure_codex(tmp_path / "v", codex_home=codex)
    assert (codex / "config.toml").read_text(encoding="utf-8") == original


def test_codex_home_env_is_honored(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "ch"))
    assert host_config.codex_home_dir() == tmp_path / "ch"


@needs_jq
def test_hook_resolves_parent_relative_patch_paths(tmp_path):
    v = tmp_path / "vault"
    proj = tmp_path / "project"
    (v / "wiki").mkdir(parents=True)
    proj.mkdir()
    (v / "wiki" / "bad.md").write_text("---\ntype: concept\n---\nx\n", encoding="utf-8")
    patch = "*** Begin Patch\n*** Update File: ../vault/wiki/bad.md\n*** End Patch"
    r = _hook({"tool_name": "apply_patch", "cwd": str(proj), "tool_input": {"command": patch}}, v)
    assert "bad.md" in json.loads(r.stdout)["reason"]
