"""The real azure-ai-documentintelligence SDK against a local stub: analyze is a long-running operation."""
import json

import pytest

pytest.importorskip("azure.ai.documentintelligence")

from azure.core.credentials import AzureKeyCredential  # noqa: E402
from azure.core.exceptions import HttpResponseError  # noqa: E402

from fixtures import analyze_result, sample  # noqa: E402
from invoice_intake import process  # noqa: E402
from invoice_intake.layout import analyze_markdown, markdown_sections  # noqa: E402
from invoice_intake.process import analyze_file, make_client  # noqa: E402

OP = "{url}/documentintelligence/documentModels/%s/analyzeResults/0000?api-version=2024-11-30"


def client(stub):
    # Plain-HTTP stub: the SDK refuses bearer tokens over HTTP, so tests use a fake key. Real runs are keyless.
    return make_client(stub.url, AzureKeyCredential("fake"))


@pytest.fixture
def invoice_png(tmp_path):
    p = tmp_path / "01-fabrikam-clean.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n fake image bytes")
    return p


def test_analyze_posts_bytes_then_polls_operation_location(stub_server, invoice_png):
    stub_server.responses += [
        (202, {"Operation-Location": OP % "prebuilt-invoice"}, None),
        (200, {}, {"status": "running"}),
        (200, {}, {"status": "succeeded", "analyzeResult": analyze_result(sample("01"))}),
    ]
    result = analyze_file(client(stub_server), invoice_png, polling_interval=0)
    post, *gets = stub_server.requests
    assert post["method"] == "POST"
    assert post["path"] == "/documentintelligence/documentModels/prebuilt-invoice:analyze?api-version=2024-11-30&locale=en-US"
    assert post["headers"]["content-type"] == "application/octet-stream"
    assert post["raw"] == invoice_png.read_bytes()
    assert [g["method"] for g in gets] == ["GET", "GET"]
    assert result["documents"][0]["fields"]["InvoiceTotal"]["valueCurrency"]["amount"] == 576.87


def test_failed_operation_raises(stub_server, invoice_png):
    stub_server.responses += [
        (202, {"Operation-Location": OP % "prebuilt-invoice"}, None),
        (200, {}, {"status": "failed", "error": {"code": "InvalidContent", "message": "The file is corrupted."}}),
    ]
    with pytest.raises(HttpResponseError):
        analyze_file(client(stub_server), invoice_png, polling_interval=0)


def test_layout_asks_for_markdown(stub_server, invoice_png):
    md = "# Travel and expenses\n\n## Mileage\n\n0.36 euros per kilometre.\n\n<!-- PageBreak -->\n"
    stub_server.responses += [
        (202, {"Operation-Location": OP % "prebuilt-layout"}, None),
        (200, {}, {"status": "succeeded", "analyzeResult": {"apiVersion": "2024-11-30", "modelId": "prebuilt-layout",
                                                            "contentFormat": "markdown", "content": md}}),
    ]
    content = analyze_markdown(client(stub_server), invoice_png, polling_interval=0)
    assert "outputContentFormat=markdown" in stub_server.requests[0]["path"]
    assert "/documentModels/prebuilt-layout:analyze" in stub_server.requests[0]["path"]
    assert markdown_sections(content) == [("Travel and expenses > Mileage", "0.36 euros per kilometre.")]


def test_markdown_sections_keep_the_heading_path_and_drop_page_metadata():
    md = ("# Handbook\n\nIntro.\n\n## Expenses\n\n### Mileage\n\nRate.\n<!-- PageNumber=\"1\" -->\n\n"
          "<figure>\nchart\n</figure>\n\n## Leave\n\nDays.")
    assert markdown_sections(md) == [("Handbook", "Intro."), ("Handbook > Expenses > Mileage", "Rate."),
                                     ("Handbook > Leave", "Days.")]


def test_replay_cli_routes_saved_results(tmp_path, capsys):
    paths = []
    for prefix in ("01", "02", "03", "05"):
        p = tmp_path / f"{prefix}.json"
        p.write_text(json.dumps(analyze_result(sample(prefix))))
        paths.append(str(p))
    assert process.main(["--replay", *paths]) == 0
    out = capsys.readouterr().out
    assert "approve: 1  review: 1  reject: 2" in out
    assert "Fabrikam Office Supplies" in out


def test_saved_live_result_round_trips(stub_server, invoice_png, tmp_path, monkeypatch, capsys):
    stub_server.responses += [
        (202, {"Operation-Location": OP % "prebuilt-invoice"}, None),
        (200, {}, {"status": "succeeded", "analyzeResult": analyze_result(sample("01"))}),
    ]
    monkeypatch.setattr(process, "make_client", lambda endpoint: client(stub_server))
    monkeypatch.setattr(process, "analyze_file",
                        lambda c, p, locale: analyze_file(c, p, locale=locale, polling_interval=0))
    out_dir = tmp_path / "results"
    assert process.main([str(invoice_png), "--endpoint", stub_server.url, "--save-json", str(out_dir)]) == 0
    saved = json.loads((out_dir / "01-fabrikam-clean.json").read_text())
    assert saved["modelId"] == "prebuilt-invoice"
    assert "approve: 1" in capsys.readouterr().out
