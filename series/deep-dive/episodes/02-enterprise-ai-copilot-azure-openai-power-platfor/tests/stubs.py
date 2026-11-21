"""One local HTTP server that stands in for Azure AI Search and the Azure OpenAI v1 endpoint.

Search:  POST /indexes('<name>')/docs/search.post.search  -> applies the group_ids search.in filter and a naive
         keyword score over an in-memory index, so trimming can be observed end to end.
         POST /indexes('<name>')/docs/search.index        -> stores documents.
OpenAI:  POST /openai/v1/chat/completions                  -> reply comes from a Python callable (messages -> text)
         POST /openai/v1/embeddings                        -> deterministic tiny vectors.
The real SDKs (azure-search-documents, openai) talk to it.
"""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FILTER = re.compile(r"^group_ids/any\(g: search\.in\(g, '([^']*)', ','\)\)$")


class Stub:
    def __init__(self, docs=None, reply=None, chat_status=200, search_status=200):
        self.docs = list(docs or [])
        self.reply = reply or (lambda messages: "Not configured [1].")
        self.chat_status, self.search_status = chat_status, search_status
        self.calls: list[dict] = []
        stub = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, body, headers=None):
                data = json.dumps(body).encode()
                self.send_response(status)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                path = self.path.split("?")[0]
                stub.calls.append({"path": path, "query": self.path.partition("?")[2], "body": body,
                                   "headers": dict(self.headers)})
                if path.endswith("/docs/search.post.search"):
                    return stub._search(self, body)
                if path.endswith("/docs/search.index"):
                    stub.docs.extend(body["value"])
                    return self._send(200, {"value": [{"key": d["id"], "status": True, "statusCode": 200}
                                                      for d in body["value"]]})
                if path == "/openai/v1/chat/completions":
                    return stub._chat(self, body)
                if path == "/openai/v1/embeddings":
                    inputs = body["input"] if isinstance(body["input"], list) else [body["input"]]
                    return self._send(200, {"object": "list", "model": body["model"],
                                            "data": [{"object": "embedding", "index": i,
                                                      "embedding": [float(len(t)), 1.0, 0.0]}
                                                     for i, t in enumerate(inputs)],
                                            "usage": {"prompt_tokens": 1, "total_tokens": 1}})
                self._send(404, {"error": {"message": f"stub: no route {path}"}})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        self.endpoint = f"http://127.0.0.1:{self.server.server_address[1]}"

    # --- Search -----------------------------------------------------------------------------------
    def _search(self, h, body):
        if self.search_status != 200:
            return h._send(self.search_status, {"error": {"code": "Throttled", "message": "stub"}})
        m = FILTER.match(body.get("filter") or "")
        if not m:
            return h._send(400, {"error": {"message": f"stub refuses unfiltered/unknown filter: {body.get('filter')}"}})
        allowed = set(m.group(1).split(","))
        words = {w for w in re.findall(r"\w+", (body.get("search") or "").lower()) if len(w) > 3}
        hits = []
        for d in self.docs:
            if not allowed & set(d["group_ids"]):
                continue
            score = sum(d["chunk"].lower().count(w) for w in words)
            if score:
                hits.append((score, d))
        hits.sort(key=lambda x: -x[0])
        select = (body.get("select") or "").split(",")
        value = [dict({k: d[k] for k in select if k in d}, **{"@search.score": float(s)})
                 for s, d in hits[: body.get("top", 50)]]
        h._send(200, {"value": value})

    # --- Chat ---------------------------------------------------------------------------------------
    def _chat(self, h, body):
        if self.chat_status == 429:
            return h._send(429, {"error": {"code": "429", "message": "Rate limit"}}, {"retry-after": "0"})
        if self.chat_status == 400:
            return h._send(400, {"error": {"code": "content_filter", "message": "filtered", "param": "prompt"}})
        text = self.reply(body["messages"])
        finish = "content_filter" if text is None else "stop"
        h._send(200, {"id": "chatcmpl-stub", "object": "chat.completion", "created": 0, "model": body["model"],
                      "choices": [{"index": 0, "finish_reason": finish,
                                   "message": {"role": "assistant", "content": text}}],
                      "usage": {"prompt_tokens": 321, "completion_tokens": 42, "total_tokens": 363}})

    def chat_calls(self):
        return [c for c in self.calls if c["path"] == "/openai/v1/chat/completions"]

    def search_calls(self):
        return [c for c in self.calls if c["path"].endswith("/docs/search.post.search")]

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
