"""One small HTTP layer for every call this episode makes: Entra bearer token, no keys, no retries unless asked.

It is the real azure-core pipeline (BearerTokenCredentialPolicy, UserAgentPolicy, optional RetryPolicy). The transport is
injectable so the tests can answer without a network; in the lab it is the default requests transport.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from urllib.parse import quote, urlencode

from azure.core.pipeline import Pipeline
from azure.core.pipeline.policies import BearerTokenCredentialPolicy, RetryPolicy, UserAgentPolicy
from azure.core.pipeline.transport import RequestsTransport
from azure.core.rest import HttpRequest

COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"
ARM_SCOPE = "https://management.azure.com/.default"
REQUEST_ID_HEADERS = ("apim-request-id", "x-ms-request-id", "x-requestid", "request-id", "x-request-id")


@dataclass
class Reply:
    status: int
    ms: int
    body: object = None
    text: str = ""
    headers: dict = field(default_factory=dict)
    error: str = ""            # transport-level problem (no HTTP status at all)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def request_id(self) -> str:
        low = {k.lower(): v for k, v in self.headers.items()}
        for h in REQUEST_ID_HEADERS:
            if low.get(h):
                return low[h]
        return ""

    @property
    def retry_after(self) -> str:
        return {k.lower(): v for k, v in self.headers.items()}.get("retry-after", "")

    def error_code(self) -> str:
        """Both 'error.code' shapes (Cognitive Services and Translator) and ARM's."""
        e = self.body.get("error") if isinstance(self.body, dict) else None
        if isinstance(e, dict):
            return f"{e.get('code', '')}: {e.get('message', '')}".strip(": ")[:300]
        return self.text[:200]


class Api:
    """`Api(credential).call(...)` for the data plane and the management plane, one pipeline per token scope."""

    def __init__(self, credential, transport=None, retries: int = 0, user_agent: str = "devladlog-aiplatform/1.0"):
        self.credential = credential
        self.transport = transport or RequestsTransport()
        self.retries = retries
        self.user_agent = user_agent
        self._pipes: dict[str, Pipeline] = {}

    def _pipe(self, scope: str) -> Pipeline:
        if scope not in self._pipes:
            policies = [UserAgentPolicy(user_agent=self.user_agent), BearerTokenCredentialPolicy(self.credential, scope)]
            if self.retries:
                policies.append(RetryPolicy(retry_total=self.retries, retry_backoff_factor=0.5))
            self._pipes[scope] = Pipeline(transport=self.transport, policies=policies)
        return self._pipes[scope]

    def call(self, method: str, url: str, scope: str = COGNITIVE_SCOPE, *, body=None, params: dict | None = None) -> Reply:
        if params:
            url += ("&" if "?" in url else "?") + urlencode(params, quote_via=quote)
        req = HttpRequest(method, url, json=body) if body is not None else HttpRequest(method, url)
        t0 = time.perf_counter()
        try:
            resp = self._pipe(scope).run(req).http_response
        except Exception as ex:                      # DNS, TLS, refused: there is no status to report
            return Reply(0, int((time.perf_counter() - t0) * 1000), error=f"{type(ex).__name__}: {ex}"[:300])
        ms = int((time.perf_counter() - t0) * 1000)
        text = resp.text() if resp.content else ""
        try:
            parsed = json.loads(text) if text else None
        except ValueError:
            parsed = None
        return Reply(resp.status_code, ms, parsed, text, dict(resp.headers))
