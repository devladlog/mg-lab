"""One adapter per wire format. Request and response shapes follow each vendor's own API reference (see README).

Adapters never raise for an API failure: they return Reply(error=...) so one broken provider does not stop the run.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .http import ApiError, is_local_url, post_json

Transport = Callable[[str, Any, dict, float], Any]

# anthropic-version values: Anthropic's API versions page lists 2026-10-21 (latest), 2023-06-01, 2023-01-01.
# In 2026-10-21 temperature, top_p and top_k are removed: sending any of them returns 400.
ANTHROPIC_DEFAULT_VERSION = "2026-10-21"
ANTHROPIC_NO_SAMPLING_FROM = "2026-10-21"


@dataclass
class Reply:
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float | None = 0.0   # None = not measured (human-collected answer)
    error: str = ""
    note: str = ""       # finish reason or anything worth showing next to the answer


def build_prompt(instructions: str, question: str, mode: str) -> tuple[str | None, str]:
    """mode 'inline': the same text for every AI (Copilot Chat has no system prompt we control).
    mode 'system': instructions go in each API's system field; Copilot Chat then gets them inline anyway."""
    if mode == "inline":
        return None, f"{instructions}\n\n{question}"
    if mode == "system":
        return instructions, question
    raise ValueError("instructions_mode must be 'inline' or 'system'")


class Provider:
    kind = ""

    def __init__(self, cfg: dict, transport: Transport | None = None):
        self.cfg = cfg
        self.id = cfg["id"]
        self.label = cfg.get("label", cfg["id"])
        self.model = cfg.get("model", "")
        self.max_tokens = int(cfg.get("max_tokens", 1500))
        self.timeout = float(cfg.get("timeout", 120))
        self.transport = transport or post_json

    def key(self) -> str:
        env = self.cfg.get("api_key_env", "")
        val = os.environ.get(env, "") if env else ""
        if not val:
            raise RuntimeError(f"environment variable {env or '(api_key_env not set)'} is empty")
        return val

    def problems(self) -> list[str]:
        out = []
        if self.kind != "manual" and (not self.model or self.model.upper().startswith("REPLACE")):
            out.append("model not set in config")
        if self.cfg.get("api_key_env") and not os.environ.get(self.cfg["api_key_env"]):
            out.append(f"{self.cfg['api_key_env']} not set")
        return out

    def ask(self, system: str | None, user: str, task_id: str = "") -> Reply:
        t0 = time.perf_counter()
        try:
            reply = self._ask(system, user, task_id)
        except ApiError as e:
            reply = Reply(error=str(e))
        except (ConnectionError, RuntimeError, ValueError, KeyError, TypeError) as e:
            reply = Reply(error=f"{type(e).__name__}: {e}")
        if self.kind != "manual":
            reply.seconds = time.perf_counter() - t0
        else:
            reply.seconds = None
        return reply

    def _ask(self, system: str | None, user: str, task_id: str) -> Reply:
        raise NotImplementedError


class OpenAIProvider(Provider):
    """POST /v1/responses. Text is read from output[] message items (never assume output[0].content[0])."""
    kind = "openai"

    def _ask(self, system, user, task_id):
        body: dict[str, Any] = {"model": self.model, "input": user, "max_output_tokens": self.max_tokens, "store": False}
        if system:
            body["instructions"] = system
        d = self.transport(self.cfg.get("base_url", "https://api.openai.com/v1/responses"), body,
                           {"Authorization": f"Bearer {self.key()}"}, self.timeout)
        text = "".join(part.get("text", "") for item in d.get("output", []) if item.get("type") == "message"
                       for part in item.get("content", []) if part.get("type") == "output_text")
        u = d.get("usage") or {}
        status = d.get("status", "")
        err = ""
        if status and status != "completed":
            err = f"status {status}: {json.dumps(d.get('incomplete_details') or d.get('error') or {})[:200]}"
        return Reply(text, int(u.get("input_tokens", 0) or 0), int(u.get("output_tokens", 0) or 0), error=err, note=status)


class AnthropicProvider(Provider):
    """POST /v1/messages with x-api-key, anthropic-version and a required max_tokens."""
    kind = "anthropic"

    def _ask(self, system, user, task_id):
        version = self.cfg.get("anthropic_version", ANTHROPIC_DEFAULT_VERSION)
        body: dict[str, Any] = {"model": self.model, "max_tokens": self.max_tokens,
                                "messages": [{"role": "user", "content": user}]}
        if system:
            body["system"] = system
        if "temperature" in self.cfg:
            if version >= ANTHROPIC_NO_SAMPLING_FROM:       # ISO dates compare as strings
                raise ValueError(f"temperature is removed in anthropic-version {version}: delete it from the config "
                                 f"or pin an older version")
            body["temperature"] = self.cfg["temperature"]
        d = self.transport(self.cfg.get("base_url", "https://api.anthropic.com/v1/messages"), body,
                           {"x-api-key": self.key(), "anthropic-version": version}, self.timeout)
        text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        u = d.get("usage") or {}
        stop = d.get("stop_reason", "")
        err = "model refused (stop_reason refusal)" if stop == "refusal" else ""
        return Reply(text, int(u.get("input_tokens", 0) or 0), int(u.get("output_tokens", 0) or 0), error=err, note=stop)


class GeminiProvider(Provider):
    """POST v1beta/models/{model}:generateContent with x-goog-api-key (the legacy-but-supported Gemini API)."""
    kind = "gemini"

    def _ask(self, system, user, task_id):
        body: dict[str, Any] = {"contents": [{"role": "user", "parts": [{"text": user}]}],
                                "generationConfig": {"maxOutputTokens": self.max_tokens}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        base = self.cfg.get("base_url", "https://generativelanguage.googleapis.com/v1beta")
        d = self.transport(f"{base}/models/{self.model}:generateContent", body, {"x-goog-api-key": self.key()}, self.timeout)
        fb = d.get("promptFeedback") or {}
        if fb.get("blockReason"):
            return Reply(error=f"prompt blocked: {fb['blockReason']}")
        cand = (d.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        u = d.get("usageMetadata") or {}
        out_tokens = int(u.get("candidatesTokenCount", 0) or 0) + int(u.get("thoughtsTokenCount", 0) or 0)
        finish = cand.get("finishReason", "")
        err = "" if text or not finish or finish == "STOP" else f"finishReason {finish}"
        return Reply(text, int(u.get("promptTokenCount", 0) or 0), out_tokens, error=err, note=finish)


class LocalProvider(Provider):
    """A local OpenAI-compatible server (Ollama /v1, LM Studio /v1, Foundry Local /v1): chat completions, no key needed."""
    kind = "local"

    def problems(self):
        out = [] if self.model and not self.model.upper().startswith("REPLACE") else ["model not set in config"]
        if not is_local_url(self.cfg.get("base_url", "")) and not self.cfg.get("allow_remote"):
            out.append("base_url is not a local address")
        return out

    def _ask(self, system, user, task_id):
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        body = {"model": self.model, "messages": msgs, "max_tokens": self.max_tokens, "stream": False}
        base = self.cfg["base_url"].rstrip("/")
        d = self.transport(base + "/chat/completions", body, {"Authorization": "Bearer none"}, self.timeout)
        choice = (d.get("choices") or [{}])[0]
        u = d.get("usage") or {}
        return Reply((choice.get("message") or {}).get("content") or "", int(u.get("prompt_tokens", 0) or 0),
                     int(u.get("completion_tokens", 0) or 0), note=choice.get("finish_reason") or "")


class ManualProvider(Provider):
    """Answers a human collected in a product with no API we may use (Microsoft Copilot Chat in the lab).
    answers_file: JSON {task_id: answer text}. The harness never invents an answer: a missing one is an error row."""
    kind = "manual"

    def __init__(self, cfg, transport=None, base_dir: Path | None = None):
        super().__init__(cfg, transport)
        path = Path(cfg["answers_file"])
        self.path = path if path.is_absolute() or base_dir is None else base_dir / path
        self._answers: dict | None = None

    def problems(self):
        return [] if self.path.exists() else [f"answers file {self.path.name} not found (run `prompts` and paste the answers)"]

    def _ask(self, system, user, task_id):
        if self._answers is None:
            self._answers = json.loads(self.path.read_text(encoding="utf-8"))
        text = (self._answers.get(task_id) or "").strip()
        if not text:
            return Reply(error=f"no manual answer for task {task_id}")
        return Reply(text)


KINDS = {c.kind: c for c in (OpenAIProvider, AnthropicProvider, GeminiProvider, LocalProvider, ManualProvider)}


def build(cfg: dict, transport: Transport | None = None, base_dir: Path | None = None) -> Provider:
    kind = cfg.get("kind")
    if kind not in KINDS:
        raise ValueError(f"unknown provider kind {kind!r} (use one of {sorted(KINDS)})")
    if kind == "manual":
        return ManualProvider(cfg, transport, base_dir)
    return KINDS[kind](cfg, transport)
