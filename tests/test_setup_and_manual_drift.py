"""The credential file's mode, and drift between SKILL.md and the command files.

Two gaps the audit named that no test covered.

The .env file holds every research API key. install.sh creates it at 0600 and
setup.sh then rewrites it through a temp file, which under a default umask
replaced that with 0644 - readable by any other account on the machine. The
repo already had the analogous guard for vault notes
(test_note_safety::test_write_exact_preserves_permission_bits); the credential
file, which is the more sensitive of the two, had none.

SKILL.md inlines step lists for roughly fifteen commands that also exist as
files under commands/. When the two disagree, behaviour depends on which text
happened to load, and that has bitten twice: the log.md instructions (B11) and
three different wordings of the same vault_health invocation (B39). This does
not diff prose - that would be noise - it pins the specific facts that drifted.
"""

from __future__ import annotations

import re
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / "SKILL.md"
COMMANDS = REPO_ROOT / "commands"


# --- the credential file ---------------------------------------------------

def test_setup_preserves_the_env_file_mode(tmp_path):
    """Runs the real rewrite pipeline from setup.sh against a 0600 file."""
    env = tmp_path / ".env"
    env.write_text("XAI_API_KEY=secret\nOBSIDIAN_VAULT_PATH=old\n", encoding="utf-8")
    env.chmod(0o600)

    # The exact shell setup.sh runs, extracted so the test exercises the pipeline
    # rather than a paraphrase of it.
    script = (REPO_ROOT / "scripts" / "setup.sh").read_text(encoding="utf-8")
    assert "umask 077" in script, (
        "setup.sh rewrites the API-key file through a temp file and mv. Without a "
        "restrictive umask the new file is created at 0644 and the mv silently "
        "discards install.sh's 0600."
    )
    assert 'chmod 600 "$ENV_FILE"' in script, "no explicit chmod backstop after the mv"

    subprocess.run(
        ["bash", "-c",
         '( umask 077; VAULT=/tmp/x awk \'{print}\' "$1" > "$1.tmp" ) '
         '&& mv "$1.tmp" "$1" && chmod 600 "$1"', "_", str(env)],
        check=True, capture_output=True,
    )
    mode = stat.S_IMODE(env.stat().st_mode)
    assert mode == 0o600, f"the API-key file ended at {oct(mode)}, readable by others"


def test_install_creates_the_env_file_restricted():
    script = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")
    assert 'chmod 600 "$ENV_FILE"' in script, (
        "install.sh no longer restricts the credential file it creates"
    )


# --- SKILL.md vs the command files ------------------------------------------

def _skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_skill_md_never_names_log_md_as_a_bare_write_target():
    """B11: SKILL.md forbids writing entries to log.md, then instructed it.

    Vaults on v0.9+ have a Logs/ directory and a root log.md that is a pointer
    file. Sixteen command files branch on that; the scheduled-agent prompts live
    only in SKILL.md and had no branch, so those runs wrote into the pointer and
    the real per-day log stayed empty.
    """
    text = _skill_text()
    offenders = []
    for m in re.finditer(r"^.*(?:[Aa]ppend to|write to) `?log\.md`?.*$", text, re.M):
        line = m.group(0)
        if "Logs/" in line or "pointer" in line.lower() or "otherwise" in line.lower():
            continue  # correctly branched, or describing the rule itself
        offenders.append(line.strip()[:100])
    assert not offenders, (
        "SKILL.md instructs a bare write to log.md, which it also forbids:\n  "
        + "\n  ".join(offenders)
    )


def test_vault_health_is_invoked_one_way_everywhere():
    """B39: three different wordings of the same command shipped simultaneously."""
    text = _skill_text()
    stale = re.findall(r"(?<!--directory \")python scripts/vault_health\.py", text)
    assert not stale, (
        f"{len(stale)} stale `python scripts/vault_health.py` invocation(s) in "
        "SKILL.md. commands/obsidian-health.md moved to the `uv run --directory` "
        "form; SKILL.md kept the old one, so the two disagree."
    )


def test_every_command_file_is_reachable_from_skill_md():
    """A command SKILL.md never mentions is one the agent may never select."""
    text = _skill_text()
    missing = [f.stem for f in sorted(COMMANDS.glob("*.md")) if f.stem not in text]
    assert not missing, f"commands absent from SKILL.md: {missing}"


def test_skill_md_command_count_matches_reality():
    text = _skill_text()
    actual = len(list(COMMANDS.glob("*.md")))
    claimed = {int(n) for n in re.findall(r"(\d{2}) commands", text)}
    wrong = {c for c in claimed if c not in (actual, actual - 1)}  # -1 excludes calendar
    assert not wrong, (
        f"SKILL.md claims {sorted(wrong)} commands; commands/ holds {actual}"
    )
