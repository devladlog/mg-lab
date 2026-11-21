"""The real Document Intelligence SDK and the real function handler, against a local stub of the REST API."""
import base64
import json

import azure.functions as func
import pytest
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError

import function_app
from docintel.extract import analyze_invoice, make_client
from stub_service import StubDocIntel

PDF = b"%PDF-1.7\n% fictional test invoice\n" + b"0" * 64


def client_for(stub):
    # A key credential only for the stub: in Azure the function uses its managed identity (no keys).
    return make_client(stub.endpoint, AzureKeyCredential("stub-key"))


def test_sdk_sends_base64_to_the_invoice_model_and_polls(invoice_result):
    with StubDocIntel(invoice_result, running_polls=2) as stub:
        result = analyze_invoice(client_for(stub), PDF, polling_interval=0)
    post = stub.requests[0]
    assert post["method"] == "POST"
    assert post["path"].startswith("/documentintelligence/documentModels/prebuilt-invoice:analyze?")
    assert "api-version=2024-11-30" in post["path"]
    assert base64.b64decode(post["body"]["base64Source"]) == PDF
    assert [r["method"] for r in stub.requests] == ["POST", "GET", "GET", "GET"]   # 2 x running, then succeeded
    assert result["modelId"] == "prebuilt-invoice"
    assert result["documents"][0]["fields"]["InvoiceTotal"]["valueCurrency"]["amount"] == 1476.0


def test_locale_is_passed_as_query_parameter(invoice_result):
    with StubDocIntel(invoice_result) as stub:
        analyze_invoice(client_for(stub), PDF, locale="pt-PT", polling_interval=0)
    assert "locale=pt-PT" in stub.requests[0]["path"]


def test_service_error_surfaces_as_http_response_error(invoice_result):
    with StubDocIntel(invoice_result, fail_status=400) as stub:
        with pytest.raises(HttpResponseError) as e:
            analyze_invoice(client_for(stub), PDF, polling_interval=0)
    assert e.value.status_code == 400
    assert len(stub.requests) == 1          # a 400 is not retried


# ---- the HTTP function -------------------------------------------------------------------------------

def request(body: bytes, ctype="application/pdf", name="INV-2026-0417.pdf"):
    return func.HttpRequest(method="POST", url="/api/invoices/extract", body=body,
                            headers={"Content-Type": ctype, "X-File-Name": name})


@pytest.fixture
def stubbed(monkeypatch, invoice_result):
    with StubDocIntel(invoice_result, running_polls=0) as stub:
        client = client_for(stub)
        monkeypatch.setattr(function_app, "get_client", lambda: client)
        yield stub


def test_function_returns_columns_and_decision(stubbed):
    resp = function_app.handle(request(PDF), env={})
    assert resp.status_code == 200
    out = json.loads(resp.get_body())
    assert out["status"] == "Ready"
    assert out["fields"]["InvVendor"] == "Fabrikam Office Supplies"
    assert out["fields"]["InvStatus"] == "Ready"
    assert (out["modelId"], out["apiVersion"], out["pages"], out["fileType"]) == ("prebuilt-invoice", "2024-11-30", 1, "pdf")


def test_function_accepts_the_flow_content_envelope(stubbed):
    envelope = {"$content-type": "application/pdf", "$content": base64.b64encode(PDF).decode()}
    resp = function_app.handle(request(json.dumps(envelope).encode(), ctype="application/json"), env={})
    assert resp.status_code == 200
    assert base64.b64decode(stubbed.requests[0]["body"]["base64Source"]) == PDF


def test_policy_comes_from_app_settings(stubbed):
    resp = function_app.handle(request(PDF), env={"APPROVAL_LIMIT": "1000"})
    out = json.loads(resp.get_body())
    assert out["status"] == "Needs review"
    assert out["reasons"] == ["Total above the approval limit (1,000)."]


@pytest.mark.parametrize("body,ctype,status", [
    (b"", "application/pdf", 400),
    (b"hello, not a pdf", "application/octet-stream", 415),
    (b'{"name": "no content"}', "application/json", 400),
    (b'{"$content": "***not base64***"}', "application/json", 400),
])
def test_bad_input_never_reaches_the_service(stubbed, body, ctype, status):
    resp = function_app.handle(request(body, ctype=ctype), env={})
    assert resp.status_code == status
    assert stubbed.requests == []          # nothing billed for garbage


def test_size_limit(stubbed):
    resp = function_app.handle(request(PDF + b"0" * 2_000_000), env={"MAX_UPLOAD_MB": "1"})
    assert resp.status_code == 413 and stubbed.requests == []


@pytest.mark.parametrize("data,kind", [
    (b"\xff\xd8\xff\xe0....", "jpeg"), (b"\x89PNG\r\n\x1a\n", "png"), (b"II*\x00....", "tiff"),
    (b"\x00\x00\x00\x18ftypheic", "heif"), (b"BM....", "bmp"), (b"PK\x03\x04", None),
])
def test_file_type_is_sniffed_from_bytes(data, kind):
    assert function_app.sniff(data) == kind


def test_throttling_maps_to_503_so_the_flow_retries(monkeypatch, invoice_result):
    with StubDocIntel(invoice_result, fail_status=429) as stub:
        client = client_for(stub)
        monkeypatch.setattr(function_app, "get_client", lambda: client)
        # retry_total=0 switches off the SDK's own retries so the 429 reaches the handler at once
        monkeypatch.setattr(function_app, "analyze_invoice",
                            lambda c, d, **k: analyze_invoice(c, d, polling_interval=0, retry_total=0, **k))
        resp = function_app.handle(request(PDF), env={})
    assert resp.status_code == 503
    assert json.loads(resp.get_body()) == {"error": "Document Intelligence call failed.", "serviceStatus": 429}
    assert len(stub.requests) == 1


def test_function_is_registered_on_the_route():
    fns = function_app.app.get_functions()
    assert len(fns) == 1
    trigger = fns[0].get_bindings_dict()["bindings"][0]
    assert trigger["type"] == "httpTrigger"
    assert trigger["route"] == "invoices/extract"
    assert [str(m.value if hasattr(m, "value") else m) for m in trigger["methods"]] == ["POST"]
    assert str(getattr(trigger["authLevel"], "value", trigger["authLevel"])).lower() == "function"


def test_sdk_already_retries_a_persistent_429_three_times(invoice_result):
    """Measured with azure-core 1.41: 1 call + 3 retries. Every flow retry on top multiplies this."""
    with StubDocIntel(invoice_result, fail_status=429) as stub:
        with pytest.raises(HttpResponseError):
            analyze_invoice(client_for(stub), PDF, polling_interval=0)
    assert len(stub.requests) == 4
