import re
import sys
from pathlib import Path

import function_app

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "samples"))
import make_samples  # noqa: E402


def test_sample_pdfs_are_valid_and_accepted_by_the_function(tmp_path):
    files = make_samples.main(tmp_path)
    assert [f.name for f in files] == ["fabrikam-clean.pdf", "fabrikam-over-limit.pdf", "fabrikam-mismatch.pdf"]
    for f in files:
        data = f.read_bytes()
        assert function_app.sniff(data) == "pdf"
        assert data.rstrip().endswith(b"%%EOF")
        # every xref offset must point at "<n> 0 obj"
        xref_at = int(re.search(rb"startxref\n(\d+)", data).group(1))
        offsets = [int(m) for m in re.findall(rb"(\d{10}) 00000 n", data[xref_at:])]
        for n, off in enumerate(offsets, start=1):
            assert data[off:].startswith(f"{n} 0 obj".encode())


def test_samples_contain_only_fictional_parties(tmp_path):
    text = b"".join(f.read_bytes() for f in make_samples.main(tmp_path))
    assert b"Fabrikam" in text and b"Contoso" in text and b"Fictional document" in text


def test_smoke_client_posts_bytes_with_key_and_name_through_the_real_handler(tmp_path, monkeypatch, invoice_result, capsys):
    """smoke.py -> local HTTP server -> function_app.handle -> SDK -> Document Intelligence stub."""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    import azure.functions as func
    from azure.core.credentials import AzureKeyCredential

    import smoke
    from docintel.extract import make_client
    from stub_service import StubDocIntel

    seen = {}

    class FunctionHost(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.update(key=self.headers["x-functions-key"], name=self.headers["X-File-Name"],
                        ctype=self.headers["Content-Type"])
            resp = function_app.handle(func.HttpRequest("POST", self.path, body=body, headers=dict(self.headers)), env={})
            data = resp.get_body()
            self.send_response(resp.status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    pdf = make_samples.main(tmp_path)[0]
    with StubDocIntel(invoice_result, running_polls=0) as di:
        client = make_client(di.endpoint, AzureKeyCredential("stub-key"))
        monkeypatch.setattr(function_app, "get_client", lambda: client)
        host = ThreadingHTTPServer(("127.0.0.1", 0), FunctionHost)
        threading.Thread(target=host.serve_forever, daemon=True).start()
        try:
            monkeypatch.setenv("INVOICE_API_URL", f"http://127.0.0.1:{host.server_address[1]}/api/invoices/extract")
            monkeypatch.setenv("INVOICE_API_KEY", "test-key")
            rc = smoke.main([str(pdf)])
        finally:
            host.shutdown()
            host.server_close()
    assert rc == 0
    assert seen == {"key": "test-key", "name": "fabrikam-clean.pdf", "ctype": "application/pdf"}
    out = capsys.readouterr().out
    assert "fabrikam-clean.pdf" in out and "Ready" in out and "Fabrikam Office Supplies" in out


def test_smoke_refuses_to_run_without_settings(monkeypatch, capsys):
    import smoke
    monkeypatch.delenv("INVOICE_API_URL", raising=False)
    monkeypatch.delenv("INVOICE_API_KEY", raising=False)
    assert smoke.main(["x.pdf"]) == 2
