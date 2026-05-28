"""Writes AI-first research notes to the Obsidian vault.

Each note follows the AI-first vault rule:
1. Self-contained context
2. "For future Claude" preamble
3. Rich frontmatter
4. Recency markers per claim
5. Sources preserved verbatim
6. Mandatory wikilinks
7. Confidence levels (where applicable)
"""

from datetime import datetime
from pathlib import Path
import re
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
    path.write_text(full)
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


def append_to_log(operation_summary: str) -> None:
    """Append to the vault's log.md per _CLAUDE.md rules."""
    log_path = VAULT_PATH / "log.md"
    date = datetime.now().strftime("%Y-%m-%d")
    entry = f"\n## [{date}] research-toolkit | {operation_summary}\n"
    with log_path.open("a") as f:
        f.write(entry)


def append_to_daily(summary_md: str) -> bool:
    """Append a research summary to today's daily note. Returns True if appended."""
    date = datetime.now().strftime("%Y-%m-%d")
    daily_path = VAULT_PATH / "wiki" / "daily" / f"{date}.md"
    if not daily_path.exists():
        return False
    current = daily_path.read_text()
    block = f"\n### Research - {datetime.now().strftime('%H:%M')}\n\n{summary_md.strip()}\n"
    if "## 🌙 Evening Review" in current:
        new = current.replace("## 🌙 Evening Review", f"{block}\n---\n\n## 🌙 Evening Review", 1)
    else:
        new = current + block
    daily_path.write_text(new)
    return True
