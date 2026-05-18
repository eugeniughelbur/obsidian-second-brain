"""Loads research-toolkit credentials and model defaults from ~/.config/obsidian-second-brain/.env"""

from pathlib import Path
from dotenv import load_dotenv
import os

CONFIG_DIR = Path.home() / ".config" / "obsidian-second-brain"
ENV_PATH = CONFIG_DIR / ".env"

load_dotenv(ENV_PATH)


def get_required(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise SystemExit(
            f"\n{name} not configured.\n"
            f"Add it to {ENV_PATH}\n"
            f"Or run install.sh from the obsidian-second-brain repo to set it up.\n"
        )
    return val


def get_optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip() or default


XAI_API_KEY = lambda: get_required("XAI_API_KEY")
PERPLEXITY_API_KEY = lambda: get_required("PERPLEXITY_API_KEY")
GEMINI_API_KEY = lambda: get_required("GEMINI_API_KEY")
YOUTUBE_API_KEY = lambda: get_optional("YOUTUBE_API_KEY", "")

GROK_MODEL = get_optional("GROK_MODEL", "grok-4")
PERPLEXITY_RESEARCH_MODEL = get_optional("PERPLEXITY_RESEARCH_MODEL", "sonar-pro")
PERPLEXITY_DEEP_MODEL = get_optional("PERPLEXITY_DEEP_MODEL", "sonar-deep-research")
NOTEBOOKLM_MODEL = get_optional("NOTEBOOKLM_MODEL", "gemini-2.5-flash")

VAULT_PATH = Path(get_required("OBSIDIAN_VAULT_PATH")).expanduser()
USAGE_LOG = Path.home() / ".research-toolkit" / "usage.log"
