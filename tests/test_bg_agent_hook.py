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
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'{{ echo "CWD=$PWD"; printf \'ARG=%s\\n\' "$@"; }} > "{record}"\n',
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
