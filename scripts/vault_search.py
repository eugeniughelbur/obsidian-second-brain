# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""Search the configured vault from a shell without starting an agent or service."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations" / "obsidian-mcp-server"))
sys.path.insert(0, str(ROOT / "scripts"))

import osb_env  # noqa: E402
import vault_ops  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--lexical", action="store_true", help="Disable semantic search")
    args = parser.parse_args(argv)
    if not osb_env.vault_path():
        print("Set OBSIDIAN_VAULT_PATH in the environment or toolkit config.", file=sys.stderr)
        return 2
    try:
        results = vault_ops.search(
            args.query, limit=args.limit, semantic=False if args.lexical else None
        )
    except (RuntimeError, OSError) as exc:
        print(f"Vault search failed: {exc}", file=sys.stderr)
        return 2
    # ASCII escapes, not raw UTF-8: a Windows console in a legacy code page cannot
    # print a CJK or emoji title and would crash after the search succeeded.
    print(json.dumps(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
