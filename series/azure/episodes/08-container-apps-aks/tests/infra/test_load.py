"""infra/load.py against a local stand-in server (tests only; the demo runs it against the real Container App)."""
import http.server
import importlib.util
import threading

from conftest import ROOT

spec = importlib.util.spec_from_file_location("load", ROOT / "infra" / "load.py")
load = importlib.util.module_from_spec(spec)
spec.loader.exec_module(load)


class Handler(http.server.BaseHTTPRequestHandler):
    seen: list = []

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers["Content-Length"]))
        Handler.seen.append((self.path, self.headers["Content-Type"], body))
        code = 200 if self.path == "/quotes" else 404
        self.send_response(code)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


def serve():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_sends_valid_quote_requests_from_every_worker_and_counts_status_codes():
    server = serve()
    try:
        result = load.run(f"http://127.0.0.1:{server.server_port}/", workers=4, seconds=1)
    finally:
        server.shutdown()
    assert result["status"] == {"200": result["total"]} and result["total"] > 4
    path, ctype, body = Handler.seen[0]
    assert path == "/quotes" and ctype == "application/json"
    assert b"MON-270" in body


def test_counts_connection_errors_instead_of_crashing():
    result = load.run("http://127.0.0.1:9", workers=2, seconds=0.3)
    assert set(result["status"]) == {"error"}
