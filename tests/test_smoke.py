"""Smoke tests for the two highest-risk subsystems: the adapter build pipeline
and the vault health checker. Both run the real scripts via subprocess. CI
installs only the small dependency list in .github/workflows/ci.yml (pytest,
requests, pyyaml, python-dotenv) - keep that list in sync with what these
tests exercise.

Adapted from the test added by the bmassenz fork (the only fork that shipped
any automated test). See FORK_INSIGHTS.md items #47/#48.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _json_from_stdout(stdout: str) -> dict:
    """vault_health.py prints a couple of human-readable lines before the JSON
    payload even in --json mode. Scan for the first line that opens the object."""
    lines = stdout.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "{":
            return json.loads("\n".join(lines[index:]))
    raise AssertionError(f"JSON payload not found in stdout:\n{stdout}")


def test_codex_cli_build_generates_expected_files():
    """The codex-cli adapter must emit the AGENTS.md manual and one native Codex
    Agent Skill per command (.agents/skills/<name>/SKILL.md). This guards the
    adapter pipeline that every command change depends on."""
    result = subprocess.run(
        ["bash", "scripts/build.sh", "--platform", "codex-cli"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, result.stderr
    assert (REPO_ROOT / "dist/codex-cli/AGENTS.md").is_file()
    skill = REPO_ROOT / "dist/codex-cli/.agents/skills/obsidian-save/SKILL.md"
    assert skill.is_file()
    # Native skills require discovery frontmatter plus the complete command body.
    content = skill.read_text(encoding="utf-8")
    head = content[:400]
    assert "name: obsidian-save" in head
    assert "description:" in head
    assert "Triggers: save this" in head
    assert "Use the obsidian-second-brain skill. Execute `/obsidian-save`:" in content
    # Calendar depends on a Claude-only MCP and is explicitly excluded from Codex.
    assert not (REPO_ROOT / "dist/codex-cli/.agents/skills/obsidian-calendar").exists()


def test_hermes_build_generates_native_skills():
    """The hermes adapter must emit one native Hermes skill per command at
    skills/<category>/<name>/SKILL.md, with the required frontmatter Hermes
    needs to load it (name, description, version, author, license)."""
    result = subprocess.run(
        ["bash", "scripts/build.sh", "--platform", "hermes"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, result.stderr
    skill = REPO_ROOT / "dist/hermes/skills/vault/obsidian-save/SKILL.md"
    assert skill.is_file()
    head = skill.read_text(encoding="utf-8")[:500]
    for field in ("name: obsidian-save", "description:", "version:", "author:", "license:"):
        assert field in head, field
    # Calendar/scheduled commands are Claude-only and must not leak to Hermes.
    assert not (REPO_ROOT / "dist/hermes/skills/vault/obsidian-calendar").exists()

    # Scheduled agents emit as opt-in blueprint skills under optional-skills/
    # (not auto-armed skills/), each carrying a cron schedule.
    nightly = REPO_ROOT / "dist/hermes/optional-skills/obsidian-nightly/SKILL.md"
    assert nightly.is_file()
    blueprint = nightly.read_text(encoding="utf-8")
    assert "blueprint:" in blueprint
    assert 'schedule: "0 22 * * *"' in blueprint
    # The opt-in arming surface, not the auto-loaded one.
    assert not (REPO_ROOT / "dist/hermes/skills/scheduled").exists()
    hooks_doc = REPO_ROOT / "dist/hermes/HOOKS.md"
    assert hooks_doc.is_file()
    # The on_session_end lifecycle hook (PostCompact analog) and its config ship.
    assert (REPO_ROOT / "dist/hermes/hooks/obsidian-hermes-session-end.sh").is_file()
    assert (REPO_ROOT / "dist/hermes/hooks/hermes-hooks.config.example.yaml").is_file()
    hooks_text = hooks_doc.read_text(encoding="utf-8")
    assert "on_session_end" in hooks_text
    # Blueprints never arm on install (#134): the docs must teach explicit arming.
    assert "hermes cron create" in hooks_text
    assert "arms as soon as" not in hooks_text
    install_text = (REPO_ROOT / "dist/hermes/INSTALL.md").read_text(encoding="utf-8")
    assert "~/.hermes/optional-skills" not in install_text
    assert "hermes cron create" in install_text


def test_pi_build_generates_package():
    """The pi adapter must emit a valid Pi package: package.json with pi
    prompts/skills entries, prompt templates with frontmatter, and a discovery
    skill with valid Agent Skills frontmatter."""
    result = subprocess.run(
        ["bash", "scripts/build.sh", "--platform", "pi"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, result.stderr

    package_json = REPO_ROOT / "dist/pi/package.json"
    assert package_json.is_file()
    manifest = json.loads(package_json.read_text(encoding="utf-8"))
    assert manifest["name"] == "obsidian-second-brain-pi"
    assert ".pi/prompts" in manifest.get("pi", {}).get("prompts", [])
    assert ".pi/skills" in manifest.get("pi", {}).get("skills", [])

    prompt = REPO_ROOT / "dist/pi/.pi/prompts/obsidian-save.md"
    assert prompt.is_file()
    head = prompt.read_text(encoding="utf-8")[:300]
    assert "---" in head
    assert "description:" in head

    skill = REPO_ROOT / "dist/pi/.pi/skills/obsidian-second-brain/SKILL.md"
    assert skill.is_file()
    skill_head = skill.read_text(encoding="utf-8")[:400]
    assert "name: obsidian-second-brain" in skill_head
    assert "description:" in skill_head

    # Paths should be rewritten for the Pi layout, not left pointing at Claude.
    prompt_body = prompt.read_text(encoding="utf-8")
    assert "~/.claude/skills/obsidian-second-brain" not in prompt_body
    assert ".pi/skills/obsidian-second-brain" in prompt_body


def test_agent_skills_build_generates_spec_compliant_tree():
    """The agent-skills adapter must emit one spec-compliant Agent Skills tree
    that Antigravity / Codex CLI / OpenCode all read from `.agents/skills/`:
    skills/<name>/SKILL.md per command plus the shared obsidian-core engine
    skill, with NO root SKILL.md (which would shadow the nested skills)."""
    result = subprocess.run(
        ["bash", "scripts/build.sh", "--platform", "agent-skills"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, result.stderr

    skills_dir = REPO_ROOT / "dist/agent-skills/skills"
    assert skills_dir.is_dir()
    # A root SKILL.md shadows every nested skill in skills.sh discovery.
    assert not (REPO_ROOT / "dist/agent-skills/SKILL.md").exists()

    # A command skill: spec-minimal frontmatter, self-sufficiency preamble, the
    # full command body, and the embedded write spec.
    save = skills_dir / "obsidian-save/SKILL.md"
    assert save.is_file()
    save_text = save.read_text(encoding="utf-8")
    head = save_text[:600]
    assert "name: obsidian-save" in head
    assert "description:" in head
    assert "Triggers: save this" in head
    # Capture-type commands carry the proactive selection policy.
    assert "Use proactively" in head
    assert "$OBSIDIAN_VAULT_PATH" in save_text
    assert "Use the obsidian-second-brain skill. Execute `/obsidian-save`:" in save_text
    assert "## AI-first vault rule (embedded)" in save_text
    assert "## For future Claude" in save_text

    # Non-capture commands get the explicit-only policy, not the proactive one.
    research = (skills_dir / "research/SKILL.md").read_text(encoding="utf-8")
    assert "Use only when the user explicitly asks" in research
    assert "Use proactively" not in research
    # SKILL_ROOT is rewritten to the installed obsidian-core location.
    assert "SKILL_ROOT" not in research
    assert 'uv run --directory ".agents/skills/obsidian-core"' in research

    # The shared engine skill ships references, scripts, and its uv project.
    core = skills_dir / "obsidian-core"
    assert (core / "SKILL.md").is_file()
    assert (core / "pyproject.toml").is_file()
    assert (core / "references/ai-first-rules.md").is_file()
    assert (core / "scripts").is_dir()

    # Calendar depends on a Claude-only MCP and is excluded from this build.
    assert not (skills_dir / "obsidian-calendar").exists()

    # Install docs cover both the skills.sh path and the manual fallback.
    install_text = (REPO_ROOT / "dist/agent-skills/INSTALL.md").read_text(encoding="utf-8")
    assert "npx skills add" in install_text
    assert "cp -R dist/agent-skills/skills/." in install_text
    assert (REPO_ROOT / "dist/agent-skills/global-rule-snippet.md").is_file()


def test_vault_health_json_reports_clean_linked_vault(tmp_path):
    """A minimal two-note vault with reciprocal wikilinks should report zero
    issues: no orphans, no broken links, no missing frontmatter."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Home.md").write_text(
        "# Home\n\nSee [[Project Alpha]].\n",
        encoding="utf-8",
    )
    (vault / "Project Alpha.md").write_text(
        "---\n"
        "type: project\n"
        "aliases:\n"
        "  - Project Alpha\n"
        "---\n"
        "# Project Alpha\n\nBack to [[Home]].\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "scripts/vault_health.py", "--path", str(vault), "--json"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = _json_from_stdout(result.stdout)
    assert payload["total_notes"] == 2
    assert payload["total_issues"] == 0
    assert payload["counts"]["Wanted notes"] == 0
    assert payload["counts"]["Orphans"] == 0


def test_substitution_check_passes_on_repo():
    """The repo source must be free of banned substitution characters in prose
    (the CI gate). Characters inside code fences/spans are allowed."""
    result = subprocess.run(
        [sys.executable, "scripts/sweep_non_ascii.py", "--check"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_substitution_check_flags_prose_em_dash(tmp_path):
    """--check must fail (exit 1) when a banned character appears in prose, and
    must NOT fail when it only appears inside an inline code span."""
    # Build the em-dash from its code point so this test's own source stays
    # ASCII (the CI gate scans .py files too); the written fixtures get the
    # real character.
    em = "\u2014"
    bad = tmp_path / "bad.md"
    bad.write_text(f"A prose line with an em{em}dash.\n", encoding="utf-8")
    flagged = subprocess.run(
        [sys.executable, "scripts/sweep_non_ascii.py", "--check", str(bad)],
        cwd=REPO_ROOT, check=False, capture_output=True, text=True,
    )
    assert flagged.returncode == 1, flagged.stdout

    ok = tmp_path / "ok.md"
    ok.write_text(f"A filename in code: `2026-01-01 {em} note.md` is fine.\n", encoding="utf-8")
    passed = subprocess.run(
        [sys.executable, "scripts/sweep_non_ascii.py", "--check", str(ok)],
        cwd=REPO_ROOT, check=False, capture_output=True, text=True,
    )
    assert passed.returncode == 0, passed.stdout


def test_health_normalizes_dashes_in_links(tmp_path):
    """Regression for #63: a wikilink written with a regular hyphen must resolve
    against a filename written with an em-dash (the #31 behavior). The non-ASCII
    sweep once rewrote _normalize_dashes()'s operands into ASCII hyphens, turning
    it into a no-op; this locks the behavior so an automated pass cannot silently
    undo it again. Em-dash built from its code point so this source stays ASCII."""
    em = "\u2014"
    (tmp_path / f"2026-05-22 {em} Learnings Review.md").write_text(
        "---\ntype: concept\n---\n# Learnings Review\n\nBack to [[Home]].\n",
        encoding="utf-8",
    )
    (tmp_path / "Home.md").write_text(
        "# Home\n\nSee [[2026-05-22 - Learnings Review]].\n", encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, "scripts/vault_health.py", "--path", str(tmp_path), "--json"],
        cwd=REPO_ROOT, check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"wanted_note"' not in result.stdout, (
        "hyphen-written link to em-dash filename was counted as a wanted note:\n" + result.stdout
    )


def _run_health_json(tmp_path):
    """Run vault_health.py --json and return the parsed result (skips the stdout header)."""
    result = subprocess.run(
        [sys.executable, "scripts/vault_health.py", "--path", str(tmp_path), "--json"],
        cwd=REPO_ROOT, check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout[result.stdout.index("{"):])


def test_health_duplicates_exempt_dated_series(tmp_path):
    """Issue #82: dated-series notes that share a descriptive title (a weekly
    review every Friday) must NOT be flagged as duplicates, but two genuinely
    same-named notes in normal folders still are."""
    reviews = tmp_path / "Reviews"
    reviews.mkdir()
    for d in ("2026-06-19", "2026-06-26"):
        (reviews / f"{d} - Weekly Review.md").write_text(
            f"---\ntype: review\n---\n# Weekly Review\nWeek of {d}.\n", encoding="utf-8"
        )
    # A real cross-folder duplicate with near-identical content.
    (tmp_path / "A").mkdir()
    (tmp_path / "B").mkdir()
    body = "---\ntype: note\n---\n# Onboarding\nStep one, step two, step three.\n"
    (tmp_path / "A" / "Onboarding.md").write_text(body, encoding="utf-8")
    (tmp_path / "B" / "Onboarding.md").write_text(body, encoding="utf-8")

    data = _run_health_json(tmp_path)
    dup_msgs = [i["message"] for i in data["issues"] if i["type"] == "duplicate"]
    assert not any("weekly review" in m.lower() for m in dup_msgs), dup_msgs
    assert any("onboarding" in m.lower() for m in dup_msgs), dup_msgs


def test_health_excludes_export_bundle(tmp_path):
    """Issue #82 follow-up: the OKF export bundle (_export/) is a full copy of the
    vault, so scanning it made every note a duplicate of its export twin. _export
    must be excluded - the note and its copy should not be flagged or counted."""
    (tmp_path / "wiki").mkdir()
    (tmp_path / "_export" / "okf" / "wiki").mkdir(parents=True)
    body = "---\ntype: note\n---\n# Spec\nThe spec body.\n"
    (tmp_path / "wiki" / "Spec.md").write_text(body, encoding="utf-8")
    (tmp_path / "_export" / "okf" / "wiki" / "Spec.md").write_text(body, encoding="utf-8")

    data = _run_health_json(tmp_path)
    assert data["total_notes"] == 1, data["total_notes"]
    assert not [i for i in data["issues"] if i["type"] == "duplicate"]


def test_health_excludes_codex_support_directories(tmp_path):
    """Generated Codex skills and references are runtime support files, not vault
    notes. Scanning them pollutes every health metric with duplicate/orphan noise."""
    (tmp_path / ".agents" / "skills" / "demo").mkdir(parents=True)
    (tmp_path / ".codex" / "references").mkdir(parents=True)
    (tmp_path / "Templates").mkdir()
    (tmp_path / ".agents" / "skills" / "demo" / "SKILL.md").write_text(
        "# Demo skill\n\nUse [[Missing Skill Example]].\n", encoding="utf-8"
    )
    (tmp_path / ".codex" / "references" / "Rules.md").write_text(
        "# Rules\n\nUse [[Missing Reference Example]].\n", encoding="utf-8"
    )
    (tmp_path / "AGENTS.md").write_text("# Runtime manual\n", encoding="utf-8")
    (tmp_path / "INSTALL.md").write_text("# Install hint\n", encoding="utf-8")
    (tmp_path / "Templates" / "Daily Note.md").write_text(
        "# Daily template\n", encoding="utf-8"
    )
    (tmp_path / "Home.md").write_text(
        "---\ndate: 2026-07-10\ntype: home\ntags: [home]\nai-first: true\n---\n"
        "## For future Claude\nThis is the test vault home.\n\n"
        "# Home\n\nUse [[Templates/Daily Note]].\n",
        encoding="utf-8",
    )

    data = _run_health_json(tmp_path)
    assert data["total_notes"] == 1, data["total_notes"]
    assert data["counts"]["Wanted notes"] == 0, data["issues"]


def test_health_wanted_notes_ignore_code_examples(tmp_path):
    """Issue #82: example wikilinks inside code fences / inline code must not be
    counted; a real link to an unwritten note still is (reported as a wanted note)."""
    (tmp_path / "Doc.md").write_text(
        "---\ntype: note\n---\n# Doc\n\n"
        "Use a link like ```\n[[Related Project]]\n``` or inline `[[Placeholder]]`.\n\n"
        "But this real one dangles: [[Nonexistent Target]].\n",
        encoding="utf-8",
    )
    data = _run_health_json(tmp_path)
    wanted = [i["message"] for i in data["issues"] if i["type"] == "wanted_note"]
    assert any("Nonexistent Target" in m for m in wanted), wanted
    assert not any("Related Project" in m or "Placeholder" in m for m in wanted), wanted


def test_health_resolves_asset_links_and_md_extension_links(tmp_path):
    """Links to non-markdown vault files ([[Bases/Tasks.base]], [[map.canvas]]) and
    links written with an explicit .md extension ([[Guide.md]]) must resolve rather
    than be counted as wanted notes, and vendored agent docs under .claude/ must be
    excluded from the scan entirely."""
    (tmp_path / "Bases").mkdir()
    (tmp_path / "Bases" / "Tasks.base").write_text("views: []\n", encoding="utf-8")
    (tmp_path / "map.canvas").write_text("{}\n", encoding="utf-8")
    (tmp_path / "Home.md").write_text(
        "# Home\n\nSee [[Bases/Tasks.base]], [[map.canvas]], and [[Guide.md]].\n",
        encoding="utf-8",
    )
    (tmp_path / "Guide.md").write_text(
        "---\ntype: note\n---\n# Guide\n\nBack to [[Home]].\n", encoding="utf-8"
    )
    skills = tmp_path / ".claude" / "skills" / "demo"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "# Demo skill\n\nUse [[Note Name]] and embed [[image.png]].\n", encoding="utf-8"
    )

    data = _run_health_json(tmp_path)
    assert data["total_notes"] == 2, data["total_notes"]  # .claude/ docs are not vault notes
    assert data["counts"]["Wanted notes"] == 0, data["issues"]
    # Guide.md is linked from Home via [[Guide.md]]; the extension must not hide it.
    assert data["counts"]["Orphans"] == 0, data["issues"]


def _load_vault_ops():
    """Import the MCP connector's vault_ops module (pure stdlib, no mcp dep)."""
    import importlib

    mod_dir = REPO_ROOT / "integrations" / "obsidian-mcp-server"
    sys.path.insert(0, str(mod_dir))
    try:
        return importlib.import_module("vault_ops")
    finally:
        sys.path.remove(str(mod_dir))


def test_mcp_vault_ops_save_read_search_roundtrip(tmp_path, monkeypatch):
    """The MCP connector's core data tools must round-trip against a real vault:
    save_note writes an AI-first note (frontmatter + preamble + source: mcp marker)
    to Inbox/, read_note returns it, search finds it. Pure stdlib path - exercises
    the logic the MCP server wraps without needing the mcp package."""
    vault_ops = _load_vault_ops()
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))

    saved = vault_ops.save_note(
        "Hermes connector test",
        "A note about the Hermes agent reading the vault over MCP.",
        note_type="note",
        tags=["mcp", "hermes"],
    )
    rel = saved["saved"]
    assert rel.startswith("Inbox/")

    note = (vault / rel).read_text(encoding="utf-8")
    assert "ai-first: true" in note
    assert "source: mcp" in note
    assert "## For future Claude" in note

    read_back = vault_ops.read_note(rel)
    assert "Hermes agent" in read_back["content"]

    hits = vault_ops.search("hermes", limit=5)
    assert any(h["path"] == rel for h in hits)


def test_mcp_vault_ops_search_ranks_title_over_noise(tmp_path, monkeypatch):
    """Search ranking regression guard (retrieval-eval fixes): a short note with the
    term in its title must outrank a long note that merely repeats it, and stopwords
    must not let a long note win on filler. Locks the stopword + sublinear-TF +
    length-normalization behavior so it cannot silently regress."""
    vault_ops = _load_vault_ops()
    vault = tmp_path / "vault"
    (vault / "wiki").mkdir(parents=True)
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))

    # The canonical answer: short, term in the title.
    (vault / "wiki" / "Velo Migration.md").write_text(
        "---\ntype: project\n---\nThe Velo migration plan.\n", encoding="utf-8"
    )
    # A long, noisy note that repeats the term and is full of stopwords.
    noise = ("What is the status of the work that we did and the things " * 80) + ("velo " * 20)
    (vault / "wiki" / "Standup Log.md").write_text(
        "---\ntype: meeting\n---\n" + noise, encoding="utf-8"
    )

    hits = vault_ops.search("what is the status of the velo migration", limit=5)
    assert hits, "search returned nothing"
    assert hits[0]["path"] == "wiki/Velo Migration.md", (
        "short title-matching note should rank first, not the long noisy note: "
        + ", ".join(h["path"] for h in hits)
    )


def test_link_graph_builds_nodes_edges_and_orphans(tmp_path):
    """link_graph.py must resolve [[wikilinks]] to real notes, count degree, flag
    orphans, and report dangling links - the data /obsidian-visualize relies on."""
    vault = tmp_path / "vault"
    (vault / "wiki").mkdir(parents=True)
    (vault / "wiki" / "Hub.md").write_text(
        "---\ntype: project\n---\nLinks to [[Leaf]] and [[Missing Note]].\n", encoding="utf-8"
    )
    (vault / "wiki" / "Leaf.md").write_text(
        "---\ntype: concept\n---\nBack to [[Hub]].\n", encoding="utf-8"
    )
    (vault / "wiki" / "Orphan.md").write_text(
        "---\ntype: note\n---\nNo links here. `[[NotCounted]]` is in code.\n", encoding="utf-8"
    )
    out = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/link_graph.py"), "--path", str(vault)],
        capture_output=True, text=True, check=True,
    )
    graph = json.loads(out.stdout)
    stats = graph["stats"]
    assert stats["node_count"] == 3
    # Hub<->Leaf is one edge each way; the [[Missing Note]] is dangling, not an edge;
    # the code-fenced [[NotCounted]] must not count.
    assert stats["edge_count"] == 2
    assert stats["dangling_link_count"] == 1
    assert "wiki/Orphan.md" in stats["orphans"]
    assert graph["stats"]["top_hubs"][0]["title"] in {"Hub", "Leaf"}


def test_semantic_search_math_and_carveout(monkeypatch):
    """Semantic layer's stdlib math is correct without needing a model: cosine
    behaves, hybrid RRF lifts a note strong in BOTH rankings, and the privacy
    carve-out excludes configured path prefixes."""
    import importlib
    sys.path.insert(0, str(REPO_ROOT / "scripts/eval"))
    monkeypatch.setenv("OBSIDIAN_EMBED_EXCLUDE", "wiki/private/,Faith")
    ss = importlib.reload(importlib.import_module("semantic_search"))

    assert ss.cosine([1, 2, 3], [1, 2, 3]) == 1.0
    assert ss.cosine([1, 0], [0, 1]) == 0.0
    assert round(ss.cosine([1, 0], [-1, 0]), 3) == -1.0

    # carve-out: configured prefixes never get embedded
    assert ss._excluded("wiki/private/diary.md")
    assert ss._excluded("Faith/prayer.md")
    assert not ss._excluded("wiki/projects/Codru.md")

    # hybrid RRF: a note present in both rankings outranks one present in only one
    monkeypatch.setattr(ss, "semantic_search",
                        lambda q, idx, limit=10: [{"path": "both", "title": "both", "score": .9},
                                                  {"path": "sem_only", "title": "s", "score": .7}])
    lexical = [{"path": "both", "title": "both"}, {"path": "lex_only", "title": "l"}]
    fused = ss.hybrid_search("q", {"notes": {}}, lexical, limit=3)
    assert fused[0]["path"] == "both", [f["path"] for f in fused]


def test_mcp_vault_ops_hybrid_fusion_and_fallback(tmp_path, monkeypatch):
    """When a semantic index + reachable model exist, search fuses lexical with
    semantic (a meaning-only match surfaces). When the model call fails, search
    silently falls back to pure lexical - it must never break."""
    import json as _json
    vault_ops = _load_vault_ops()
    vault = tmp_path / "vault"
    (vault / "wiki").mkdir(parents=True)
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))
    # A note that shares NO query words - only meaning-search could surface it.
    (vault / "wiki" / "Valencia basis.md").write_text(
        "---\ntype: note\n---\nBased in Valencia, CET.\n", encoding="utf-8"
    )
    (vault / "wiki" / "Other.md").write_text("---\ntype: note\n---\nUnrelated.\n", encoding="utf-8")
    # Fake index: the Valencia note's vector points the same way as our stub query vector.
    index = {"model": "test", "notes": {
        "wiki/Valencia basis.md": {"hash": "x", "title": "Valencia basis", "vec": [1.0, 0.0]},
        "wiki/Other.md": {"hash": "y", "title": "Other", "vec": [0.0, 1.0]},
    }}
    (vault / vault_ops._SEMANTIC_INDEX_FILE).write_text(_json.dumps(index), encoding="utf-8")

    monkeypatch.setattr(vault_ops, "_embed_query", lambda q: [1.0, 0.0])
    hits = vault_ops.search("where am I based", limit=5)
    assert any(h["path"] == "wiki/Valencia basis.md" for h in hits), \
        "semantic match should surface via fusion: " + ", ".join(h["path"] for h in hits)

    # Model unreachable -> fallback to lexical, no exception.
    def _boom(q):
        raise RuntimeError("ollama down")
    monkeypatch.setattr(vault_ops, "_embed_query", _boom)
    assert vault_ops.search("Valencia", limit=5)  # still returns lexical hits, no crash


def test_mcp_vault_ops_read_guards_path_escape(tmp_path, monkeypatch):
    """read_note must refuse paths that escape the vault root."""
    vault_ops = _load_vault_ops()
    vault = tmp_path / "vault"
    vault.mkdir()
    (tmp_path / "secret.md").write_text("outside the vault\n", encoding="utf-8")
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))

    assert vault_ops.read_note("../secret.md").get("error")


def test_mcp_vault_ops_skills_exclude_niche(monkeypatch):
    """list_skills exposes the real commands but never the niche/agent-only ones,
    and get_skill blocks the excluded set (the #60 contract)."""
    vault_ops = _load_vault_ops()
    names = {s["name"] for s in vault_ops.list_skills()}
    assert "obsidian-save" in names
    assert names.isdisjoint({"obsidian-health", "obsidian-challenge", "create-command"})
    assert vault_ops.get_skill("obsidian-health").get("error")
    assert "instructions" in vault_ops.get_skill("obsidian-save")


def test_mcp_vault_ops_get_skill_rejects_path_traversal(monkeypatch):
    """get_skill must reject names that are not flat slugs, so a crafted name
    cannot escape the commands/ dir via path traversal (lstrip('/') alone does
    not remove '..' segments)."""
    vault_ops = _load_vault_ops()
    for bad in ("../../etc/passwd", "foo/bar", "a.b", "../obsidian-save", "with space"):
        res = vault_ops.get_skill(bad)
        assert res.get("error"), f"expected error for {bad!r}"
        assert "instructions" not in res
    # a legitimate flat slug still resolves
    assert "instructions" in vault_ops.get_skill("obsidian-save")


def test_mcp_vault_ops_update_note_guarded_edit(tmp_path, monkeypatch):
    """update_note appends a section and merges scalar frontmatter on an existing
    note, preserves the tags block, stamps `updated`, and refuses a path escape
    and a non-existent note (curator-mode guards, #79)."""
    vault_ops = _load_vault_ops()
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))
    note = vault / "Project Alpha.md"
    note.write_text(
        "---\ntype: project\nstatus: active\ntags:\n  - work\nai-first: true\n---\n\n"
        "## For future Claude\nAlpha.\n",
        encoding="utf-8",
    )

    res = vault_ops.update_note(
        "Project Alpha.md",
        append="Shipped the adapter.",
        heading="Update",
        set_fields={"status": "done"},
    )
    assert res.get("updated") == "Project Alpha.md"
    text = note.read_text(encoding="utf-8")
    assert "status: done" in text and "status: active" not in text
    assert "updated:" in text
    assert "## Update" in text and "Shipped the adapter." in text
    assert "  - work" in text  # list frontmatter preserved verbatim

    # Guards: never create, never escape.
    assert vault_ops.update_note("Nope.md", append="x").get("error")
    assert vault_ops.update_note("../escape.md", append="x").get("error")


def test_mcp_vault_ops_validate_and_backlinks_and_health(tmp_path, monkeypatch):
    """validate_note flags a missing preamble + unresolved wikilink; backlinks
    finds the referencing note; vault_health reports the wanted note."""
    vault_ops = _load_vault_ops()
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))
    (vault / "Home.md").write_text(
        "---\ntype: note\ndate: 2026-06-27\ntags:\n  - x\nai-first: true\n---\n\n"
        "## For future Claude\nSee [[Project Alpha]] and [[Ghost Note]].\n",
        encoding="utf-8",
    )
    (vault / "Project Alpha.md").write_text(
        "---\ntype: project\n---\n# Alpha\n",
        encoding="utf-8",
    )

    v = vault_ops.validate_note("Project Alpha.md")
    assert v["ok"] is False
    joined = " ".join(v["issues"])
    assert "For future Claude" in joined
    assert "date" in joined  # missing required key

    bl = vault_ops.backlinks("Project Alpha")
    assert "Home.md" in bl["backlinks"]

    health = vault_ops.vault_health()
    assert any(b["link"] == "Ghost Note" for b in health["wanted_notes"]["sample"])


def test_mcp_vault_ops_skips_claude_dir(tmp_path, monkeypatch):
    """The MCP connector must not scan a vault-local .claude/ config dir as notes
    (issue #80). search and vault_health should ignore it entirely."""
    vault_ops = _load_vault_ops()
    vault = tmp_path / "vault"
    (vault / "wiki").mkdir(parents=True)
    (vault / ".claude" / "commands").mkdir(parents=True)
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))
    (vault / "wiki" / "Real.md").write_text("---\ntype: note\n---\nwidget content\n", encoding="utf-8")
    (vault / ".claude" / "CLAUDE.md").write_text("widget config\n", encoding="utf-8")
    (vault / ".claude" / "commands" / "save.md").write_text("widget command\n", encoding="utf-8")

    hits = {h["path"] for h in vault_ops.search("widget", limit=10)}
    assert "wiki/Real.md" in hits
    assert not any(p.startswith(".claude") for p in hits)
    assert vault_ops.vault_health()["notes_scanned"] == 1


def test_architect_scan_emits_manifest(tmp_path):
    """architect_scan.py must produce a JSON manifest with the expected shape
    on a minimal project (no network, no install)."""
    proj = tmp_path / "proj"
    (proj / "src" / "billing").mkdir(parents=True)
    (proj / "src" / "billing" / "charge.py").write_text("def charge():\n    pass\n", encoding="utf-8")
    (proj / "pyproject.toml").write_text(
        '[project]\nname = "paymentbot"\ndependencies = ["requests"]\n', encoding="utf-8"
    )

    result = subprocess.run(
        [sys.executable, "scripts/architect_scan.py", "--path", str(proj)],
        cwd=REPO_ROOT, check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    data = _json_from_stdout(result.stdout)
    assert data["name"] == "paymentbot"
    assert data["kind"] == "python"
    assert any(m["name"] == "billing" for m in data["modules"])
    assert "requests" in data["dependencies"]
    assert any(lang["language"] == "Python" for lang in data["languages"])


_RESEARCH_MODE_PROBE = """
import importlib
import sys

mod = importlib.import_module(sys.argv[1])
setattr(mod, sys.argv[2], lambda *a, **k: print("CHOSE=paid") or 0)
setattr(mod, sys.argv[3], lambda *a, **k: print("CHOSE=free") or 0)
sys.exit(mod.main(["prog", "smoke test topic"]))
"""


@pytest.mark.parametrize(
    ("module", "paid_fn", "free_fn"),
    [
        ("scripts.research.research", "run_paid", "run_free"),
        ("scripts.research.research_deep", "run_paid_deep", "run_free_deep"),
    ],
)
def test_research_key_in_config_env_selects_paid_mode(tmp_path, module, paid_fn, free_fn):
    """A PERPLEXITY_API_KEY set only in ~/.config/obsidian-second-brain/.env (the
    documented setup) must select paid mode, and no key anywhere must keep the
    zero-config free mode. Regression fence for #124: the free-vs-paid decision
    read os.environ before anything had loaded the .env file, so paid-mode users
    silently got the free pipeline."""
    fake_home = tmp_path / "home"
    config_dir = fake_home / ".config" / "obsidian-second-brain"
    config_dir.mkdir(parents=True)
    vault = tmp_path / "vault"
    vault.mkdir()

    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env.pop("PERPLEXITY_API_KEY", None)
    env.pop("OBSIDIAN_VAULT_PATH", None)

    def chosen_mode(env_file: str) -> str:
        (config_dir / ".env").write_text(env_file, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-c", _RESEARCH_MODE_PROBE, module, paid_fn, free_fn],
            cwd=REPO_ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    # research_deep requires a vault path at import time; research ignores it.
    vault_line = f"OBSIDIAN_VAULT_PATH={vault}\n"
    assert "CHOSE=paid" in chosen_mode(vault_line + "PERPLEXITY_API_KEY=pplx-smoke-test-key\n")
    assert "CHOSE=free" in chosen_mode(vault_line)


def test_update_vault_integration_script_guards():
    """The updater must be syntactically valid and fail loudly on bad input
    (missing --vault, unknown platform) BEFORE touching anything. The full
    pull->build->gate->backup->install->rollback flow is exercised manually
    (it needs a clean repo + a real vault); these fences catch regressions in
    the argument and platform guards."""
    script = REPO_ROOT / "scripts/update-vault-integration.sh"
    assert script.is_file()

    syntax = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr

    no_vault = subprocess.run(["bash", str(script)], capture_output=True, text=True)
    assert no_vault.returncode != 0
    assert "--vault is required" in no_vault.stderr

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        bogus = subprocess.run(
            ["bash", str(script), "--vault", tmp, "--platform", "bogus"],
            capture_output=True, text=True,
        )
        assert bogus.returncode != 0
        assert "unknown platform" in bogus.stderr


def test_retrieval_eval_external_mode(tmp_path):
    """--mode external benchmarks any engine via RETRIEVAL_EVAL_EXTERNAL_CMD:
    the command gets the query as final argv and prints ranked paths (JSON
    array or lines). A fake always-right engine must score recall@1 = 1.0."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "real.md").write_text("# real\n", encoding="utf-8")

    cases = tmp_path / "cases.jsonl"
    cases.write_text('{"q": "test question", "gold": ["real.md"], "title": "real"}\n', encoding="utf-8")

    engine = tmp_path / "engine.sh"
    engine.write_text('#!/usr/bin/env bash\necho \'["real.md", "other.md"]\'\n', encoding="utf-8")
    engine.chmod(0o755)

    env = dict(os.environ,
               OBSIDIAN_VAULT_PATH=str(vault),
               RETRIEVAL_EVAL_EXTERNAL_CMD=f"bash {engine}")
    result = subprocess.run(
        [sys.executable, "scripts/eval/retrieval_eval.py",
         "--cases", str(cases), "--mode", "external", "--json"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout[result.stdout.find("{"):])
    assert payload["summary"]["recall_at"]["1"] == 1.0
    assert "external engine" in payload["summary"]["search"]

    # Without the env var, external mode must fail with a clear message.
    env.pop("RETRIEVAL_EVAL_EXTERNAL_CMD")
    missing = subprocess.run(
        [sys.executable, "scripts/eval/retrieval_eval.py",
         "--cases", str(cases), "--mode", "external"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
    )
    assert missing.returncode != 0
    assert "RETRIEVAL_EVAL_EXTERNAL_CMD" in missing.stderr


def test_mcp_search_supersedes_reverse_edge(tmp_path, monkeypatch):
    """When ADR A declares `supersedes: [[B]]`, B must rank below A even though
    B's own status was never updated (the reverse edge from fork-insights r2).
    Both notes match the query; without the edge, B (more term hits) wins."""
    vault_ops = _load_vault_ops()
    vault = tmp_path / "vault"
    (vault / "Knowledge").mkdir(parents=True)
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))

    # Old ADR: status still says accepted (the vault forgot to update it),
    # and it mentions the topic MORE, so pure lexical ranks it first.
    (vault / "Knowledge" / "ADR-1 caching strategy.md").write_text(
        "---\ntype: decision\nstatus: accepted\n---\n"
        "# ADR-1 caching strategy\n\ncaching strategy caching strategy caching layer choice.\n",
        encoding="utf-8",
    )
    # New ADR: declares it supersedes ADR-1.
    (vault / "Knowledge" / "ADR-2 caching strategy v2.md").write_text(
        '---\ntype: decision\nstatus: accepted\nsupersedes: "[[Knowledge/ADR-1 caching strategy]]"\n---\n'
        "# ADR-2 caching strategy v2\n\ncaching strategy: use the new layer.\n",
        encoding="utf-8",
    )

    results = vault_ops.search("caching strategy", limit=5)
    paths = [r["path"] for r in results]
    assert any("ADR-1" in p for p in paths) and any("ADR-2" in p for p in paths)
    assert paths.index(next(p for p in paths if "ADR-2" in p)) < \
           paths.index(next(p for p in paths if "ADR-1" in p)), paths
