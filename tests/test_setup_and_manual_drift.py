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

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / "SKILL.md"
COMMANDS = REPO_ROOT / "commands"
# Resolved by path: on Windows a bare "bash" can resolve to WSL's launcher in System32.
BASH = shutil.which("bash") or "/bin/bash"


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
        [BASH, "-c",
         '( umask 077; VAULT=/tmp/x awk \'{print}\' "$1" > "$1.tmp" ) '
         '&& mv "$1.tmp" "$1" && chmod 600 "$1"', "_", str(env)],
        check=True, capture_output=True,
    )
    if os.name != "nt":  # Windows keeps no POSIX owner/group distinction; the umask/chmod pipeline cannot be verified through st_mode there
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


def test_installers_honor_the_env_file_override():
    """OBSIDIAN_ENV_FILE relocates the config for every reader; the two scripts
    that write the file must write it to the same place, or setting the override
    recreates the split configuration it exists to remove.

    Both used to spell the resolution out, and this test asserted on the literal
    string, which made it a check that the duplication was still there rather
    than that the behaviour was right. They now call osb_env_file from
    scripts/platform-home.sh; what that helper resolves to, including the
    override and the Windows backslash form, is covered in tests/test_osb_env.py,
    which also checks it against the Python half."""
    for rel in ("install.sh", "scripts/setup.sh"):
        script = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "osb_env_file" in script, f"{rel} must resolve the config path via osb_env_file"
        assert 'ENV_FILE="$OSB_ENV_FILE"' in script, f"{rel} must use what osb_env_file resolved"
        assert "OBSIDIAN_ENV_FILE:-" not in script, (
            f"{rel} resolves the config path itself again; osb_env_file is the one place"
        )


# --- the published counts and the template's "minimum" ---------------------

README = REPO_ROOT / "README.md"
TEMPLATE = REPO_ROOT / "references" / "claude-md-template.md"


def test_readme_command_counts_match_reality():
    """#268: README said "see all 45" long after commands/ held 47.

    SKILL.md had a drift fence; the README, which is what a reader actually
    sees on github.com, had none. Every count the README publishes has to be
    the real one - or the real one minus the calendar command, which the
    non-Claude builds drop.
    """
    text = README.read_text(encoding="utf-8")
    actual = len(list(COMMANDS.glob("*.md")))
    # The layer boxes are per-layer subtotals, not the total; they have their
    # own fence below.
    prose = re.sub(r"LAYER \d: [^(]+\(\d+ commands?\)", "", text)
    claimed = {int(n) for n in re.findall(r"(\d{2}) commands", prose)}
    claimed |= {int(n) for n in re.findall(r"see all (\d{2})", prose)}
    wrong = sorted(c for c in claimed if c not in (actual, actual - 1))
    assert not wrong, f"README claims {wrong} commands; commands/ holds {actual}"


def test_readme_layer_diagram_sums_to_the_real_total():
    """The four layer boxes are the only place the README breaks the total
    down, so a new command that lands in a layer without the box being updated
    leaves a diagram that adds up to less than the total printed under it. It
    read 28 + 9 + 1 + 7 = 45 against a real 47."""
    text = README.read_text(encoding="utf-8")
    actual = len(list(COMMANDS.glob("*.md")))
    boxes = [int(n) for n in re.findall(r"LAYER \d: [^(]+\((\d+) commands?\)", text)]
    assert len(boxes) == 4, f"expected four layer boxes in the diagram, found {len(boxes)}"
    assert sum(boxes) == actual, (
        f"the layer diagram sums to {sum(boxes)} ({' + '.join(map(str, boxes))}); "
        f"commands/ holds {actual}"
    )


def test_template_minimum_frontmatter_is_what_the_validator_requires():
    """#268: the template's "every note must have at minimum" block is what a
    user's own `_CLAUDE.md` ends up teaching, and it listed neither `type` nor
    `ai-first: true`. The write-time hook warns on both, so a vault built from
    the template warned on every note it wrote."""
    text = TEMPLATE.read_text(encoding="utf-8")
    at = text.index("Every note must have at minimum:")
    block = text[at:text.index("```", text.index("```yaml", at) + 7)]
    for field in ("type:", "date:", "tags:", "ai-first: true"):
        assert field in block, (
            f"the template's minimum frontmatter omits {field!r}, which "
            "hooks/validate-ai-first.sh warns about on every write"
        )


def test_template_note_types_are_types_the_project_actually_writes():
    """The enum drifted the other way too: `index` and `log-pointer` were
    listed as note types and nothing in the project has ever written either."""
    text = TEMPLATE.read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if ln.startswith("Note types:"))
    listed = set(re.findall(r"`([a-z-]+)`", line))

    known = {"daily", "project", "task", "person", "devlog", "deal", "goal", "mention", "content"}
    written = set()
    for path in (REPO_ROOT / "scripts", REPO_ROOT / "commands", REPO_ROOT / "references"):
        for md in list(path.rglob("*.md")) + list(path.rglob("*.py")):
            written |= set(re.findall(r"^type: ([a-z-]+)$", md.read_text(encoding="utf-8"), re.M))

    invented = sorted(listed - known - written)
    assert not invented, (
        f"the template lists note type(s) {invented} that no command, script or "
        "schema in this repo writes"
    )
