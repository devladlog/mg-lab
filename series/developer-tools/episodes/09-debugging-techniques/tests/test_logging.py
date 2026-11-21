"""Find the one request in the logs: the trace id in the problem details body, the scopes in the JSON logs, tools/trace_lines.py."""
from __future__ import annotations

import io
import json
import subprocess
import sys

import pytest
import trace_lines

from conftest import APP, build_api, copy_app, free_port, get, needs_dotnet, running_api


@pytest.fixture(scope="module")
def api_run(tmp_path_factory):
    """One real run of the API: a rejected month and a good one, both with a caller-supplied W3C traceparent."""
    app = copy_app(tmp_path_factory.mktemp("logging"))
    build_api(app)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    bad = "11111111111111112222222222222222"
    good = "33333333333333334444444444444444"
    with running_api(app, port) as (_, log):
        bad_response = get(f"{base}/reports/monthly?month=2026-13", {"traceparent": f"00-{bad}-00f067aa0ba902b7-01"})
        good_response = get(f"{base}/reports/monthly?month=2026-01", {"traceparent": f"00-{good}-00f067aa0ba902b7-01"})
        other = get(f"{base}/reports/monthly?month=nope")
    return {"bad": bad, "good": good, "bad_response": bad_response, "good_response": good_response,
            "other": other, "log": log.read_text()}


@needs_dotnet
def test_problem_details_traceId_is_the_w3c_form_with_the_callers_trace_id(api_run):
    status, _, body = api_run["bad_response"]
    trace = json.loads(body)["traceId"]
    assert status == 400
    version, trace_id, span_id, flags = trace.split("-")
    assert (version, trace_id, flags) == ("00", api_run["bad"], "01")
    assert len(span_id) == 16 and span_id != "00f067aa0ba902b7"       # the server's own span, not the caller's


@needs_dotnet
def test_the_log_line_of_the_rejected_request_is_found_with_the_traceId_from_the_body(api_run):
    from_body = json.loads(api_run["bad_response"][2])["traceId"]
    found = list(trace_lines.lines_for(trace_lines.trace_id(from_body), api_run["log"].splitlines()))
    assert found == [("Warning", "Contoso.Orders.Reports", "Rejected month 2026-13: expected yyyy-MM")]


@needs_dotnet
def test_the_successful_request_is_found_by_its_bare_trace_id(api_run):
    found = list(trace_lines.lines_for(api_run["good"], api_run["log"].splitlines()))
    assert [(level, message) for level, _, message in found] == [
        ("Information", "Monthly revenue 2026-01: 5 customers, 30 orders, total 14959.65")]


@needs_dotnet
def test_scopes_carry_trace_span_parent_and_the_request_path(api_run):
    entries = [json.loads(line) for line in api_run["log"].splitlines() if line.startswith("{")]
    entry = next(e for e in entries if e["Message"].startswith("Monthly revenue"))
    names = {key for scope in entry["Scopes"] for key in scope}
    assert {"TraceId", "SpanId", "ParentId", "RequestId", "RequestPath", "ConnectionId"} <= names
    assert next(s for s in entry["Scopes"] if "RequestPath" in s)["RequestPath"] == "/reports/monthly"


@needs_dotnet
def test_a_request_without_traceparent_gets_a_trace_id_of_its_own(api_run):
    trace = json.loads(api_run["other"][2])["traceId"]
    _, trace_id, _, _ = trace.split("-")
    assert trace_id not in (api_run["bad"], api_run["good"])
    assert len(list(trace_lines.lines_for(trace_id, api_run["log"].splitlines()))) == 1


@needs_dotnet
def test_the_command_line_tool_end_to_end(api_run):
    from_body = json.loads(api_run["bad_response"][2])["traceId"]
    done = subprocess.run([sys.executable, "-I", str(APP / "tools" / "trace_lines.py"), from_body],
                          input=api_run["log"], capture_output=True, text=True)
    assert done.returncode == 0
    assert done.stdout.strip() == "Warning     Contoso.Orders.Reports: Rejected month 2026-13: expected yyyy-MM"


# --- the tool on its own (no dotnet needed) -------------------------------------------------------------------------

def test_trace_id_accepts_both_forms_and_rejects_the_rest():
    bare = "4bf92f3577b34da6a3ce929d0e0e4736"
    assert trace_lines.trace_id(bare) == bare
    assert trace_lines.trace_id(f"00-{bare}-00f067aa0ba902b7-01") == bare
    assert trace_lines.trace_id(f" 00-{bare.upper()}-00F067AA0BA902B7-00\n") == bare
    for bad in ["", "abc", bare[:-1], f"00-{bare}", f"00-{bare}-00f067aa0ba902b7", "0HNQ7JGBFSH1E:00000001"]:
        with pytest.raises(ValueError):
            trace_lines.trace_id(bad)


def test_plain_text_lines_and_lines_without_scopes_are_ignored():
    trace = "a" * 32
    lines = [
        "Unhandled exception. System.InvalidOperationException: boom",
        json.dumps({"LogLevel": "Information", "Category": "x", "Message": "no scopes"}),
        json.dumps({"LogLevel": "Information", "Category": "x", "Message": "null scopes", "Scopes": None}),
        json.dumps(["not", "an", "object"]),
        json.dumps({"LogLevel": "Error", "Category": "c", "Message": "mine", "Scopes": [{"RequestId": "1"}, {"TraceId": trace}]}),
        json.dumps({"LogLevel": "Error", "Category": "c", "Message": "someone else", "Scopes": [{"TraceId": "b" * 32}]}),
    ]
    assert list(trace_lines.lines_for(trace, lines)) == [("Error", "c", "mine")]


def test_exit_codes(monkeypatch, capsys):
    trace = "c" * 32
    log = json.dumps({"LogLevel": "Warning", "Category": "c", "Message": "m", "Scopes": [{"TraceId": trace}]}) + "\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(log))
    assert trace_lines.main(["trace_lines.py", trace]) == 0
    monkeypatch.setattr(sys, "stdin", io.StringIO(log))
    assert trace_lines.main(["trace_lines.py", "d" * 32]) == 1          # valid id, nothing found
    assert trace_lines.main(["trace_lines.py", "nope"]) == 2            # not an id
    assert trace_lines.main(["trace_lines.py"]) == 2                    # no argument
    assert "no log line with TraceId" in capsys.readouterr().err
