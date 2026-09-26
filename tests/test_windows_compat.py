"""Windows compatibility fences (#240-#247, PRs #243 and #248 by @motkoning).

The write-time hook's path normalization, the USERPROFILE-based config home,
CRLF notes, the OBSIDIAN_ENV_FILE override, and the external-engine command
split. The Windows-only cases skip off Windows; the portable ones run on the
ubuntu CI runner too. Split out of test_smoke.py, which had grown past 1700
lines, as a follow-up to the #243/#248 review.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
# Resolved by path: on Windows a bare "bash" can resolve to WSL's launcher in System32.
BASH = shutil.which("bash") or "/bin/bash"


def test_validate_hook_matches_windows_backslash_paths(tmp_path):
    """On Windows, Claude Code hands the hook tool_input.file_path with
    backslashes ("C:\\Users\\...") while OBSIDIAN_VAULT_PATH is written with
    forward slashes. The vault-scope check compared the two as strings, so the
    hook exited 0 before reading the note - a silent no-op on every Windows
    install (found on a fresh plugin install: two deliberately bad writes, no
    warning). Both sides are now normalized to forward slashes and a lowercase
    drive letter. Windows path forms only exist on Windows, so this runs there
    and skips elsewhere; the POSIX form is covered by the tests above."""
    if os.name != "nt":
        pytest.skip("Windows path forms only exist on Windows")
    hook = REPO_ROOT / "hooks/validate-ai-first.sh"
    bad = tmp_path / "bad.md"
    bad.write_text("# bad note\njust a test\n", encoding="utf-8")
    backslash_file = str(bad)
    assert "\\" in backslash_file, "expected the native Windows path form"
    slash_vault = tmp_path.as_posix()

    def run(file_path, vault):
        return subprocess.run(
            [BASH, str(hook)],
            input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": file_path}}),
            env=dict(os.environ, OBSIDIAN_VAULT_PATH=vault),
            capture_output=True,
            text=True,
        )

    # Backslash file path against a forward-slash vault path: must warn.
    r = run(backslash_file, slash_vault)
    assert r.returncode == 0, r.stderr
    assert "AI-first warning" in json.loads(r.stdout)["systemMessage"]

    # The drive letter's case must not matter either.
    r = run(backslash_file, slash_vault[0].swapcase() + slash_vault[1:])
    assert r.returncode == 0, r.stderr
    assert "AI-first warning" in json.loads(r.stdout)["systemMessage"]

    # The vault may be spelled the way a Windows shell spells it, the MSYS form
    # (/c/Users/...) or with a trailing separator; both must still match.
    msys_vault = subprocess.run(
        ["cygpath", "-u", str(tmp_path)], capture_output=True, text=True, check=True
    ).stdout.strip()
    r = run(backslash_file, msys_vault)
    assert r.returncode == 0, r.stderr
    assert "AI-first warning" in json.loads(r.stdout)["systemMessage"], "MSYS-form vault path must match"
    r = run(backslash_file, str(tmp_path) + "\\")
    assert r.returncode == 0, r.stderr
    assert "AI-first warning" in json.loads(r.stdout)["systemMessage"], (
        "a trailing separator on the vault path must not break the match"
    )

    # The literal spellings of both runtimes, not just what this shell's cygpath
    # emits: MSYS misreads /cygdrive/c/... and Cygwin misreads /c/..., so the hook
    # maps both by hand. And Windows paths are case-insensitive, so a differently
    # cased vault path must match as well.
    drive = tmp_path.drive[0].lower()
    rest = tmp_path.as_posix()[2:]
    for spelling in (f"/{drive}{rest}", f"/cygdrive/{drive}{rest}", str(tmp_path).upper()):
        r = run(backslash_file, spelling)
        assert r.returncode == 0, r.stderr
        assert "AI-first warning" in json.loads(r.stdout)["systemMessage"], f"vault spelled {spelling!r} must match"

    # Classification is case-insensitive on Windows as well: an upper-case
    # extension is still a note, and an excluded folder spelled in another case
    # is still excluded.
    upper = tmp_path / "BAD.MD"
    upper.write_text("# bad note\n", encoding="utf-8")
    r = run(str(upper), slash_vault)
    assert r.returncode == 0, r.stderr
    assert "AI-first warning" in json.loads(r.stdout)["systemMessage"], "BAD.MD must be validated"
    excluded = tmp_path / "TEMPLATES" / "t.md"
    excluded.parent.mkdir()
    excluded.write_text("# a template, no frontmatter by design\n", encoding="utf-8")
    r = run(str(excluded), slash_vault)
    assert r.returncode == 0 and r.stdout == "", "an excluded folder in another case must stay excluded"
    # And the mixed-case entries of the exclusion list keep matching the
    # lowercased key, so the vault's operating surfaces raise no false warnings.
    for rel in ("Logs/2026-01-01.md", "_CLAUDE.md", "Home.md"):
        surface = tmp_path / rel
        surface.parent.mkdir(exist_ok=True)
        surface.write_text("# operating surface, no frontmatter by design\n", encoding="utf-8")
        r = run(str(surface), slash_vault)
        assert r.returncode == 0 and r.stdout == "", f"{rel} must stay excluded"

    # A file outside the vault stays silent regardless of path form.
    outside = tmp_path.parent / "outside-the-vault.md"
    outside.write_text("# outside\n", encoding="utf-8")
    r = run(str(outside), slash_vault)
    assert r.returncode == 0 and r.stdout == ""


def test_validate_hook_env_fallback_uses_the_platform_home(tmp_path):
    """The optional .env fallback must live where the Python tools look for it.
    Path.home() reads USERPROFILE on Windows and ignores HOME, while the hook
    read $HOME; on a machine whose HOME points at another drive (a corporate
    roaming home) the two halves resolved different files and a user following
    the README configured one half only. On Windows shells the hook now uses
    USERPROFILE; elsewhere HOME is the home and nothing changes."""
    hook = REPO_ROOT / "hooks/validate-ai-first.sh"
    vault = tmp_path / "vault"
    vault.mkdir()
    bad = vault / "bad.md"
    bad.write_text("# bad note\n", encoding="utf-8")
    other_home = tmp_path / "other-home"
    platform_home = tmp_path / "platform-home"
    for home in (other_home, platform_home):
        (home / ".config" / "obsidian-second-brain").mkdir(parents=True)
    # CRLF on purpose: a .env written on Windows and read by macOS or Linux bash
    # kept a trailing carriage return in the vault path and never matched.
    (platform_home / ".config" / "obsidian-second-brain" / ".env").write_bytes(
        f"OBSIDIAN_VAULT_PATH={vault}\r\n".encode("utf-8")
    )

    env = dict(os.environ)
    env.pop("OBSIDIAN_VAULT_PATH", None)
    env.pop("OBSIDIAN_ENV_FILE", None)
    if os.name == "nt":
        env["USERPROFILE"] = str(platform_home)
        env["HOME"] = str(other_home)  # won before the fix, and found nothing
    else:
        env["HOME"] = str(platform_home)
        env.pop("USERPROFILE", None)
    r = subprocess.run(
        [BASH, str(hook)],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(bad)}}),
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "AI-first warning" in json.loads(r.stdout)["systemMessage"], (
        "the hook must find the .env under the platform home and validate the note"
    )

    if os.name == "nt":
        # Without cygpath the scripts fall back to USERPROFILE with the separators
        # flipped, and the path normalization falls back to the same flip; the
        # fallback must still find the file and match the note.
        broken = tmp_path / "no-cygpath"
        broken.mkdir()
        (broken / "cygpath").write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
        env["PATH"] = f"{broken}{os.pathsep}{env['PATH']}"
        r = subprocess.run(
            [BASH, str(hook)],
            input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(bad)}}),
            env=env,
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, r.stderr
        assert "AI-first warning" in json.loads(r.stdout)["systemMessage"], (
            "the fallback without cygpath must still resolve the platform home"
        )

    # OBSIDIAN_ENV_FILE overrides the location, in the native spelling of the
    # platform (backslashes on Windows), and the CRLF tolerance applies to it too.
    elsewhere = tmp_path / "elsewhere" / "osb.env"
    elsewhere.parent.mkdir()
    elsewhere.write_bytes(f"OBSIDIAN_VAULT_PATH={vault}\r\n".encode("utf-8"))
    env["OBSIDIAN_ENV_FILE"] = str(elsewhere)
    r = subprocess.run(
        [BASH, str(hook)],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(bad)}}),
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "AI-first warning" in json.loads(r.stdout)["systemMessage"], (
        "OBSIDIAN_ENV_FILE in the platform's native spelling must be read"
    )


def test_validate_hook_accepts_crlf_notes(tmp_path):
    """A note saved with CRLF line endings (a Windows editor, git autocrlf) used to
    fail every delimiter check because each line carried a trailing carriage
    return, so a valid note was reported as having no frontmatter. The checks
    now read a CR-free copy; a valid CRLF note is silent and an invalid one still
    warns."""
    hook = REPO_ROOT / "hooks/validate-ai-first.sh"
    vault = tmp_path / "vault"
    vault.mkdir()
    good = vault / "good.md"
    good.write_bytes(
        "---\r\ntype: note\r\ndate: 2026-09-02\r\ntags: [t]\r\nai-first: true\r\n---\r\n\r\n"
        "## For future agent\r\n\r\nA CRLF note that follows every rule.\r\n".encode("utf-8")
    )
    bad = vault / "bad.md"
    bad.write_bytes("# no frontmatter\r\njust text\r\n".encode("utf-8"))

    def run(f):
        return subprocess.run(
            [BASH, str(hook)],
            input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(f)}}),
            env=dict(os.environ, OBSIDIAN_VAULT_PATH=str(vault)),
            capture_output=True,
            text=True,
        )

    r = run(good)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "", f"a valid CRLF note must be silent, got: {r.stdout[:200]}"
    r = run(bad)
    assert r.returncode == 0, r.stderr
    assert "frontmatter" in json.loads(r.stdout)["systemMessage"]

    # The Python scans (banned characters, secret material) read the real file,
    # not the CR-free copy, and must still fire on a CRLF note.
    dirty = vault / "dirty.md"
    dirty.write_bytes(
        (
            "---\r\ntype: note\r\ndate: 2026-09-02\r\ntags: [t]\r\nai-first: true\r\n---\r\n\r\n"
            "## For future agent\r\n\r\nA dash \u2014 here and key sk-test1234567890abcdefghijklmnop here\r\n"
        ).encode("utf-8")
    )
    r = run(dirty)
    assert r.returncode == 0, r.stderr
    msg = json.loads(r.stdout)["systemMessage"]
    assert "U+2014" in msg, f"the banned-character scan must run on a CRLF note, got: {msg[:300]}"
    assert "secret material" in msg, f"the secret scan must run on a CRLF note, got: {msg[:300]}"


def test_validate_hook_leaves_posix_backslash_paths_alone(tmp_path):
    """A backslash is a legal character in a macOS or Linux filename. The path
    normalization runs only on Windows shells, so such a path must still be
    found and validated elsewhere."""
    if os.name == "nt":
        pytest.skip("a backslash cannot be part of a Windows filename")
    hook = REPO_ROOT / "hooks/validate-ai-first.sh"
    vault = tmp_path / "vault"
    odd = vault / "back\\slash"
    odd.mkdir(parents=True)
    bad = odd / "bad.md"
    bad.write_text("# no frontmatter\n", encoding="utf-8")
    r = subprocess.run(
        [BASH, str(hook)],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(bad)}}),
        env=dict(os.environ, OBSIDIAN_VAULT_PATH=str(vault)),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "frontmatter" in json.loads(r.stdout)["systemMessage"]


def test_bash_constant_never_resolves_to_wsl():
    """On Windows, CreateProcess's search order checks System32 before PATH, so a
    bare "bash" silently becomes WSL's launcher when WSL is installed, even though
    shutil.which("bash") still finds Git Bash (#308). Every subprocess call in
    this suite uses the resolved BASH constant instead of the bare name because of
    that: this pins the resolution itself, via `uname`, which reports "Linux ...
    microsoft-standard-WSL2" from WSL's bash and "MINGW64_NT ... Msys" from Git
    Bash."""
    if os.name != "nt":
        pytest.skip("the bare-bash/WSL collision only exists on Windows")
    r = subprocess.run([BASH, "-c", "uname -s"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "MINGW" in r.stdout or "MSYS" in r.stdout, (
        f"BASH resolved to something other than Git Bash: {r.stdout!r} - "
        "did the resolution fall through to WSL's bash.exe?"
    )


def test_research_config_honors_env_file_override(tmp_path):
    """OBSIDIAN_ENV_FILE points every half of the toolkit at one file. The MCP
    server and the write-time hook already honored it (#160); the research
    loaders and the retrieval eval read only the default location, so a user
    whose config lives elsewhere (or whose HOME and USERPROFILE disagree on
    Windows) could not steer them. Environment still wins over the file."""
    vault = tmp_path / "vault"
    vault.mkdir()
    env_file = tmp_path / "elsewhere.env"
    env_file.write_text(
        f"OBSIDIAN_VAULT_PATH={vault}\nPERPLEXITY_API_KEY=pplx-from-the-override-file\n",
        encoding="utf-8",
    )
    empty_home = tmp_path / "home"
    empty_home.mkdir()
    base_env = dict(os.environ, OBSIDIAN_ENV_FILE=str(env_file),
                    HOME=str(empty_home), USERPROFILE=str(empty_home))
    base_env.pop("OBSIDIAN_VAULT_PATH", None)
    base_env.pop("PERPLEXITY_API_KEY", None)

    def run(code: str, **extra: str):
        r = subprocess.run(
            [sys.executable, "-c", code], cwd=REPO_ROOT, env=dict(base_env, **extra),
            capture_output=True, text=True, encoding="utf-8",
        )
        assert r.returncode == 0, r.stderr
        return r.stdout.strip().splitlines()

    # Each loader alone, in its own interpreter, so neither can piggyback on the other.
    out = run("from scripts.research.lib import config; print(config.VAULT_PATH)")
    assert out == [str(vault)], "config.py must read the vault path from OBSIDIAN_ENV_FILE"
    out = run(
        "import os; from scripts.research.lib import source_config; "
        "print(source_config._ENV_PATH); print(os.environ.get('PERPLEXITY_API_KEY', ''))"
    )
    assert out == [str(env_file), "pplx-from-the-override-file"], (
        "source_config.py must load the override file itself"
    )
    # The environment still wins over the file.
    out = run(
        "import os; from scripts.research.lib import source_config; "
        "print(os.environ['PERPLEXITY_API_KEY'])",
        PERPLEXITY_API_KEY="pplx-from-the-environment",
    )
    assert out == ["pplx-from-the-environment"], "a variable set in the environment must not be overridden by the file"


@pytest.mark.parametrize("os_name", ["nt", "posix"])
def test_retrieval_eval_external_cmd_splitting(tmp_path, os_name):
    """RETRIEVAL_EVAL_EXTERNAL_CMD must survive Windows paths. POSIX shlex eats
    the backslashes of a Windows path, and blindly doubling them would corrupt a
    quoted literal such as '\\d+'; on Windows the command is split in non-POSIX
    mode with one layer of surrounding quotes removed, elsewhere POSIX rules
    apply unchanged. Exercised through the real function in a subprocess, once
    per branch: the function keys on the os.name string alone, so the subprocess
    sets it and the ubuntu CI runner covers the Windows split as well (the first
    version gated the Windows cases on the runner's own os.name, so CI never ran
    them; found in the #243 review)."""
    script = REPO_ROOT / "scripts/eval/retrieval_eval.py"
    bs = "\\"
    if os_name == "nt":
        plain = bs.join(["C:", "Users", "me", "engine.sh"])
        spaced = bs.join(["C:", "Program Files", "x", "engine.sh"])
        unc = bs + bs + bs.join(["server", "share", "engine.exe"])
        cases = {
            f"bash {plain}": ["bash", plain],
            f'bash "{spaced}" --flag': ["bash", spaced, "--flag"],
            f"tool --regex '{bs}d+'": ["tool", "--regex", bs + "d+"],
            f"{unc} q": [unc, "q"],
        }
    else:
        cases = {
            f"bash /tmp/engine.sh --regex '{bs}d+'": ["bash", "/tmp/engine.sh", "--regex", bs + "d+"],
            'bash "/tmp/my dir/engine.sh"': ["bash", "/tmp/my dir/engine.sh"],
        }
    # The JSON form is the exact grammar on every platform: spaces, embedded
    # quotes, an empty argument and backslashes pass through untouched.
    json_argv = ["bash", "some dir/engine.sh", "--out", 'say "hi"', "", bs + "d+"]
    cases[json.dumps(json_argv)] = json_argv
    # And one written by hand, the way a user would put it in the environment:
    # JSON escapes only (\" for a quote, \\ for a backslash).
    literal = '["bash", "C:/Program Files/x/engine.sh", "--out", "say \\"hi\\"", "", "\\\\d+"]'
    cases[literal] = ["bash", "C:/Program Files/x/engine.sh", "--out", 'say "hi"', "", bs + "d+"]
    code = (
        "import importlib.util, json, sys; "
        f"spec = importlib.util.spec_from_file_location('retrieval_eval', {str(script)!r}); "
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
        # Set after the imports: pathlib and friends pick their flavour at import time.
        "import os; os.name = sys.argv[2]; "
        "print(json.dumps([m._split_external_cmd(c) for c in json.loads(sys.argv[1])]))"
    )
    r = subprocess.run(
        [sys.executable, "-c", code, json.dumps(list(cases)), os_name],
        cwd=REPO_ROOT, env=dict(os.environ, OBSIDIAN_VAULT_PATH=str(tmp_path)),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout.strip().splitlines()[-1]) == list(cases.values())
