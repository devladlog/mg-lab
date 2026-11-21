import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


class StubServer:
    """Local HTTP server: records every request (raw bytes + parsed JSON when possible) and replays scripted
    (status, headers, body) responses. A header value may contain "{url}", replaced by the stub's own base URL,
    so a 202 can point Operation-Location back at the stub. Used to run the real Document Intelligence SDK
    (including its long-running-operation polling) without any cloud resource."""

    def __init__(self):
        self.requests = []
        self.responses = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def _handle(self):
                length = int(self.headers.get("content-length", 0) or 0)
                raw = self.rfile.read(length) if length else b""
                try:
                    body = json.loads(raw) if raw else None
                except (ValueError, UnicodeDecodeError):
                    body = None
                stub.requests.append({"method": self.command, "path": self.path, "raw": raw, "body": body,
                                      "headers": {k.lower(): v for k, v in self.headers.items()}})
                status, headers, payload = stub.responses.pop(0)
                data = b"" if payload is None else json.dumps(payload).encode()
                self.send_response(status)
                for k, v in {"content-type": "application/json", **headers}.items():
                    self.send_header(k, v.replace("{url}", stub.url))
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = _handle

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def stub_server():
    server = StubServer()
    yield server
    server.close()
