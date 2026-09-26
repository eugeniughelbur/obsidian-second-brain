"""Cross-platform conformance for the adapter build pipeline.

The existing smoke tests build four platforms individually and assert that a few
paths exist. That left three ways for a build to ship broken while CI stayed
green, all three of which had actually happened:

  1. `bash scripts/build.sh` with no --platform (the all-platforms loop) was
     never exercised, and three adapters were never built at all. A sabotaged
     adapter could emit an empty tree and the suite still passed 198/198.
  2. The SKILL_ROOT placeholder is a Claude Code affordance. Five of seven builds
     shipped it unresolved, so every Python-backed command tried to cd into a
     directory literally named SKILL_ROOT.
  3. `rewrite_platform_paths()` only matched `.claude/`, which appears in no
     command or reference file. Every bare `references/...` path shipped
     unrewritten, so the AI-first write spec was unreachable on four platforms.

These tests are parametrized over the adapters directory, so a new adapter is
covered the day it lands rather than the day someone remembers to add a test.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DIST = REPO_ROOT / "dist"
# Resolved by path: on Windows a bare "bash" can resolve to WSL's launcher in System32.
BASH = shutil.which("bash") or "/bin/bash"

# Discovered rather than hardcoded: a new adapter is covered automatically.
PLATFORMS = sorted(p.name for p in (REPO_ROOT / "adapters").iterdir() if (p / "adapter.sh").is_file())

# Claude Code is the identity build. It is the one harness that supplies a real
# "Skill root" at session start, so the placeholder is correct there and only
# there.
SKILL_ROOT_EXEMPT = {"claude-code"}

CITED_REFERENCE = re.compile(r"[^\s`(\"']*references/[a-z0-9-]+\.md")


def _tree_relative(cited: str) -> str:
    """Map a citation onto a path inside the built tree. Kept in step with
    scripts/conformance_report.py, which the CI report runs from."""
    if cited.startswith(("/", "~", "$")):
        return "references/" + cited.split("references/", 1)[1]
    return cited.removeprefix("./")


@pytest.fixture(scope="module")
def built() -> Path:
    """Build every platform once, the way a release actually does it."""
    result = subprocess.run(
        [BASH, "scripts/build.sh"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, f"all-platforms build failed:\n{result.stderr}"
    return DIST


def test_every_adapter_is_discovered():
    """Guards the parametrization itself: if this drops to a handful, the rest of
    the file silently stops covering the platforms it claims to."""
    assert len(PLATFORMS) >= 7, f"expected 7+ adapters, found {PLATFORMS}"


@pytest.mark.parametrize("platform", PLATFORMS)
def test_build_emits_a_non_empty_tree(built: Path, platform: str) -> None:
    """A build that exits 0 with an empty output tree is the failure mode CI
    could not see. Assert content, not just that the directory exists."""
    tree = built / platform
    assert tree.is_dir(), f"{platform} produced no output directory"

    markdown = list(tree.rglob("*.md"))
    assert len(markdown) >= 20, (
        f"{platform} emitted only {len(markdown)} markdown files; "
        "an adapter that silently produces a near-empty tree is the bug this catches"
    )


@pytest.mark.parametrize("platform", PLATFORMS)
def test_skill_root_placeholder_is_resolved(built: Path, platform: str) -> None:
    """SKILL_ROOT must be rewritten to a real path on every harness that does not
    supply one. Shipping the literal string breaks every Python-backed command.

    Scoped to markdown, because markdown is what the agent reads as instructions.
    Python sources under scripts/ are shipped verbatim and may legitimately name
    the placeholder in a comment; scripts/conformance_report.py does exactly
    that, and an all-files scan flagged the checker's own source as a defect."""
    offenders = [
        p.relative_to(built).as_posix()
        for p in (built / platform).rglob("*.md")
        if "SKILL_ROOT" in p.read_text(encoding="utf-8", errors="ignore")
    ]

    if platform in SKILL_ROOT_EXEMPT:
        assert offenders, (
            f"{platform} is the identity build and is expected to keep SKILL_ROOT; "
            "if it no longer does, this exemption is stale"
        )
        return

    assert not offenders, (
        f"{platform} ships an unresolved SKILL_ROOT in {len(offenders)} file(s): "
        f"{offenders[:5]}"
    )


@pytest.mark.parametrize("platform", PLATFORMS)
def test_every_cited_reference_path_resolves(built: Path, platform: str) -> None:
    """A command that cites `references/ai-first-rules.md` at a path which does
    not exist in its own build leaves the agent unable to open the one spec the
    project calls non-negotiable."""
    tree = built / platform
    unresolved: list[str] = []

    for md in tree.rglob("*.md"):
        text = md.read_text(encoding="utf-8", errors="ignore")
        for cited in set(CITED_REFERENCE.findall(text)):
            # The identity build deliberately keeps the SKILL_ROOT placeholder,
            # so a path rooted at it cannot be resolved on disk here.
            if platform in SKILL_ROOT_EXEMPT and cited.startswith("SKILL_ROOT/"):
                continue

            # removeprefix, not lstrip: lstrip strips characters, so a genuine
            # ".pi/..." path would lose its leading dot and never resolve.
            # Shared with scripts/conformance_report.py::_tree_relative - a build
            # whose agent runs outside the install root has to name that root
            # absolutely (#191), and no absolute path resolves against dist/, so
            # only the tail from `references/` onward is checkable there.
            rel = _tree_relative(cited)

            candidates = [
                tree / rel,        # rewritten, install-relative path
                md.parent / rel,   # genuine sibling reference
                # agent-skills writes post-install paths (.agents/skills/...);
                # the dist tree stores that same content under skills/.
                tree / rel.replace(".agents/skills/", "skills/", 1),
            ]
            # A doc nested inside a skill may cite relative to that skill's root
            # (the nearest ancestor holding a SKILL.md) rather than to itself.
            for ancestor in md.parents:
                if ancestor == tree.parent:
                    break
                if (ancestor / "SKILL.md").is_file():
                    candidates.append(ancestor / rel)
                    break
            if any(c.is_file() for c in candidates):
                continue
            unresolved.append(f"{md.relative_to(tree).as_posix()} -> {cited}")

    assert not unresolved, (
        f"{platform} cites {len(unresolved)} reference path(s) that do not exist "
        f"in its own build:\n  " + "\n  ".join(sorted(unresolved)[:8])
    )


@pytest.mark.parametrize("platform", PLATFORMS)
def test_python_toolkit_ships_with_its_project(built: Path, platform: str) -> None:
    """`uv run --directory <root>` needs a pyproject.toml beside the scripts to
    resolve both the module path and its dependencies. One adapter shipped the
    scripts without it, so every Python command failed on that platform."""
    tree = built / platform
    script_dirs = [d for d in tree.rglob("scripts") if d.is_dir() and (d / "vault_health.py").is_file()]
    if not script_dirs:
        pytest.skip(f"{platform} does not ship the Python toolkit")

    for scripts in script_dirs:
        assert (scripts.parent / "pyproject.toml").is_file(), (
            f"{platform} ships {scripts.relative_to(tree).as_posix()} with no "
            "pyproject.toml beside it"
        )
