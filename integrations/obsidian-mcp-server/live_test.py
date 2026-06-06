"""Live MCP round-trip test for the Obsidian connector.

Drives server.py with a real MCP client over stdio - the same protocol Hermes
Agent / Claude Desktop / Cursor use - and exercises every tool. Proves the
connector works end-to-end without needing Hermes itself installed.

Usage:
    OBSIDIAN_VAULT_PATH=/path/to/vault uv run --with mcp python live_test.py
    OBSIDIAN_VAULT_PATH=/path/to/vault uv run --with mcp python live_test.py --save "query"

Without --save the run is read-only (safe against a real vault). With --save it
also writes one test note to the vault's Inbox/.
"""

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")


async def main(query: str, do_save: bool) -> None:
    vault = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
    if not vault:
        sys.exit("set OBSIDIAN_VAULT_PATH first")

    params = StdioServerParameters(
        command=sys.executable,  # reuse the interpreter that already has mcp
        args=[SERVER],
        env={**os.environ, "OBSIDIAN_VAULT_PATH": vault},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("HANDSHAKE OK. tools:", [t.name for t in tools.tools])

            r = await session.call_tool("obsidian_search", {"query": query, "limit": 3})
            results = json.loads(r.content[0].text).get("results", [])
            print(f"\nSEARCH '{query}' -> {len(results)} hits")
            for h in results:
                print("  -", h["path"])

            if results:
                rd = await session.call_tool("obsidian_read_note", {"path": results[0]["path"]})
                body = json.loads(rd.content[0].text).get("content", "")
                print(f"\nREAD {results[0]['path']} -> {body[:160]!r}")

            if do_save:
                sv = await session.call_tool(
                    "obsidian_save_note",
                    {
                        "title": "MCP live test",
                        "content": "Written by the Obsidian MCP connector during a live round-trip test.",
                        "type": "note",
                        "tags": ["test", "mcp"],
                    },
                )
                print("\nSAVE ->", sv.content[0].text)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--save"]
    asyncio.run(main(args[0] if args else "hermes", "--save" in sys.argv))
