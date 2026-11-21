"""Client for any OpenAI-compatible local server: Ollama (/v1), LM Studio (/v1), Foundry Local (dynamic port + /v1)."""
from __future__ import annotations

import time
from typing import Any

from .http import request_json
from .ollama import ChatResult

KNOWN_SERVERS = {
    "ollama": "http://127.0.0.1:11434/v1",      # Ollama docs: http://localhost:11434/v1/
    "lmstudio": "http://127.0.0.1:1234/v1",     # LM Studio docs: http://localhost:1234/v1
    # Foundry Local picks a dynamic port each start: read it with `foundry server status`, then append /v1.
}


class OpenAICompatClient:
    def __init__(self, base_url: str, api_key: str = "none", timeout: float = 600.0):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"}   # local servers ignore the value but clients send one
        self.timeout = timeout

    def models(self) -> list[str]:
        d = request_json("GET", self.base_url + "/models", headers=self.headers, timeout=self.timeout)
        return [m.get("id", "") for m in d.get("data", [])]

    def chat(self, model: str, messages: list[dict], *, response_format: dict | None = None,
             max_tokens: int | None = None, temperature: float | None = None, seed: int | None = None) -> ChatResult:
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if response_format is not None:
            body["response_format"] = response_format
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature
        if seed is not None:
            body["seed"] = seed
        t0 = time.perf_counter()
        d = request_json("POST", self.base_url + "/chat/completions", body, headers=self.headers, timeout=self.timeout)
        wall = time.perf_counter() - t0
        choice = (d.get("choices") or [{}])[0]
        usage = d.get("usage") or {}
        return ChatResult(
            text=(choice.get("message") or {}).get("content") or "", model=d.get("model", model),
            done_reason=choice.get("finish_reason") or "", prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            gen_tokens=int(usage.get("completion_tokens", 0) or 0), total_s=wall, eval_s=wall, raw=d)
        # eval_s = wall clock here: the compat API has no per-phase timings, so tokens/s includes prompt time.


def probe(servers: dict[str, str], timeout: float = 2.0) -> dict[str, dict]:
    """Ask each base URL for GET /models. Returns {name: {"up": bool, "models": [...], "error": str}}."""
    out: dict[str, dict] = {}
    for name, url in servers.items():
        try:
            out[name] = {"up": True, "models": OpenAICompatClient(url, timeout=timeout).models(), "error": ""}
        except Exception as e:  # connection refused, HTTP error, bad JSON: all mean "not usable"
            out[name] = {"up": False, "models": [], "error": str(e)[:200]}
    return out
