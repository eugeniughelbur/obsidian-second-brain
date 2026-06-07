"""Obsidian Second Brain MCP server.

Exposes the vault as a set of MCP tools so any MCP client - Hermes Agent (via
`discover_mcp_tools()`), Claude Desktop, Claude Code, Cursor - can search, read,
and add notes to an Obsidian vault. This is the "second brain as a tool" connector
(GitHub Issue #60): it does NOT touch the agent's own memory; it gives the agent a
doorway into the knowledge vault.

Run:
    OBSIDIAN_VAULT_PATH=/path/to/vault uv run --with mcp python server.py

or wire it into a client's MCP config (see README.md).
"""

from __future__ import annotations

import json
import os
import sys

# Make `vault_ops` importable regardless of the working directory the client
# launches us from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP  # noqa: E402

import vault_ops  # noqa: E402

mcp = FastMCP("obsidian-second-brain")


@mcp.tool()
def obsidian_search(query: str, limit: int = 6) -> str:
    """Search the Obsidian vault for relevant notes.

    Returns ranked matches with a snippet and the vault-relative path of each
    note (pass that path to obsidian_read_note to read the whole note).
    """
    return json.dumps({"results": vault_ops.search(query, limit=limit)})


@mcp.tool()
def obsidian_read_note(path: str) -> str:
    """Read the full content of a vault note by its vault-relative path."""
    return json.dumps(vault_ops.read_note(path))


@mcp.tool()
def obsidian_save_note(
    title: str,
    content: str,
    type: str = "note",
    tags: list[str] | None = None,
) -> str:
    """Save a new note to the vault Inbox (AI-first format).

    Use for facts, ideas, or anything worth keeping in the knowledge vault.
    """
    return json.dumps(vault_ops.save_note(title, content, note_type=type, tags=tags))


@mcp.tool()
def obsidian_capture(text: str, tags: list[str] | None = None) -> str:
    """Quick-capture an idea or thought as a lightweight note (type: idea) in the vault."""
    return json.dumps(vault_ops.capture_idea(text, tags=tags))


@mcp.tool()
def obsidian_list_skills() -> str:
    """List the obsidian-second-brain skills (commands) available to run.

    Use this to discover higher-level behaviors beyond raw search/read/save -
    e.g. ingest a source, capture and graduate ideas, reconcile contradictions.
    Then call obsidian_get_skill(name) to get the steps.
    """
    return json.dumps({"skills": vault_ops.list_skills()})


@mcp.tool()
def obsidian_get_skill(name: str) -> str:
    """Get a skill's playbook (step-by-step instructions) by name.

    Returns instructions you should then execute yourself, using the other
    obsidian_* tools for the actual vault reads and writes. Example names:
    'obsidian-ingest', 'idea-discovery', 'obsidian-find', 'obsidian-save'.
    """
    return json.dumps(vault_ops.get_skill(name))


if __name__ == "__main__":
    mcp.run()
