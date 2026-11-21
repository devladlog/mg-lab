import base64
import json
import struct
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class StubServer:
    """Local HTTP server: records every request and replays scripted (status, headers, body) responses.

    Used to run the real azure-search-documents and openai SDKs without any cloud resource.
    """

    def __init__(self):
        self.requests = []
        self.responses = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def _handle(self):
                length = int(self.headers.get("content-length", 0) or 0)
                raw = self.rfile.read(length) if length else b""
                body = json.loads(raw) if raw else None
                stub.requests.append({"method": self.command, "path": self.path, "body": body,
                                      "headers": {k.lower(): v for k, v in self.headers.items()}})
                status, headers, payload = stub.responses.pop(0)
                if callable(payload):
                    payload = payload(body)
                data = b"" if payload is None else json.dumps(payload).encode()
                self.send_response(status)
                for k, v in {"content-type": "application/json; odata.metadata=none", **headers}.items():
                    self.send_header(k, v)
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PUT = do_DELETE = _handle

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


def embedding_payload(dimensions=8, honor_request=True):
    """Build an OpenAI embeddings response for whatever the request asked (float or base64 encoding)."""

    def make(body):
        inputs = body["input"] if isinstance(body["input"], list) else [body["input"]]
        dims = body.get("dimensions", dimensions) if honor_request else dimensions
        data = []
        for i, _ in enumerate(inputs):
            vec = [float(i + 1)] + [0.0] * (dims - 1)
            if body.get("encoding_format") == "base64":
                emb = base64.b64encode(struct.pack(f"<{dims}f", *vec)).decode()
            else:
                emb = vec
            data.append({"object": "embedding", "index": i, "embedding": emb})
        return {"object": "list", "data": data, "model": "text-embedding-3-small",
                "usage": {"prompt_tokens": 10, "total_tokens": 10}}

    return make


@pytest.fixture
def handbook():
    return ROOT / "data" / "handbook"


@pytest.fixture
def questions_path():
    return ROOT / "data" / "questions.jsonl"
