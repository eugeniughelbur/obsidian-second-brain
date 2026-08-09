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


def _fire_to_files(tmp_path: Path, tag: str, stdin: str, env: dict) -> tuple[int, str]:
    """Run the hook with stdout/stderr going to FILES, not pipes.

    Deliberate: the detached subshell inherits the hook's stdout and stderr, so
    capture_output=True would keep those pipes open until the spawned agent
    exits. subprocess.run would then block for the agent's whole lifetime, the
    two runs below would never overlap, and the collision under test could not
    happen - the test would pass against the bug it exists to catch.
    """
    out = tmp_path / f"out-{tag}.txt"
    err = tmp_path / f"err-{tag}.txt"
    with open(out, "w") as o, open(err, "w") as e:
        r = subprocess.run(["bash", str(HOOK)], input=stdin, env=env, text=True,
                           stdout=o, stderr=e, timeout=30)
    return r.returncode, err.read_text(encoding="utf-8")


def test_overlapping_runs_do_not_share_one_prompt_file(tmp_path):
    """A second compaction while the first agent is still running must not
    collide on the prompt file.

    BSD mktemp substitutes the X's only when they END the template, so a
    template carrying a suffix is a literal path on macOS and every run reuses
    one filename. GNU mktemp accepts the suffix, so this passes on Linux and in
    CI and fails only on a Mac, only when two runs overlap.

    The burst-dedup lock does not cover this: its trap releases on hook exit,
    under a second in, while the agent it spawned runs for minutes.

    Two failures at once when they collide - stderr reaches the user, because
    PostCompact surfaces stderr, and the second agent starts with an empty
    prompt, so that compaction propagates nothing while its run log says
    completed.
    """
    vault = tmp_path / "vault"; vault.mkdir()
    stub_dir = tmp_path / "bin"; stub_dir.mkdir()
    sizes = tmp_path / "prompt-sizes.txt"
    stub = stub_dir / "claude"
    # Record the prompt size, then stay alive so the next hook overlaps this one.
    stub.write_text("#!/usr/bin/env bash\n"
                    f'cat | wc -c | tr -d " " >> "{sizes}"\n'
                    "sleep 3\n", encoding="utf-8")
    stub.chmod(0o755)

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"isCompactSummary": True,
                    "message": {"content": "a summary worth propagating"}}) + "\n",
        encoding="utf-8",
    )
    env = {**os.environ, "PATH": f"{stub_dir}:{os.environ['PATH']}",
           "OBSIDIAN_VAULT_PATH": str(vault), "OBSIDIAN_BG_AGENT_ENABLED": "1"}
    stdin = json.dumps({"transcript_path": str(transcript)})

    for tag in ("first", "second"):
        code, err = _fire_to_files(tmp_path, tag, stdin, env)
        assert code == 0, f"{tag} hook exited {code}"
        assert err == "", f"{tag} run leaked stderr to the user:\n{err}"

    lines: list[str] = []
    for _ in range(30):
        if sizes.exists():
            lines = [l for l in sizes.read_text(encoding="utf-8").splitlines() if l.strip()]
        if len(lines) == 2:
            break
        time.sleep(0.2)
    assert len(lines) == 2, f"both compactions must reach an agent, got {lines}"
    assert all(int(l) > 0 for l in lines), f"an agent was launched with an empty prompt: {lines}"


def test_unusable_tmpdir_is_a_logged_no_op_not_a_cascade(tmp_path):
    """When the prompt file cannot be created, stop and say so.

    The failure mode being fenced off is a cascade: an empty PROMPT_FILE meant
    `cat > ""` three times over, all of it on stderr and all of it shown to the
    user mid-compaction, followed by an agent started with no prompt.
    """
    vault = tmp_path / "vault"; vault.mkdir()
    stub_dir = tmp_path / "bin"; stub_dir.mkdir()
    marker = tmp_path / "agent-ran.txt"
    stub = stub_dir / "claude"
    stub.write_text(f'#!/usr/bin/env bash\ncat > "{marker}"\n', encoding="utf-8")
    stub.chmod(0o755)

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"isCompactSummary": True, "message": {"content": "did work"}}) + "\n",
        encoding="utf-8",
    )
    env = {**os.environ, "PATH": f"{stub_dir}:{os.environ['PATH']}",
           "OBSIDIAN_VAULT_PATH": str(vault), "OBSIDIAN_BG_AGENT_ENABLED": "1",
           "TMPDIR": str(tmp_path / "does-not-exist")}
    code, err = _fire_to_files(tmp_path, "notmp", json.dumps({"transcript_path": str(transcript)}), env)

    assert code == 0, "an unusable TMPDIR must not fail the compaction"
    assert err == "", f"nothing may reach the user's stderr:\n{err}"
    assert not marker.exists(), "no agent may be launched without a prompt"
    statuses = [e["status"] for e in _read_run_log(vault)]
    assert "no_prompt_file" in statuses, f"the skip must be recorded, got {statuses}"
