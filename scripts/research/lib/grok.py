"""xAI Grok client. Uses the Agent Tools API at /v1/responses.

Live Search (`search_parameters` on /v1/chat/completions) was deprecated by xAI and
now returns HTTP 410 - do not reintroduce it. Live X/web access comes from the
`tools` argument below instead.
"""

import re
import time
from typing import Any

import requests

from . import usage
from .config import GROK_MODEL, XAI_API_KEY

# Strip Grok's internal tool-call protocol XML if it leaks into output text.
# Seen patterns:
#   <xai:function_call>...</xai:function_call>
#   <parameter name="...">...</parameter>
_TOOL_CALL_LEAK = re.compile(
    r"<xai:function_call[^>]*>.*?</xai:function_call>|<parameter\s+name=\"[^\"]*\">[^<]*</parameter>",
    re.DOTALL,
)

API_URL = "https://api.x.ai/v1/responses"
MAX_RETRIES = 3
BACKOFF_SECONDS = (1, 3, 8)


def call(
    prompt: str,
    *,
    command: str,
    model: str | None = None,
    tools: list[dict] | None = None,
    max_output_tokens: int = 4000,
) -> dict[str, Any]:
    """Call xAI's /v1/responses endpoint. Returns {text, usage, raw}.

    tools example: [{"type": "x_search"}] for live X access,
                   [{"type": "web_search"}] for web,
                   or both. Grok decides when to invoke each.
    """
    model = model or GROK_MODEL
    headers = {
        "Authorization": f"Bearer {XAI_API_KEY()}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": model,
        "input": prompt,
        "max_output_tokens": max_output_tokens,
    }
    if tools:
        body["tools"] = tools

    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(API_URL, json=body, headers=headers, timeout=180)
            if r.status_code == 200:
                data = r.json()
                text = _extract_text(data)
                u = data.get("usage", {})
                input_tokens = u.get("input_tokens") or u.get("prompt_tokens") or 0
                output_tokens = u.get("output_tokens") or u.get("completion_tokens") or 0
                cost = usage.estimate_cost(model, input_tokens, output_tokens)
                usage.log_call(command, model, input_tokens, output_tokens, cost,
                               extra={"tools": [t.get("type") for t in (tools or [])]})
                return {
                    "text": text,
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": cost,
                    "cost_is_estimate": usage.is_estimate(model),
                    "raw": data,
                }
            if r.status_code in (429, 500, 502, 503, 504):
                wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                print(f"[Grok {r.status_code}, retrying in {wait}s...]")
                time.sleep(wait)
                continue
            raise RuntimeError(f"Grok API error {r.status_code}: {r.text[:500]}")
        except requests.RequestException as e:
            last_err = e
            wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
            print(f"[Grok network error: {e}, retrying in {wait}s...]")
            time.sleep(wait)

    raise RuntimeError(f"Grok API failed after {MAX_RETRIES} retries: {last_err}")


def _extract_text(data: dict) -> str:
    """Pull text from xAI /v1/responses payload (handles output_text + nested output array).

    Also strips leaked tool-call protocol XML from the model's text output.
    """
    if "output_text" in data and isinstance(data["output_text"], str):
        return _clean(data["output_text"])
    output = data.get("output", [])
    chunks: list[str] = []
    for item in output:
        if isinstance(item, dict):
            if item.get("type") == "message":
                for c in item.get("content", []):
                    if isinstance(c, dict) and c.get("type") in ("output_text", "text"):
                        chunks.append(c.get("text", ""))
            elif item.get("type") in ("output_text", "text"):
                chunks.append(item.get("text", ""))
    return _clean("\n".join([c for c in chunks if c]))


def _clean(text: str) -> str:
    """Remove leaked tool-call XML and trim leading/trailing whitespace."""
    cleaned = _TOOL_CALL_LEAK.sub("", text)
    return cleaned.strip()
