"""evaluate.py talks HTTP for real; here the server is a local test double (NOT a model) that records what it was sent."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import evaluate
import pytest
import triage
from conftest import SRC

GOLDEN = SRC / "eval" / "golden.jsonl"
TRUTH = {g["notes"]: g for g in triage.load_golden(GOLDEN)}


class Handler(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        Handler.seen.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        if self.path == "/v1/messages":
            notes = body["messages"][0]["content"][-1]["text"][len("Notes: "):]
        else:
            c = body["messages"][-1]["content"]
            notes = (c[0]["text"] if isinstance(c, list) else c)[len("Notes: "):]
        g = TRUTH[notes]
        text = json.dumps({"summary": "test double", "category": g["category"], "severity": g["severity"] if g["id"] != "g02" else "Minor", "confidence": 70})
        if self.path == "/v1/messages":
            out = {"content": [{"type": "text", "text": text}], "usage": {"input_tokens": 100, "output_tokens": 20}}
        else:
            out = {"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture()
def server():
    Handler.seen = []
    s = HTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()


def run(capsys, *argv):
    assert evaluate.main(list(argv)) == 0
    return json.loads(capsys.readouterr().out)


def test_foundry_route_posts_to_the_v1_path_with_a_bearer_token_and_counts_the_one_under_call(server, capsys, monkeypatch):
    monkeypatch.setenv("T", "tok-123")
    res = run(capsys, "run", "--route", "foundry", "--endpoint", server, "--model", "triage", "--token-env", "T", "--price-in", "1", "--price-out", "2")
    path, headers, body = Handler.seen[0]
    assert path == "/openai/v1/chat/completions" and headers["authorization"] == "Bearer tok-123"
    assert body["model"] == "triage" and body["messages"][0]["content"] == triage.SYSTEM_PROMPT
    assert res["n"] == 13 and res["invalid"] == 0 and res["under_calls"] == 1 and res["severity_correct"] == 12
    assert res["tokens_in"] == 1300 and res["tokens_out"] == 260 and res["estimated_cost_usd"] == round((1300 * 1 + 260 * 2) / 1e6, 6)
    assert "tok-123" not in json.dumps(res)


def test_claude_route_sends_key_and_version_headers_and_the_messages_shape(server, capsys, monkeypatch):
    monkeypatch.setenv("K", "key-abc")
    res = run(capsys, "run", "--route", "claude", "--base-url", server, "--model", "m1", "--key-env", "K")
    path, headers, body = Handler.seen[0]
    assert path == "/v1/messages" and headers["x-api-key"] == "key-abc" and headers["anthropic-version"] == triage.ANTHROPIC_VERSION
    assert body["system"] == triage.SYSTEM_PROMPT and body["max_tokens"] == 300 and "authorization" not in headers
    assert res["route"] == "claude" and "key-abc" not in json.dumps(res)


def test_missing_secret_stops_before_any_request(server, monkeypatch):
    monkeypatch.delenv("NOPE", raising=False)
    with pytest.raises(SystemExit) as e:
        evaluate.main(["run", "--route", "claude", "--base-url", server, "--model", "m", "--key-env", "NOPE"])
    assert "NOPE" in str(e.value) and Handler.seen == []


def test_there_is_no_flag_that_takes_a_secret_on_the_command_line():
    with pytest.raises(SystemExit):
        evaluate.main(["run", "--route", "claude", "--model", "m", "--key", "abc"])


def test_save_then_score_offline_round_trip(server, capsys, tmp_path):
    out = tmp_path / "answers.jsonl"
    run(capsys, "run", "--route", "openai-compatible", "--endpoint", server, "--model", "mock", "--save", str(out))
    again = run(capsys, "score", "--answers", str(out))
    assert again["n"] == 13 and again["severity_correct"] == 12


def test_a_dead_endpoint_counts_as_invalid_and_does_not_crash(capsys):
    res = run(capsys, "run", "--route", "openai-compatible", "--endpoint", "http://127.0.0.1:1", "--model", "m")
    assert res["invalid"] == 13 and res["severity_correct"] == 0
