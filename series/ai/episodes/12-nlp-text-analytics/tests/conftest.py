"""Test doubles. Nothing here calls Azure. The REAL azure-ai-textanalytics SDK sends its real requests (Entra bearer token,
analyze-text route, JSON body) through a stand-in transport, and a small rule-based 'service' answers them in the response
shape of the Azure Language analyze-text API. The rules are keyword and regex lookups, NOT language understanding, and
the limits it enforces (documents per request, characters per document) are the ones Learn documents. These tests prove
our plumbing: batching, chunking, fail-closed redaction, routing, scoring. They say nothing about real accuracy."""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest
import requests
from azure.core.pipeline.transport import HttpTransport, RequestsTransportResponse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

ENDPOINT = "https://contoso-lang.cognitiveservices.azure.com"
NAMES = re.compile(r"\b(?:Alex|Sam|Taylor|Jordan|Riley) Demo\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.\w+\b")
PHONE = re.compile(r"\+?\d{3}[ ]?\d{3}[ ]?\d{3}(?:[ ]?\d{3})?")
PT_WORDS = ("não", "obrigad", "ecrã", "portátil", "voltou", "teclado", "desiludida")
LIMITS = {"SentimentAnalysis": 10, "KeyPhraseExtraction": 10, "EntityRecognition": 5, "PiiEntityRecognition": 5, "LanguageDetection": 1000}


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


def sentiment_of(text: str):
    t = text.lower()
    neg = sum(w in t for w in ("frustrating", "drops", "molesto", "desiludida", "jams", "down again", "falha", "perdi", "barely", "noisy"))
    pos = sum(w in t for w in ("thanks", "great", "lindamente", "obrigado", "simpática", "fast", "ótimo"))
    if neg and pos:
        return "mixed", {"positive": .4, "neutral": .1, "negative": .5}
    if neg:
        return "negative", {"positive": .02, "neutral": .05, "negative": .93}
    if pos:
        return "positive", {"positive": .95, "neutral": .04, "negative": .01}
    return "neutral", {"positive": .05, "neutral": .9, "negative": .05}


class FakeService:
    def __init__(self):
        self.calls: list[dict] = []
        self.fail_pii_for: set[str] = set()          # document ids for which the PII call returns a document error
        self.language_override: dict[str, tuple[str, float]] = {}
        self.status_override: int | None = None
        self.first_pii_markers: list[str] = []

    # ---- the response builders -------------------------------------------------------------------------------
    def handle(self, body: dict):
        kind = body["kind"]
        docs = body["analysisInput"]["documents"]
        self.calls.append({"kind": kind, "n": len(docs), "params": body.get("parameters", {}), "docs": docs})
        if self.status_override:
            return self.status_override, {"error": {"code": "InternalServerError", "message": "boom"}}
        if len(docs) > LIMITS[kind]:
            return 400, {"error": {"code": "InvalidRequest", "message": f"Too many documents: {len(docs)} > {LIMITS[kind]}", "innererror": {"code": "InvalidDocumentBatch", "message": "limit"}}}
        ok, errors = [], []
        for d in docs:
            if len(d["text"]) > 5120:
                errors.append({"id": d["id"], "error": {"code": "InvalidDocument", "message": "Document text is too long."}})
            elif kind == "PiiEntityRecognition" and d["id"] in self.fail_pii_for:
                errors.append({"id": d["id"], "error": {"code": "InternalServerError", "message": "pii failed"}})
            else:
                ok.append(getattr(self, "_" + kind)(d, body.get("parameters", {})))
        return 200, {"kind": kind + "Results", "results": {"documents": ok, "errors": errors, "modelVersion": "test"}}

    def _LanguageDetection(self, d, p):
        t = d["text"]
        iso, name, conf = ("pt", "Portuguese", .99) if any(w in t.lower() for w in PT_WORDS) else \
                          ("es", "Spanish", .98) if "impresora" in t.lower() else ("en", "English", .99)
        if "Hello team, o VPN" in t:
            iso, name, conf = "en", "English", .5
        iso, conf = self.language_override.get(d["id"].split("#")[0], (iso, conf))
        return {"id": d["id"], "detectedLanguage": {"name": name, "iso6391Name": iso, "confidenceScore": conf}, "warnings": []}

    def _PiiEntityRecognition(self, d, p):
        t, ents = d["text"], []
        for cat, rx in (("Person", NAMES), ("Email", EMAIL), ("PhoneNumber", PHONE)):
            for m in rx.finditer(t):
                ents.append({"text": m.group(), "category": cat, "offset": m.start(), "length": len(m.group()), "confidenceScore": .9})
        red = list(t)
        for e in ents:
            red[e["offset"]:e["offset"] + e["length"]] = "*" * e["length"]
        return {"id": d["id"], "redactedText": "".join(red), "entities": ents, "warnings": []}

    def _SentimentAnalysis(self, d, p):
        label, scores = sentiment_of(d["text"])
        sentence = {"sentiment": label, "confidenceScores": scores, "offset": 0, "length": len(d["text"]), "text": d["text"],
                    "targets": [], "assessments": []}
        if p.get("opinionMining") and "VPN" in d["text"]:
            i = d["text"].index("VPN")
            sentence["targets"] = [{"sentiment": "negative", "confidenceScores": {"positive": .0, "negative": 1.0}, "offset": i, "length": 3,
                                    "text": "VPN", "relations": [{"relationType": "assessment", "ref": "#/documents/0/sentences/0/assessments/0"}]}]
            sentence["assessments"] = [{"sentiment": "negative", "confidenceScores": {"positive": .0, "negative": 1.0}, "offset": 0, "length": 4,
                                        "text": "drops", "isNegated": False}]
        return {"id": d["id"], "sentiment": label, "confidenceScores": scores, "sentences": [sentence], "warnings": []}

    def _KeyPhraseExtraction(self, d, p):
        words = ("VPN", "Outlook", "printer", "laptop", "battery", "docking station", "badge", "Alex Demo", "reports")
        return {"id": d["id"], "keyPhrases": [w for w in words if w.lower() in d["text"].lower()], "warnings": []}

    def _EntityRecognition(self, d, p):
        ents = []
        for w, cat in (("Porto", "Location"), ("Contoso", "Organization"), ("Alex Demo", "Person"), ("Sam Demo", "Person")):
            if w in d["text"]:
                ents.append({"text": w, "category": cat, "offset": d["text"].index(w), "length": len(w), "confidenceScore": .95})
        return {"id": d["id"], "entities": ents, "warnings": []}


class FakeTransport(HttpTransport):
    def __init__(self, service: FakeService):
        self.service, self.requests = service, []

    def open(self):
        pass

    def close(self):
        pass

    def __exit__(self, *a):
        pass

    def send(self, request, **kwargs):
        self.requests.append(request)
        status, body = self.service.handle(json.loads(request.body))
        r = requests.Response()
        r.status_code = status
        r._content = json.dumps(body).encode()
        r.headers["Content-Type"] = "application/json"
        r.reason = "OK" if status == 200 else "Error"
        return RequestsTransportResponse(request, r)


@pytest.fixture
def service():
    return FakeService()


@pytest.fixture
def cred():
    return FakeCredential()


@pytest.fixture
def transport(service):
    return FakeTransport(service)


@pytest.fixture
def client(transport, cred):
    from ticketnlp.client import make_client
    return make_client(ENDPOINT, cred, transport=transport, retry_total=0)


@pytest.fixture
def analyzer(client):
    from ticketnlp.analyzer import Analyzer
    return Analyzer(client)
