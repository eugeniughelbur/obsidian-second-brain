"""Platform ownership has to be real, not a governance file nobody reads.

Five audit findings in this repo (B3, B19, B20, S15, S23) were one defect: a
build that compiled cleanly, shipped, and was wrong in a way only a daily user
of that platform would spot. Ownership is the fix, and the thing that makes
someone want to own a build is their name shipping inside it.

So the table in adapters/OWNERS.md is not documentation, it is input to the
build. These tests pin that: every platform appears exactly once, a claimed
platform's credit reaches its INSTALL.md, and an unclaimed one stays clean. If
the table and the builds can disagree, the incentive quietly stops existing.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNERS = REPO_ROOT / "adapters" / "OWNERS.md"
# Resolved by path: on Windows a bare "bash" can resolve to WSL's launcher in System32.
BASH = shutil.which("bash") or "/bin/bash"


def _rows(text: str | None = None) -> dict[str, str]:
    """{platform: owner} from the marked table."""
    text = text if text is not None else OWNERS.read_text(encoding="utf-8")
    m = re.search(r"<!-- owners:start -->(.*?)<!-- owners:end -->", text, re.S)
    assert m, "OWNERS.md has no owners:start/end block, so the build cannot read it"
    out = {}
    for line in m.group(1).splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 4 or cells[1] in ("Platform", "") or set(cells[1]) <= {"-", ":"}:
            continue
        out[cells[1]] = cells[2]
    return out


def _platforms() -> set:
    return {p.name for p in (REPO_ROOT / "adapters").iterdir()
            if p.is_dir() and (p / "adapter.sh").is_file()}


def test_every_build_has_a_row():
    missing = _platforms() - set(_rows())
    assert not missing, (
        f"{sorted(missing)} ship a build with no row in OWNERS.md, so nobody can "
        "claim them and their credit can never be emitted"
    )


def test_no_row_names_a_build_that_does_not_exist():
    extra = set(_rows()) - _platforms()
    assert not extra, f"OWNERS.md lists {sorted(extra)}, which have no adapter.sh"


def test_owner_cells_are_a_handle_or_the_word_unclaimed():
    bad = [p for p, o in _rows().items()
           if o != "unclaimed" and not re.match(r"^\[@[\w-]+\]\(https://github\.com/[\w-]+\)$", o)]
    assert not bad, (
        f"{bad} have an Owner cell that is neither 'unclaimed' nor a "
        "[@handle](https://github.com/handle) link, so owner_of would emit it verbatim "
        "into a published INSTALL.md"
    )


def test_the_previously_contributed_column_is_credit_not_assignment():
    """Anyone listed there did merged work and owes nothing further."""
    text = OWNERS.read_text(encoding="utf-8")
    assert "not an assignment" in text and "implies no obligation" in text, (
        "OWNERS.md credits past contributors by name without stating that it is "
        "credit rather than an assignment of ongoing work"
    )


# --- the table actually drives the build ------------------------------------

def _build(platform: str, tmp: Path) -> str:
    """Build one platform from a copy of the repo and return its INSTALL.md."""
    r = subprocess.run([BASH, "scripts/build.sh", "--platform", platform],
                       cwd=tmp, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr or r.stdout
    return (tmp / "dist" / platform / "INSTALL.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory):
    """A copy of the repo, so claiming a platform in a test cannot touch the real one."""
    dst = tmp_path_factory.mktemp("repo") / "osb"
    shutil.copytree(REPO_ROOT, dst, ignore=shutil.ignore_patterns(
        ".git", "dist", "__pycache__", "node_modules", ".venv"))
    return dst


def test_an_unclaimed_platform_ships_no_credit_line(sandbox):
    assert "maintained by" not in _build("hermes", sandbox)


def test_a_claimed_platform_ships_its_owner_inside_the_build(sandbox):
    """The whole incentive. If this breaks, ownership buys nobody anything."""
    owners = sandbox / "adapters" / "OWNERS.md"
    original = owners.read_text(encoding="utf-8")
    owners.write_text(
        original.replace("| pi | unclaimed |",
                         "| pi | [@testowner](https://github.com/testowner) |"),
        encoding="utf-8")
    try:
        install = _build("pi", sandbox)
        assert "@testowner" in install, (
            "a claimed platform's build carries no credit, so the one thing an "
            "owner gets in return does not happen"
        )
        assert "maintained by" in install
    finally:
        owners.write_text(original, encoding="utf-8")


def test_a_malformed_owners_file_does_not_break_the_build(sandbox):
    """Governance must never be able to stop a release."""
    owners = sandbox / "adapters" / "OWNERS.md"
    original = owners.read_text(encoding="utf-8")
    owners.write_text("total garbage, no table at all\n", encoding="utf-8")
    try:
        assert "maintained by" not in _build("pi", sandbox)
    finally:
        owners.write_text(original, encoding="utf-8")


def test_owners_is_reachable_from_the_contributor_path():
    for doc in (REPO_ROOT / "CONTRIBUTING.md", REPO_ROOT / "README.md"):
        if "OWNERS.md" in doc.read_text(encoding="utf-8"):
            return
    pytest.fail("neither README nor CONTRIBUTING links adapters/OWNERS.md, so the "
                "only people who find it are people already reading adapters/")
