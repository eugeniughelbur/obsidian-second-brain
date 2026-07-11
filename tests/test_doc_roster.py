"""SKILL.md and README.md must know every command that exists (fix 22/24).

The audit found six SKILL sections describing removed flows or stale steps,
and README counts that disagreed with the filesystem. The roster fence: every
command file appears in both docs, and the headline count is the file count.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_every_command_is_in_skill_and_readme():
    commands = sorted(p.stem for p in (REPO_ROOT / "commands").glob("*.md"))
    skill = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    missing = [f"SKILL.md lacks {c}" for c in commands if c not in skill]
    missing += [f"README.md lacks {c}" for c in commands if c not in readme]
    assert missing == [], "\n".join(missing)


def test_headline_count_matches_filesystem():
    n = len(list((REPO_ROOT / "commands").glob("*.md")))
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert f"{n} commands" in readme, f"README does not state the real count ({n})"
    assert f"## {n} Commands" in readme, "README's command-table heading disagrees"
