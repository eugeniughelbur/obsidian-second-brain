"""Loads research-toolkit credentials and model defaults from ~/.config/obsidian-second-brain/.env"""

import os
from pathlib import Path

from dotenv import load_dotenv

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
OPENAI_API_KEY = lambda: get_required("OPENAI_API_KEY")
YOUTUBE_API_KEY = lambda: get_optional("YOUTUBE_API_KEY", "")

# grok-4 no longer appears in GET /v1/models (it still resolves server-side, but is
# unlisted). grok-4.5 is current and verified against the x_search tool.
GROK_MODEL = get_optional("GROK_MODEL", "grok-4.5")
PERPLEXITY_RESEARCH_MODEL = get_optional("PERPLEXITY_RESEARCH_MODEL", "sonar-pro")
PERPLEXITY_DEEP_MODEL = get_optional("PERPLEXITY_DEEP_MODEL", "sonar-deep-research")
NOTEBOOKLM_MODEL = get_optional("NOTEBOOKLM_MODEL", "gemini-2.5-flash")
# behavior_eval.py's judge - deliberately a different provider from GROK_MODEL,
# which generates the answers being judged, so grading a model's own answers
# never happens by default.
GPT_JUDGE_MODEL = get_optional("GPT_JUDGE_MODEL", "gpt-4o-mini")

VAULT_PATH = Path(get_required("OBSIDIAN_VAULT_PATH")).expanduser()
USAGE_LOG = Path.home() / ".research-toolkit" / "usage.log"
