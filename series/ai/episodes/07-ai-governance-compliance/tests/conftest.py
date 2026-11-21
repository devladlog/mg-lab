"""Test helpers. Azure is never called: a requests adapter answers inside the real azure-core RequestsTransport,
so the real pipeline (bearer token policy over HTTPS, retries, paging) runs against canned ARM responses.
The canned JSON follows the documented REST shapes; it was written for these tests, not captured from Azure."""
import io
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from requests.adapters import BaseAdapter
from urllib3.response import HTTPResponse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SUB = "00000000-0000-0000-0000-000000000000"
RG = "rg-mglab-ai-07"
RGP = f"/subscriptions/{SUB}/resourceGroups/{RG}"
ACC = f"{RGP}/providers/Microsoft.CognitiveServices/accounts"


class FakeArm(BaseAdapter):
    """Routes (method, path) to JSON bodies; records every request."""

    def __init__(self, routes: dict):
        super().__init__()
        self.routes = routes
        self.requests = []

    def send(self, request, **kwargs):
        url = urlparse(request.url)
        self.requests.append({"method": request.method, "path": url.path, "query": parse_qs(url.query),
                              "headers": dict(request.headers)})
        key = (request.method, url.path, parse_qs(url.query).get("$skiptoken", [None])[0])
        status, body = self.routes.get(key) or self.routes.get(key[:2]) or (404, {"error": {"code": "NotFound"}})
        data = json.dumps(body).encode()
        r = requests.Response()
        r.status_code = status
        r.raw = HTTPResponse(body=io.BytesIO(data), status=status, preload_content=False,
                             headers={"content-type": "application/json", "content-length": str(len(data))})
        r._content = data
        r.headers.update({"content-type": "application/json", "content-length": str(len(data))})
        r.url = request.url
        r.request = request
        return r

    def close(self):
        pass


class FakeCredential:
    def __init__(self):
        self.scopes = []

    def get_token(self, *scopes, **kwargs):
        from azure.core.credentials import AccessToken

        self.scopes.extend(scopes)
        return AccessToken("fake-arm-token", 4_102_444_800)

    def get_token_info(self, *scopes, options=None):
        from azure.core.credentials import AccessTokenInfo

        self.scopes.extend(scopes)
        return AccessTokenInfo("fake-arm-token", 4_102_444_800)


def account(name, tags=None, local_auth_disabled=True):
    return {"id": f"{ACC}/{name}", "name": name, "kind": "OpenAI", "location": "swedencentral",
            "tags": tags or {}, "properties": {"disableLocalAuth": local_auth_disabled,
                                               "publicNetworkAccess": "Enabled"}}


def deployment(name, model, version, sku="DataZoneStandard", upgrade="NoAutoUpgrade", policy="contoso-hr-strict"):
    return {"name": name, "sku": {"name": sku, "capacity": 10},
            "properties": {"model": {"format": "OpenAI", "name": model, "version": version},
                           "versionUpgradeOption": upgrade, "raiPolicyName": policy}}


STRICT_FILTERS = [{"name": "Jailbreak", "blocking": True, "enabled": True, "source": "Prompt"},
                  {"name": "Indirect Attack", "blocking": True, "enabled": True, "source": "Prompt"}]


def lab_routes():
    """The lab resource group as designed in infra/main.bicep: hr-bot account (compliant) + shadow account,
    with the shadow account non-compliant for the diagnostic-logs policy. Deployments list is paged."""
    hr, shadow = "mglab-gov-aoai-abc123", "mglab-gov-shadow-abc123"
    return {
        ("GET", f"{ACC}"): (200, {"value": [account(hr, {"ai-system-id": "hr-bot"}), account(shadow)]}),
        ("GET", f"{ACC}/{hr}/deployments", None): (200, {
            "value": [deployment("chat", "gpt-5-mini", "2025-08-07")],
            "nextLink": f"https://management.azure.com{ACC}/{hr}/deployments?api-version=2025-06-01&$skiptoken=p2"}),
        ("GET", f"{ACC}/{hr}/deployments", "p2"): (200, {"value": []}),
        ("GET", f"{ACC}/{shadow}/deployments"): (200, {"value": []}),
        ("GET", f"{ACC}/{hr}/raiPolicies/contoso-hr-strict"): (200, {"properties": {"contentFilters": STRICT_FILTERS}}),
        ("GET", f"{ACC}/{hr}/providers/Microsoft.Insights/diagnosticSettings"): (200, {"value": [
            {"name": "to-log-analytics", "properties": {
                "workspaceId": f"{RGP}/providers/Microsoft.OperationalInsights/workspaces/law",
                "logs": [{"category": "Audit", "enabled": True}, {"category": "RequestResponse", "enabled": True},
                         {"category": "Trace", "enabled": False}]}}]}),
        ("GET", f"{ACC}/{shadow}/providers/Microsoft.Insights/diagnosticSettings"): (200, {"value": []}),
        ("POST", f"{RGP}/providers/Microsoft.PolicyInsights/policyStates/latest/queryResults"): (200, {
            "@odata.context": "x", "@odata.count": 1,
            "value": [{"resourceId": f"{ACC}/{shadow}".upper(), "complianceState": "NonCompliant",
                       "policyAssignmentName": "ai-diagnostic-logs-audit",
                       "policyDefinitionName": "1b4d1c4e-934c-4703-944c-27c82c06bebb"}]}),
    }


@pytest.fixture
def fake_arm():
    return FakeArm(lab_routes())


@pytest.fixture
def arm(fake_arm):
    from azure.core.pipeline.transport import RequestsTransport

    from aigov.arm import Arm

    session = requests.Session()
    session.mount("https://", fake_arm)
    cred = FakeCredential()
    client = Arm(cred, transport=RequestsTransport(session=session, session_owner=False))
    client.credential = cred
    return client


@pytest.fixture
def register_path():
    return ROOT / "governance" / "register.yaml"
