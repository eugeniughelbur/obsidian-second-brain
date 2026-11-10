# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""Topic tokenization for vault scans - delegates to the search tokenizer.

One tokenizer, one fix (#159, #188, #192, #212): `vault_scan` in notebooklm.py
and research_deep.py each kept a private whitespace-split + `len(w) > 2` copy
that returned nothing for CJK topics, and the copies survived three fixes to
the canonical tokenizer because every fix landed in one path and not the
others. This module is the single sanctioned import path to
`vault_ops._query_terms` for the research toolkit; do not re-implement
tokenization here or in a caller.
"""

from __future__ import annotations

import sys
from pathlib import Path

_MCP_DIR = Path(__file__).resolve().parents[3] / "integrations" / "obsidian-mcp-server"


def topic_terms(topic: str) -> list[str]:
    """CJK-aware meaningful terms for a research topic.

    Lowercased, stopwords dropped, CJK runs expanded to bigrams - exactly what
    vault search itself matches on, so a topic that finds notes in search
    finds the same notes in a scan.
    """
    if str(_MCP_DIR) not in sys.path:
        sys.path.insert(0, str(_MCP_DIR))
    import vault_ops
    return vault_ops._query_terms(topic)
