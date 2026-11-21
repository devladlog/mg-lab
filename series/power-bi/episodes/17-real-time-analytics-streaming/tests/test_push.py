"""The push client against a real HTTP server on an ephemeral port (a local stand-in for the Power BI REST API; the real one is the demo)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import events
import push


class Api:
    """Records requests; ``script`` is a list of (status, headers, body) answers consumed in order, then 200."""

    def __init__(self):
        self.requests, self.script = [], []


@pytest.fixture()
def api():
    state = Api()

    class H(BaseHTTPRequestHandler):
        def _handle(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n)) if n else None
            state.requests.append((self.command, self.path, self.headers.get("Authorization"), body))
            status, headers, out = state.script.pop(0) if state.script else (200, {}, {})
            if status == 200 and self.command == "POST" and self.path.split("?")[0].endswith("/datasets"):
                status, out = 201, {"id": "11111111-1111-1111-1111-111111111111", "name": body["name"]}
            data = json.dumps(out).encode()
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_POST = do_GET = do_DELETE = _handle

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    state.url = f"http://127.0.0.1:{srv.server_port}"
    yield state
    srv.shutdown()
    srv.server_close()


WS = "00000000-0000-0000-0000-000000000000"


def test_definition_matches_the_documented_create_body():
    d = push.dataset_definition()
    assert d["defaultMode"] == "PushStreaming"
    cols = {c["name"]: c["dataType"] for c in d["tables"][0]["columns"]}
    assert list(cols) == events.FIELDS
    assert cols["EventTime"] == "DateTime" and cols["Quantity"] == "Int64" and cols["Amount"] == "Double" and cols["Store"] == "string"
    assert len(cols) <= 75 and len(d["tables"]) <= 75  # Learn: 75 columns, 75 tables


def test_limits_are_the_ones_on_learn():
    assert (push.MAX_ROWS_PER_POST, push.MAX_ROWS_PER_HOUR, push.MAX_POSTS_PER_MINUTE) == (10_000, 1_000_000, 120)
    assert push.MAX_STREAMING_REQUEST_BYTES == 15 * 1024


def test_chunk_rows_by_count():
    rows = [{"i": i} for i in range(25)]
    chunks = list(push.chunk_rows(rows, max_rows=10))
    assert [len(c) for c in chunks] == [10, 10, 5]
    assert [r for c in chunks for r in c] == rows
    assert list(push.chunk_rows([])) == []


def test_chunk_rows_by_bytes_keeps_each_body_under_the_limit(records):
    limit = push.MAX_STREAMING_REQUEST_BYTES
    chunks = list(push.chunk_rows(records, max_bytes=limit))
    assert len(chunks) > 1
    for c in chunks:
        assert len(json.dumps({"rows": c}, separators=(",", ":")).encode("utf-8")) <= limit
    assert sum(len(c) for c in chunks) == len(records)


def test_one_row_bigger_than_the_byte_limit_is_an_error():
    with pytest.raises(ValueError):
        list(push.chunk_rows([{"x": "y" * 100}], max_bytes=50))


def test_default_chunk_is_ten_thousand_rows():
    assert [len(c) for c in push.chunk_rows(({"i": i} for i in range(10_001)))] == [10_000, 1]


def test_create_post_delete_use_the_documented_urls_and_the_bearer_token(api, records):
    c = push.PushClient("tok", base_url=api.url)
    ds = c.create_dataset(WS, push.dataset_definition("Demo"))
    assert ds == "11111111-1111-1111-1111-111111111111"
    n = c.post_rows(WS, ds, records[:5])
    c.delete_rows(WS, ds)
    c.delete_dataset(WS, ds)
    assert n == 1
    (m1, p1, a1, b1), (m2, p2, _, b2), (m3, p3, _, _), (m4, p4, _, _) = api.requests
    assert (m1, p1) == ("POST", f"/v1.0/myorg/groups/{WS}/datasets?defaultRetentionPolicy=basicFIFO")
    assert a1 == "Bearer tok" and b1["name"] == "Demo"
    assert (m2, p2) == ("POST", f"/v1.0/myorg/groups/{WS}/datasets/{ds}/tables/TillEvents/rows")
    assert b2 == {"rows": records[:5]}
    assert (m3, p3) == ("DELETE", f"/v1.0/myorg/groups/{WS}/datasets/{ds}/tables/TillEvents/rows")
    assert (m4, p4) == ("DELETE", f"/v1.0/myorg/groups/{WS}/datasets/{ds}")


def test_429_waits_the_retry_after_header_then_succeeds(api, records):
    waits = []
    api.script = [(429, {"Retry-After": "7"}, {"error": {"code": "TooManyRequests"}})]
    c = push.PushClient("tok", base_url=api.url, sleep=waits.append)
    assert c.post_rows(WS, "ds", records[:3]) == 1
    assert waits == [7.0]
    assert len(api.requests) == 2


def test_gives_up_after_max_retries(api):
    api.script = [(429, {"Retry-After": "1"}, {})] * 10
    c = push.PushClient("tok", base_url=api.url, sleep=lambda s: None, max_retries=2)
    with pytest.raises(push.PushError) as e:
        c.post_rows(WS, "ds", [{"a": 1}])
    assert e.value.status == 429 and len(api.requests) == 3


def test_other_errors_are_raised_with_status_and_body(api):
    api.script = [(403, {}, {"error": {"code": "Forbidden"}})]
    with pytest.raises(push.PushError, match="403"):
        push.PushClient("tok", base_url=api.url).create_dataset(WS, push.dataset_definition())


def test_paces_itself_to_120_posts_per_minute(api):
    waits = []
    c = push.PushClient("tok", base_url=api.url, sleep=waits.append)
    assert c.post_rows(WS, "ds", [{"i": i} for i in range(130)], max_rows=1) == 130  # 130 requests of one row
    assert len(waits) == 1 and 0 <= waits[0] <= 60  # after request 120 it waits for the minute to end


def test_a_token_is_required():
    with pytest.raises(ValueError):
        push.PushClient("")


def test_a_pasted_authorization_header_value_is_accepted(api):
    push.PushClient("Bearer tok123 ", base_url=api.url).delete_rows(WS, "ds")
    assert api.requests[0][2] == "Bearer tok123"
    with pytest.raises(ValueError):
        push.PushClient("Bearer ")
