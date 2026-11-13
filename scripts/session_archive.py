#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""Session archive - keep a redacted copy of an agent chat under raw/sessions/.

`/obsidian-save` rewrites a conversation into notes and drops the conversation
itself. A fact the save step skipped is then gone for good once the agent
prunes its own transcripts (Claude Code deletes them after 30 days by
default). The Memory Tax study (arXiv 2610.34073, 2026-10-25) measured that
rewrite step losing facts across 11 memory systems, and its fix is to keep a
path back to the raw history and search it next to the notes. This script is
that path back.

What it keeps: what the user and the agent said, in order, with timestamps.
What it drops: tool calls, tool output, thinking, injected context
(system reminders, hook output) and subagent side chains. Tool output is where
the bulk and the secrets live: across one maintainer's 248 Claude Code
sessions it cut 1.9 GB of JSONL to 5.5 MB of text. Secrets that survive in
the conversation itself are redacted before anything is written.

Opt-in and inert by default: nothing is written unless OBSIDIAN_SESSION_ARCHIVE
is on (environment or the config file). A chat is cut into parts of about
7,000 characters at turn boundaries, so the semantic index embeds every part
whole; parts link to each other. Files are keyed by the session id, so a
second save of the same chat refreshes its parts instead of adding copies.

Usage:
  uv run python scripts/session_archive.py --latest --cwd "$PWD"
  uv run python scripts/session_archive.py --transcript ~/.claude/projects/<dir>/<id>.jsonl
  uv run python scripts/session_archive.py --latest --cwd "$PWD" --dry-run --json

Only Claude Code transcripts are read for now. Other agents get their own
reader in READERS when their transcript format is pinned.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import osb_env  # noqa: E402

ENABLE_KEY = "OBSIDIAN_SESSION_ARCHIVE"
SESSIONS_DIR = Path("raw") / "sessions"
# Body characters per part. The semantic index embeds 8 chunks of ~1,000 body
# characters each after the identity header, so 7,000 leaves room for the
# header and frontmatter and every part is embedded whole.
PART_CHARS = 7000

# Injected context that rides inside user turns but was never said by the user.
_INJECTED = re.compile(
    r"<(system-reminder|ide_selection|ide_opened_file|command-message|command-args"
    r"|local-command-stdout|local-command-caveat|task-notification|browser_instruction"
    r"|diagnostics|user-prompt-submit-hook)>.*?</\1>",
    re.S,
)
_COMMAND_NAME = re.compile(r"<command-name>(.*?)</command-name>", re.S)

# Ordered: the specific token shapes run before the generic NAME=value rule so a
# key keeps its precise label.
_SECRETS: list[tuple[str, re.Pattern[str]]] = [
    ("private-key", re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("api-key", re.compile(r"\bsk-(?:ant-|proj-|or-)?[A-Za-z0-9_-]{20,}")),
    ("api-key", re.compile(r"\bxai-[A-Za-z0-9]{20,}")),
    ("api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("bearer", re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/-]{16,}=*")),
    # Env style is case-sensitive on purpose: a case-blind version redacted IAM
    # action names such as `secretsmanager:GetSecretValue`, and every false hit
    # deletes a fact the archive exists to keep.
    ("env-secret", re.compile(
        r"\b([A-Z][A-Z0-9_]*(?:_KEY|SECRET|TOKEN|PASSWORD|PASSWD)[A-Z0-9_]*\s*[=:]\s*)"
        r"[\"']?[^\s\"'`]{8,}[\"']?")),
    ("config-secret", re.compile(
        r"(?i)([\"']?\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token"
        r"|client[_-]?secret|secret[_-]?key|password)\b[\"']?\s*[=:]\s*)"
        r"[\"']?[^\s\"'`,}]{8,}[\"']?")),
]


def redact(text: str) -> tuple[str, int]:
    """Replace secret-shaped strings with a labelled marker; return the count."""
    total = 0
    for label, pattern in _SECRETS:
        marker = f"[REDACTED:{label}]"
        if pattern.groups:
            text, n = pattern.subn(lambda m, mk=marker: m.group(1) + mk, text)
        else:
            text, n = pattern.subn(marker, text)
        total += n
    return text, total


def _clean_user_text(text: str) -> str:
    text = _COMMAND_NAME.sub(lambda m: m.group(1).strip(), text)
    return _INJECTED.sub("", text).strip()


def read_claude_code(path: Path) -> dict:
    """Turns, title and metadata from one Claude Code session JSONL."""
    turns: list[dict] = []
    seen: set[str] = set()
    title = ""
    session_id = path.stem
    cwd = ""
    with path.open(encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            kind = entry.get("type")
            if kind == "ai-title" and entry.get("aiTitle"):
                title = entry["aiTitle"]
                continue
            if kind not in ("user", "assistant"):
                continue
            if entry.get("isMeta") or entry.get("isCompactSummary") or entry.get("isSidechain"):
                continue
            uuid = entry.get("uuid")
            if uuid:
                if uuid in seen:
                    continue
                seen.add(uuid)
            session_id = entry.get("sessionId") or session_id
            # The folder the session started in names it; later `cd`s do not.
            cwd = cwd or entry.get("cwd") or ""
            content = (entry.get("message") or {}).get("content")
            answered = entry.get("toolUseResult")
            if kind == "user" and isinstance(answered, dict) and answered.get("answers"):
                # Answers to the agent's multiple-choice questions arrive as a tool
                # result, but they are the user's own words: keep them.
                parts = [f"> {q}\n\n{a}" for q, a in answered["answers"].items()]
            elif isinstance(content, str):
                parts = [content]
            elif isinstance(content, list):
                parts = [b.get("text", "") for b in content if b.get("type") == "text"]
            else:
                parts = []
            text = "\n\n".join(p for p in parts if p)
            if kind == "user":
                text = _clean_user_text(text)
            text = text.strip()
            if not text:
                continue
            role = "user" if kind == "user" else "agent"
            stamp = entry.get("timestamp", "")
            if turns and turns[-1]["role"] == role:
                turns[-1]["text"] += "\n\n" + text
            else:
                turns.append({"role": role, "time": stamp, "text": text})
    return {"agent": "claude-code", "session_id": session_id, "title": title,
            "cwd": cwd, "turns": turns}


READERS = {"claude-code": read_claude_code}


def claude_projects_dir() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base).expanduser() / "projects"


def latest_transcript(cwd: str) -> Path | None:
    """The newest Claude Code session for a working folder: the one being written now."""
    folder = claude_projects_dir() / re.sub(r"[^A-Za-z0-9]", "-", cwd)
    if not folder.is_dir():
        return None
    files = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _slug(title: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9 _-]+", "", title).strip()
    return re.sub(r"\s+", " ", clean)[:60].strip() or "session"


def _local(stamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def _blocks(turns: list[dict]) -> tuple[list[str], int]:
    """One redacted, labelled text block per turn, long turns cut to fit a part."""
    blocks: list[str] = []
    redactions = 0
    for turn in turns:
        when = _local(turn["time"])
        label = "User" if turn["role"] == "user" else "Agent"
        stamp = when.strftime("%Y-%m-%d %H:%M") if when else ""
        text, n = redact(turn["text"])
        redactions += n
        room = PART_CHARS - 80
        pieces = [text[i:i + room] for i in range(0, len(text), room)] or [""]
        for k, piece in enumerate(pieces):
            more = " (continued)" if k else ""
            blocks.append(f"**{label}** ({stamp}){more}\n\n{piece}\n")
    return blocks, redactions


def _split(blocks: list[str]) -> list[str]:
    """Greedy, in order: earlier parts keep their content as a chat grows."""
    parts: list[str] = []
    current = ""
    for block in blocks:
        if current and len(current) + len(block) > PART_CHARS:
            parts.append(current)
            current = ""
        current += block + "\n"
    if current:
        parts.append(current)
    return parts


def render(session: dict, source: Path, base: str | None = None
           ) -> tuple[list[tuple[str, str]], int]:
    """Return ([(file name, note text) per part], redaction count).

    A long chat is cut into parts at turn boundaries because the semantic index
    embeds only the first 8 chunks (~9.6k characters) of a note. In one file,
    everything said after that point was findable by exact words only.
    """
    turns = session["turns"]
    first = _local(turns[0]["time"]) if turns else None
    day = first.strftime("%Y-%m-%d") if first else datetime.now().strftime("%Y-%m-%d")
    title = session["title"] or turns[0]["text"].splitlines()[0][:60]
    safe_title, redactions = redact(title)
    blocks, n = _blocks(turns)
    redactions += n
    bodies = _split(blocks)
    base = base or f"{day} - {_slug(safe_title)} ({session['session_id'][:8]})"
    names = [f"{base} part {i}" for i in range(1, len(bodies) + 1)]

    out: list[tuple[str, str]] = []
    for i, body in enumerate(bodies):
        content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        frontmatter = "\n".join([
            "---",
            f"date: {day}",
            "type: source",
            "tags: [source, session]",
            "source_type: session",
            f"source_path: {json.dumps(str(source))}",
            f"session_id: {json.dumps(session['session_id'])}",
            f"agent: {session['agent']}",
            f"part: {i + 1}",
            f"parts: {len(bodies)}",
            f"content_hash: {content_hash}",
            "capture_scope: bounded-local",
            "source_quality: medium",
            f"redactions: {redactions}",
            "ai-first: true",
            "---",
        ])
        nav = []
        if i:
            nav.append(f"previous: [[{names[i - 1]}]]")
        if i + 1 < len(bodies):
            nav.append(f"next: [[{names[i + 1]}]]")
        header = "\n".join([
            f"# Session: {safe_title} (part {i + 1} of {len(bodies)})",
            "",
            f"> **Agent:** {session['agent']} - **Session:** {session['session_id']}",
            f"> **Folder:** {session['cwd'] or 'unknown'}",
            "> **Kept:** what the user and the agent said. Tool calls, tool output, thinking",
            f"> and injected context were dropped. {redactions} secret(s) redacted.",
            *([f"> **Parts:** {' - '.join(nav)}"] if nav else []),
            "",
        ])
        out.append((f"{names[i]}.md", f"{frontmatter}\n\n{header}\n{body.rstrip()}\n"))
    return out, redactions


def existing_parts(sessions: Path, session_id: str) -> list[Path]:
    """Files already holding this session, under whatever title they got."""
    marker = f"session_id: {json.dumps(session_id)}"
    found = []
    for path in sessions.glob(f"*({session_id[:8]})*.md"):
        if marker in path.read_text(encoding="utf-8")[:1200]:
            found.append(path)
    return sorted(found)


def is_enabled() -> bool:
    return osb_env.env_value(ENABLE_KEY).lower() in {"1", "true", "yes", "on"}


def archive(transcript: Path, vault: Path, agent: str = "claude-code",
            dry_run: bool = False) -> dict:
    session = READERS[agent](transcript)
    if not session["turns"]:
        return {"status": "empty", "transcript": str(transcript)}
    sessions = vault / SESSIONS_DIR
    old = existing_parts(sessions, session["session_id"]) if sessions.is_dir() else []
    # A session keeps the name it was first archived under, even if its title changes.
    base = re.sub(r"( part \d+)?\.md$", "", old[0].name) if old else None
    parts, redactions = render(session, transcript, base)
    targets = [sessions / name for name, _ in parts]
    result = {
        "status": "dry-run" if dry_run else "written",
        "paths": [p.relative_to(vault).as_posix() for p in targets],
        "turns": len(session["turns"]),
        "chars": sum(len(text) for _, text in parts),
        "redactions": redactions,
    }
    if not dry_run:
        sessions.mkdir(parents=True, exist_ok=True)
        for target, (_, text) in zip(targets, parts):
            target.write_text(text, encoding="utf-8")
        # Only files of this same session are ever removed: the unsplit file an
        # earlier version wrote, replaced by its parts just above.
        for stale in set(old) - set(targets):
            stale.unlink()
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--transcript", type=Path, help="Path to one session transcript")
    src.add_argument("--latest", action="store_true",
                     help="Archive the newest session for --cwd (the one running now)")
    ap.add_argument("--cwd", default=str(Path.cwd()),
                    help="Working folder of the session (default: current folder)")
    ap.add_argument("--agent", choices=sorted(READERS), default="claude-code")
    ap.add_argument("--vault", type=Path, help="Vault root (default: OBSIDIAN_VAULT_PATH)")
    ap.add_argument("--dry-run", action="store_true", help="Report, write nothing")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not is_enabled():
        msg = {"status": "off", "hint": f"set {ENABLE_KEY}=1 to keep raw chats"}
        print(json.dumps(msg) if args.json else f"session archive is off ({msg['hint']})")
        return 0

    vault = args.vault or Path(osb_env.vault_path()).expanduser()
    if not str(vault) or not vault.is_dir():
        print("error: no vault (set OBSIDIAN_VAULT_PATH or pass --vault)", file=sys.stderr)
        return 2

    transcript = args.transcript.expanduser() if args.transcript else latest_transcript(args.cwd)
    if not transcript or not transcript.is_file():
        print(f"error: no session transcript found for {args.cwd}", file=sys.stderr)
        return 2

    result = archive(transcript, vault.resolve(), args.agent, args.dry_run)
    if args.json:
        print(json.dumps(result))
    else:
        print(" ".join(f"{k}={v}" for k, v in result.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
