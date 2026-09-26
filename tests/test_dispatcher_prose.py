"""The AI-first rule summary must have exactly one definition.

Four adapters each emit a "How to operate" block whose third step summarises the
vault-write spec: the `## For future agent` preamble, the required frontmatter
keys, wikilinks, recency markers, sources, confidence. Until now each adapter
carried its own hand-typed copy, differing only in the path it cites and in how
the prose happened to be line-wrapped.

CLAUDE.md says this rule is non-negotiable and must move in lockstep across
platforms. Four copies make that a promise nobody can keep: B21 was a path in
one copy that did not exist in that platform's own build, and it survived
because the other three were right and nobody diffed them.

These tests do not check the wording. They check that the wording has one home,
and that every platform's dispatcher actually ships it pointing at a file that
exists in that platform's own tree.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = REPO_ROOT / "adapters"
DIST = REPO_ROOT / "dist"
# Resolved by path: on Windows a bare "bash" can resolve to WSL's launcher in System32.
BASH = shutil.which("bash") or "/bin/bash"

# (adapter dir, built dispatcher path relative to dist/<platform>/)
DISPATCHERS = [
    ("gemini-cli", "GEMINI.md"),
    ("opencode", "AGENTS.md"),
    ("codex-cli", "AGENTS.md"),
    ("pi", ".pi/skills/obsidian-second-brain/SKILL.md"),
]

MARKER = "Treat the AI-first vault rule"


@pytest.fixture(scope="module")
def built() -> Path:
    result = subprocess.run(
        [BASH, "scripts/build.sh"], cwd=REPO_ROOT, check=False,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, f"all-platforms build failed:\n{result.stderr}"
    return DIST


def test_the_rule_summary_is_defined_once():
    """In lib.sh, and nowhere else."""
    lib = (ADAPTERS / "lib.sh").read_text(encoding="utf-8")
    assert MARKER in lib, "emit_ai_first_rule no longer holds the rule summary"

    offenders = []
    for adapter in sorted(ADAPTERS.glob("*/adapter.sh")):
        if MARKER in adapter.read_text(encoding="utf-8"):
            offenders.append(adapter.parent.name)
    assert not offenders, (
        f"{offenders} re-inlined the AI-first rule summary instead of calling "
        "emit_ai_first_rule. Copies drift silently - that is how B21 shipped a "
        "reference path that did not exist in its own platform's build."
    )


@pytest.mark.parametrize("platform,_dispatcher", DISPATCHERS)
def test_each_dispatcher_calls_the_helper(platform, _dispatcher):
    text = (ADAPTERS / platform / "adapter.sh").read_text(encoding="utf-8")
    assert "emit_ai_first_rule " in text, (
        f"{platform}'s dispatcher no longer emits the AI-first rule at all, so "
        "that platform's agent is never told the vault-write spec is binding"
    )


@pytest.mark.parametrize("platform,dispatcher", DISPATCHERS)
def test_the_cited_path_exists_in_that_platforms_build(built, platform, dispatcher):
    """B21 verbatim: the rule is useless if its own path 404s.

    Resolved relative to the dispatcher's own directory, which is what an agent
    reading that file would do - not relative to the build root.
    """
    doc = built / platform / dispatcher
    assert doc.is_file(), f"{platform} did not emit {dispatcher}"

    # Collapse whitespace: the summary is prose emitted by a heredoc and wraps
    # at whatever width that heredoc uses.
    text = " ".join(doc.read_text(encoding="utf-8").split())
    assert MARKER in text, f"{platform}'s dispatcher does not carry the rule summary"
    m = re.search(r"The full spec is `([^`]+)`", text)
    assert m, f"{platform}'s rule summary no longer cites the spec path"

    cited = (doc.parent / m.group(1)).resolve()
    assert cited.is_file(), (
        f"{platform}'s dispatcher points at {m.group(1)}, which does not exist "
        f"relative to {dispatcher}. The agent is told to follow a spec it "
        "cannot open."
    )

    # The path is relative, so it only resolves from one directory. That is the
    # #171 class: it cannot be made absolute at build time, so the instruction
    # must carry a recovery path and must fail loudly instead of silently.
    assert "search upward" in text and "say so before writing" in text, (
        f"{platform} cites a relative spec path with no recovery and no loud "
        "failure. An agent started outside the install root would skip the "
        "AI-first rule with nothing in the session saying so."
    )


# Builds that generate their own frontmatter, so a source `trigger-mode` only
# reaches the model if the adapter encodes it. The other three (claude-code,
# gemini-cli, opencode) copy the command body verbatim, frontmatter included,
# so the field travels on its own and needs no encoding.
GENERATED_DESC_PLATFORMS = ["codex-cli", "agent-skills", "hermes", "pi"]


@pytest.mark.parametrize("platform", GENERATED_DESC_PLATFORMS)
def test_generated_descriptions_carry_the_trigger_policy(built, platform):
    """#181, reported by @konsone: hermes never read `trigger-mode`, so its
    skills shipped purely reactive. It was encoded in agent-skills alone, which
    left codex-cli and pi with the same gap - 7 of the 8 commands that declare
    the field are proactive, so three builds lost the signal on all 7.

    Nothing failed. The builds compiled, the skills loaded, and they simply
    never volunteered - which is the defect class this repo keeps finding, and
    the one CI has to hold rather than a reader.
    """
    src = REPO_ROOT / "commands"
    proactive, explicit = [], []
    for f in sorted(src.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        m = re.search(r"^trigger-mode:\s*(\S+)\s*$", text, re.M)
        if not m:
            continue
        (proactive if m.group(1) == "proactive" else explicit).append(f.stem)

    assert proactive, "no command declares trigger-mode: proactive - fence is vacuous"

    missing = []
    for stem in proactive + explicit:
        hits = [
            p for p in (built / platform).rglob("*.md")
            if stem in p.as_posix()
        ]
        if not hits:
            continue  # excluded from this platform, which is legitimate
        want = "Use proactively" if stem in proactive else "only when the user explicitly asks"
        if not any(want in " ".join(p.read_text(encoding="utf-8").split()) for p in hits):
            missing.append(f"{stem} (wanted: {want!r})")

    assert not missing, (
        f"{platform} generates its own description but drops the trigger-mode "
        f"policy for:\n  " + "\n  ".join(missing[:10])
    )
