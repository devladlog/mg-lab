"""Ollama native API client (non-streaming). Endpoints and field names from docs.ollama.com/api."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .http import request_json

NS = 1e9  # Ollama reports durations in nanoseconds


@dataclass
class ChatResult:
    text: str
    thinking: str = ""
    model: str = ""
    done_reason: str = ""
    prompt_tokens: int = 0
    gen_tokens: int = 0
    load_s: float = 0.0
    prompt_eval_s: float = 0.0
    eval_s: float = 0.0
    total_s: float = 0.0
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def gen_tps(self) -> float:
        """Generated tokens per second: eval_count / eval_duration (both reported by the server)."""
        return self.gen_tokens / self.eval_s if self.eval_s > 0 else 0.0

    @property
    def prompt_tps(self) -> float:
        return self.prompt_tokens / self.prompt_eval_s if self.prompt_eval_s > 0 else 0.0


class OllamaClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: float = 600.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _call(self, method: str, path: str, payload: Any | None = None) -> Any:
        return request_json(method, self.base_url + path, payload, timeout=self.timeout)

    def tags(self) -> list[dict]:
        """GET /api/tags: models on disk (size in bytes, details.parameter_size, details.quantization_level)."""
        return self._call("GET", "/api/tags").get("models", [])

    def ps(self) -> list[dict]:
        """GET /api/ps: models in memory (size, size_vram, context_length, expires_at)."""
        return self._call("GET", "/api/ps").get("models", [])

    def show(self, model: str) -> dict:
        """POST /api/show: details and model_info (architecture keys such as llama.block_count)."""
        return self._call("POST", "/api/show", {"model": model})

    def chat(self, model: str, messages: list[dict], *, fmt: Any | None = None, options: dict | None = None,
             keep_alive: str | int | None = None, think: bool | str | None = None) -> ChatResult:
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if fmt is not None:
            body["format"] = fmt            # "json" or a JSON schema object
        if options:
            body["options"] = options       # seed, temperature, num_ctx, num_predict, ...
        if keep_alive is not None:
            body["keep_alive"] = keep_alive
        if think is not None:
            body["think"] = think
        d = self._call("POST", "/api/chat", body)
        msg = d.get("message") or {}
        return ChatResult(
            text=msg.get("content", ""), thinking=msg.get("thinking", "") or "", model=d.get("model", model),
            done_reason=d.get("done_reason", ""), prompt_tokens=int(d.get("prompt_eval_count", 0) or 0),
            gen_tokens=int(d.get("eval_count", 0) or 0), load_s=(d.get("load_duration", 0) or 0) / NS,
            prompt_eval_s=(d.get("prompt_eval_duration", 0) or 0) / NS, eval_s=(d.get("eval_duration", 0) or 0) / NS,
            total_s=(d.get("total_duration", 0) or 0) / NS, raw=d)

    def unload(self, model: str) -> None:
        """Docs: an empty messages array with keep_alive 0 unloads the model from memory."""
        self._call("POST", "/api/chat", {"model": model, "messages": [], "keep_alive": 0})


def placement(ps_entry: dict) -> str:
    """Where a loaded model sits, computed from /api/ps (size vs size_vram). 'ollama ps' prints the same idea."""
    size, vram = int(ps_entry.get("size", 0) or 0), int(ps_entry.get("size_vram", 0) or 0)
    if size <= 0:
        return "unknown"
    if vram >= size:
        return "100% GPU"
    if vram <= 0:
        return "100% CPU"
    gpu = round(100 * vram / size)
    return f"{100 - gpu}%/{gpu}% CPU/GPU"
