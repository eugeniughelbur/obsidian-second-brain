"""Commands and references must not teach what the guard forbids (fix 19/24).

validate-ai-first.sh check 5 blocks vault writes containing substitution
Unicode (em/en-dashes, curly quotes, Unicode math), yet 15 instruction files
taught the agent to write exactly those - filename templates, index-line
formats, footer boilerplate. CI never noticed because the repo sweep exempts
backtick spans, and in instruction files backticked templates are precisely
what the agent copies into the vault. This lint scans commands/ and
references/ with NO backtick exemption; the single allowlisted line is the
rules table that defines the banned characters (a rulebook must be able to
name what it bans - quoted as specimens, never as instructions).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Written as escapes so this file itself passes the repo-wide sweep -
# the guards must not trip over the guard.
BANNED = "\u2014\u2013\u00b1\u201c\u201d\u2018\u2019\u2265\u2264\u2260"
ALLOW_MARKER = "Em-dash (`\u2014`)"  # the specimen row in ai-first-rules.md


def test_instruction_files_carry_no_banned_characters():
    offenders: list[str] = []
    targets = [*sorted((REPO_ROOT / "commands").glob("*.md")),
               *sorted((REPO_ROOT / "references").glob("*.md")),
               REPO_ROOT / "SKILL.md"]
    for md in targets:
        folder = md.parent.name if md.parent != REPO_ROOT else "."
        if True:
            for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
                if ALLOW_MARKER in line:
                    continue
                hits = [c for c in BANNED if c in line]
                if hits:
                    offenders.append(
                        f"{folder}/{md.name}:{i}: {[hex(ord(c)) for c in hits]} {line.strip()[:70]}"
                    )
    assert offenders == [], (
        "banned substitution characters in instruction files "
        "(the guard blocks what these lines teach):\n" + "\n".join(offenders)
    )
