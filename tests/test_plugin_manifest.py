"""CI fence for the Claude Code plugin-marketplace distribution.

The repo doubles as its own plugin marketplace: `.claude-plugin/marketplace.json`
is the catalog, `.claude-plugin/plugin.json` the plugin manifest, and
`hooks/hooks.json` the plugin hook wiring. These tests keep the three manifests
parseable, mutually consistent, version-synced with pyproject.toml, and honest
about the files they reference - so `/plugin install` never ships a broken tree.

Verified against a live local install (marketplace add + install + `claude mcp
list` shows the bundled server Connected) before this fence was written.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(relpath: str):
    return json.loads((REPO_ROOT / relpath).read_text(encoding="utf-8"))


def _pyproject_version() -> str:
    with (REPO_ROOT / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def test_plugin_manifest_parses_and_matches_pyproject_version():
    plugin = _load(".claude-plugin/plugin.json")
    assert plugin["name"] == "obsidian-second-brain"
    assert plugin["version"] == _pyproject_version()


def test_citation_cff_version_matches_pyproject():
    """CLAUDE.md's release process says this file fails CI if CITATION.cff
    drifts. It did not: nothing here opened that file, so a missed bump shipped
    a release whose Zenodo/DOI citation advertised the wrong version, and the
    only way to notice was to read it. A regex avoids adding a YAML dependency
    to the CI install list."""
    text = (REPO_ROOT / "CITATION.cff").read_text(encoding="utf-8")
    match = re.search(r'^version:\s*"?([^"\n]+)"?\s*$', text, re.MULTILINE)
    assert match, "CITATION.cff has no top-level version key"
    assert match.group(1).strip() == _pyproject_version()


def test_marketplace_metadata_version_matches_pyproject():
    """The marketplace has two version fields. Only the plugin entry was
    checked, so metadata.version could drift unnoticed."""
    market = _load(".claude-plugin/marketplace.json")
    assert market["metadata"]["version"] == _pyproject_version()


def test_marketplace_catalog_agrees_with_plugin_manifest():
    plugin = _load(".claude-plugin/plugin.json")
    market = _load(".claude-plugin/marketplace.json")
    assert market["name"] == "obsidian-second-brain"
    entries = market["plugins"]
    assert len(entries) == 1
    entry = entries[0]
    # The repo root is both the marketplace and its only plugin.
    assert entry["source"] == "./"
    assert entry["name"] == plugin["name"]
    assert entry["version"] == plugin["version"]


def test_plugin_manifest_paths_exist():
    plugin = _load(".claude-plugin/plugin.json")
    assert (REPO_ROOT / plugin["commands"]).is_dir()
    # hooks/hooks.json is auto-loaded by convention. Declaring it AGAIN in
    # plugin.json makes Claude Code reject the plugin with "Duplicate hooks
    # file detected" (hit live 2026-07-12) - the manifest field is only for
    # ADDITIONAL hook files beyond the standard path.
    assert "hooks" not in plugin, "do not redeclare hooks/hooks.json in plugin.json"
    assert (REPO_ROOT / "hooks/hooks.json").is_file()
    # Inline MCP server definition: the script it points at must exist.
    # (Inline is the mechanism that works - a root .mcp.json expands
    # ${CLAUDE_PLUGIN_ROOT} to empty, and would also register as a project
    # MCP server for anyone opening this repo.)
    servers = plugin["mcpServers"]
    assert isinstance(servers, dict) and servers, "MCP server must be defined inline"
    for server in servers.values():
        for arg in server.get("args", []):
            if "${CLAUDE_PLUGIN_ROOT}" in arg:
                rel = arg.replace("${CLAUDE_PLUGIN_ROOT}/", "")
                assert (REPO_ROOT / rel).is_file(), f"missing MCP file: {rel}"


def test_mcp_launch_pins_the_mcp_dependency():
    """`uv run --with mcp` resolves to the newest PyPI release at launch time,
    so an upstream SDK release breaks every install at once. mcp 2.0.0 did
    exactly that (#183): it removed `mcp.server.fastmcp`, server.py's
    `from mcp.server.fastmcp import FastMCP` raised ModuleNotFoundError, and
    Claude Code reported only a generic `-32000` reconnect failure. The
    manifest arg must therefore carry a version constraint, not a bare name."""
    plugin = _load(".claude-plugin/plugin.json")
    for name, server in plugin["mcpServers"].items():
        args = server.get("args", [])
        assert "--with" in args, f"MCP server {name} must declare its deps with --with"
        spec = args[args.index("--with") + 1]
        assert spec.startswith("mcp"), f"MCP server {name}: unexpected --with target {spec!r}"
        assert spec != "mcp", (
            f"MCP server {name}: pin the mcp dependency (e.g. 'mcp<2'); an unpinned "
            "--with lets the next breaking SDK release take the server down"
        )


# `--with mcp` not followed by a version constraint - the shape that breaks.
UNPINNED_MCP_RE = re.compile(r"--with[\"',\s]+\"?mcp(?![<>=!~\w-])")

# CHANGELOG entries quote the broken command verbatim while describing the fix.
UNPINNED_SWEEP_SKIP = {"CHANGELOG.md", "tests/test_plugin_manifest.py"}


def test_no_documented_command_reinstalls_the_unpinned_mcp():
    """The pin only holds if every copy of the launch command carries it. The
    command is duplicated across the manifest, setup.sh, SKILL.md, README.md and
    the integration's own docs - fixing one and missing another leaves a path
    that reinstalls the broken resolution."""
    # Sweep tracked files only. An rglob walk also picks up gitignored local
    # files - a maintainer's AUDIT.md, .claude/settings.local.json - which CI
    # never sees, so the guard passed in CI and failed on the machine of anyone
    # who had one. What ships is what is tracked.
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.split("\0")

    offenders = []
    for rel in tracked:
        if not rel or not rel.endswith((".md", ".py", ".sh", ".json")):
            continue
        if rel in UNPINNED_SWEEP_SKIP:
            continue
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        if UNPINNED_MCP_RE.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(rel)
    assert offenders == [], f"unpinned `--with mcp` still documented in: {offenders}"


def test_plugin_hooks_reference_shipped_executable_scripts():
    hooks = _load("hooks/hooks.json")["hooks"]
    # PostToolUse carries validate-ai-first.sh. It shipped in hooks/ but was
    # never wired here, so the AI-first rule CLAUDE.md calls "enforced" was
    # enforcing nothing on a plugin install (found by the claude-code owner,
    # issue #171). Keep it in this set so an adapter refactor cannot drop it
    # back out silently.
    assert set(hooks) == {"SessionStart", "PostToolUse", "PostCompact"}
    assert any(
        "validate-ai-first.sh" in hook["command"]
        for group in hooks["PostToolUse"]
        for hook in group["hooks"]
    ), "PostToolUse must wire validate-ai-first.sh - it is the write-time enforcement primitive"
    matchers = " ".join(group.get("matcher", "") for group in hooks["PostToolUse"])
    assert "create_file" in matchers, (
        "PostToolUse matcher must include create_file - the VS Code Claude Code "
        "extension writes with that tool name, not Write/Edit"
    )
    for event, groups in hooks.items():
        for group in groups:
            for hook in group["hooks"]:
                paths = re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\"]+)", hook["command"])
                assert paths, f"{event} hook must reference a plugin-rooted script"
                for rel in paths:
                    target = REPO_ROOT / rel
                    assert target.is_file(), f"missing hook script: {rel}"
    # The background agent writes unattended: it must keep its hard env gate so
    # the plugin-shipped PostCompact wiring stays inert by default.
    bg = (REPO_ROOT / "hooks/obsidian-bg-agent.sh").read_text(encoding="utf-8")
    assert "OBSIDIAN_BG_AGENT_ENABLED" in bg


def test_plugin_commands_cover_all_command_files():
    plugin = _load(".claude-plugin/plugin.json")
    commands_dir = REPO_ROOT / plugin["commands"]
    assert len(list(commands_dir.glob("*.md"))) >= 40
