"""Obsidian Second Brain MCP server.

Exposes the vault as a set of MCP tools so any MCP client - Hermes Agent (via
`discover_mcp_tools()`), Claude Desktop, Claude Code, Cursor - can search, read,
and add notes to an Obsidian vault. This is the "second brain as a tool" connector
(GitHub Issue #60): it does NOT touch the agent's own memory; it gives the agent a
doorway into the knowledge vault.

Run:
    OBSIDIAN_VAULT_PATH=/path/to/vault uv run --no-project --with 'mcp<2' python server.py

or wire it into a client's MCP config (see README.md).
"""

# DO NOT add `from __future__ import annotations` to this module.
#
# Symptom if you do: the server dies during startup and the client lists zero
# vault tools, with "issubclass() arg 1 must be a class" in the logs.
#
# Cause: PEP 563 turns every annotation in this module into a plain string.
# fastmcp inspects each tool's signature at registration time and calls
# `issubclass(param.annotation, Context)` to find the context parameter.
# `issubclass` needs a real class, so a string annotation raises TypeError on
# the FIRST @mcp.tool() it walks, which aborts registration for all of them.
#
# This is a fastmcp limitation, not a defect in this file. Annotations below
# are therefore evaluated eagerly at import time, so every name used in an
# annotation on a decorated function must be importable at module scope
# (no `if TYPE_CHECKING:` guarded names in those positions).
#
# Note that the `mcp<2` pin in .claude-plugin/plugin.json does not prevent
# this: `mcp<2` resolves to 1.9.4, which is precisely the fastmcp that trips
# on string annotations. The pin guards against the 2.x rewrite dropping
# `mcp.server.fastmcp` entirely; it does not guard against this. If the pin is
# ever lifted to 2.x, recheck whether the issubclass path was fixed there, in
# which case this import can come back.

import json
import sys
from pathlib import Path

# Make `vault_ops` importable regardless of the working directory the client
# launches us from.
sys.path.insert(0, Path(__file__).parent.as_posix())

import vault_ops  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("obsidian-second-brain")


@mcp.tool()
def obsidian_search(query: str, limit: int = 6) -> str:
    """Search the Obsidian vault for relevant notes.

    Returns ranked matches with a snippet and the vault-relative path of each
    note (pass that path to obsidian_read_note to read the whole note).
    """
    return json.dumps({"results": vault_ops.search(query, limit=limit)})


@mcp.tool()
def obsidian_read_note(path: str, offset: int = 0, limit: int = 20_000) -> str:
    """Read a vault note by path with explicit pagination.

    If `truncated` is true, call again with the returned `next_offset` until it
    is null. This avoids silently losing the newest part of large dossiers.
    """
    return json.dumps(vault_ops.read_note(path, offset=offset, limit=limit))


@mcp.tool()
def obsidian_save_note(
    title: str,
    content: str,
    type: str = "note",
    tags: list[str] | None = None,
    path: str | None = None,
    summary: str | None = None,
) -> str:
    """Save a new AI-first note.

    `path` is an optional vault-relative markdown path such as
    `wiki/entities/Ada Lovelace.md`. Omit it for a dated Inbox capture.
    `summary` becomes the platform-neutral `## For future agent` preamble. If
    content already begins with a legacy or generic future-agent heading, the
    server normalizes it and never duplicates it.
    """
    return json.dumps(
        vault_ops.save_note(
            title, content, note_type=type, tags=tags, path=path, summary=summary
        )
    )


@mcp.tool()
def obsidian_capture(text: str, tags: list[str] | None = None) -> str:
    """Quick-capture an idea or thought as a lightweight note (type: idea) in the vault."""
    return json.dumps(vault_ops.capture_idea(text, tags=tags))


@mcp.tool()
def obsidian_update_note(
    path: str,
    append: str | None = None,
    heading: str | None = None,
    set_fields: dict[str, str] | None = None,
) -> str:
    """Guarded edit of an EXISTING vault note (curator mode).

    Appends a section (`append`, optionally under a `## heading`) and/or merges
    scalar frontmatter fields (`set_fields`, e.g. {"owner": "alex"}). Preserves
    the rest of the note verbatim, never creates a note, never touches list
    frontmatter like `tags:`, and refuses paths outside the vault. Stamps
    `updated` with today's date. To create a new note, use obsidian_save_note.

    `status` is not a free-form label: the values superseded, declined,
    rejected, archived, obsolete, cancelled, closed, parked, inactive and done
    fade the note in every future vault search. Setting one is closer to
    archiving than to labelling, so only set it when the note genuinely no
    longer holds. The response echoes a `faded` field when it happens.
    """
    return json.dumps(
        vault_ops.update_note(path, append=append, heading=heading, set_fields=set_fields)
    )


@mcp.tool()
def obsidian_replace_text(path: str, old_text: str, new_text: str) -> str:
    """Guarded exact patch of an existing note.

    The old block must occur exactly once. The operation is atomic and refuses
    protected directories, path escapes, missing anchors, and ambiguous matches.
    """
    return json.dumps(vault_ops.replace_text(path, old_text, new_text))


@mcp.tool()
def obsidian_move_note(source: str, destination: str) -> str:
    """Move a markdown note inside the vault without overwriting a destination.

    Use to graduate Inbox captures into canonical entity/project folders. The
    result reminds callers to repair any path-qualified links to the old path.
    """
    return json.dumps(vault_ops.move_note(source, destination))


@mcp.tool()
def obsidian_validate_note(path: str) -> str:
    """Check a note for AI-first compliance and unresolved wikilinks.

    Returns {path, ok, issues}: missing frontmatter or required keys
    (type/date/tags/ai-first), a missing/empty future-agent preamble, and
    any `[[wikilink]]` whose target note does not exist. Use before/after a
    write to keep the vault self-consistent.
    """
    return json.dumps(vault_ops.validate_note(path))


@mcp.tool()
def obsidian_backlinks(target: str) -> str:
    """List every note that links to `target` via [[wikilink]].

    `target` is a note title/stem or vault-relative path. Use to understand how
    a note is referenced before editing or to navigate the knowledge graph.
    """
    return json.dumps(vault_ops.backlinks(target))


@mcp.tool()
def obsidian_vault_health() -> str:
    """Bounded structural health check of the vault.

    Returns counts plus capped samples of orphan notes (no links in or out),
    wanted notes (a link exists but its target note does not yet - a wishlist,
    not an error), and notes with no frontmatter. Use to decide what to curate.
    """
    return json.dumps(vault_ops.vault_health())


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
