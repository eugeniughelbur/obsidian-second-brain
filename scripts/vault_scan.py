# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""Canonical vault-scanning policy: which directories every tool skips.

Six tools each carried their own hardcoded exclude set. Only five entries were
common to all six, and the differences were a mix of two very different things:

  Real intent, worth keeping
    export_okf skips `excalidraw`  - drawings are not exportable prose
    vault_stats skips `raw`/`references` - not user notes for counting purposes

  Drift, which is the bug
    `_trash` appeared in 4 of 6, `node_modules` in 4 of 6
    agent config dirs (.agents, .codex, .gemini, .opencode) in only 2 of 6
    `Templates` in one tool and `templates` in three others, so the same folder
    was skipped or scanned depending on which tool ran and how the user had
    capitalised it

So this is a shared BASE plus explicit per-tool additions, not one merged set.
Merging outright would have silently widened three tools and thrown away the
intent behind the other two.

Matching is case-insensitive, which is what makes the Templates/templates split
stop mattering. `vault_health.VaultExcludes` remains the user-facing extension
point for `.vault-config.json`; this module is the floor beneath it.
"""

from __future__ import annotations

import os
import re

# Never scanned by any tool. Everything here is machine-owned: version control,
# editor and agent configuration, build output, trash, dependencies.
BASE_EXCLUDE_DIRS: frozenset[str] = frozenset({
    # version control and editor config
    ".git",
    ".obsidian",
    # trash, in both spellings vaults use
    ".trash",
    "_trash",
    # build and export output
    "_export",
    "__pycache__",
    "node_modules",
    # agent config directories. These hold instructions and commands, not vault
    # content, and counting them inflates every result (issue #80). Previously
    # only vault_health and freshness_lint skipped the full set.
    ".claude",
    ".agents",
    ".codex",
    ".gemini",
    ".opencode",
    # note templates. Scanned, they duplicate every real note's structure.
    # Spelled capital-T by the bootstrapper and lowercase by three tools, hence
    # the case-insensitive matching below.
    "templates",
})

# Per-tool additions, kept separate because each encodes a deliberate decision
# about what that tool is for, not an oversight.
EXPORT_ONLY_EXCLUDES: frozenset[str] = frozenset({"excalidraw"})
STATS_ONLY_EXCLUDES: frozenset[str] = frozenset({"raw", "references"})


def excluded_dirs(*extra: str) -> frozenset[str]:
    """The base policy plus any tool-specific additions, all casefolded."""
    return frozenset(d.lower() for d in (*BASE_EXCLUDE_DIRS, *extra))


def is_hidden(parts) -> bool:
    """True when any path component starts with a dot.

    On a volume with no native extended attributes (exFAT, FAT32, many SMB
    shares) macOS writes a small binary ``._<name>`` companion beside every
    file it touches.  ``rglob("*.md")`` matches ``._Note.md``, and counting
    it doubles the note in every stat, graph, and export.  Dot-prefixed
    generally rather than ``._`` specifically, because that is the rule
    Obsidian applies: it indexes no dot-prefixed file or folder.

    vault_health already does this via its ``_is_hidden()`` helper (#290).
    Placing the check here lets every tool that imports vault_scan benefit.
    """
    return any(str(p).startswith(".") for p in parts)


def is_excluded(parts, excludes: frozenset[str]) -> bool:
    """True when any path component matches, compared case-insensitively.

    `parts` must be VAULT-RELATIVE. Passing absolute parts means an ancestor
    directory outside the vault can match and disable the whole scan, which is
    exactly what happened in vault_health's empty-folder check (B29).
    """
    return any(str(p).lower() in excludes for p in parts)


# ── Semantic-index carve-out ────────────────────────────────────────────────
# OBSIDIAN_EMBED_EXCLUDE names vault-relative path PREFIXES that are never
# embedded. semantic_search applies it when it builds the index and vault_health
# when it measures index coverage; parsing it once here keeps the two from
# disagreeing about which notes the index is meant to hold (#273).


def embed_exclude_prefixes(raw: str | None = None) -> tuple[str, ...]:
    """OBSIDIAN_EMBED_EXCLUDE (comma-separated) as a tuple of prefixes, blanks dropped."""
    if raw is None:
        raw = os.environ.get("OBSIDIAN_EMBED_EXCLUDE", "")
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def is_embed_excluded(rel: str, prefixes) -> bool:
    """True when a vault-relative POSIX path equals or starts with any prefix."""
    return any(rel == p or rel.startswith(p) for p in prefixes)


# ── Frontmatter ─────────────────────────────────────────────────────────────
# Six tools parsed the frontmatter block with three different algorithms and
# three different regexes. They disagreed on real input: a note whose opening
# fence carries trailing whitespace had frontmatter according to vault_health
# and vault_stats, and none according to export_okf - which then wrote the
# frontmatter into the exported body as prose and typed the note `note`.
#
# `\s*` after both fences is the permissive form the two scanners already used.
# `\r?\n` on each fence: a note saved with CRLF line endings is frontmatter to
# vault_health and vault_stats (their `\s*` absorbs the `\r`) and was none to
# this pattern and to export_okf.FM_RE - the same disagreement, on line endings.
FRONTMATTER_RE = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL)


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_text, body). Both empty-safe.

    Tolerates a UTF-8 BOM and trailing whitespace on either fence, which is what
    the divergent copies disagreed about. A note with no frontmatter returns
    ("", text) rather than raising, so callers need no special case.
    """
    if text.startswith("﻿"):
        text = text[1:]
    m = FRONTMATTER_RE.match(text)
    if not m:
        return "", text
    return m.group(1), text[m.end():]
