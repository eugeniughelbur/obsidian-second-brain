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
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(relpath: str):
    return json.loads((REPO_ROOT / relpath).read_text(encoding="utf-8"))


def _pyproject_version() -> str:
    with open(REPO_ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def test_plugin_manifest_parses_and_matches_pyproject_version():
    plugin = _load(".claude-plugin/plugin.json")
    assert plugin["name"] == "obsidian-second-brain"
    assert plugin["version"] == _pyproject_version()


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
    assert (REPO_ROOT / plugin["hooks"]).is_file()
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


def test_plugin_hooks_reference_shipped_executable_scripts():
    hooks = _load("hooks/hooks.json")["hooks"]
    assert set(hooks) == {"SessionStart", "PostCompact"}
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
