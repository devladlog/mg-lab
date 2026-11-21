"""Test doubles. Nothing here calls Azure. The REAL azure-ai-vision-imageanalysis SDK sends its real request
(POST <endpoint>/computervision/imageanalysis:analyze?api-version=...&features=..., body = image bytes, Entra bearer token)
through a stand-in transport, which answers in the response shape of the Image Analysis 4.0 API. The answers are
scripted by each test: they prove our plumbing, limits, privacy rules and gate, NOT the accuracy of the service."""
import io
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from azure.core.pipeline.transport import HttpTransport
from azure.core.rest._requests_basic import RestRequestsTransportResponse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from photoscan import samples  # noqa: E402
from photoscan.model import Analysis, Box, Crop, Line, Person, Word  # noqa: E402

ENDPOINT = "https://contoso-vision.cognitiveservices.azure.com"


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


def line_json(text, conf=0.99):
    return {"text": text, "boundingPolygon": [{"x": 1, "y": 1}, {"x": 9, "y": 1}, {"x": 9, "y": 9}, {"x": 1, "y": 9}],
            "words": [{"text": w, "boundingPolygon": [{"x": 1, "y": 1}, {"x": 2, "y": 1}, {"x": 2, "y": 2}, {"x": 1, "y": 2}],
                       "confidence": conf if not isinstance(conf, dict) else conf.get(w, 0.99)} for w in text.split()]}


class FakeService:
    """answers the analyze route; `reply` is a function (image_bytes, features, query) -> (status, body) set by the test"""
    def __init__(self):
        self.requests = []
        self.reply = self.default_reply

    @staticmethod
    def default_reply(image, features, query):
        from PIL import Image
        w, h = Image.open(io.BytesIO(image)).size
        body = {"modelVersion": "2023-10-01", "metadata": {"width": w, "height": h}}
        if "caption" in features:
            body["captionResult"] = {"text": "a laptop with a label", "confidence": 0.71}
        if "tags" in features:
            body["tagsResult"] = {"values": [{"name": "laptop", "confidence": 0.98}, {"name": "text", "confidence": 0.95}]}
        if "objects" in features:
            body["objectsResult"] = {"values": [{"boundingBox": {"x": 1, "y": 2, "w": 30, "h": 40}, "tags": [{"name": "laptop", "confidence": 0.8}]}]}
        if "read" in features:
            body["readResult"] = {"blocks": [{"lines": [line_json("CONTOSO PORTO"), line_json("CON-48213", 0.97)]}]}
        if "people" in features:
            body["peopleResult"] = {"values": [{"boundingBox": {"x": 10, "y": 10, "w": 50, "h": 80}, "confidence": 0.9}]}
        if "smartcrops" in features:
            ratios = [float(x) for x in query.get("smartcrops-aspect-ratios", ["1.0"])[0].split(",")]
            body["smartCropsResult"] = {"values": [{"aspectRatio": r, "boundingBox": {"x": 0, "y": 0, "w": min(w, int(h * r)), "h": h}} for r in ratios]}
        return 200, body


class FakeTransport(HttpTransport):
    def __init__(self, service):
        self.service = service

    def open(self):
        pass

    def close(self):
        pass

    def __exit__(self, *a):
        pass

    def send(self, request, **kwargs):
        u = urlparse(request.url)
        q = parse_qs(u.query)
        feats = [f.lower() for f in q.get("features", [""])[0].split(",")]
        self.service.requests.append({"path": u.path, "query": q, "headers": dict(request.headers), "body_len": len(request.body or b"")})
        status, body = self.service.reply(request.body, feats, q)
        r = requests.Response()
        r.status_code = status
        r.raw = io.BytesIO(json.dumps(body).encode())
        r.headers["Content-Type"] = "application/json"
        r.reason = "OK" if status == 200 else "Error"
        return RestRequestsTransportResponse(request=request, internal_response=r)


@pytest.fixture
def service():
    return FakeService()


@pytest.fixture
def cred():
    return FakeCredential()


@pytest.fixture
def sdk_backend(service, cred):
    from photoscan.azure_backend import AzureVisionBackend, make_client
    client = make_client(ENDPOINT, cred, transport=FakeTransport(service))
    return AzureVisionBackend(client)


class Scripted:
    """a VisionBackend that returns prepared Analysis objects in order (for pipeline and gate tests)"""
    def __init__(self, *items):
        self.items, self.seen = list(items), []

    def analyze(self, image):
        self.seen.append(image)
        it = self.items.pop(0)
        if isinstance(it, Exception):
            raise it
        return it


def analysis(lines=(), people=(), crops=(), w=1200, h=800):
    return Analysis(w, h, "test", "a label", 0.7, [("text", .9)], [], [Line(t, [Word(x, c) for x in t.split()]) for t, c in lines],
                    [Person(Box(*b), c) for b, c in people], [Crop(r, Box(*b)) for r, b in crops])
