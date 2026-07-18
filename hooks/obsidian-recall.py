#!/usr/bin/env python3
"""Bounded vault recall on every prompt - opt-in UserPromptSubmit hook.

Injects a SMALL, read-only brief of the most relevant vault notes into the
prompt context, so Claude knows what the vault already holds before answering.
Design contract (fork-insights round 2, the local-first memory fork's
bounded-recall pattern):

  BOUNDED   at most MAX_NOTES notes and MAX_CHARS characters - a hint, not a dump
  ABSTAINS  low-confidence matches inject NOTHING (silence beats noise)
  FAIL-CLOSED any error exits 0 with no output - recall must never break a prompt
  OBSERVABLE every decision (inject or abstain) appends one JSONL line to
             <vault>/.claude-runs/recall-YYYY-MM-DD.jsonl (fail-soft)
  OPT-IN    ships inert; runs only when BOTH env vars are set:
              OBSIDIAN_VAULT_PATH=/path/to/vault
              OBSIDIAN_RECALL_ENABLED=1

Register under UserPromptSubmit (see hooks/recall.hook.example.json). Reuses
the shipped vault_ops.search - the exact ranking the MCP serves, including
freshness and supersession reranking.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

MAX_NOTES = 4
MAX_CHARS = 900          # hard budget for the injected brief (~250 tokens)
MIN_PROMPT_CHARS = 12    # ignore "ok", "yes", slash commands, etc.
MIN_TERM_OVERLAP = 1     # top hit must share at least one meaningful term


def _log(vault: Path, entry: dict) -> None:
    try:
        d = vault / ".claude-runs"
        d.mkdir(exist_ok=True)
        entry["ts"] = datetime.now().isoformat(timespec="seconds")
        with (d / f"recall-{datetime.now():%Y-%m-%d}.jsonl").open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - observability is never fatal
        pass


def _terms(s: str) -> set:
    return {t for t in re.split(r"\W+", s.lower()) if len(t) > 3}


def main() -> int:
    if os.environ.get("OBSIDIAN_RECALL_ENABLED", "").strip() != "1":
        return 0
    vault_path = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
    if not vault_path or not Path(vault_path).is_dir():
        return 0

    raw = sys.stdin.read()
    try:
        prompt = (json.loads(raw).get("prompt") or "").strip()
    except json.JSONDecodeError:
        return 0
    if len(prompt) < MIN_PROMPT_CHARS or prompt.startswith("/"):
        return 0

    vault = Path(vault_path)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integrations" / "obsidian-mcp-server"))
    import vault_ops  # noqa: E402

    results = vault_ops.search(prompt, limit=MAX_NOTES)
    if not results:
        _log(vault, {"prompt_chars": len(prompt), "abstained": True, "reason": "no results"})
        return 0

    # Abstention: the top hit must share at least one meaningful term with the
    # prompt (title or snippet). Weak matches inject nothing - silence beats
    # noise, and the user can always search explicitly.
    ptoks = _terms(prompt)
    top = results[0]
    ttoks = _terms(str(top.get("title", "")) + " " + str(top.get("snippet", "")))
    if len(ptoks & ttoks) < MIN_TERM_OVERLAP:
        _log(vault, {"prompt_chars": len(prompt), "abstained": True, "reason": "low confidence"})
        return 0

    lines = ["Vault notes that may be relevant (read-only recall; verify before relying on them):"]
    for r in results:
        line = f"- [[{r.get('title', r['path'])}]] ({r['path']})"
        snippet = str(r.get("snippet") or "").strip().replace("\n", " ")
        if snippet:
            line += f" - {snippet[:110]}"
        if sum(len(x) + 1 for x in lines) + len(line) > MAX_CHARS:
            break
        lines.append(line)

    brief = "\n".join(lines)
    _log(vault, {"prompt_chars": len(prompt), "abstained": False,
                 "notes": [r["path"] for r in results[: len(lines) - 1]]})
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": brief,
        }
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - fail closed: recall must never break a prompt
        sys.exit(0)
