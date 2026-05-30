# scripts/research/lib/http.py
"""Shared requests.Session with polite User-Agent + retries on 5xx.

Sources should NOT create their own sessions; import `get_session()` instead.
The User-Agent is built from the per-client name + optional contact email
loaded from source_config (RESEARCH_CONTACT_EMAIL env var).
"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# source_config holds only the polite-pool email + tunables (no vault path, no
# API keys), so importing it here is safe. Guarded in case it is ever absent.
try:
    from .source_config import get_contact_email
except ImportError:
    def get_contact_email() -> str | None:
        return None

DEFAULT_TIMEOUT = 15  # seconds; sources can override per-call
USER_AGENT_BASE = "obsidian-second-brain/1.0"


def polite_user_agent(client_name: str, contact_email: str | None) -> str:
    """Build a User-Agent string in arXiv/CrossRef/OpenAlex polite-pool format."""
    if contact_email:
        return f"{client_name} (mailto:{contact_email})"
    return client_name


def get_session(retries: int = 3, backoff: float = 1.0) -> requests.Session:
    """Return a requests.Session with retry-on-5xx wired in.

    Each source client should call this once at construction.
    """
    sess = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    sess.headers.update({"User-Agent": polite_user_agent(USER_AGENT_BASE, get_contact_email())})
    return sess


__all__ = ["get_session", "polite_user_agent", "DEFAULT_TIMEOUT", "USER_AGENT_BASE"]
