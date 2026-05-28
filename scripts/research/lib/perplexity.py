"""Perplexity Sonar client. Uses the OpenAI-compatible /chat/completions endpoint."""

import re
import time
import requests
from typing import Any

from .config import PERPLEXITY_API_KEY, PERPLEXITY_RESEARCH_MODEL, PERPLEXITY_DEEP_MODEL

API_URL = "https://api.perplexity.ai/chat/completions"
MAX_RETRIES = 3
BACKOFF_SECONDS = (1, 3, 8)

# sonar-reasoning and sonar-deep-research wrap their internal deliberation in <think>...</think>.
# Strip it before returning to keep the output clean.
_THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


def call(prompt: str, *, model: str | None = None, deep: bool = False, max_tokens: int = 4000) -> dict[str, Any]:
    model = model or (PERPLEXITY_DEEP_MODEL if deep else PERPLEXITY_RESEARCH_MODEL)
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY()}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    timeout = 300 if deep else 120

    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(API_URL, json=body, headers=headers, timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                text = data["choices"][0]["message"]["content"]
                text = _THINK_BLOCK.sub("", text)
                # Handle unclosed <think> (truncated mid-reasoning) - drop everything from it onward
                if "<think>" in text:
                    text = text.split("<think>")[0]
                text = text.strip()
                citations = data.get("citations") or data.get("search_results") or []
                return {
                    "text": text,
                    "citations": citations,
                    "model": model,
                    "raw": data,
                }
            if r.status_code in (429, 500, 502, 503, 504):
                wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                print(f"[Perplexity {r.status_code}, retrying in {wait}s...]")
                time.sleep(wait)
                continue
            raise RuntimeError(f"Perplexity API error {r.status_code}: {r.text[:500]}")
        except requests.RequestException as e:
            last_err = e
            wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
            print(f"[Perplexity network error: {e}, retrying in {wait}s...]")
            time.sleep(wait)

    raise RuntimeError(f"Perplexity API failed after {MAX_RETRIES} retries: {last_err}")
