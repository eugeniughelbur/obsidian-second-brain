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


def _run_hook(stdin: str, env_extra: dict, tmp_path: Path) -> subprocess.CompletedProcess:
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    record = tmp_path / "claude-invocation.txt"
    stub = stub_dir / "claude"
    # Capture args AND stdin: the prompt is fed to `claude -p` via stdin, not
    # as an argv element (avoids the ~32K Windows command-line limit), so the
    # summary now arrives on stdin rather than in "$@".
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'{{ echo "CWD=$PWD"; printf \'ARG=%s\\n\' "$@"; echo "STDIN<<<"; cat; }} > "{record}"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{stub_dir}:{os.environ['PATH']}", **env_extra}
    env.pop("OBSIDIAN_VAULT_PATH", None)
    env.pop("OBSIDIAN_BG_AGENT_ENABLED", None)
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
