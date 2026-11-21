"""A tiny local stand-in for the Document Intelligence REST API (v4.0, 2024-11-30).

Implements just the long-running analyze pattern the SDK uses:
  POST {endpoint}/documentintelligence/documentModels/{modelId}:analyze?api-version=...  -> 202 + Operation-Location
  GET  {Operation-Location}                                                               -> running ... succeeded
so the *real* azure-ai-documentintelligence client can be exercised offline.
"""
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class StubDocIntel:
    def __init__(self, analyze_result: dict, running_polls: int = 1, fail_status: int | None = None):
        self.analyze_result = analyze_result
        self.running_polls = running_polls
        self.fail_status = fail_status
        self.requests: list[dict] = []
        self._polls: dict[str, int] = {}
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # keep pytest output clean
                pass

            def _send(self, status, body=None, headers=None):
                data = json.dumps(body).encode() if body is not None else b""
                self.send_response(status)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                stub.requests.append({"method": "POST", "path": self.path, "headers": dict(self.headers), "body": body})
                if stub.fail_status:
                    # Only throttling/unavailable responses carry Retry-After. (azure-core retries ANY 4xx/5xx
                                    # that has a Retry-After header, so a stub that always sends it lies.)
                    hdrs = {"Retry-After": "0"} if stub.fail_status in (429, 503) else {}
                    return self._send(stub.fail_status, {"error": {"code": "Failed", "message": "stub failure"}}, hdrs)
                op = str(uuid.uuid4())
                stub._polls[op] = 0
                model = self.path.split("/documentModels/")[1].split(":analyze")[0]
                loc = f"http://{self.headers['Host']}/documentintelligence/documentModels/{model}/analyzeResults/{op}?api-version=2024-11-30"
                self._send(202, None, {"Operation-Location": loc, "Retry-After": "0"})

            def do_GET(self):
                stub.requests.append({"method": "GET", "path": self.path, "headers": dict(self.headers)})
                op = self.path.split("/analyzeResults/")[1].split("?")[0]
                stub._polls[op] += 1
                if stub._polls[op] <= stub.running_polls:
                    return self._send(200, {"status": "running", "createdDateTime": "2026-11-21T10:00:00Z",
                                            "lastUpdatedDateTime": "2026-11-21T10:00:01Z"}, {"Retry-After": "0"})
                self._send(200, {"status": "succeeded", "createdDateTime": "2026-11-21T10:00:00Z",
                                 "lastUpdatedDateTime": "2026-11-21T10:00:02Z", "analyzeResult": stub.analyze_result})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.endpoint = f"http://127.0.0.1:{self.server.server_address[1]}"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
