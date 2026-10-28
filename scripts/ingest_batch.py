"""Directory ingestion bookkeeping; extraction and vault knowledge stay with the agent.

Usage: ingest_batch.py --vault VAULT discover SOURCE
       ingest_batch.py --vault VAULT plan SOURCE --allow SOURCE --limit 10
       ingest_batch.py --vault VAULT complete < source.json

Discover reads paths only. Plan hashes only explicitly allowed paths, after the
agent resolves sensitive-content permissions. Complete takes JSON on stdin and
appends one completion receipt to the existing operation log. No separate state file.
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

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vault_health import VaultExcludes  # noqa: E402

FORMATS = {
    **dict.fromkeys((".md", ".markdown", ".txt"), "text"),
    ".pdf": "pdf",
    # Office/OpenDocument text goes through document_to_pdf.py, as in single-source ingest.
    **dict.fromkeys((".docx", ".doc", ".odt"), "document"),
    **dict.fromkeys((".m4a", ".mp3", ".wav", ".ogg", ".webm"), "audio"),
    **dict.fromkeys((".png", ".jpg", ".jpeg", ".webp"), "image"),
}
OUTPUT_DIRS = {"raw", "wiki", "logs", "research", "bases", "boards"}
MARKER = "<!-- ingest-complete "
HASH = re.compile(r"[0-9a-f]{64}")


def local_path(vault: Path, name: str | Path) -> Path:
    path = Path(name)
    return path if path.is_absolute() else vault / path


def linked(path: Path) -> bool:
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def checked(path: Path) -> Path:
    if any(linked(p) for p in (path, *path.parents)):
        raise ValueError(f"Linked paths are not supported: {path}")
    return path.resolve()


def identity(vault: Path, path: Path) -> str:
    path = checked(path)
    return (path.relative_to(vault) if path.is_relative_to(vault) else path).as_posix()


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def discover(vault: Path, source: Path, outputs=()) -> dict:
    source = checked(source)
    if not source.is_dir():
        raise ValueError("The batch source must be a directory")
    for destination in outputs:
        destination = checked(local_path(vault, destination))
        if not destination.is_relative_to(vault):
            raise ValueError("Output destinations must remain inside the vault")
        if destination.is_relative_to(source) or source.is_relative_to(destination):
            raise ValueError(f"Source and output destinations overlap: {destination}")
    config = checked(vault / ".vault-config.json")
    data = {}
    if config.exists():
        data = json.loads(config.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or any(
            not isinstance(data.get(key, []), list)
            or any(not isinstance(v, str) for v in data.get(key, []))
            for key in ("exclude-dirs", "exclude-paths")
        ):
            raise ValueError("Invalid ingestion exclusion configuration")
    rules = VaultExcludes(set(data.get("exclude-dirs", [])),
                         [p.strip("/") for p in data.get("exclude-paths", []) if p.strip("/")])
    candidates, excluded = [], []

    def reason(path: Path) -> str | None:
        if linked(path):
            return "linked path"
        rel = path.relative_to(vault) if path.is_relative_to(vault) else path.relative_to(source)
        if rules.skip(rel.parts, rel.as_posix()):
            return "scan exclusion"
        if any(part.lower() in OUTPUT_DIRS for part in rel.parts):
            return "generated output"
        return None

    root_reason = reason(source)
    if root_reason:
        return {"candidates": [], "excluded": [{"path": str(source), "reason": root_reason}]}

    def scan_error(error):
        raise error  # Never report an unreadable subtree as an empty collection.

    for directory, dirs, files in os.walk(source, followlinks=False, onerror=scan_error):
        for name in list(dirs):
            path = Path(directory) / name
            why = reason(path)
            if why:
                dirs.remove(name)
                excluded.append({"path": str(path), "reason": why, "directory": True})
        for name in files:
            path = Path(directory) / name
            why = reason(path)
            if not why and path.suffix.lower() not in FORMATS:
                why = "unsupported format"
            if why:
                excluded.append({"path": str(path), "reason": why})
            else:
                candidates.append({"source_path": identity(vault, path),
                                   "format": FORMATS[path.suffix.lower()]})
    candidates.sort(key=lambda item: (item["source_path"].casefold(), item["source_path"]))
    excluded.sort(key=lambda item: item["path"])
    return {"candidates": candidates, "excluded": excluded}


def receipts(vault: Path) -> dict:
    """Only completion receipts establish progress; captures and prose do not."""
    latest, timestamps = {}, {}
    logs = checked(vault / "Logs")
    paths = [vault / "log.md", *sorted(logs.glob("????-??-??.md"))]
    for path in paths:
        checked(path)
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.startswith(MARKER):
                continue
            if not line.endswith(" -->"):
                continue  # a torn final append never establishes completion
            event = json.loads(line[len(MARKER):-4])
            if (not isinstance(event, dict)
                    or not isinstance(event.get("source_path"), str)
                    or not HASH.fullmatch(event.get("source_file_hash", ""))
                    or not isinstance(event.get("raw_path"), str)):
                raise ValueError(f"Invalid ingest-complete entry in {path}")
            stamp = datetime.fromisoformat(event["timestamp"])
            if stamp.tzinfo is None:
                raise ValueError(f"Missing timezone in ingest-complete entry: {path}")
            name = event["source_path"]
            if name not in timestamps or stamp >= timestamps[name]:
                latest[name], timestamps[name] = event, stamp
    return latest


def raw_metadata(path: Path) -> dict:
    """Read only frontmatter, never a raw source body during discovery."""
    with path.open(encoding="utf-8-sig") as stream:
        if stream.readline().strip() != "---":
            return {}
        lines = []
        for line in stream:
            if line.strip() == "---":
                return yaml.safe_load("".join(lines)) or {}
            lines.append(line)
            if sum(map(len, lines)) > 65536:
                raise ValueError(f"Oversized raw frontmatter: {path}")
    return {}


def raw_reference(vault: Path, value: str | None, raw_root: Path) -> str | None:
    if not value:
        return None
    path = checked(local_path(vault, value))
    if not path.is_relative_to(raw_root) or not path.is_file() or path.suffix.lower() != ".md":
        return None
    meta = raw_metadata(path)
    return identity(vault, path) if isinstance(meta, dict) and meta.get("type") == "source" else None


def plan(vault: Path, source: Path, allow=(), block=(), limit=10, outputs=(), raw_root=None) -> dict:
    if limit < 1:
        raise ValueError("Batch size must be positive")
    raw_root = checked(local_path(vault, raw_root or "raw"))
    if not raw_root.is_relative_to(vault):
        raise ValueError("Raw captures must remain inside the vault")
    scope = discover(vault, source, (*outputs, identity(vault, raw_root)))
    allowed = [checked(local_path(vault, p)) for p in allow]
    denied = [checked(local_path(vault, p)) for p in block]
    latest = receipts(vault)
    batch, skipped, failed, blocked = [], [], [], []
    raw_index = None
    for item in scope["candidates"]:
        path = checked(local_path(vault, item["source_path"]))
        if (not any(path.is_relative_to(p) for p in allowed)
                or any(path.is_relative_to(p) for p in denied)):
            blocked.append({**item, "reason": "read permission not granted"})
            continue
        try:
            source_hash = digest(path)
            previous = latest.get(item["source_path"], {})
            same = previous.get("source_file_hash") == source_hash
            raw = raw_reference(vault, previous.get("raw_path") if same else None, raw_root)
            item = {**item, "source_file_hash": source_hash, "raw_path": raw}
            if same and raw:
                skipped.append(item)
                continue
            if not raw:
                if raw_index is None:
                    index = {}
                    for capture in sorted(raw_root.rglob("*.md")):
                        checked(capture)
                        meta = raw_metadata(capture)
                        if isinstance(meta, dict) and meta.get("type") == "source":
                            index[(meta.get("source_path"), meta.get("source_file_hash"))] = (
                                identity(vault, capture))
                    raw_index = index
                item["raw_path"] = raw_index.get((item["source_path"], source_hash))
            batch.append(item)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            failed.append({**item, "error": str(exc)})
    return {**scope, "batch": batch[:limit], "remaining": len(batch), "skipped": skipped,
            "failed": failed, "blocked": blocked}


def log_header(day: str) -> str:
    return (f"---\ntype: log\ndate: {day}\ntags: [log, operations]\nai-first: true\n---\n\n"
            "## For future agent\n\nAppend-only vault operation history and ingestion progress.\n\n")


def complete(vault: Path, outcome: dict, raw_root=None) -> dict:
    """Attest that the agent finished all required work for this source version."""
    if set(outcome) != {"source_path", "source_file_hash", "raw_path"}:
        raise ValueError("Completion requires only source_path, source_file_hash and raw_path")
    source = checked(local_path(vault, outcome["source_path"]))
    name = identity(vault, source)
    source_hash = outcome["source_file_hash"]
    if not HASH.fullmatch(source_hash):
        raise ValueError("Invalid source hash")
    raw_root = checked(local_path(vault, raw_root or "raw"))
    if not raw_root.is_relative_to(vault):
        raise ValueError("Raw captures must remain inside the vault")
    checked(vault / "Logs")
    raw = raw_reference(vault, outcome.get("raw_path"), raw_root)
    if not raw:
        raise ValueError("Raw reference must identify an existing source capture (.md)")
    if digest(source) != source_hash:
        raise ValueError("Source changed; do not mark this version complete. Replan.")
    now = datetime.now().astimezone()
    event = {"timestamp": now.isoformat(), "source_path": name,
             "source_file_hash": source_hash, "raw_path": raw}
    target = vault / "Logs" / f"{now.date().isoformat()}.md" if (
        vault / "Logs").is_dir() else vault / "log.md"
    target = checked(target)
    old = target.read_bytes() if target.exists() else b""
    old.decode("utf-8-sig")  # refuse to append to a log we cannot decode
    payload = json.dumps(event, ensure_ascii=True, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e")
    with target.open("ab") as stream:
        if not old:
            stream.write(log_header(now.date().isoformat()).encode("utf-8"))
        stream.write(f"\n{MARKER}{payload} -->\n".encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    return event


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True, type=Path)
    parser.add_argument("--raw-root", default="raw")
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("discover", "plan"):
        command = sub.add_parser(action)
        command.add_argument("source", type=Path)
        command.add_argument("--output", action="append", default=[])
        if action == "plan":
            command.add_argument("--allow", action="append", default=[])
            command.add_argument("--block", action="append", default=[])
            command.add_argument("--limit", type=int, default=10)
    sub.add_parser("complete")
    args = parser.parse_args(argv)
    try:
        vault = checked(args.vault)
        if not vault.is_dir():
            raise ValueError("Vault must be an existing directory")
        if args.action == "complete":
            result = complete(vault, json.load(sys.stdin), args.raw_root)
        elif args.action == "discover":
            result = discover(vault, local_path(vault, args.source), args.output)
        else:
            result = plan(vault, local_path(vault, args.source), args.allow, args.block,
                          args.limit, args.output, args.raw_root)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
