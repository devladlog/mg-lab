"""Read-only Azure Resource Manager calls through the azure-core pipeline (Entra ID token, retries, paging).

Only GET/POST reads with documented api-versions; nothing here can change a resource.
"""
from __future__ import annotations

from azure.core import PipelineClient
from azure.core.pipeline.policies import (BearerTokenCredentialPolicy, HeadersPolicy, NetworkTraceLoggingPolicy,
                                          RetryPolicy, UserAgentPolicy)
from azure.core.rest import HttpRequest

ARM = "https://management.azure.com"
SCOPE = "https://management.azure.com/.default"

API = {
    "cognitive": "2025-06-01",           # Microsoft.CognitiveServices accounts, deployments, raiPolicies
    "diagnostics": "2021-05-01-preview",  # Microsoft.Insights/diagnosticSettings
    "policy_states": "2019-10-01",       # Microsoft.PolicyInsights policyStates/latest/queryResults
}


class ArmError(RuntimeError):
    def __init__(self, status: int, method: str, url: str, body: str):
        super().__init__(f"{method} {url} -> HTTP {status}: {body[:300]}")
        self.status = status


class Arm:
    def __init__(self, credential, *, transport=None, base_url: str = ARM):
        policies = [
            HeadersPolicy(),
            UserAgentPolicy(sdk_moniker="mglab-aigov/1.0"),
            RetryPolicy(retry_total=3),
            BearerTokenCredentialPolicy(credential, SCOPE),
            NetworkTraceLoggingPolicy(),
        ]
        self._client = PipelineClient(base_url=base_url, policies=policies, transport=transport)

    def _send(self, method: str, url: str, params: dict | None = None, json=None) -> dict:
        # send_request() does not join relative paths with base_url (generated SDKs call format_url first)
        request = HttpRequest(method, self._client.format_url(url), params=params, json=json)
        response = self._client.send_request(request)
        if response.status_code >= 400:
            raise ArmError(response.status_code, method, url, response.text())
        return response.json() if response.content else {}

    def list(self, url: str, api_version: str, *, method: str = "GET", params: dict | None = None) -> list[dict]:
        """Follow nextLink (ARM) and @odata.nextLink (Policy Insights) until the last page."""
        items: list[dict] = []
        page = self._send(method, url, params={"api-version": api_version, **(params or {})})
        while True:
            items.extend(page.get("value", []))
            nxt = page.get("nextLink") or page.get("@odata.nextLink")
            if not nxt:
                return items
            page = self._send(method, nxt)       # the link already carries api-version and the skip token

    def get(self, url: str, api_version: str) -> dict:
        return self._send("GET", url, params={"api-version": api_version})


def rg_path(subscription_id: str, resource_group: str) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
