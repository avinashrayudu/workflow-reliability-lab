"""
Model adapters. Every adapter takes a Messages-API-shaped request and returns a
Messages-API-shaped response, so the agent loop never knows which one it has.

  AnthropicModel   the real API (needs ANTHROPIC_API_KEY); standard library HTTP, no SDK
  MockModel        offline and deterministic; see agent/mock.py for exactly what it does

Built by Avinash Rayudu.
"""
from __future__ import annotations

import http.client
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "config" / "models.yaml").read_text())
API_URL = "https://api.anthropic.com/v1/messages"


def estimate_tokens(obj) -> int:
    """About 4 characters per token. Used for the dry run and for mock mode only."""
    s = obj if isinstance(obj, str) else json.dumps(obj)
    return max(1, len(s) // 4)


class AnthropicModel:
    live = True

    def __init__(self, model=None, max_tokens=None, temperature=None):
        self.key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.key:
            raise SystemExit("ANTHROPIC_API_KEY is not set. Live mode needs a key; use --mode mock to run offline.")
        self.model = model or CONFIG["default_model"]
        self.max_tokens = max_tokens or CONFIG["max_tokens"]
        self.temperature = CONFIG["temperature"] if temperature is None else temperature

    def create(self, system, messages, tools, context=None):
        body = {"model": self.model, "max_tokens": self.max_tokens, "temperature": self.temperature,
                "system": cached_system(system), "messages": cached_messages(messages)}
        if tools:
            body["tools"] = cached_tools(tools)
        data = json.dumps(body).encode()
        last = None
        for attempt in range(8):
            req = urllib.request.Request(API_URL, data=data, method="POST", headers={
                "x-api-key": self.key, "anthropic-version": CONFIG["api_version"], "content-type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    resp = json.loads(r.read())
                resp["_cost_usd"] = price_usage(self.model, resp.get("usage", {}))
                return resp
            except urllib.error.HTTPError as e:
                if e.code in RETRY_CODES and attempt < 7:
                    wait = e.headers.get("retry-after") if e.headers else None
                    time.sleep(min(90, float(wait) if wait and wait.replace(".", "", 1).isdigit() else 2 ** attempt * 3))
                    continue
                raise RuntimeError(f"API error {e.code}: {e.read()[:400]!r}") from e
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as e:
                # a dropped connection or timeout is retried; nothing was billed for a request that never answered
                last = e
                if attempt < 7:
                    time.sleep(min(90, 2 ** attempt * 3))
                    continue
        raise RuntimeError(f"API retries exhausted: {last!r}")


RETRY_CODES = (408, 429, 500, 502, 503, 504, 529)
EPHEMERAL = {"type": "ephemeral"}


def cached_system(system):
    """The system prompt is identical across every call of a variant, so it is cached once and read after that."""
    return [{"type": "text", "text": system, "cache_control": EPHEMERAL}]


def cached_tools(tools):
    tools = [dict(t) for t in tools]
    tools[-1]["cache_control"] = EPHEMERAL
    return tools


def cached_messages(messages):
    """Mark the end of the conversation so the next turn of the same agent loop reads it from cache.
    The conversation itself is not modified; only the copy that is sent."""
    if not messages:
        return messages
    msgs = list(messages)
    last = dict(msgs[-1])
    c = last["content"]
    blocks = [{"type": "text", "text": c}] if isinstance(c, str) else [dict(b) for b in c]
    blocks[-1]["cache_control"] = EPHEMERAL
    last["content"] = blocks
    msgs[-1] = last
    return msgs


def _rates(model, prompt_tokens):
    p = CONFIG["prices_per_mtok"].get(model)
    if not p:
        return None
    tier = p["over_100k"] if "over_100k" in p and prompt_tokens > 100_000 else p
    return {"input": tier["input"], "output": tier["output"],
            # if a cache price is not configured, assume the standard multipliers: 1.25x to write, 0.1x to read
            "cache_write": tier.get("cache_write", tier["input"] * 1.25),
            "cache_read": tier.get("cache_read", tier["input"] * 0.1)}


def price(model: str, input_tokens: int, output_tokens: int, cache_write: int = 0, cache_read: int = 0):
    """Dollar cost of one request. The prompt-length tier counts every input token, cached or not."""
    r = _rates(model, input_tokens + cache_write + cache_read)
    if r is None:
        return None
    return (input_tokens * r["input"] + output_tokens * r["output"] + cache_write * r["cache_write"]
            + cache_read * r["cache_read"]) / 1e6


def price_usage(model, usage):
    return price(model, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)),
                 int(usage.get("cache_creation_input_tokens", 0) or 0),
                 int(usage.get("cache_read_input_tokens", 0) or 0))
