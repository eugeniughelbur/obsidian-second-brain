#!/usr/bin/env bash
# =============================================================================
# scripts/orcarouter-live-test.sh - live smoke test for the OrcaRouter gateway
# =============================================================================
# Verifies the OpenAI-compatible chat endpoint that the OpenCode build's
# opencode.json example points at (https://api.orcarouter.ai/v1). Each case
# prints PASS/FAIL with a short real-response excerpt. No dependencies beyond
# curl.
#
# Get an API key: sign up at https://www.orcarouter.ai/console, create a key
# (it starts with sk-orca-), then run:
#   ORCAROUTER_API_KEY=sk-orca-... bash scripts/orcarouter-live-test.sh
# =============================================================================

set -u

KEY="${ORCAROUTER_API_KEY:-}"
if [[ -z "$KEY" ]]; then
  echo "ERROR: ORCAROUTER_API_KEY is not set." >&2
  echo "Get a key at https://www.orcarouter.ai/console and retry:" >&2
  echo "  ORCAROUTER_API_KEY=sk-orca-... bash scripts/orcarouter-live-test.sh" >&2
  exit 1
fi

API="https://api.orcarouter.ai/v1/chat/completions"
AUTH="Authorization: Bearer $KEY"
PASS=0
FAIL=0

check_case() {
  local name="$1" payload="$2"
  local out code
  out=$(curl -sS -w $'\n%{http_code}' "$API" \
    -H "$AUTH" \
    -H "Content-Type: application/json" \
    -H "HTTP-Referer: https://github.com/eugeniughelbur/obsidian-second-brain" \
    -H "X-Title: obsidian-second-brain" \
    -d "$payload" 2>&1)
  code="${out##*$'\n'}"
  body="${out%$'\n'*}"
  if [[ "$code" == "200" ]]; then
    echo "PASS  $name (HTTP $code)"
    PASS=$((PASS + 1))
  else
    echo "FAIL  $name (HTTP $code): ${body:0:200}"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== OrcaRouter live smoke test ==="

# A pinned model. opencode parses the config "orcarouter/openai/gpt-5.5" into
# provider "orcarouter" + model "openai/gpt-5.5", and the SDK sends the bare
# model id as the wire model - this is that wire form.
check_case "openai/gpt-5.5 (wire form of orcarouter/openai/gpt-5.5)" \
  '{"model":"openai/gpt-5.5","messages":[{"role":"user","content":"Reply with exactly: PONG"}],"max_tokens":32}'

# The smart router, as referenced in the docs.
check_case "orcarouter/auto" \
  '{"model":"orcarouter/auto","messages":[{"role":"user","content":"Reply with exactly: PONG"}],"max_tokens":32}'

# A strong pinned model for the synthesis-heavy commands.
check_case "anthropic/claude-sonnet-5" \
  '{"model":"anthropic/claude-sonnet-5","messages":[{"role":"user","content":"Reply with exactly: PONG"}],"max_tokens":32}'

# Error path: a bogus key must be rejected cleanly (401), not crash.
bad=$(curl -sS -o /dev/null -w "%{http_code}" "$API" \
  -H "Authorization: Bearer sk-orca-invalid" \
  -H "Content-Type: application/json" \
  -d '{"model":"orcarouter/auto","messages":[{"role":"user","content":"PONG"}],"max_tokens":16}' 2>&1)
if [[ "$bad" == "401" ]]; then
  echo "PASS  invalid key rejected (HTTP $bad)"
  PASS=$((PASS + 1))
else
  echo "FAIL  invalid key not rejected (HTTP $bad)"
  FAIL=$((FAIL + 1))
fi

echo "=== $PASS passed, $FAIL failed ==="
[[ "$FAIL" -eq 0 ]]
