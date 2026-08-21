"""OpenAI GPT client - used ONLY as the blind judge in behavior_eval.py.

Deliberately a different provider from research.lib.grok, which generates the
two answers behavior_eval.py compares: judging with the same model that wrote
an answer risks self-preference bias inflating the vault-on score, so the
answer generator and the judge must never resolve to the same provider+model.

Uses the official `openai` package - already a project dependency
(pyproject.toml), and already imported elsewhere in this codebase for Whisper
transcription (research/lib/podcast.py) - rather than a hand-rolled HTTP
client, so this file only wires auth, retries and the shared return shape.
"""

from __future__ import annotations

import time
from typing import Any

from . import usage
from .config import GPT_JUDGE_MODEL, OPENAI_API_KEY

MAX_RETRIES = 3
BACKOFF_SECONDS = (1, 3, 8)

# Pricing per 1M tokens (approximate, for spend visibility only - not billing).
# Unknown models fall back to the gpt-4o-mini rate and are flagged via
# `cost_is_estimate`, same convention as GROK_PRICING in research/lib/usage.py.
OPENAI_PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}


def _is_estimate(model: str) -> bool:
    return model not in OPENAI_PRICING


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = OPENAI_PRICING.get(model, OPENAI_PRICING["gpt-4o-mini"])
    return (input_tokens / 1_000_000) * rates["input"] + (output_tokens / 1_000_000) * rates["output"]


def call(
    prompt: str,
    *,
    command: str,
    model: str | None = None,
    max_output_tokens: int = 4000,
) -> dict[str, Any]:
    """Call OpenAI's chat completions API. Returns {text, model, input_tokens,
    output_tokens, cost_usd, cost_is_estimate, raw} - the grok.call shape, so
    behavior_eval.py's judge can be swapped for another provider without
    touching call sites."""
    from openai import APIConnectionError, APIStatusError, OpenAI

    model = model or GPT_JUDGE_MODEL
    client = OpenAI(api_key=OPENAI_API_KEY())

    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_output_tokens,
            )
            text = (resp.choices[0].message.content or "").strip()
            u = resp.usage
            input_tokens = getattr(u, "prompt_tokens", 0) or 0
            output_tokens = getattr(u, "completion_tokens", 0) or 0
            cost = _estimate_cost(model, input_tokens, output_tokens)
            usage.log_call(command, model, input_tokens, output_tokens, cost,
                           extra={"provider": "openai"})
            return {
                "text": text,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost,
                "cost_is_estimate": _is_estimate(model),
                "raw": resp.model_dump() if hasattr(resp, "model_dump") else {},
            }
        except APIStatusError as e:
            status = getattr(e, "status_code", None)
            if status in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                print(f"[OpenAI {status}, retrying in {wait}s...]")
                time.sleep(wait)
                continue
            raise RuntimeError(f"OpenAI API error {status}: {str(e)[:500]}") from e
        except APIConnectionError as e:
            last_err = e
            wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
            print(f"[OpenAI network error: {e}, retrying in {wait}s...]")
            time.sleep(wait)

    raise RuntimeError(f"OpenAI API failed after {MAX_RETRIES} retries: {last_err}")
