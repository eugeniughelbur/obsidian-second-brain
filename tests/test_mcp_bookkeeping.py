"""Service-side bookkeeping for MCP writes.

An agent capturing from another project may only write to Inbox/ and cannot
touch the log or the catalog, so a note saved through the server used to sit
unlogged, unindexed and unvalidated until some vault session happened to run
(#255). The server now does that bookkeeping after every successful write and
reports each part under its own key; anything beyond the vault (commit, sync)
is an opt-in post-write command it runs bounded and never raises from.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "integrations" / "obsidian-mcp-server"))

INDEX_WITH_INBOX = "# Index\n\n## Root\n\n- [[Home]] - dashboard.\n\n## Inbox/\n\nQuarantine.\n\n- [[Inbox/2026-01-01 - seed]] - spent.\n\n## Boards/\n\n- [[Boards/Work|Work]] - kanban.\n"


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    v = tmp_path / "vault"
    (v / "Inbox").mkdir(parents=True)
    (v / "Logs").mkdir()
    (v / "Templates").mkdir()
    (v / "raw").mkdir()
    (v / "index.md").write_text(INDEX_WITH_INBOX, encoding="utf-8")
    (v / "note.md").write_text("---\ntype: note\ndate: 2026-01-01\ntags: [t]\nai-first: true\n---\n\n## For future agent\n\nhello\n", encoding="utf-8")
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(v))
    monkeypatch.delenv("OBSIDIAN_BOOKKEEPING", raising=False)
    monkeypatch.delenv("OBSIDIAN_POST_WRITE_CMD", raising=False)
    import vault_ops
    importlib.reload(vault_ops)
    return v, vault_ops


def _today_log(v: Path) -> str:
    files = sorted((v / "Logs").glob("*.md"))
    assert len(files) == 1, files
    return files[0].read_text(encoding="utf-8")


def test_capture_is_validated_logged_and_indexed(vault):
    v, ops = vault
    res = ops.capture_idea("Decision of 2026-01-02: keep the union merge.\nMore detail.", tags=["codex", "capture"])
    assert res["saved"].startswith("Inbox/"), res
    assert res["validation"]["ok"] is True and res["validation"]["issues"] == [], res
    assert res["index"] == "index.md '## Inbox/' entry added", res
    assert res["log"].startswith("Logs/"), res
    assert "post_write" not in res, "no post-write command was configured"
    log = _today_log(v)
    assert " - capture | " in log and f"[[{res['saved'][:-3]}]]" in log and "(tags: codex, capture)" in log
    assert log.startswith("---\ntype: log\n"), "a new day file carries the log frontmatter"
    index = (v / "index.md").read_text(encoding="utf-8")
    inbox = index.split("## Inbox/")[1].split("## Boards/")[0]
    assert f"- [[{res['saved'][:-3]}]] - `type: idea`, captured" in inbox
    assert inbox.index("seed") < inbox.index(res["saved"][:-3]), "new entry goes after the last bullet of the section"


def test_log_falls_back_to_log_md_when_logs_dir_is_absent(vault, monkeypatch):
    v, ops = vault
    (v / "Logs").rmdir()
    (v / "log.md").write_text("# Log\n", encoding="utf-8")
    res = ops.save_note("A note", "valid summary line")
    assert res["log"] == "log.md", res
    assert "\n## [" in (v / "log.md").read_text(encoding="utf-8") and "] capture | A note" in (v / "log.md").read_text(encoding="utf-8")


def test_index_without_a_matching_section_is_reported_not_guessed(vault):
    v, ops = vault
    (v / "index.md").write_text("# Index\n\n## Root\n\n- [[Home]] - dashboard.\n", encoding="utf-8")
    res = ops.capture_idea("no section for me")
    assert res["index"] == "index.md has no '## Inbox/' section; no entry added", res
    assert "[[Inbox/" not in (v / "index.md").read_text(encoding="utf-8")
    assert (v / res["saved"]).is_file(), "the note itself is still saved"


def test_bookkeeping_can_be_switched_off(vault, monkeypatch):
    v, ops = vault
    monkeypatch.setenv("OBSIDIAN_BOOKKEEPING", "0")
    res = ops.capture_idea("quiet capture")
    assert set(res) == {"saved"}, res
    assert not list((v / "Logs").glob("*.md"))


def test_writes_to_the_log_and_catalog_are_never_logged(vault):
    v, ops = vault
    res = ops.update_note("index.md", append="- [[note]] - added by hand.")
    assert "updated" in res and "log" not in res and "validation" not in res, res
    assert not list((v / "Logs").glob("*.md")), "logging a catalog edit would loop forever"


def test_update_replace_and_move_carry_bookkeeping(vault):
    v, ops = vault
    up = ops.update_note("note.md", append="more")
    assert up["log"].startswith("Logs/") and up["validation"]["ok"] is True, up
    rp = ops.replace_text("note.md", "hello", "goodbye")
    assert rp["replacements"] == 1 and rp["log"].startswith("Logs/"), rp
    (v / "wiki").mkdir()
    mv = ops.move_note("note.md", "wiki/note.md")
    assert mv["moved"] == "note.md" and mv["log"].startswith("Logs/"), mv
    log = _today_log(v)
    assert " - update | [[note]] appended" in log and " - edit | [[note]] text replaced" in log and " - move | note.md -> [[wiki/note]]" in log


def test_post_write_command_runs_with_the_vault_note_and_action(vault, monkeypatch, tmp_path):
    v, ops = vault
    script = tmp_path / "hook.py"
    out = tmp_path / "argv.json"
    script.write_text(f"import json, sys; json.dump(sys.argv[1:], open({str(out)!r}, 'w'))\n", encoding="utf-8")
    monkeypatch.setenv("OBSIDIAN_POST_WRITE_CMD", f'"{sys.executable}" "{script}"')
    res = ops.capture_idea("with a post-write command")
    assert res["post_write"] == {"ran": True, "ok": True, "detail": "ok"}, res
    assert json.loads(out.read_text(encoding="utf-8")) == [str(v), res["saved"], "capture"]


def test_post_write_failures_are_reported_never_raised(vault, monkeypatch, tmp_path):
    v, ops = vault
    failing = tmp_path / "fail.py"
    failing.write_text("import sys; print('push failed: offline', file=sys.stderr); sys.exit(1)\n", encoding="utf-8")
    monkeypatch.setenv("OBSIDIAN_POST_WRITE_CMD", f'"{sys.executable}" "{failing}"')
    res = ops.capture_idea("post-write fails")
    assert res["post_write"] == {"ran": True, "ok": False, "detail": "push failed: offline"}, res
    assert (v / res["saved"]).is_file() and res["log"].startswith("Logs/"), "the note and its log line are unaffected"

    slow = tmp_path / "slow.py"
    slow.write_text("import time; time.sleep(5)\n", encoding="utf-8")
    monkeypatch.setenv("OBSIDIAN_POST_WRITE_CMD", f'"{sys.executable}" "{slow}"')
    monkeypatch.setenv("OBSIDIAN_POST_WRITE_TIMEOUT", "1")
    res = ops.capture_idea("post-write hangs")
    assert res["post_write"]["ran"] is True and res["post_write"]["ok"] is False and "timed out" in res["post_write"]["detail"], res

    monkeypatch.setenv("OBSIDIAN_POST_WRITE_CMD", "no-such-command-xyz")
    res = ops.capture_idea("post-write missing")
    assert res["post_write"]["ran"] is False and "command not found" in res["post_write"]["detail"], res


def test_post_write_cmd_split_strips_windows_quotes(vault):
    """On Windows, non-POSIX shlex keeps the quote marks, so a quoted
    interpreter path reached subprocess as '"C:\\...\\python.exe"' and was
    never found. Found by the Windows CI job; this pins the split on any OS."""
    _, ops = vault
    cmd = r'"C:\Program Files\Python\python.exe" "C:\hooks\post write.py" --flag'
    assert ops._split_post_write_cmd(cmd, windows=True) == [
        r"C:\Program Files\Python\python.exe", r"C:\hooks\post write.py", "--flag",
    ]
    assert ops._split_post_write_cmd('"/usr/bin/python3" "/tmp/a b.py"', windows=False) == [
        "/usr/bin/python3", "/tmp/a b.py",
    ]


def test_index_summary_never_leaves_a_wikilink_open(vault):
    """A capture that cites an earlier note near the 140-character cut used to
    leave its catalog line ending in an open `[[...`; one live vault had about
    170 such lines in two months of captures."""
    v, ops = vault
    cited = "Inbox/2026-09-25 - leane-workbook-review-completed"
    first = "Laser reconciliation completed on 25 September 2026. " * 2 + f"Following [[{cited}]]."
    assert first.index("[[") < 140 < first.index("]]"), "the plain cut would land inside the link"
    res = ops.capture_idea(first + "\nMore detail.")
    index = (v / "index.md").read_text(encoding="utf-8")
    line = next(x for x in index.splitlines() if x.startswith(f"- [[{res['saved'][:-3]}]]"))
    assert line.endswith(f"[[{cited}]]"), line
    assert line.count("[[") == line.count("]]"), line


@pytest.mark.parametrize(
    ("text", "limit", "expected"),
    [
        ("see [[A]] now", 140, "see [[A]] now"),
        ("a\t b \n second line", 140, "a b"),
        ("0123456789 [[Target note]] tail", 20, "0123456789 [[Target note]]"),
        ("0123456789 [[Target note never closes", 20, "0123456789"),
        ("0123456789012345678[[X]] tail", 20, "0123456789012345678[[X]]"),
        ("0123456789 [[Targe]] tail", 19, "0123456789 [[Targe]]"),
        ("[[A]] 0123456789012345678901", 20, "[[A]] 01234567890123"),
    ],
)
def test_summary_excerpt_cuts_outside_wikilinks(vault, text, limit, expected):
    _, ops = vault
    assert ops._summary_excerpt(text, limit) == expected
