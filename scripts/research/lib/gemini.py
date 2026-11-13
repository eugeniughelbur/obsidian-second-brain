# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
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

GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"
GEMINI_SUMMARY_MODEL = get_optional("GEMINI_SUMMARY_MODEL", GEMINI_DEFAULT_MODEL)
# Model access is per-key-cohort (issue #211, both directions measured
# 2026-08-16): keys from before the 2.5 retirement generate with
# gemini-2.5-flash and 404 on the -latest aliases; keys created after it get
# "no longer available to new users" 404s on gemini-2.5-flash. The GET
# /models listing returns 200 for names a key cannot generate with, so only a
# generation call can validate a model. No single pinned name works for
# everyone: the default walks this ladder and sticks with the first model
# that generates. An explicit GEMINI_SUMMARY_MODEL or model= is never
# laddered - a configured name that 404s should fail loud, with the fix named.
# Lite alias before the full-Flash alias: on the free tier the Lite models
# carry ~25x the daily quota (15 RPM / 500 RPD vs 5 / 20, measured in #211),
# and the workloads here are summarization, where Lite is plenty.
MODEL_LADDER = (
    GEMINI_DEFAULT_MODEL,
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
    "gemini-3.1-flash-lite",
)
_ENV_HINT = ("set GEMINI_SUMMARY_MODEL in ~/.config/obsidian-second-brain/.env "
             "to a model your key can generate with")
_resolved_default: str | None = None

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_RETRIES = 3
BACKOFF_SECONDS = (1, 3, 8)


class _ModelUnavailable(RuntimeError):
    """The model name 404s for this API key - a cohort miss, not an outage."""


def call(
    prompt: str,
    *,
    command: str,
    model: str | None = None,
    max_output_tokens: int = 4000,
) -> dict[str, Any]:
    """Call Gemini generateContent. Returns {text, input_tokens, output_tokens,
    cost_usd, raw} - the grok.call shape, so callers can swap providers."""
    global _resolved_default
    explicit = model is not None or GEMINI_SUMMARY_MODEL != GEMINI_DEFAULT_MODEL
    if explicit:
        candidates = [model or GEMINI_SUMMARY_MODEL]
    elif _resolved_default:
        candidates = [_resolved_default]
    else:
        candidates = list(MODEL_LADDER)

    last_404: Exception | None = None
    for m in candidates:
        try:
            result = _generate(m, prompt, command=command, max_output_tokens=max_output_tokens)
        except _ModelUnavailable as e:
            last_404 = e
            if explicit:
                raise RuntimeError(
                    f"Gemini model '{m}' is not available to this API key "
                    f"(HTTP 404); {_ENV_HINT}. {e}") from e
            print(f"[Gemini model {m} not available to this key (404); trying the next fallback...]")
            continue
        if not explicit:
            _resolved_default = m
        return result

    raise RuntimeError(
        f"No Gemini model in the fallback ladder generates with this key "
        f"(tried: {', '.join(candidates)}); {_ENV_HINT}. Last error: {last_404}")


def _generate(
    model: str,
    prompt: str,
    *,
    command: str,
    max_output_tokens: int,
) -> dict[str, Any]:
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
            if r.status_code == 404:
                raise _ModelUnavailable(f"Gemini API error 404: {r.text[:300]}")
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
