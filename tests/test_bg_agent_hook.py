"""Runtime tests for the PostCompact background agent hook.

The audit's completeness critic flagged this as the highest-risk untested
surface: it writes to the vault UNATTENDED with permissions skipped. These
tests exercise the real script end-to-end - gates, stdin parsing, transcript
extraction, prompt construction, and the spawn - against a stub `claude`
binary, so nothing real is ever written.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / "hooks" / "obsidian-bg-agent.sh"


def _run_hook(stdin: str, env_extra: dict, tmp_path: Path,
              stub_writes: list[str] | None = None) -> subprocess.CompletedProcess:
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    record = tmp_path / "claude-invocation.txt"
    stub = stub_dir / "claude"
    # Capture args AND stdin: the prompt is fed to `claude -p` via stdin, not
    # as an argv element (avoids the ~32K Windows command-line limit), so the
    # summary now arrives on stdin rather than in "$@".
    body = (
        "#!/usr/bin/env bash\n"
        f'{{ echo "CWD=$PWD"; printf \'ARG=%s\\n\' "$@"; echo "STDIN<<<"; cat; }} > "{record}"\n'
    )
    # stub_writes names vault-relative paths the stub should create, standing in
    # for notes the real agent would propagate. Paths, not a count: a loop over
    # `seq 1 $n` looks equivalent but BSD seq counts DOWN when first > last, so
    # `seq 1 0` yields "1 0" and the write-nothing case silently writes two
    # files - which reads as a hook bug rather than a harness one.
    for rel in stub_writes or []:
        body += f'mkdir -p "$(dirname "$PWD/{rel}")" && printf \'stub\\n\' > "$PWD/{rel}"\n'
    stub.write_text(body, encoding="utf-8")
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{stub_dir}:{os.environ['PATH']}", **env_extra}
    # Clear every var the hook reads, so a developer whose own shell has these
    # exported does not get different results from CI.
    env.pop("OBSIDIAN_VAULT_PATH", None)
    env.pop("OBSIDIAN_BG_AGENT_ENABLED", None)
    env.pop("OBSIDIAN_BG_COUNT_IGNORE", None)
    env.update(env_extra)
    return subprocess.run(["bash", str(HOOK)], input=stdin, env=env,
                          capture_output=True, text=True, timeout=30)


def test_inert_without_vault_path(tmp_path):
    r = _run_hook("{}", {}, tmp_path)
    assert r.returncode == 0
    assert not (tmp_path / "claude-invocation.txt").exists()


def test_inert_without_enable_flag(tmp_path):
    vault = tmp_path / "vault"; vault.mkdir()
    r = _run_hook("{}", {"OBSIDIAN_VAULT_PATH": str(vault)}, tmp_path)
    assert r.returncode == 0
    assert not (tmp_path / "claude-invocation.txt").exists()


def test_garbage_stdin_exits_clean(tmp_path):
    vault = tmp_path / "vault"; vault.mkdir()
    r = _run_hook("this is not json{{", {
        "OBSIDIAN_VAULT_PATH": str(vault), "OBSIDIAN_BG_AGENT_ENABLED": "1",
    }, tmp_path)
    assert r.returncode == 0
    assert not (tmp_path / "claude-invocation.txt").exists()


def test_full_chain_spawns_agent_with_summary(tmp_path):
    vault = tmp_path / "vault"; vault.mkdir()
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"type": "user", "message": {"content": "noise"}}) + "\n" +
        json.dumps({"isCompactSummary": True,
                    "message": {"content": "SUMMARY-SENTINEL: shipped the widget,\nmet a new person"}}) + "\n",
        encoding="utf-8",
    )
    r = _run_hook(json.dumps({"transcript_path": str(transcript)}), {
        "OBSIDIAN_VAULT_PATH": str(vault), "OBSIDIAN_BG_AGENT_ENABLED": "1",
    }, tmp_path)
    assert r.returncode == 0
    record = tmp_path / "claude-invocation.txt"
    for _ in range(50):  # the spawn is async by design
        if record.exists() and record.read_text(encoding="utf-8").strip():
            break
        time.sleep(0.1)
    body = record.read_text(encoding="utf-8")
    assert f"CWD={vault}" in body, "agent must run inside the vault"
    assert "ARG=--dangerously-skip-permissions" in body
    assert "SUMMARY-SENTINEL" in body, "the compact summary must reach the prompt"
    assert "met a new person" in body, "multi-line summaries must survive the base64 hop"
    # The prompt must arrive via stdin, never as an argv element - passing it as
    # a command-line argument hits the ~32K CreateProcess limit on Git Bash for
    # Windows and dies silently ("Argument list too long").
    args_section, _, stdin_section = body.partition("STDIN<<<")
    assert "SUMMARY-SENTINEL" in stdin_section, "prompt must be delivered on stdin"
    assert "SUMMARY-SENTINEL" not in args_section, "prompt must not be an argv element"


def _read_run_log(vault: Path) -> list[dict]:
    runs = sorted((vault / ".claude-runs").glob("*.jsonl"))
    lines: list[dict] = []
    for f in runs:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                lines.append(json.loads(line))
    return lines


def test_run_log_records_starting_and_completed(tmp_path):
    vault = tmp_path / "vault"; vault.mkdir()
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"isCompactSummary": True,
                    "message": {"content": "shipped the widget"}}) + "\n",
        encoding="utf-8",
    )
    r = _run_hook(json.dumps({"transcript_path": str(transcript)}), {
        "OBSIDIAN_VAULT_PATH": str(vault), "OBSIDIAN_BG_AGENT_ENABLED": "1",
    }, tmp_path)
    assert r.returncode == 0
    entries: list[dict] = []
    for _ in range(50):  # the completed entry is appended from the async subshell
        entries = _read_run_log(vault)
        if any(e["status"] == "completed" for e in entries):
            break
        time.sleep(0.1)
    statuses = [e["status"] for e in entries]
    assert "starting" in statuses
    assert "completed" in statuses
    completed = next(e for e in entries if e["status"] == "completed")
    assert completed["exit_code"] == 0
    assert "duration_sec" in completed
    starting = next(e for e in entries if e["status"] == "starting")
    assert starting["summary_chars"] == len("shipped the widget")


def test_early_exit_is_logged_not_silent(tmp_path):
    vault = tmp_path / "vault"; vault.mkdir()
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"type": "user", "message": {"content": "no summary here"}}) + "\n",
        encoding="utf-8",
    )
    r = _run_hook(json.dumps({"transcript_path": str(transcript)}), {
        "OBSIDIAN_VAULT_PATH": str(vault), "OBSIDIAN_BG_AGENT_ENABLED": "1",
    }, tmp_path)
    assert r.returncode == 0
    assert not (tmp_path / "claude-invocation.txt").exists()
    statuses = [e["status"] for e in _read_run_log(vault)]
    assert "no_summary" in statuses, "a decision not to propagate must be recorded"


def test_project_hints_injected_only_when_opted_in(tmp_path):
    vault = tmp_path / "vault"; vault.mkdir()
    project = tmp_path / "project"; project.mkdir()
    (project / "CLAUDE.md").write_text(
        "# Project\n\nSome rules.\n\n"
        "## Vault propagation hints\n\nHINT-SENTINEL: route facts to the hub.\n\n"
        "## Other section\n\nirrelevant tail\n",
        encoding="utf-8",
    )
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"isCompactSummary": True,
                    "message": {"content": "did some work"}}) + "\n",
        encoding="utf-8",
    )
    stdin = json.dumps({"transcript_path": str(transcript), "cwd": str(project)})

    def _prompt_body():
        record = tmp_path / "claude-invocation.txt"
        for _ in range(50):
            if record.exists() and record.read_text(encoding="utf-8").strip():
                return record.read_text(encoding="utf-8")
            time.sleep(0.1)
        return record.read_text(encoding="utf-8")

    # Opted in: the hints section is injected, the surrounding sections are not.
    r = _run_hook(stdin, {
        "OBSIDIAN_VAULT_PATH": str(vault), "OBSIDIAN_BG_AGENT_ENABLED": "1",
        "CLAUDE_VAULT_PROPAGATION": "1",
    }, tmp_path)
    assert r.returncode == 0
    body = _prompt_body()
    assert "HINT-SENTINEL" in body, "opted-in project hints must reach the prompt"
    assert "irrelevant tail" not in body, "only the hints section may travel, not the whole CLAUDE.md"

    # Opted out (flag absent): no hints, even though the CLAUDE.md has the section.
    (tmp_path / "claude-invocation.txt").unlink(missing_ok=True)
    r = _run_hook(stdin, {
        "OBSIDIAN_VAULT_PATH": str(vault), "OBSIDIAN_BG_AGENT_ENABLED": "1",
    }, tmp_path)
    assert r.returncode == 0
    assert "HINT-SENTINEL" not in _prompt_body(), "hints must stay inert without CLAUDE_VAULT_PROPAGATION=1"


def test_launch_uses_strict_mcp_config(tmp_path):
    """The headless agent must launch with --strict-mcp-config. Its prompt
    declares MCP unavailable in the subprocess; without the flag the run loads
    every enabled MCP server and can seize a concurrent MCP-based bot's single
    session (e.g. a Telegram/Slack integration). Regression fence for #136."""
    vault = tmp_path / "vault"; vault.mkdir()
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"isCompactSummary": True,
                    "message": {"content": "SUMMARY-SENTINEL: did a thing"}}) + "\n",
        encoding="utf-8",
    )
    r = _run_hook(json.dumps({"transcript_path": str(transcript)}), {
        "OBSIDIAN_VAULT_PATH": str(vault), "OBSIDIAN_BG_AGENT_ENABLED": "1",
    }, tmp_path)
    assert r.returncode == 0
    record = tmp_path / "claude-invocation.txt"
    for _ in range(50):  # the spawn is async by design
        if record.exists() and record.read_text(encoding="utf-8").strip():
            break
        time.sleep(0.1)
    body = record.read_text(encoding="utf-8")
    assert "ARG=--strict-mcp-config" in body, "headless run must enforce filesystem-only MCP"


# --- files_changed -----------------------------------------------------------
# Without this field the completed line is identical for a run that wrote three
# notes and a run that wrote none - and the prompt instructs the agent to exit
# without changes when the summary holds nothing new, so the no-op is the common
# outcome, not an edge case. exit_code 0 was never evidence of a write.

def _completed_entry(vault: Path) -> dict:
    for _ in range(50):  # appended from the async subshell
        entries = _read_run_log(vault)
        done = [e for e in entries if e["status"] == "completed"]
        if done:
            return done[-1]
        time.sleep(0.1)
    raise AssertionError(f"no completed entry in run log: {_read_run_log(vault)}")


def _fire(tmp_path: Path, vault: Path, env_extra: dict, stub_writes=None):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"isCompactSummary": True,
                    "message": {"content": "did some work worth propagating"}}) + "\n",
        encoding="utf-8",
    )
    env = {"OBSIDIAN_VAULT_PATH": str(vault), "OBSIDIAN_BG_AGENT_ENABLED": "1", **env_extra}
    r = _run_hook(json.dumps({"transcript_path": str(transcript)}), env, tmp_path,
                  stub_writes=stub_writes)
    assert r.returncode == 0
    return _completed_entry(vault)


def test_files_changed_is_zero_when_the_agent_writes_nothing(tmp_path):
    """A no-op run must be distinguishable from a productive one. Zero is the
    load-bearing end of this field, so the hook's own .claude-runs log and lock
    file must not leak into the count - they are dot-prefixed and pruned."""
    vault = tmp_path / "vault"; vault.mkdir()
    completed = _fire(tmp_path, vault, {}, stub_writes=[])
    assert completed["files_changed"] == 0


def test_files_changed_counts_what_the_agent_wrote(tmp_path):
    vault = tmp_path / "vault"; vault.mkdir()
    completed = _fire(tmp_path, vault, {},
                      stub_writes=["Daily/2026-01-01.md", "Projects/Widget.md"])
    # Assert the setup did what it claimed, independently of the hook: a harness
    # that trusts its own fixture reports the fixture's bugs as the hook's.
    assert len(list(vault.rglob("*.md"))) == 2
    assert completed["files_changed"] == 2


def test_files_changed_excludes_generated_paths(tmp_path):
    """The headless agent is a full Claude Code session that loads this same
    plugin, so its own SessionStart/SessionEnd hooks rewrite boards, rollups,
    an index and a memory mirror during the run. Without OBSIDIAN_BG_COUNT_IGNORE
    the count never reaches 0 and the field stops meaning anything."""
    vault = tmp_path / "vault"; vault.mkdir()
    completed = _fire(
        tmp_path, vault,
        {"OBSIDIAN_BG_COUNT_IGNORE": r"^(index\.md|Boards/)"},
        stub_writes=["index.md", "Boards/Work.md", "Daily/2026-01-01.md"],
    )
    assert len(list(vault.rglob("*.md"))) == 3, "all three must exist on disk"
    assert completed["files_changed"] == 1, "only the non-generated write counts"


def test_files_changed_omitted_rather_than_guessed_when_the_count_fails(tmp_path):
    """A malformed ignore pattern must not read as 'wrote nothing'. grep exits 1
    when it filtered everything out and >=2 on a bad pattern; conflating them
    would turn a typo into a confident, wrong zero.

    Differential on purpose: the same write with a VALID pattern must produce the
    field. Asserting only the absence would pass against any build that never
    emits files_changed at all, which is exactly nothing."""
    good = tmp_path / "good"; good.mkdir()
    ok = _fire(tmp_path, good, {"OBSIDIAN_BG_COUNT_IGNORE": r"^Boards/"},
               stub_writes=["Daily/2026-01-01.md"])
    assert ok["files_changed"] == 1, "a valid pattern must still yield a count"

    bad = tmp_path / "bad"; bad.mkdir()
    completed = _fire(tmp_path, bad, {"OBSIDIAN_BG_COUNT_IGNORE": "^(["},
                      stub_writes=["Daily/2026-01-01.md"])
    assert "files_changed" not in completed, "an unavailable count must be absent, not 0"
    assert completed["exit_code"] == 0, "the run itself must still be reported"
