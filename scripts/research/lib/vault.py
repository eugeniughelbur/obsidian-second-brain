"""Writes AI-first research notes to the Obsidian vault.

Each note follows the AI-first vault rule:
1. Self-contained context
2. "For future agent" preamble
3. Rich frontmatter
4. Recency markers per claim
5. Sources preserved verbatim
6. Mandatory wikilinks
7. Confidence levels (where applicable)
"""

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .config import VAULT_PATH

# Subfolder routing per command (relative to vault root, under Research/)
SUBFOLDERS = {
    "x-read":      Path("Research") / "X-reads",
    "x-pulse":     Path("Research") / "X-pulse",
    "research":    Path("Research") / "Web",
    "research-deep": Path("Research") / "Deep",
    "youtube":     Path("Research") / "YouTube",
    "podcast":     Path("Research") / "Podcasts",
}


def slugify(text: str, max_len: int = 80) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", " ", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:max_len].strip().rstrip(" -")


def filename_for(command: str, topic: str) -> str:
    date = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(topic) or "untitled"
    return f"{date} - {slug}.md"


def write_note(command: str, topic: str, frontmatter: dict[str, Any], body: str) -> Path:
    """Write a research note to the vault. Returns the absolute path."""
    if command not in SUBFOLDERS:
        raise ValueError(f"Unknown command: {command}")
    folder = VAULT_PATH / SUBFOLDERS[command]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename_for(command, topic)

    fm_lines = ["---"]
    for k, v in frontmatter.items():
        fm_lines.append(_yaml_kv(k, v))
    fm_lines.append("---")
    fm_text = "\n".join(fm_lines)

    full = f"{fm_text}\n\n{body.strip()}\n"
    # UTF-8 by name, here and in the two appenders below: the platform default
    # on Windows is the ANSI code page, where a note carrying a character the
    # page cannot encode (a CJK word, on a Western-European system) failed to
    # save and one it can encode was saved as bytes Obsidian reads as mojibake.
    path.write_text(full, encoding="utf-8")
    return path


def _yaml_kv(key: str, value: Any) -> str:
    if isinstance(value, list):
        if not value:
            return f"{key}: []"
        items = "\n".join(f"  - {_yaml_scalar(v)}" for v in value)
        return f"{key}:\n{items}"
    if isinstance(value, dict):
        items = "\n".join(f"  {k}: {_yaml_scalar(v)}" for k, v in value.items())
        return f"{key}:\n{items}"
    return f"{key}: {_yaml_scalar(value)}"


def _yaml_scalar(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if any(c in s for c in [":", "#", "\n", '"', "'", "[", "]", "{", "}"]) or s.strip() != s:
        s = s.replace('"', '\\"')
        return f'"{s}"'
    return s


def obsidian_uri(note_path: Path) -> str:
    """Build an obsidian://open?... URI that opens this note directly in Obsidian."""
    vault_name = VAULT_PATH.name
    rel = note_path.relative_to(VAULT_PATH)
    file_no_ext = str(rel).removesuffix(".md")
    return f"obsidian://open?vault={quote(vault_name)}&file={quote(file_no_ext)}"


def print_save_links(note_path: Path, file=None) -> None:
    """Print save confirmation with clickable Obsidian + VS Code links to the saved note.

    Also auto-opens the note in Obsidian unless disabled via RESEARCH_AUTOOPEN=0.
    """
    import os
    import subprocess
    import sys
    out = file or sys.stderr
    rel = note_path.relative_to(VAULT_PATH)
    uri = obsidian_uri(note_path)
    print(f"\n💾 Saved: {rel}", file=out)
    print(f"   📖 Open in Obsidian: {uri}", file=out)
    print(f"   ✏️  Open in VS Code:  code \"{note_path}\"", file=out)

    # Auto-open in Obsidian by default. Disable with RESEARCH_AUTOOPEN=0.
    if os.environ.get("RESEARCH_AUTOOPEN", "1") != "0":
        try:
            import platform
            # Platform-aware open: `open` on macOS, `xdg-open` on Linux,
            # `cmd /c start "" <uri>` on Windows (the empty "" is the window title).
            open_cmd = {
                "Darwin": ["open", uri],
                "Linux": ["xdg-open", uri],
                "Windows": ["cmd", "/c", "start", "", uri],
            }.get(platform.system(), ["open", uri])
            subprocess.run(open_cmd, check=False, timeout=5)
        except Exception:
            pass  # auto-open is a nice-to-have, never block the save flow


def append_to_log(operation_summary: str) -> bool:
    """Append to the vault's log.md per _CLAUDE.md rules. Returns True if appended.

    A log that is not UTF-8 (one an earlier Windows run wrote in its code page)
    is left exactly as it is, as append_to_daily does: UTF-8 bytes appended to
    it would leave a file that decodes correctly as neither encoding. The
    refusal is said on stderr, so a run that saved its note but changed no log
    does not look like a silent success.
    """
    log_path = VAULT_PATH / "log.md"
    if log_path.exists():
        try:
            log_path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            print(
                "[vault] log.md is not UTF-8 - left untouched, nothing appended. "
                "Re-save it as UTF-8 once (see the README FAQ) and re-run.",
                file=sys.stderr,
            )
            return False
    date = datetime.now().strftime("%Y-%m-%d")
    entry = f"\n## [{date}] research-toolkit | {operation_summary}\n"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(entry)
    return True


def append_to_daily(summary_md: str) -> bool:
    """Append a research summary to today's daily note. Returns True if appended.

    Both reasons for not appending - no daily note for today, or a daily note
    that is not UTF-8 - are said on stderr, since callers ignore the return
    value and the research note itself has already been saved by then.
    """
    date = datetime.now().strftime("%Y-%m-%d")
    daily_path = VAULT_PATH / "wiki" / "daily" / f"{date}.md"
    if not daily_path.exists():
        print(
            f"[vault] no daily note at {daily_path.relative_to(VAULT_PATH)} - "
            "research summary not appended (the research note itself is saved).",
            file=sys.stderr,
        )
        return False
    try:
        current = daily_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Not UTF-8 (a note an earlier Windows run rewrote in its code page):
        # leave it as it is rather than rewrite it lossily, as note_io's rule says.
        print(
            f"[vault] {daily_path.name} is not UTF-8 - left untouched, research summary "
            "not appended. Re-save it as UTF-8 once (see the README FAQ) and re-run.",
            file=sys.stderr,
        )
        return False
    block = f"\n### Research - {datetime.now().strftime('%H:%M')}\n\n{summary_md.strip()}\n"
    if "## 🌙 Evening Review" in current:
        new = current.replace("## 🌙 Evening Review", f"{block}\n---\n\n## 🌙 Evening Review", 1)
    else:
        new = current + block
    daily_path.write_text(new, encoding="utf-8")
    return True
