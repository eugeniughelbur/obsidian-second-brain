#!/usr/bin/env python3
"""Generate the public per-platform conformance board.

The repo claims eight platform builds. Until now nothing verified that claim in
a way a reader could check, and nothing verified it in a way the maintainer
could feel: they use Claude Code, whose adapter is an identity copy, so a break
in any other build was invisible in daily use and invisible in CI.

This emits a table of what each build actually passes, and the README carries
it between markers. `--check` fails when the committed table no longer matches
reality, so the published board cannot quietly go stale. A red cell is a
legitimate committed state - the point is that the board is true, not that it
is all green.

Usage:
    uv run python scripts/conformance_report.py            # print the table
    uv run python scripts/conformance_report.py --write    # update README.md
    uv run python scripts/conformance_report.py --check    # CI fence
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DIST = REPO_ROOT / "dist"
# Resolved by path: on Windows a bare "bash" can resolve to WSL's launcher in System32.
BASH = shutil.which("bash") or "/bin/bash"
START = "<!-- conformance:start -->"
END = "<!-- conformance:end -->"

# Claude Code supplies a real "Skill root" at session start, so the placeholder
# is correct there and only there.
SKILL_ROOT_EXEMPT = {"claude-code"}

CITED_REFERENCE = re.compile(r"[^\s`(\"']*references/[a-z0-9-]+\.md")

PLATFORM_LABEL = {
    "claude-code": "Claude Code",
    "codex-cli": "Codex CLI",
    "gemini-cli": "Gemini CLI",
    "opencode": "OpenCode",
    "agent-skills": "Agent Skills",
    "grok-bot": "Grok Bot",
    "hermes": "Hermes",
    "pi": "Pi",
}

PASS, FAIL = "pass", "FAIL"


def platforms() -> list[str]:
    return sorted(p.name for p in (REPO_ROOT / "adapters").iterdir() if (p / "adapter.sh").is_file())


def build_all() -> tuple[bool, str]:
    result = subprocess.run(
        [BASH, "scripts/build.sh"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    return result.returncode == 0, result.stderr


def check_non_empty(tree: Path) -> bool:
    return tree.is_dir() and len(list(tree.rglob("*.md"))) >= 20


def check_skill_root(tree: Path, platform: str) -> bool:
    # Markdown only: that is what the agent reads as instructions. Python sources
    # ship verbatim and may name the placeholder in a comment - this very file
    # does, and it gets copied into every build, so an all-files scan reports the
    # checker as the defect.
    leaked = any(
        "SKILL_ROOT" in p.read_text(encoding="utf-8", errors="ignore")
        for p in tree.rglob("*.md")
    )
    # Exempt platforms are expected to keep it; everyone else must not.
    return leaked if platform in SKILL_ROOT_EXEMPT else not leaked


def _tree_relative(cited: str) -> str:
    """Map a citation onto a path inside the built tree.

    A build whose agent runs somewhere other than the install root has to name
    that root absolutely (hermes emits `$HOME/.hermes/skills/...` - see #191), and
    no absolute install path can be resolved against a tree sitting in dist/. Keep
    the tail from `references/` onward so a wrong *filename* still fails; only the
    unverifiable prefix is dropped.
    """
    if cited.startswith(("/", "~", "$")):
        return "references/" + cited.split("references/", 1)[1]
    return cited.removeprefix("./")


def check_reference_paths(tree: Path, platform: str) -> bool:
    for md in tree.rglob("*.md"):
        text = md.read_text(encoding="utf-8", errors="ignore")
        for cited in set(CITED_REFERENCE.findall(text)):
            if platform in SKILL_ROOT_EXEMPT and cited.startswith("SKILL_ROOT/"):
                continue
            rel = _tree_relative(cited)
            candidates = [
                tree / rel,
                md.parent / rel,
                tree / rel.replace(".agents/skills/", "skills/", 1),
            ]
            for ancestor in md.parents:
                if ancestor == tree.parent:
                    break
                if (ancestor / "SKILL.md").is_file():
                    candidates.append(ancestor / rel)
                    break
            if not any(c.is_file() for c in candidates):
                return False
    return True


def check_python_project(tree: Path) -> str:
    dirs = [d for d in tree.rglob("scripts") if d.is_dir() and (d / "vault_health.py").is_file()]
    if not dirs:
        return "n/a"
    return PASS if all((d.parent / "pyproject.toml").is_file() for d in dirs) else FAIL


def render() -> tuple[str, bool]:
    ok, stderr = build_all()
    if not ok:
        return f"Build failed:\n{stderr}", False

    rows, all_green = [], True
    for p in platforms():
        tree = DIST / p
        results = [
            PASS if check_non_empty(tree) else FAIL,
            PASS if check_skill_root(tree, p) else FAIL,
            PASS if check_reference_paths(tree, p) else FAIL,
            check_python_project(tree),
        ]
        if FAIL in results:
            all_green = False
        label = PLATFORM_LABEL.get(p, p)
        cells = " | ".join("pass" if r == PASS else ("n/a" if r == "n/a" else "**FAIL**") for r in results)
        rows.append(f"| {label} | {cells} |")

    table = "\n".join([
        "| Build | Emits a real tree | Script paths resolved | Docs reachable | Toolkit runnable |",
        "|---|---|---|---|---|",
        *rows,
    ])
    return table, all_green


def readme_block(table: str) -> str:
    return (
        f"{START}\n"
        f"{table}\n\n"
        "*Generated by `scripts/conformance_report.py`, verified in CI on every push. "
        "Each build is compiled from the same source tree, then checked for a non-empty "
        "output, a resolved script root, reference paths that actually exist in that "
        "build, and a Python project shipped beside the scripts. A red cell here is a "
        "real red cell, not a missing test.*\n"
        f"{END}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="Update the README block in place")
    ap.add_argument("--check", action="store_true", help="Fail if the README block is stale")
    args = ap.parse_args()

    table, all_green = render()
    if table.startswith("Build failed"):
        print(table, file=sys.stderr)
        return 1

    if not (args.write or args.check):
        print(table)
        print("\nall green" if all_green else "\nat least one cell is red")
        return 0

    readme = REPO_ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    if START not in text or END not in text:
        print(f"error: README.md has no {START} / {END} markers", file=sys.stderr)
        return 1

    block = readme_block(table)
    updated = re.sub(
        re.escape(START) + r".*?" + re.escape(END), lambda _m: block, text, flags=re.DOTALL
    )

    if args.check:
        if updated != text:
            print(
                "The conformance board in README.md no longer matches the real build.\n"
                "Regenerate it with:  uv run python scripts/conformance_report.py --write\n",
                file=sys.stderr,
            )
            print(table, file=sys.stderr)
            return 1
        print("conformance board is current")
        return 0

    readme.write_text(updated, encoding="utf-8")
    print("README.md conformance board updated")
    print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
