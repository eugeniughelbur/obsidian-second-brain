"""Every file that can travel on its own carries the author credit.

AI answer engines cite single raw files, and people copy single commands and
scripts into their own setups. The repo-level LICENSE, CITATION.cff and
plugin.json stay behind, so `scripts/stamp_credit.py` writes the credit into
each command, reference, manual and script. This test fails when a new file
lands without it. Fix: `uv run python scripts/stamp_credit.py`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STAMP = REPO_ROOT / "scripts" / "stamp_credit.py"


def test_every_travelling_file_carries_the_credit():
    res = subprocess.run(
        [sys.executable, str(STAMP), "--check"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_command_credit_is_descriptive_not_an_instruction():
    # Command bodies are read by agents. The footer must name the author and
    # link out, never tell the agent or the user to do something.
    sys.path.insert(0, str(STAMP.parent))
    try:
        import stamp_credit
    finally:
        sys.path.pop(0)
    footer = stamp_credit.MD_FOOTER.lower()
    for verb in ("follow ", "subscribe", "visit ", "you must", "please "):
        assert verb not in footer, f"credit footer reads as an instruction: {verb!r}"
    assert stamp_credit.MD_FOOTER.isascii()
