"""Unit tests for the three small tools. Inputs are synthetic or one real dotnet-counters capture (fixtures/)."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

import counters_summary
import load
import speedscope_top
from conftest import APP, TESTS


# ---- load.py -------------------------------------------------------------------------------------------------------

def test_percentile_is_nearest_rank():
    data = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    assert load.percentile(data, 50) == 50.0
    assert load.percentile(data, 95) == 100.0
    assert load.percentile(data, 10) == 10.0
    assert load.percentile([7.0], 95) == 7.0
    assert load.percentile([], 50) == 0.0


def test_summarize_counts_errors_as_requests():
    result = load.summarize([300.0, 100.0, 200.0], errors=1)
    assert result == {"requests": 4, "errors": 1, "p50_ms": 200.0, "p95_ms": 300.0, "max_ms": 300.0}
    assert load.summarize([], 0)["max_ms"] == 0.0


def test_load_invalidates_the_cache_before_every_request():
    """A tiny local HTTP server records the order of the calls: invalidate, report, invalidate, report ..."""
    import http.server
    import threading

    calls: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append("POST " + self.path)
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            calls.append("GET " + self.path)
            body = b"{}"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        result = load.run(f"http://127.0.0.1:{server.server_address[1]}", workers=1, seconds=None, requests=4)
    finally:
        server.shutdown()
    assert result["requests"] == 4 and result["errors"] == 0
    assert calls[0::2] == ["POST /reports/cache/invalidate"] * 4
    assert [c.split("?")[0] for c in calls[1::2]] == ["GET /reports/monthly"] * 4
    assert [c.split("=")[1] for c in calls[1::2]] == load.MONTHS[:4]


def test_load_reports_failures_with_exit_code_1():
    port = _closed_port()
    done = subprocess.run([sys.executable, str(APP / "tools" / "load.py"), f"http://127.0.0.1:{port}", "--requests", "2", "--workers", "1"],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 1 and "2 errors" in done.stdout


def _closed_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---- speedscope_top.py ---------------------------------------------------------------------------------------------

def _evented(frames: list[str], events: list[tuple[str, int, float]]) -> dict:
    return {"shared": {"frames": [{"name": n} for n in frames]},
            "profiles": [{"type": "evented", "startValue": 0, "endValue": events[-1][2],
                          "events": [{"type": t, "frame": f, "at": at} for t, f, at in events]}]}


FRAMES = ["Process64 Main", "CPU_TIME", "UNMANAGED_CODE_TIME", "App!Reports.MonthlyRevenueAsync()", "App!Sqlite.Read()", "App!Other.Method()"]


def test_busy_time_counts_only_cpu_time_and_ignores_waits():
    # 0-100 ms: Reports -> Sqlite -> CPU_TIME (busy); 100-400 ms: waiting (UNMANAGED_CODE_TIME); 400-500 ms: Other -> CPU_TIME
    events = [("O", 3, 0), ("O", 4, 0), ("O", 1, 0), ("C", 1, 100), ("O", 2, 100), ("C", 2, 400), ("C", 4, 400), ("C", 3, 400),
              ("O", 5, 400), ("O", 1, 400), ("C", 1, 500), ("C", 5, 500)]
    total, self_ms, incl_ms, names = speedscope_top.analyze(_evented(FRAMES, events))
    assert total == pytest.approx(200)
    assert self_ms[4] == pytest.approx(100) and self_ms[5] == pytest.approx(100)
    assert incl_ms[3] == pytest.approx(100) and incl_ms[4] == pytest.approx(100)
    assert 1 not in self_ms and 2 not in self_ms and 1 not in incl_ms        # pseudo frames are never reported


def test_sampled_profiles_use_the_weights():
    doc = {"shared": {"frames": [{"name": "A"}, {"name": "B"}]},
           "profiles": [{"type": "sampled", "samples": [[0, 1], [0], [0, 1]], "weights": [10, 5, 20]}]}
    total, self_ms, incl_ms, _ = speedscope_top.analyze(doc)
    assert total == 35 and self_ms[1] == 30 and self_ms[0] == 5 and incl_ms[0] == 35


def test_unknown_profile_type_is_an_error():
    with pytest.raises(ValueError):
        speedscope_top.analyze({"shared": {"frames": []}, "profiles": [{"type": "other"}]})


def test_short_drops_arguments_and_cuts_long_names():
    assert speedscope_top.short("App!Ns.Type.Method(System.String, Int32)") == "App!Ns.Type.Method"
    assert len(speedscope_top.short("x" * 300, width=50)) == 50


def test_cli_prints_top_and_match(tmp_path):
    events = [("O", 3, 0), ("O", 1, 0), ("C", 1, 100), ("C", 3, 100)]
    path = tmp_path / "t.speedscope.json"
    path.write_text(json.dumps(_evented(FRAMES, events)))
    done = subprocess.run([sys.executable, str(APP / "tools" / "speedscope_top.py"), str(path), "--match", "Reports"],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0
    assert "Busy thread time in the trace: 0.1 s" in done.stdout
    assert "100.0%  App!Reports.MonthlyRevenueAsync" in done.stdout


def test_cli_fails_on_an_idle_trace(tmp_path):
    events = [("O", 2, 0), ("C", 2, 100)]
    path = tmp_path / "idle.json"
    path.write_text(json.dumps(_evented(FRAMES, events)))
    done = subprocess.run([sys.executable, str(APP / "tools" / "speedscope_top.py"), str(path)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 1 and "no busy samples" in done.stderr


# ---- counters_summary.py (a real capture of the slow build, 100k orders, 14 s) --------------------------------------

def test_counters_summary_of_the_real_capture():
    doc = json.loads((TESTS / "fixtures" / "counters-slow.json").read_text())
    s = counters_summary.summarize(doc)
    assert s["seconds"] == 14
    assert s["allocated_mb"] == pytest.approx(813.2, abs=0.1)
    assert s["gc_pause_s"] == pytest.approx(5.54, abs=0.01)
    assert (s["gen0"], s["gen1"], s["gen2"]) == (12, 2, 10)
    assert s["working_set_mb"] == 353
    assert s["request_p50_ms"] == 3726 and s["request_p95_ms"] == 4477


def test_counters_summary_without_requests_for_the_route():
    doc = json.loads((TESTS / "fixtures" / "counters-slow.json").read_text())
    s = counters_summary.summarize(doc, route="/nothing")
    assert s["request_p50_ms"] is None and s["allocated_mb"] > 0


def test_counters_cli_json_and_empty_file(tmp_path):
    fixture = TESTS / "fixtures" / "counters-slow.json"
    done = subprocess.run([sys.executable, str(APP / "tools" / "counters_summary.py"), str(fixture), "--json"], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and json.loads(done.stdout)["gen2"] == 10
    empty = tmp_path / "e.json"
    empty.write_text('{"Events": []}')
    done = subprocess.run([sys.executable, str(APP / "tools" / "counters_summary.py"), str(empty)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 1
