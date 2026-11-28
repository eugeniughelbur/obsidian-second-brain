"""scripts/checkin.py and scripts/check_notes.py: /obsidian-checkin asks the owner
whether old notes still hold, and hook-less hosts get the write-time check.
These drive both CLIs the way the command does."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from _bash import BASH

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
CHECKIN = SCRIPTS / "checkin.py"
CHECK_NOTES = SCRIPTS / "check_notes.py"
TODAY = "2026-10-24"


def note(fm: str, body: str = "## For future agent\nA person.\n\n- Lives in Lisbon\n") -> str:
    return f"---\n{fm}\ntags: [person]\nai-first: true\n---\n\n{body}"


def checkin(vault: Path, *args: str, today: str = TODAY) -> tuple[int, str, str]:
    r = subprocess.run(
        [sys.executable, str(CHECKIN), "--path", str(vault), "--today", today, *args],
        capture_output=True, text=True,
    )
    return r.returncode, r.stdout, r.stderr


def picked(vault: Path, *args: str) -> list[str]:
    code, out, err = checkin(vault, "pick", *args)
    assert code == 0, err
    return [c["note"] for c in json.loads(out)]


@pytest.fixture
def vault(tmp_path):
    people = tmp_path / "people"
    people.mkdir()
    (people / "Ana.md").write_text(note("date: 2026-01-10\ntype: person"), encoding="utf-8")
    (people / "Mum.md").write_text(
        note("date: 2026-03-01\ntype: person").replace("tags: [person]", "tags: [person, family]"),
        encoding="utf-8")
    (people / "Fresh.md").write_text(note("date: 2026-10-20\ntype: person"), encoding="utf-8")
    (people / "Gone.md").write_text(note("date: 2026-01-01\ntype: person\nstatus: archived"),
                                    encoding="utf-8")
    (people / "Quiet.md").write_text(note("date: 2026-01-01\ntype: person\ncheckin: never"),
                                     encoding="utf-8")
    return tmp_path


def test_pick_puts_family_first_and_skips_fresh_closed_and_opted_out(vault):
    assert picked(vault) == ["people/Mum.md", "people/Ana.md"]


def test_last_checked_beats_a_newer_updated_and_updated_beats_date(vault):
    ana = vault / "people" / "Ana.md"
    ana.write_text(note("date: 2026-01-10\nupdated: 2026-10-20\ntype: person"), encoding="utf-8")
    assert "people/Ana.md" not in picked(vault)
    ana.write_text(note("date: 2026-01-10\nupdated: 2026-10-20\nlast-checked: 2026-05-01\n"
                        "type: person"), encoding="utf-8")
    assert "people/Ana.md" in picked(vault)


def test_pick_never_holds_more_than_max_open(vault):
    assert checkin(vault, "ask", "--note", "people/Ana.md", "--fact", "Lives in Lisbon")[0] == 0
    assert picked(vault, "--max-open", "1") == []
    assert picked(vault, "--max-open", "2") == ["people/Mum.md"]


def test_reminders_repeat_the_full_card_until_answered(vault):
    checkin(vault, "ask", "--note", "people/Mum.md", "--fact", "Lives in Porto", "--fact", "Retired")
    checkin(vault, "ask", "--note", "people/Ana.md", "--fact", "Lives in Lisbon")
    first = checkin(vault, "message")[1]
    assert first.startswith("Vault check-in: 2 notes to confirm")
    assert "**1. Mum** (facts from 1 Mar)" in first and "- Retired" in first
    again = checkin(vault, "message", today="2026-10-25")[1]
    assert again.startswith("Reminder 1: still waiting on 2 notes")
    assert "- Lives in Porto" in again and "- Lives in Lisbon" in again


def test_peek_renders_without_counting_a_send(vault):
    checkin(vault, "ask", "--note", "people/Ana.md", "--fact", "Lives in Lisbon")
    checkin(vault, "message", "--peek")
    assert checkin(vault, "message")[1].startswith("Vault check-in")


def test_done_same_stamps_last_checked_and_keeps_the_rest_byte_exact(vault):
    ana = vault / "people" / "Ana.md"
    ana.write_bytes(note("date: 2026-01-10\ntype: person").replace("\n", "\r\n").encode())
    checkin(vault, "ask", "--note", "people/Ana.md", "--fact", "Lives in Lisbon")
    checkin(vault, "message")
    code, out, err = checkin(vault, "done", "--number", "1", "--outcome", "same")
    assert code == 0, err
    assert json.loads(out)["open_left"] == 0
    raw = ana.read_bytes().decode()
    assert "date: 2026-01-10\r\nlast-checked: 2026-10-24\r\ntype: person" in raw
    assert "\n" not in raw.replace("\r\n", "")
    assert checkin(vault, "message")[1].strip() == ""


def test_skip_closes_without_a_stamp_and_waits_out_the_window(vault):
    checkin(vault, "ask", "--note", "people/Ana.md", "--fact", "Lives in Lisbon")
    checkin(vault, "message")
    checkin(vault, "done", "--number", "1", "--outcome", "skipped")
    assert "last-checked" not in (vault / "people" / "Ana.md").read_text(encoding="utf-8")
    assert "people/Ana.md" not in picked(vault)
    code, out, _ = checkin(vault, "pick", today="2026-11-10")
    assert "people/Ana.md" in [c["note"] for c in json.loads(out)]


def test_a_corrupt_queue_stops_the_run_instead_of_dropping_open_questions(vault):
    (vault / ".checkin.json").write_text("{not json", encoding="utf-8")
    code, _, err = checkin(vault, "message")
    assert code != 0 and "not valid JSON" in err
    assert (vault / ".checkin.json").read_text(encoding="utf-8") == "{not json"


def test_ask_refuses_more_than_three_facts(vault):
    facts = [a for f in ("a", "b", "c", "d") for a in ("--fact", f)]
    code, _, err = checkin(vault, "ask", "--note", "people/Ana.md", *facts)
    assert code != 0 and "1 to 3 facts" in err


# check_notes.py

GOOD = (
    "---\ndate: 2026-10-24\ntype: idea\ntags: [idea]\nai-first: true\n---\n\n"
    "## For future agent\nA note \u2014 with a dash, a [[A\u2014B]] link.\n"
    "\u4e2d\u6587\u2014\u2014\u7834\u6298\u53f7\n"
)


def check(vault: Path, *args: str) -> tuple[int, dict]:
    r = subprocess.run([sys.executable, str(CHECK_NOTES), "--path", str(vault), *args],
                       capture_output=True, text=True)
    return r.returncode, json.loads(r.stdout)


@pytest.mark.skipif(BASH == "bash", reason="needs bash on PATH for the hook")
def test_check_notes_fails_then_fix_rewrites_prose_only(tmp_path):
    (tmp_path / "n.md").write_text(GOOD, encoding="utf-8")
    code, out = check(tmp_path, "n.md")
    assert code == 1 and out["failed"][0]["path"] == "n.md"
    code, out = check(tmp_path, "--fix", "n.md")
    text = (tmp_path / "n.md").read_text(encoding="utf-8")
    assert code == 0 and out["fixed"] == ["n.md"], out
    assert "A note - with a dash" in text
    assert "[[A\u2014B]]" in text
    assert "\u4e2d\u6587\u2014\u2014" in text


@pytest.mark.skipif(BASH == "bash", reason="needs bash on PATH for the hook")
def test_check_notes_reports_what_it_cannot_fix(tmp_path):
    (tmp_path / "bare.md").write_text("# Bare\n\nNo frontmatter.\n", encoding="utf-8")
    code, out = check(tmp_path, "--fix", "bare.md")
    assert code == 1 and "frontmatter" in " ".join(out["failed"][0]["issues"])


def test_check_notes_changed_picks_up_new_and_modified_notes_only(tmp_path):
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)
    git("init", "-q")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x")
    (tmp_path / "new note.md").write_text(GOOD, encoding="utf-8")
    (tmp_path / "skip.txt").write_text("x", encoding="utf-8")
    sys.path.insert(0, str(SCRIPTS))
    try:
        from check_notes import changed_notes
    finally:
        sys.path.remove(str(SCRIPTS))
    assert changed_notes(tmp_path) == ["new note.md"]


def test_check_notes_fails_loudly_when_validator_hook_is_missing(tmp_path):
    """Regression for #421: a missing hooks/validate-ai-first.sh must error out
    rather than exit 0 and report every note as clean, and --fix must not mutate
    the note before failing."""
    import shutil

    isolated = tmp_path / "install"
    scripts_copy = isolated / "scripts"
    scripts_copy.mkdir(parents=True)
    for name in ("check_notes.py", "note_io.py", "sweep_non_ascii.py"):
        shutil.copy2(SCRIPTS / name, scripts_copy / name)

    vault = tmp_path / "vault"
    vault.mkdir()
    note_file = vault / "n.md"
    note_file.write_text(GOOD, encoding="utf-8")
    before = note_file.read_bytes()

    r = subprocess.run(
        [sys.executable, str(scripts_copy / "check_notes.py"), "--path", str(vault), "--fix", "n.md"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert r.returncode == 2, r.stdout
    assert "validate-ai-first.sh" in r.stderr
    assert r.stdout.strip() == ""
    assert note_file.read_bytes() == before


def test_check_notes_missing_jq_fails_loudly_with_no_writes(tmp_path):
    """Missing jq must exit 2 instead of silently passing a broken note."""
    import os

    vault = tmp_path / "vault"
    vault.mkdir()
    note_file = vault / "n.md"
    note_file.write_text(GOOD, encoding="utf-8")
    before = note_file.read_bytes()

    # PATH with bash (if available) but no jq: must fail with exit 2 and 0 writes.
    bin_dir = tmp_path / "no-jq-bin"
    bin_dir.mkdir()
    if BASH != "bash" and Path(BASH).is_file():
        link = bin_dir / Path(BASH).name
        try:
            link.symlink_to(BASH)
        except OSError:
            pass
    env = {k: v for k, v in os.environ.items() if k != "PATH"}
    env["PATH"] = str(bin_dir)

    r = subprocess.run(
        [sys.executable, str(CHECK_NOTES), "--path", str(vault), "--fix", "n.md"],
        env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert "jq" in r.stderr.lower() or "bash" in r.stderr.lower()
    assert r.stdout.strip() == ""
    assert note_file.read_bytes() == before


@pytest.mark.skipif(BASH == "bash", reason="needs bash on PATH for the hook")
def test_check_notes_fix_does_not_mutate_note_when_hook_errors(tmp_path):
    """If the validator hook exits non-zero (e.g. exit 37), --fix must fail with
    exit 2 and leave the note's raw bytes untouched."""
    import shutil

    isolated = tmp_path / "install"
    scripts_copy = isolated / "scripts"
    hooks_copy = isolated / "hooks"
    scripts_copy.mkdir(parents=True)
    hooks_copy.mkdir(parents=True)
    for name in ("check_notes.py", "note_io.py", "sweep_non_ascii.py"):
        shutil.copy2(SCRIPTS / name, scripts_copy / name)
    (hooks_copy / "validate-ai-first.sh").write_bytes(b"echo broken >&2\nexit 37\n")

    vault = tmp_path / "vault"
    vault.mkdir()
    note_file = vault / "n.md"
    note_file.write_text(GOOD, encoding="utf-8")
    before = note_file.read_bytes()

    r = subprocess.run(
        [sys.executable, str(scripts_copy / "check_notes.py"), "--path", str(vault), "--fix", "n.md"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert "37" in r.stderr
    assert r.stdout.strip() == ""
    assert note_file.read_bytes() == before


def test_check_notes_rejects_outside_vault_missing_file_and_nongit_changed(tmp_path):
    """Outside-vault paths, missing explicit files, and --changed outside git
    must all exit 2 instead of silently passing with checked: 0."""
    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text(GOOD, encoding="utf-8")
    before = outside.read_bytes()

    r_out = subprocess.run(
        [sys.executable, str(CHECK_NOTES), "--path", str(vault), "--fix", str(outside)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert r_out.returncode == 2 and "outside vault" in r_out.stderr
    assert r_out.stdout.strip() == ""
    assert outside.read_bytes() == before

    # A symlink inside the vault pointing outside must also be rejected.
    escape_link = vault / "escape.md"
    try:
        escape_link.symlink_to(outside)
    except OSError:
        escape_link = None
    if escape_link is not None:
        r_sym = subprocess.run(
            [sys.executable, str(CHECK_NOTES), "--path", str(vault), "--fix", "escape.md"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert r_sym.returncode == 2 and "outside vault" in r_sym.stderr
        assert r_sym.stdout.strip() == ""
        assert outside.read_bytes() == before

    r_missing = subprocess.run(
        [sys.executable, str(CHECK_NOTES), "--path", str(vault), "does-not-exist.md"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert r_missing.returncode == 2 and "not found" in r_missing.stderr
    assert r_missing.stdout.strip() == ""

    r_nongit = subprocess.run(
        [sys.executable, str(CHECK_NOTES), "--path", str(vault), "--changed"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert r_nongit.returncode == 2 and "git status failed" in r_nongit.stderr
    assert r_nongit.stdout.strip() == ""


def test_hook_issues_rejects_missing_hook_nonzero_exit_and_bad_json(tmp_path, monkeypatch, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()
    note_path = vault / "n.md"
    note_path.write_text("# Bare\n", encoding="utf-8")

    sys.path.insert(0, str(SCRIPTS))
    try:
        import check_notes

        missing = tmp_path / "missing.sh"
        monkeypatch.setattr(check_notes, "HOOK", missing)
        with pytest.raises(FileNotFoundError, match="validate-ai-first|not found"):
            check_notes.hook_issues(vault, note_path)

        fake_hook = tmp_path / "fake.sh"
        fake_hook.write_bytes(b"exit 37\n")
        monkeypatch.setattr(check_notes, "HOOK", fake_hook)
        monkeypatch.setattr(check_notes, "_require_validator_env", lambda: "bash")

        def _fake_run(returncode: int, stdout: str = "", stderr: str = ""):
            return lambda *a, **kw: subprocess.CompletedProcess(a[0], returncode, stdout, stderr)

        monkeypatch.setattr(check_notes.subprocess, "run", _fake_run(37, stderr="boom"))
        with pytest.raises(RuntimeError, match="37"):
            check_notes.hook_issues(vault, note_path)

        for bad_stdout in ("[]", '{"systemMessage": null}', "not-json"):
            monkeypatch.setattr(check_notes.subprocess, "run", _fake_run(0, stdout=bad_stdout))
            with pytest.raises(RuntimeError, match="invalid JSON|unexpected payload"):
                check_notes.hook_issues(vault, note_path)

        # PermissionError during --fix mid-batch must return 2 and name already-fixed files.
        first = vault / "first.md"
        second = vault / "second.md"
        first.write_text(GOOD, encoding="utf-8")
        second.write_text(GOOD, encoding="utf-8")
        monkeypatch.setattr(check_notes, "hook_issues", lambda _v, _n: [])

        def _fix_second_denied(path: Path) -> int:
            if path == second:
                raise PermissionError("read-only")
            return 1

        monkeypatch.setattr(check_notes, "fix_chars", _fix_second_denied)
        monkeypatch.setattr(
            sys, "argv", ["check_notes.py", "--path", str(vault), "--fix", "first.md", "second.md"]
        )
        assert check_notes.main() == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "first.md" in captured.err and "already fixed before abort" in captured.err
    finally:
        sys.path.remove(str(SCRIPTS))


@pytest.mark.skipif(BASH == "bash", reason="needs bash on PATH for the hook")
def test_validate_hook_strict_mode_exits_2_without_jq(tmp_path):
    """Invoking hooks/validate-ai-first.sh directly in strict mode without jq
    must exit 2 instead of silently exiting 0."""
    hook = SCRIPTS.parent / "hooks" / "validate-ai-first.sh"
    vault = tmp_path / "vault"
    vault.mkdir()
    note_file = vault / "bare.md"
    note_file.write_text("# Bare\n", encoding="utf-8")

    env = {
        "PATH": str(tmp_path / "empty-bin"),
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "OBSIDIAN_VAULT_PATH": str(vault),
        "OBSIDIAN_CHECK_NOTES_STRICT": "1",
    }
    (tmp_path / "empty-bin").mkdir()

    r = subprocess.run(
        [BASH, str(hook)],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(note_file)}}),
        env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert "jq" in r.stderr.lower()
    assert r.stdout.strip() == ""
