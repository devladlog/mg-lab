"""Function middleware that writes an audit record for every tool the agent actually runs."""
from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_framework import FunctionInvocationContext, FunctionMiddleware


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


class AuditTrail(FunctionMiddleware):
    """Records tool, arguments, outcome and duration. Optionally appends JSON lines to a file."""

    def __init__(self, path: Path | str | None = None, *, max_result_chars: int = 300):
        self.records: list[dict] = []
        self.path = Path(path) if path else None
        self.max_result_chars = max_result_chars

    async def process(self, context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]) -> None:
        start = time.perf_counter()
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tool": context.function.name,
            "arguments": _plain(context.arguments),
        }
        try:
            await call_next()
            text = _result_text(context.result)
            record["outcome"] = _outcome(text)
            record["result"] = text[: self.max_result_chars]
        except Exception as exc:  # recorded, then re-raised: the framework turns it into a tool error
            record["outcome"] = "exception"
            record["result"] = type(exc).__name__
            raise
        finally:
            record["ms"] = round((time.perf_counter() - start) * 1000, 1)
            self.records.append(record)
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\n")


def _result_text(result: Any) -> str:
    """Tool results arrive as a list of Content items (text for our JSON-returning tools)."""
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        return "".join(getattr(c, "text", None) or "" for c in result)
    return json.dumps(_plain(result), default=str)


def _outcome(text: str) -> str:
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return "ok"
    if isinstance(data, dict) and (data.get("ok") is False or "error" in data):
        return "refused" if data.get("error") == "policy" else "error"
    return "ok"
