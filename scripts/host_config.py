#!/usr/bin/env python3
"""Register the vault with Claude Code and Codex. Idempotent, stdlib-only.

What it changes (each file is backed up to <file>.osb-bak before the first
write of a run, and only written when something actually changes):

Toolkit config  ~/.config/obsidian-second-brain/.env
    OBSIDIAN_VAULT_PATH, OSB_LANGUAGE (other keys are kept).

Claude Code     ~/.claude/settings.json
    permissions.additionalDirectories += vault   (edit the vault from any project)
    env.OBSIDIAN_VAULT_PATH = vault              (an env value wins over the .env file)
    hooks.PostToolUse: AI-first validator on Write|Edit|MultiEdit
    Removes hook entries left by older installs (anything under
    obsidian-second-brain/hooks/ or naming validate-ai-first.sh) first.
    (Codex: nothing is removed or moved, because Codex trusts hooks by position;
    an existing validator is updated in place, otherwise one group is appended.)

Codex           ~/.codex/config.toml
    [sandbox_workspace_write] writable_roots += vault, network_access = true
                ~/.codex/hooks.json
    hooks.PostToolUse: AI-first validator on Write|Edit|apply_patch
    (Codex asks you to trust a new hook the first time it runs.)

Usage:
    python3 host_config.py --vault PATH --language ko --hosts claude,codex
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

HOME = Path.home()
ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = ROOT / "hooks" / "validate-ai-first.sh"
STALE_MARKERS = ("obsidian-second-brain/hooks/", "validate-ai-first.sh")

_backed_up: set[Path] = set()


def backup(path: Path) -> None:
    if path.exists() and path not in _backed_up:
        shutil.copy2(path, path.with_name(path.name + ".osb-bak"))
        _backed_up.add(path)


def validator_command() -> str:
    return f'bash "{VALIDATOR}"'


# ---------------------------------------------------------------- toolkit .env

def write_env(vault: Path, language: str, env_file: Path | None = None) -> bool:
    env_file = env_file or HOME / ".config" / "obsidian-second-brain" / ".env"
    want = {"OBSIDIAN_VAULT_PATH": str(vault), "OSB_LANGUAGE": language}
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    out, seen = [], set()
    for line in lines:
        key = line.split("=", 1)[0].strip().removeprefix("export ").strip()
        if key in want:
            if key not in seen:
                out.append(f'{key}="{want[key]}"')
                seen.add(key)
            continue
        out.append(line)
    out += [f'{k}="{v}"' for k, v in want.items() if k not in seen]
    new = "\n".join(out) + "\n"
    if env_file.exists() and env_file.read_text(encoding="utf-8") == new:
        return False
    env_file.parent.mkdir(parents=True, exist_ok=True)
    backup(env_file)
    env_file.write_text(new, encoding="utf-8")
    return True


# ---------------------------------------------------------------- hook merging

def _is_validator(handler: dict) -> bool:
    return "validate-ai-first.sh" in str(handler.get("command", ""))


def _is_legacy(handler: dict) -> bool:
    return any(m in str(handler.get("command", "")) for m in STALE_MARKERS)


def merge_hooks(hooks: dict, matcher: str, enable: bool = True) -> None:
    """Claude Code: drop our old handlers and legacy ones, append one fresh group.

    Claude has no positional trust, so compacting the arrays is safe here.
    Foreign handlers keep their groups and matchers.
    """
    for event in list(hooks):
        groups = []
        for group in hooks.get(event) or []:
            kept = [h for h in group.get("hooks", []) if not (_is_validator(h) or _is_legacy(h))]
            if kept:
                group["hooks"] = kept
                groups.append(group)
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    if enable:
        hooks.setdefault("PostToolUse", []).append({"matcher": matcher, "hooks": [_ours()]})


def merge_hooks_positional(hooks: dict, matcher: str, enable: bool = True) -> list[str]:
    """Codex: never remove, reorder, or re-match anything that is not ours.

    Codex keys hook trust by position (event:group:handler), so every existing
    group and handler stays at its index. An existing validator handler is
    updated where it stands; its group's matcher is changed only when every
    handler in that group is ours (otherwise another tool's trigger would
    change). With no validator present, one group is appended at the end.
    Returns notes about things left in place that the user may want to clean up.
    """
    notes: list[str] = []
    found = False
    for event, groups in hooks.items():
        for gi, group in enumerate(groups or []):
            handlers = group.get("hooks", [])
            for hi, h in enumerate(handlers):
                if _is_validator(h):
                    found = True
                    if enable:
                        handlers[hi] = _ours()
                    else:
                        notes.append(f"validator left at {event}[{gi}][{hi}]; remove it with /hooks")
                elif _is_legacy(h):
                    notes.append(f"legacy hook left at {event}[{gi}][{hi}]: {h.get('command')}")
            if enable and handlers and all(_is_validator(h) for h in handlers):
                group["matcher"] = matcher
    if enable and not found:
        hooks.setdefault("PostToolUse", []).append({"matcher": matcher, "hooks": [_ours()]})
    return notes


def _ours() -> dict:
    return {"type": "command", "command": validator_command(), "timeout": 15}


def _write_json(path: Path, data: dict, before: str) -> bool:
    new = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if new == before:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    backup(path)
    path.write_text(new, encoding="utf-8")
    return True


def _load_json(path: Path) -> tuple[dict, str]:
    if not path.exists():
        return {}, ""
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: {path} is not valid JSON ({exc}); fix it and re-run.")
    return data, text


# ---------------------------------------------------------------- Claude Code

def configure_claude(vault: Path, settings: Path | None = None, hooks: bool = True) -> bool:
    settings = settings or HOME / ".claude" / "settings.json"
    data, before = _load_json(settings)
    perms = data.setdefault("permissions", {})
    dirs = perms.setdefault("additionalDirectories", [])
    if str(vault) not in dirs:
        dirs.append(str(vault))
    data.setdefault("env", {})["OBSIDIAN_VAULT_PATH"] = str(vault)
    h = data.setdefault("hooks", {})
    merge_hooks(h, "Write|Edit|MultiEdit", enable=hooks)
    if not h:
        del data["hooks"]
    return _write_json(settings, data, before)


# ---------------------------------------------------------------- Codex

def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


_STR_RE = re.compile(r'"((?:[^"\\]|\\.)*)"|\'([^\']*)\'')


def update_codex_toml(text: str, vault: Path) -> str:
    """Return config text with the vault writable and network on in workspace-write."""
    header = re.compile(r"(?m)^\[sandbox_workspace_write\][ \t]*(?:#.*)?$")
    m = header.search(text)
    if not m:
        block = (f"\n[sandbox_workspace_write]\nwritable_roots = [{_toml_str(str(vault))}]\n"
                 "network_access = true\n")
        return text.rstrip("\n") + "\n" + block
    start = m.end()
    nxt = re.compile(r"(?m)^[ \t]*\[").search(text, start)
    end = nxt.start() if nxt else len(text)
    body = text[start:end]

    roots = re.search(r"(?ms)^[ \t]*writable_roots[ \t]*=[ \t]*\[(.*?)\]", body)
    if roots:
        items = [a if a else b for a, b in _STR_RE.findall(roots.group(1))]
        unescaped = [i.replace('\\"', '"').replace("\\\\", "\\") for i in items]
        if str(vault) not in unescaped:
            items_out = [_toml_str(i) for i in unescaped] + [_toml_str(str(vault))]
            body = (body[:roots.start()] + "writable_roots = [" + ", ".join(items_out) + "]"
                    + body[roots.end():])
    else:
        body = f"\nwritable_roots = [{_toml_str(str(vault))}]" + body

    if re.search(r"(?m)^[ \t]*network_access[ \t]*=", body):
        body = re.sub(r"(?m)^[ \t]*network_access[ \t]*=.*$", "network_access = true", body)
    else:
        body = body.rstrip("\n") + "\nnetwork_access = true"
    # Normalize the section's trailing blank lines so re-runs are byte-identical.
    body = body.rstrip("\n") + ("\n\n" if nxt else "\n")
    return text[:start] + body + text[end:]


def codex_home_dir() -> Path:
    """Codex's home: $CODEX_HOME when set (the installer honors it too), else ~/.codex."""
    env = os.environ.get("CODEX_HOME", "").strip()
    return Path(env).expanduser() if env else HOME / ".codex"


def _toml_loads(text: str) -> dict:
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10: tomli is in requirements.txt
        try:
            import tomli as tomllib
        except ModuleNotFoundError:
            raise SystemExit("error: cannot verify the Codex config edit: install tomli "
                             "(pip install tomli) or use Python 3.11+.")
    return tomllib.loads(text)


def _verify_codex_toml(text: str, vault: Path, cfg: Path) -> None:
    """Refuse to write a config that does not parse or does not say what we meant.

    The edit is textual (stdlib has no TOML writer), so unusual spellings of the
    table - a dotted `sandbox_workspace_write.x = ...` key or an inline table -
    are caught here instead of producing a broken config.
    """
    manual = (f"Add this to {cfg} by hand, then re-run:\n\n[sandbox_workspace_write]\n"
              f"writable_roots = [{_toml_str(str(vault))}]\nnetwork_access = true")
    try:
        parsed = _toml_loads(text)
    except SystemExit:
        raise
    except Exception as exc:
        raise SystemExit(f"error: refusing to write {cfg}: the edit would not parse ({exc}).\n{manual}")
    sww = parsed.get("sandbox_workspace_write", {})
    if not (isinstance(sww, dict) and str(vault) in sww.get("writable_roots", [])
            and sww.get("network_access") is True):
        raise SystemExit(f"error: could not update {cfg} safely.\n{manual}")


def configure_codex(vault: Path, codex_home: Path | None = None, hooks: bool = True) -> list[str]:
    codex_home = codex_home or codex_home_dir()
    changed = []
    cfg = codex_home / "config.toml"
    before = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
    after = update_codex_toml(before, vault)
    _verify_codex_toml(after, vault, cfg)
    if after != before:
        codex_home.mkdir(parents=True, exist_ok=True)
        backup(cfg)
        cfg.write_text(after, encoding="utf-8")
        changed.append(str(cfg))
        mode = re.search(r'(?m)^sandbox_mode\s*=\s*"([^"]+)"', after)
        if mode and mode.group(1) != "workspace-write":
            print(f'note: {cfg} has sandbox_mode = "{mode.group(1)}"; writable_roots and '
                  "network_access apply only in workspace-write mode.", file=sys.stderr)

    hooks_file = codex_home / "hooks.json"
    data, before_json = _load_json(hooks_file)
    h = data.setdefault("hooks", {})
    for note in merge_hooks_positional(h, "Write|Edit|apply_patch", enable=hooks):
        print(f"note: {hooks_file}: {note}", file=sys.stderr)
    if _write_json(hooks_file, data, before_json):
        changed.append(str(hooks_file))
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description="Register the vault with Claude Code and Codex.")
    ap.add_argument("--vault", required=True)
    ap.add_argument("--language", default="ko", choices=["ko", "en"])
    ap.add_argument("--hosts", default="claude,codex", help="comma list: claude,codex")
    ap.add_argument("--no-hooks", action="store_true", help="do not register the validator hook")
    args = ap.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    if not vault.is_dir():
        print(f"error: {vault} is not a directory", file=sys.stderr)
        return 2
    hosts = {h.strip() for h in args.hosts.split(",") if h.strip()}
    report = []
    if write_env(vault, args.language):
        report.append("toolkit config (.env)")
    if "claude" in hosts and configure_claude(vault, hooks=not args.no_hooks):
        report.append("~/.claude/settings.json")
    if "codex" in hosts:
        report += configure_codex(vault, hooks=not args.no_hooks)
    print("updated: " + (", ".join(report) if report else "nothing (already configured)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
