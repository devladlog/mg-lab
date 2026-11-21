import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

SAMPLE = Path(__file__).resolve().parents[1] / "src" / "data" / "sample"


@pytest.fixture(autouse=True)
def _no_proxy(monkeypatch):
    # tests talk to 127.0.0.1 only; make sure a proxy variable of the build machine is not used
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")


class FakeDataverse:
    """Local stand-in used ONLY by automated tests: serves the sample files in Web API shape with server-driven paging."""

    def __init__(self, fail_with=None, loop=False):
        self.requests = []
        self.fail_with = fail_with
        self.loop = loop
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                outer.requests.append({"path": self.path, "headers": dict(self.headers)})
                if outer.fail_with:
                    body = json.dumps({"error": {"message": "caller is not authorised"}}).encode()
                    self.send_response(outer.fail_with)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                u = urlsplit(self.path)
                entity = u.path.rsplit("/", 1)[-1]
                f = SAMPLE / f"{entity}.json"
                if not f.exists():
                    self.send_response(404)
                    self.end_headers()
                    return
                rows = json.loads(f.read_text())["value"]
                prefer = self.headers.get("Prefer", "")
                size = int(prefer.split("odata.maxpagesize=")[1].split(";")[0]) if "maxpagesize" in prefer else 5000
                start = int(parse_qs(u.query).get("$skiptoken", ["0"])[0])
                page = rows[start:start + size]
                out = {"value": page}
                if outer.loop:
                    out["@odata.nextLink"] = f"http://127.0.0.1:{outer.port}{self.path}"
                elif start + size < len(rows):
                    q = u.query + ("&" if u.query else "") + f"$skiptoken={start + size}"
                    base = u.query.split("&$skiptoken")[0]
                    out["@odata.nextLink"] = f"http://127.0.0.1:{outer.port}{u.path}?{base + ('&' if base else '')}$skiptoken={start + size}"
                body = json.dumps(out).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@pytest.fixture
def fake():
    def make(**kw):
        return FakeDataverse(**kw)
    return make
