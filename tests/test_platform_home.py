"""The OSB_HOME / OSB_WIN block (USERPROFILE on Windows shells, #242) lives in
scripts/platform-home.sh and is sourced by five scripts. Two files keep an
inline copy because they must stay standalone: hooks/validate-ai-first.sh
(copied into other harnesses' hook systems by hand) and scripts/quick-install.sh
(curl | bash before any checkout exists). This fence fails when a copy drifts,
the failure mode the tokenizer copies (#159/#188/#192) already demonstrated.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "scripts" / "platform-home.sh"
# Resolved by path: on Windows a bare "bash" can resolve to WSL's launcher in System32.
BASH = shutil.which("bash") or "/bin/bash"
INLINE_COPIES = ("hooks/validate-ai-first.sh", "scripts/quick-install.sh")
SOURCING = (
    "install.sh",
    "update.sh",
    "scripts/setup.sh",
    "scripts/run-command.sh",
    "integrations/telegram-journal/setup.sh",
)


def _case_block(text: str) -> list[str]:
    """The `case "$(uname -s)"` block that sets OSB_WIN, whitespace-normalized.
    The hook carries two other uname switches (path normalization), so the
    anchor is the OSB_WIN assignment that follows within two lines."""
    lines = text.splitlines()
    start = next(
        i for i, line in enumerate(lines)
        if line.strip().startswith('case "$(uname -s 2>/dev/null)" in')
        and any("OSB_WIN=1" in lines[j] for j in range(i, min(i + 3, len(lines))))
    )
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == "esac")
    return [line.strip() for line in lines[start:end + 1]]


def test_the_inline_copies_match_the_helper():
    canonical = _case_block(HELPER.read_text(encoding="utf-8"))
    joined = "\n".join(canonical)
    assert "USERPROFILE" in joined and "cygpath -u" in joined, "helper lost its Windows arm"
    for rel in INLINE_COPIES:
        copy = _case_block((REPO_ROOT / rel).read_text(encoding="utf-8"))
        assert copy == canonical, f"{rel} drifted from scripts/platform-home.sh"


def test_the_other_scripts_source_the_helper_instead_of_copying_it():
    for rel in SOURCING:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "platform-home.sh" in text and "osb_platform_home" in text, (
            f"{rel} does not source scripts/platform-home.sh"
        )
        assert 'OSB_HOME="${USERPROFILE' not in text, f"{rel} still carries an inline copy"


def test_the_helper_resolves_home_on_this_platform(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path))
    env.pop("USERPROFILE", None)
    r = subprocess.run(
        [BASH, "-c", f'. "{HELPER}"; osb_platform_home; printf "%s|%s" "$OSB_WIN" "$OSB_HOME"'],
        env=env, capture_output=True, text=True, check=True,
    )
    win, home = r.stdout.split("|")
    if os.name == "nt":
        assert win == "1"
    else:
        assert (win, home) == ("0", str(tmp_path))


def test_every_sourcing_script_still_parses():
    for rel in SOURCING:
        r = subprocess.run([BASH, "-n", str(REPO_ROOT / rel)], capture_output=True, text=True)
        assert r.returncode == 0, f"{rel}: {r.stderr}"
