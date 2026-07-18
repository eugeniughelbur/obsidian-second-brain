"""Gemini text client for plain summarization calls (no grounding, no tools).

The cheap summarizer: /youtube prefers this over Grok when GEMINI_API_KEY is
set because gemini-2.5-flash has a generous free tier (as of 2026-07,
ai.google.dev/pricing). Same return shape as grok.call so call sites can fall
back transparently. Pattern from fork-insights round 2 (the api-ledger fork),
with one hygiene change: the key travels in the x-goog-api-key header, never
in the URL query string, so it cannot leak into access or proxy logs.
"""

from __future__ import annotations

import time
from typing import Any

import requests

from . import usage
from .config import GEMINI_API_KEY, get_optional

GEMINI_SUMMARY_MODEL = get_optional("GEMINI_SUMMARY_MODEL", "gemini-2.5-flash")
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_RETRIES = 3
BACKOFF_SECONDS = (1, 3, 8)


def call(
    prompt: str,
    *,
    command: str,
    model: str | None = None,
    max_output_tokens: int = 4000,
) -> dict[str, Any]:
    """Call Gemini generateContent. Returns {text, input_tokens, output_tokens,
    cost_usd, raw} - the grok.call shape, so callers can swap providers."""
    model = model or GEMINI_SUMMARY_MODEL
    headers = {
        "x-goog-api-key": GEMINI_API_KEY(),
        "Content-Type": "application/json",
    }
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_output_tokens},
    }

    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(API_URL.format(model=model), json=body, headers=headers, timeout=180)
            if r.status_code == 200:
                data = r.json()
                parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts).strip()
                if not text:
                    raise RuntimeError(f"Gemini returned no text (finishReason: "
                                       f"{(data.get('candidates') or [{}])[0].get('finishReason')})")
                u = data.get("usageMetadata") or {}
                in_tok = int(u.get("promptTokenCount") or 0)
                out_tok = int(u.get("candidatesTokenCount") or 0)
                # Free tier by default; 0.0 is honest for the default model.
                # If a paid tier/model is configured, the tokens are still logged.
                cost = 0.0
                usage.log_call(command, model, in_tok, out_tok, cost,
                               extra={"provider": "gemini"})
                return {
                    "text": text,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "cost_usd": cost,
                    "raw": data,
                }
            if r.status_code in (429, 500, 502, 503, 504):
                wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                print(f"[Gemini {r.status_code}, retrying in {wait}s...]")
                time.sleep(wait)
                continue
            raise RuntimeError(f"Gemini API error {r.status_code}: {r.text[:500]}")
        except requests.RequestException as e:
            last_err = e
            wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
            print(f"[Gemini network error: {e}, retrying in {wait}s...]")
            time.sleep(wait)

    raise RuntimeError(f"Gemini API failed after {MAX_RETRIES} retries: {last_err}")
