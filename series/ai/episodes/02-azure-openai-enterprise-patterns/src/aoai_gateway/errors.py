"""Turn a gateway/Azure OpenAI error into a decision the app can act on.

Sources (Microsoft Learn):
  * llm-token-limit: over the tokens-per-minute rate -> 429 with Retry-After; over the token quota -> 403.
  * Backend circuit breaker tripped (and no healthy pool member) -> 503 from API Management.
  * Content filtering: HTTP 400 with code "content_filter"; don't retry the same prompt unchanged.
  * The OpenAI SDK already retries 408/409/429/5xx (twice by default) and honours retry-after(-ms); when you get the
    exception, those retries are spent.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class Decision:
    kind: str            # throttled | quota_exhausted | content_filtered | unavailable | auth | not_found | bad_request | backend_error
    retry: bool          # is retrying the same request later reasonable?
    retry_after_s: float | None
    message: str


def _retry_after(headers: Mapping[str, str]) -> float | None:
    h = {k.lower(): v for k, v in headers.items()}
    for name, divisor in (("retry-after-ms", 1000.0), ("retry-after", 1.0)):
        try:
            return float(h[name]) / divisor
        except (KeyError, ValueError):
            continue
    return None


def _error_code(body: Any) -> str | None:
    if isinstance(body, Mapping):
        inner = body.get("error", body)
        if isinstance(inner, Mapping) and inner.get("code"):
            return str(inner["code"])
    return None


def classify(status: int, headers: Mapping[str, str] | None = None, body: Any = None) -> Decision:
    headers = headers or {}
    retry_after = _retry_after(headers)
    code = _error_code(body)
    if status == 429:
        return Decision("throttled", True, retry_after, "Rate exceeded; wait for Retry-After.")
    if status == 403:
        return Decision("quota_exhausted", False, None, "Token quota used up; alert the owner.")
    if status == 400 and code == "content_filter":
        return Decision("content_filtered", False, None, "Content filtered; don't resend unchanged.")
    if status == 503:
        return Decision("unavailable", True, retry_after, "No healthy backend; retry later.")
    if status == 401:
        return Decision("auth", False, None, "Missing or invalid subscription key.")
    if status == 404:
        return Decision("not_found", False, None, "Unknown route or deployment name.")
    if status >= 500:
        return Decision("backend_error", True, retry_after, f"Server error {status}.")
    return Decision("bad_request", False, None, f"Client error {status}{f' ({code})' if code else ''}.")


def classify_exception(exc: Exception) -> Decision:
    """Classify an openai.APIStatusError (or anything with status_code/response/body)."""
    status = getattr(exc, "status_code", None)
    if status is None:
        return Decision("backend_error", True, None, f"{type(exc).__name__}: {exc}")
    response = getattr(exc, "response", None)
    headers = dict(response.headers) if response is not None else {}
    return classify(int(status), headers, getattr(exc, "body", None))
