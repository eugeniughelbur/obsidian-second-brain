# Obsidian Second Brain MCP server

An MCP server that turns an Obsidian vault into a set of tools any MCP client can call - [Hermes Agent](https://github.com/NousResearch/hermes-agent) (via `discover_mcp_tools()`), Claude Desktop, Claude Code, or Cursor.

This is the connector half of [Issue #60](https://github.com/eugeniughelbur/obsidian-second-brain/issues/60): the agent gets a doorway to **use** your vault as a knowledge second brain (search it, read it, add to it) **without** the vault becoming the agent's own behavioral memory. Those stay two distinct things, as requested.

## Status

v0, live-tested at the protocol level. The vault logic (`vault_ops.py`) is pure stdlib and unit-tested, and the full MCP round-trip (a real client connecting over stdio, discovering tools, and calling search / read / save) passes via `live_test.py`. The one thing not yet done is driving it from an actual Hermes instance - see "Testing" below.

## Tools exposed

| Tool | What it does |
|---|---|
| `obsidian_search(query, limit=6)` | Ranked keyword search across vault notes; returns snippets + paths |
| `obsidian_read_note(path)` | Read a full note by vault-relative path (path-traversal guarded) |
| `obsidian_save_note(title, content, type, tags)` | Save a new AI-first note to the vault `Inbox/` |

Saved notes follow `references/ai-first-rules.md` (frontmatter, `## For future Claude` preamble, `source: mcp` marker) so connector-written notes are distinguishable from hand-authored ones.

## Run it

Requires the vault path in the environment and the `mcp` package:

```bash
export OBSIDIAN_VAULT_PATH="/path/to/your/vault"
uv run --with mcp python integrations/obsidian-mcp-server/server.py
```

## Wire it into a client

Hermes Agent and most MCP clients take a launch command. Example client config entry:

```json
{
  "mcpServers": {
    "obsidian-second-brain": {
      "command": "uv",
      "args": ["run", "--with", "mcp", "python", "/abs/path/integrations/obsidian-mcp-server/server.py"],
      "env": { "OBSIDIAN_VAULT_PATH": "/path/to/your/vault" }
    }
  }
}
```

For Hermes specifically, add the server to its MCP config; Hermes picks the tools up through `discover_mcp_tools()` with zero Hermes-specific code. The same server works unchanged in Claude Desktop / Claude Code / Cursor.

## Testing

`vault_ops.py` is covered by a standalone harness (search / read / save / path-guard) - no `mcp` install needed. `live_test.py` runs the full MCP round-trip with a real client:

```bash
# read-only (safe against a real vault)
OBSIDIAN_VAULT_PATH=/path/to/vault uv run --with mcp python live_test.py "your query"
# also write one test note to Inbox/
OBSIDIAN_VAULT_PATH=/path/to/vault uv run --with mcp python live_test.py --save "your query"
```

Live-test checklist:
  - [x] Server starts and an MCP client completes the handshake.
  - [x] Client lists the three tools.
  - [x] Client calls `obsidian_search` (results), `obsidian_read_note` (content), `obsidian_save_note` (writes a valid AI-first note to `Inbox/`). Verified 2026-06-06 via `live_test.py` against both a throwaway vault and a real vault (read-only).
  - [ ] Connect from a real Hermes instance and confirm the tools appear via `discover_mcp_tools()`.

## Notes

- Search is a bounded linear scan (good for small/medium vaults; large vaults want an index).
- `vault_ops.py` is intentionally dependency-free and overlaps with the memory-provider integration; the two are separate artifacts and can later share a common module if both are kept.
