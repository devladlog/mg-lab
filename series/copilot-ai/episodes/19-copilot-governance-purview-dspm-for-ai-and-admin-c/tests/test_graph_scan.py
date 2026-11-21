"""graph_scan against a local loopback HTTP server (TEST ONLY: the demo runs against the real Graph)."""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from copilot_governance.graph_scan import GraphClient, GraphError, main, scan  # noqa: E402


def make_server(state):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, headers=None):
            raw = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            state["seen"].append((self.path, self.headers.get("Authorization")))
            base = f"http://127.0.0.1:{self.server.server_port}"
            if self.path.startswith("/sites?search="):
                if "page=2" in self.path:
                    return self._send(200, {"value": [{"id": "s2", "displayName": "Marketing", "webUrl": "https://contoso.example/sites/m"}]})
                return self._send(200, {"value": [{"id": "s1", "displayName": "HR", "webUrl": "https://contoso.example/sites/hr"}],
                                        "@odata.nextLink": base + "/sites?search=*&page=2"})
            if self.path.endswith("/drives") and "/sites/" in self.path:
                return self._send(200, {"value": [{"id": "d-" + self.path.split("/")[2], "name": "Documents"}]})
            if "/root/children" in self.path:
                return self._send(200, {"value": [{"id": "i1", "name": "salary-bands.xlsx"}, {"id": "i2", "name": "folder", "folder": {}}]})
            if self.path.endswith("/permissions"):
                if state["throttle"] and "i1" in self.path and not state["throttled"]:
                    state["throttled"] = True
                    return self._send(429, {"error": {"code": "tooManyRequests"}}, {"Retry-After": "2"})
                if "i2" in self.path:
                    return self._send(200, {"value": []})
                return self._send(200, {"value": [{"id": "p", "roles": ["read"], "link": {"type": "view", "scope": "anonymous"}}]})
            self._send(403, {"error": {"code": "accessDenied"}})
    return H


@pytest.fixture
def server():
    state = {"seen": [], "throttle": True, "throttled": False}
    srv = HTTPServer(("127.0.0.1", 0), make_server(state))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}", state
    srv.shutdown()
    srv.server_close()


def test_scan_pages_sites_retries_429_and_sends_bearer(server):
    base, state = server
    sleeps = []
    client = GraphClient("test-token", base=base, sleep=sleeps.append)
    data = scan(client, "*", max_sites=10, max_items=10)
    assert [s["name"] for s in data["sites"]] == ["HR", "Marketing"]       # followed @odata.nextLink
    hr_items = data["sites"][0]["items"]
    assert [i["name"] for i in hr_items] == ["salary-bands.xlsx", "folder"]
    assert hr_items[0]["permissions"][0]["link"]["scope"] == "anonymous" and hr_items[1]["isFolder"]
    assert sleeps == [2.0]                                                 # honoured Retry-After once
    assert all(auth == "Bearer test-token" for _, auth in state["seen"])


def test_max_sites_and_http_error(server):
    base, _ = server
    data = scan(GraphClient("t", base=base, sleep=lambda s: None), max_sites=1, max_items=1)
    assert len(data["sites"]) == 1 and len(data["sites"][0]["items"]) == 1
    with pytest.raises(GraphError, match="HTTP 403"):
        GraphClient("t", base=base).get("/nope")


def test_cli_requires_token_and_writes_file(server, tmp_path, monkeypatch, capsys):
    base, _ = server
    out = tmp_path / "scan.json"
    monkeypatch.delenv("GRAPH_TOKEN", raising=False)
    assert main(["--out", str(out)]) == 2
    monkeypatch.setenv("GRAPH_TOKEN", "x")
    assert main(["--out", str(out), "--base", base, "--max-sites", "1", "--max-items", "5"]) == 0
    assert json.loads(out.read_text())["sites"][0]["items"][0]["name"] == "salary-bands.xlsx"
    assert "x" not in capsys.readouterr().out.replace("request(s)", "").replace("max", "")  # token not echoed (loose check)
