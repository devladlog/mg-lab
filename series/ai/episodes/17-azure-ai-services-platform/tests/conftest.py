"""Test doubles. Nothing here calls Azure. The REAL azure-core pipeline and the REAL azure-ai-documentintelligence SDK send
their real requests (Entra bearer token, URL, JSON body) through a stand-in transport, and a small rule-based 'platform'
answers in the response shapes Learn documents. It proves our plumbing: routing, verdicts, rules, scanning, arithmetic.
It says nothing about what the real services return. The numbers in the fixtures (limit 500, counts, latencies) are invented."""
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from azure.core.pipeline.transport import HttpTransport
from azure.core.rest._requests_basic import RestRequestsTransportResponse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

ENDPOINT = "https://contoso-ai.cognitiveservices.azure.com"
SUB = "00000000-0000-0000-0000-000000000000"
RID = f"/subscriptions/{SUB}/resourceGroups/rg-contoso-ai/providers/Microsoft.CognitiveServices/accounts/contoso-ai"
CS_USER = "a97b65f3-24c7-4388-baec-2e87135dc908"
OWNER = "8e3af657-a8ff-443c-a75c-2fe8c4bcb635"


class FakeCredential:
    def __init__(self):
        self.scopes = []

    def get_token(self, *scopes, **kwargs):
        from azure.core.credentials import AccessToken
        self.scopes.extend(scopes)
        return AccessToken("fake-entra-token", 4_102_444_800)

    def get_token_info(self, *scopes, options=None):
        from azure.core.credentials import AccessTokenInfo
        self.scopes.extend(scopes)
        return AccessTokenInfo("fake-entra-token", 4_102_444_800)


def good_account(**over):
    a = {"name": "contoso-ai", "kind": "AIServices", "sku": {"name": "S0"}, "location": "westeurope",
         "tags": {"owner": "lab", "costcenter": "mglab"},
         "properties": {"provisioningState": "Succeeded", "customSubDomainName": "contoso-ai", "disableLocalAuth": True,
                        "publicNetworkAccess": "Enabled", "endpoint": ENDPOINT + "/"}}
    for k, v in over.items():
        if k == "properties":
            a["properties"].update(v)
        else:
            a[k] = v
    return a


GOOD_DIAG = [{"name": "to-log-analytics", "properties": {"workspaceId": "/subscriptions/x/resourceGroups/rg/providers/Microsoft.OperationalInsights/workspaces/w",
              "logs": [{"category": "Audit", "enabled": True}, {"category": "RequestResponse", "enabled": True}],
              "metrics": [{"category": "AllMetrics", "enabled": True}]}}]


def assignment(role_guid, scope=RID, ptype="User"):
    return {"properties": {"roleDefinitionId": f"/subscriptions/{SUB}/providers/Microsoft.Authorization/roleDefinitions/{role_guid}",
                           "principalId": "11111111-1111-1111-1111-111111111111", "principalType": ptype, "scope": scope}}


def metric_doc(name, per_api):
    """per_api: {api name or None: [values per minute]}"""
    ts = []
    for api, vals in per_api.items():
        t = {"data": [{"timeStamp": f"2026-11-21T10:{i:02d}:00Z", "total": v, "average": v} for i, v in enumerate(vals)]}
        if api:
            t["metadatavalues"] = [{"name": {"value": "apiname"}, "value": api}]
        ts.append(t)
    return {"name": {"value": name}, "timeseries": ts}


class FakePlatform(HttpTransport):
    """Answers like Foundry would, per documented shapes. `mode` switches behaviours."""

    def __init__(self, **mode):
        self.mode = {"data_plane": True, "throttle": None, "boom": None, "account": good_account(), "diag": GOOD_DIAG,
                     "roles": [assignment(CS_USER)], "arm_status": {}, **mode}
        self.calls = []

    def open(self): pass
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass

    def _resp(self, request, status, body=None, headers=None):
        r = requests.Response()
        r.status_code = status
        r._content = (json.dumps(body) if body is not None else "").encode()
        r.raw = io.BytesIO(r._content)
        r.headers.update({"Content-Type": "application/json", **(headers or {})})
        r.request = requests.Request(request.method, request.url).prepare()
        resp = RestRequestsTransportResponse(request=request, internal_response=r)
        resp.read()                      # what the real transport does for a non-streamed request
        return resp

    def send(self, request, **kwargs):
        u = urlparse(request.url)
        q = parse_qs(u.query)
        raw = getattr(request, 'content', None) or getattr(request, 'body', None)
        body = json.loads(raw) if raw else None
        h = {k.lower(): v for k, v in request.headers.items()}
        self.calls.append({"method": request.method, "host": u.hostname, "path": u.path, "query": q, "body": body, "headers": h})
        if self.mode["boom"] and self.mode["boom"] in u.path:
            raise requests.ConnectionError("name resolution failed")
        if h.get("authorization") != "Bearer fake-entra-token":
            return self._resp(request, 401, {"error": {"code": "401", "message": "Access denied due to missing token."}})
        if u.hostname == "management.azure.com":
            return self._arm(request, u, q)
        if not u.hostname.endswith(".cognitiveservices.azure.com"):
            return self._resp(request, 401, {"error": {"code": "401", "message": "Regional endpoints do not support Entra."}})
        if not self.mode["data_plane"]:
            return self._resp(request, 403, {"error": {"code": "PermissionDenied", "message": "Principal does not have access to API/Operation."}},
                              {"apim-request-id": "req-403"})
        if self.mode["throttle"] and self.mode["throttle"] in u.path:
            return self._resp(request, 429, {"error": {"code": "429", "message": "Too many requests"}}, {"Retry-After": "7"})
        rid = {"apim-request-id": "req-" + u.path.split("/")[1][:6]}
        if u.path == "/language/:analyze-text":
            assert q["api-version"] == ["2023-04-01"]
            txt = body["analysisInput"]["documents"][0]["text"]
            lang = "pt" if re.search(r"voltou|manhã", txt) else "en"
            return self._resp(request, 200, {"kind": "LanguageDetectionResults", "results": {"documents": [
                {"id": "1", "detectedLanguage": {"name": "x", "iso6391Name": lang, "confidenceScore": 0.99}, "warnings": []}], "errors": [], "modelVersion": "2022-10-01"}}, rid)
        if u.path == "/translator/text/v3.0/translate":
            return self._resp(request, 200, [{"detectedLanguage": {"language": "en", "score": 1.0},
                                              "translations": [{"text": "O VPN falhou novamente esta manhã.", "to": q["to"][0]}]}], {"X-RequestId": "tr-1"})
        if u.path == "/contentsafety/text:analyze":
            assert q["api-version"] == ["2024-09-01"]
            return self._resp(request, 200, {"blocklistsMatch": [], "categoriesAnalysis": [{"category": c, "severity": 0} for c in ("Hate", "SelfHarm", "Sexual", "Violence")]}, rid)
        if u.path == "/documentintelligence/info":
            return self._resp(request, 200, {"customDocumentModels": {"count": 2, "limit": 500}}, rid)
        return self._resp(request, 404, {"error": {"code": "404", "message": "Resource not found"}})

    def _arm(self, request, u, q):
        for k, st in self.mode["arm_status"].items():
            if k in u.path:
                return self._resp(request, st, {"error": {"code": "AuthorizationFailed", "message": "no"}})
        p = u.path
        if p.endswith("/diagnosticSettings"):
            return self._resp(request, 200, {"value": self.mode["diag"]})
        if p.endswith("/roleAssignments"):
            assert q["$filter"] == ["atScope()"]
            return self._resp(request, 200, {"value": self.mode["roles"]})
        if p.endswith("/providers/Microsoft.Insights/metrics"):
            names = q["metricnames"][0].split(",")
            agg = q["aggregation"][0]
            flt = q.get("$filter", [""])[0]
            return self._resp(request, 200, {"value": [self._metric(n, agg, flt) for n in names]})
        if p.endswith(RID.lower()) or p.lower().endswith("/accounts/contoso-ai"):
            return self._resp(request, 200, self.mode["account"])
        return self._resp(request, 404, {"error": {"code": "NotFound", "message": p}})

    @staticmethod
    def _metric(name, agg, flt):
        table = {"TotalCalls": {"/language/:analyze-text": [3, 1], "TranslateText": [2], "AnalyzeText": [1]},
                 "TotalErrors": {"/language/:analyze-text": [1, 0], "TranslateText": [0], "AnalyzeText": [0]},
                 "ClientErrors": {"/language/:analyze-text": [1, 0]}, "ServerErrors": {},
                 "Latency": {"/language/:analyze-text": [120, 80], "TranslateText": [200], "AnalyzeText": [90]},
                 "ProcessedTextRecords": {None: [4, 2]}, "TextCharactersTranslated": {None: [33]}, "ContentSafetyTextAnalyzeRequestCount": {None: [1]}}
        per = table.get(name, {})
        if "ApiName" not in flt:
            per = {None: v for k, v in per.items() if k is None} or ({None: [sum(sum(x) for x in per.values())]} if per else {})
        return metric_doc(name, per)


@pytest.fixture
def cred():
    return FakeCredential()


@pytest.fixture
def platform():
    return FakePlatform()


@pytest.fixture
def api(cred, platform):
    from aiplatform.http import Api
    return Api(cred, transport=platform)
