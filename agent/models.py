"""
Model adapters. Every adapter takes a Messages-API-shaped request and returns a
Messages-API-shaped response, so the agent loop never knows which one it has.

  AnthropicModel   the real API (needs ANTHROPIC_API_KEY); standard library HTTP, no SDK
  MockModel        offline and deterministic; see agent/mock.py for exactly what it does

Built by Avinash Rayudu.
"""
from __future__ import annotations

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
                "system": system, "messages": messages}
        if tools:
            body["tools"] = tools
        data = json.dumps(body).encode()
        for attempt in range(6):
            req = urllib.request.Request(API_URL, data=data, method="POST", headers={
                "x-api-key": self.key, "anthropic-version": CONFIG["api_version"], "content-type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 529) and attempt < 5:
                    time.sleep(min(60, 2 ** attempt * 3))
                    continue
                raise RuntimeError(f"API error {e.code}: {e.read()[:400]!r}") from e
        raise RuntimeError("API retries exhausted")


def price(model: str, input_tokens: int, output_tokens: int):
    p = CONFIG["prices_per_mtok"].get(model)
    if not p:
        return None
    tier = p
    if "over_100k" in p and input_tokens > 100_000:
        tier = p["over_100k"]
    return input_tokens / 1e6 * tier["input"] + output_tokens / 1e6 * tier["output"]
