"""Both SDKs raise different exception classes for the same HTTP problems. Map them to one small vocabulary."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional


class RunError(Exception):
    """Configuration problem (missing key, bad file). CLI exit code 2."""


@dataclass
class Failure(Exception):
    vendor: str
    kind: str            # quota | rate_limit | auth | bad_request | not_found | server | network
    message: str
    status: Optional[int] = None
    retry_after: Optional[float] = None

    def __str__(self) -> str:
        return f"{self.vendor} {self.kind} ({self.status}): {self.message}"

    @property
    def retryable(self) -> bool:
        return self.kind in ("rate_limit", "server", "network")


def classify(vendor: str, exc: BaseException) -> Failure:
    status = getattr(exc, "status_code", None)
    name = type(exc).__name__
    message = str(exc)[:200]
    if status is None:
        return Failure(vendor, "network", f"{name}: {message}")
    retry_after = None
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is not None and headers.get("retry-after"):
        try:
            retry_after = float(headers["retry-after"])
        except ValueError:
            pass
    if status == 429:
        # OpenAI uses 429 for both "slow down" and "your billing quota is used up". Only the first is worth retrying.
        kind = "quota" if getattr(exc, "code", None) == "insufficient_quota" else "rate_limit"
    elif status in (401, 403):
        kind = "auth"
    elif status == 404:
        kind = "not_found"
    elif status >= 500:
        kind = "server"
    else:
        kind = "bad_request"
    return Failure(vendor, kind, message, status, retry_after)


def with_retry(fn: Callable, *, attempts: int = 3, base_delay: float = 1.0, sleep: Optional[Callable[[float], None]] = None):
    """Retry only what is retryable, honour Retry-After, back off exponentially otherwise."""
    sleep = sleep or time.sleep
    for n in range(1, attempts + 1):
        try:
            return fn()
        except Failure as f:
            if not f.retryable or n == attempts:
                raise
            sleep(f.retry_after if f.retry_after is not None else base_delay * 2 ** (n - 1))
