"""HTTP function the flow calls: POST the file bytes, get back library column values + a routing decision.

Python v2 programming model. App settings:
  DOCINTEL_ENDPOINT   https://<name>.cognitiveservices.azure.com/
  AZURE_CLIENT_ID     client id of the user-assigned identity (keyless call to Document Intelligence)
  MIN_CONFIDENCE, APPROVAL_LIMIT, ALLOWED_CURRENCIES, TOTAL_TOLERANCE, MAX_UPLOAD_MB   (optional policy)
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import os

import azure.functions as func
from azure.core.exceptions import HttpResponseError

from docintel.extract import MODEL_ID, analyze_invoice, make_client
from docintel.mapping import extract
from docintel.rules import Policy, decide

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
log = logging.getLogger("docintel")

# Formats the prebuilt models accept: PDF, JPEG, PNG, BMP, TIFF, HEIF (checked by magic bytes, not by name).
_MAGIC = ((b"%PDF", "pdf"), (b"\xff\xd8\xff", "jpeg"), (b"\x89PNG", "png"), (b"BM", "bmp"),
          (b"II*\x00", "tiff"), (b"MM\x00*", "tiff"))

_client = None


def get_client():
    """One client per worker; tests replace this function."""
    global _client
    if _client is None:
        _client = make_client(os.environ["DOCINTEL_ENDPOINT"])
    return _client


def sniff(data: bytes) -> str | None:
    for magic, kind in _MAGIC:
        if data.startswith(magic):
            return kind
    if data[4:8] == b"ftyp":  # HEIF/HEIC container
        return "heif"
    return None


def read_body(req: func.HttpRequest) -> bytes:
    """Raw bytes (Content-Type application/pdf, octet-stream, image/*), or the flow's JSON content envelope
    {"$content-type": "...", "$content": "<base64>"} when the file is embedded in a JSON body."""
    body = req.get_body() or b""
    ctype = (req.headers.get("Content-Type") or "").lower()
    if ctype.startswith("application/json"):
        try:
            doc = json.loads(body)
            return base64.b64decode(doc["$content"], validate=True)
        except (ValueError, KeyError, TypeError, binascii.Error) as e:
            raise ValueError("JSON body must be a file content object with a base64 '$content'.") from e
    return body


def _json(status: int, payload: dict) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(payload), status_code=status, mimetype="application/json")


def handle(req: func.HttpRequest, env=os.environ) -> func.HttpResponse:
    name = req.headers.get("X-File-Name", "")
    try:
        data = read_body(req)
    except ValueError as e:
        return _json(400, {"error": str(e)})
    if not data:
        return _json(400, {"error": "Empty body. POST the file bytes."})
    max_bytes = int(float(env.get("MAX_UPLOAD_MB", "20")) * 1024 * 1024)
    if len(data) > max_bytes:
        return _json(413, {"error": f"File is larger than {max_bytes // (1024 * 1024)} MB."})
    kind = sniff(data)
    if kind is None:
        return _json(415, {"error": "Not a PDF or a supported image (JPEG, PNG, BMP, TIFF, HEIF)."})

    try:
        result = analyze_invoice(get_client(), data, locale=env.get("DOCINTEL_LOCALE") or None)
    except HttpResponseError as e:
        # Don't echo service internals to the caller; the flow only needs to know it can retry.
        log.error("Document Intelligence failed for %s: %s %s", name, e.status_code, e.message)
        status = 503 if e.status_code in (429, 500, 503) else 502
        return _json(status, {"error": "Document Intelligence call failed.", "serviceStatus": e.status_code})

    decision = decide(extract(result), Policy.from_env(env))
    log.info("%s -> %s (%s)", name, decision.status, "; ".join(decision.reasons) or "no issues")
    return _json(200, {
        "status": decision.status,
        "reasons": decision.reasons,
        "fields": decision.columns,
        "modelId": result.get("modelId", MODEL_ID),
        "apiVersion": result.get("apiVersion"),
        "pages": len(result.get("pages") or []),
        "fileType": kind,
    })


@app.route(route="invoices/extract", methods=["POST"])
def extract_invoice(req: func.HttpRequest) -> func.HttpResponse:
    return handle(req)
