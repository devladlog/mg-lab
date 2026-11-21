"""A scripted stand-in for the Ollama HTTP API, used ONLY by these tests (the recorded demo uses the real servers)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

GIB = 1024 ** 3
TAGS = {"models": [
    {"name": "demo-8b:q4", "model": "demo-8b:q4", "size": int(5 * GIB),
     "details": {"format": "gguf", "family": "llama", "parameter_size": "8.0B", "quantization_level": "Q4_K_M"}},
    {"name": "demo-70b:q4", "model": "demo-70b:q4", "size": int(40 * GIB),
     "details": {"format": "gguf", "family": "llama", "parameter_size": "70B", "quantization_level": "Q4_K_M"}},
]}
SHOW = {"details": {"family": "llama"}, "model_info": {
    "general.architecture": "llama", "llama.block_count": 32, "llama.attention.head_count": 32,
    "llama.attention.head_count_kv": 8, "llama.embedding_length": 4096, "llama.context_length": 8192}}
GOOD_JSON = {"vendor": "Fabrikam Cloud", "invoice_number": "FC-2026-0417", "total_eur": 4600.0,
             "due_date": "2026-12-15", "category": "cloud", "asks_to_change_bank_details": True}


class State:
    def __init__(self):
        self.requests = []          # (method, path, body)
        self.loaded = {"name": "demo-8b:q4", "model": "demo-8b:q4", "size": 6 * GIB, "size_vram": 6 * GIB,
                       "context_length": 4096}
        self.chat_reply = json.dumps(GOOD_JSON)


@pytest.fixture()
def server():
    state = State()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj, code=200):
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            state.requests.append(("GET", self.path, None))
            if self.path == "/api/tags":
                self._send(TAGS)
            elif self.path == "/api/ps":
                self._send({"models": [state.loaded]})
            elif self.path == "/v1/models":
                self._send({"object": "list", "data": [{"id": "demo-8b:q4"}]})
            else:
                self._send({"error": "not found"}, 404)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            state.requests.append(("POST", self.path, body))
            if self.path == "/api/show":
                self._send(SHOW)
            elif self.path == "/api/chat":
                if body.get("messages") == []:
                    self._send({"model": body["model"], "done": True, "done_reason": "unload"})
                    return
                self._send({"model": body["model"], "message": {"role": "assistant", "content": state.chat_reply},
                            "done": True, "done_reason": "stop", "total_duration": 2_500_000_000,
                            "load_duration": 1_500_000_000, "prompt_eval_count": 50, "prompt_eval_duration": 100_000_000,
                            "eval_count": 100, "eval_duration": 1_000_000_000})
            elif self.path == "/v1/chat/completions":
                self._send({"model": body["model"], "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
                            "usage": {"prompt_tokens": 7, "completion_tokens": 3}})
            else:
                self._send({"error": "not found"}, 404)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    state.url = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield state
    httpd.shutdown()
    httpd.server_close()
