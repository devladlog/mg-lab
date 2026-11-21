"""The three small tools around the collection, on the real collection and on mutated copies."""
from __future__ import annotations

import copy
import json
import subprocess
import sys

import pytest

import collection_lint
import junit_gate
import openapi_coverage
from conftest import API_TESTS, COLLECTION, ENVIRONMENT, OPENAPI, load_json

COL = load_json(COLLECTION)
SPEC = load_json(OPENAPI)


def find(col: dict, name: str) -> dict:
    stack = list(col["item"])
    while stack:
        it = stack.pop()
        if "item" in it:
            stack += it["item"]
        elif it["name"] == name:
            return it
    raise KeyError(name)


def test_committed_collection_and_environment_pass_the_lint():
    assert collection_lint.lint_collection(COL) == []
    assert collection_lint.lint_environment(load_json(ENVIRONMENT)) == []


def test_collection_shape():
    assert COL["info"]["schema"] == "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    assert [f["name"] for f in COL["item"]] == ["Health", "Orders", "Validation", "Data-driven"]
    assert {v["key"] for v in COL["variable"]} >= {"orderSchema"}
    json.loads(next(v["value"] for v in COL["variable"] if v["key"] == "orderSchema"))   # a valid schema string
    # one collection-level test, so every request is also checked for speed
    assert any("responseTime" in "".join(e["script"]["exec"]) for e in COL["event"] if e["listen"] == "test")


def test_no_hardcoded_ids_or_hosts_anywhere_in_the_files():
    text = COLLECTION.read_text() + ENVIRONMENT.read_text()
    assert "azurewebsites" not in text and "devladlog" not in text
    assert "localhost:8080" in ENVIRONMENT.read_text()          # the only host, in the environment, not in requests
    assert "http://" not in COLLECTION.read_text().replace("https://schema.getpostman.com", "")


def test_lint_catches_a_request_without_tests():
    col = copy.deepcopy(COL)
    find(col, "Order not found")["event"] = []
    assert any(p.startswith("no-tests: 'Orders / Order not found'") for p in collection_lint.lint_collection(col))


def test_lint_catches_a_test_that_never_looks_at_the_status():
    col = copy.deepcopy(COL)
    find(col, "Order not found")["event"] = [{"listen": "test", "script": {"exec": ['pm.test("x", () => pm.expect(1).to.eql(1));']}}]
    assert any(p.startswith("no-status:") for p in collection_lint.lint_collection(col))


def test_lint_catches_a_hardcoded_host_and_a_secret_literal_and_a_duplicate():
    col = copy.deepcopy(COL)
    r = find(col, "GET healthz")
    r["request"]["url"]["raw"] = "https://orders.example.com/healthz"
    r["request"]["header"].append({"key": "Authorization", "value": "Bearer abcdefghijklmnopqrstuvwxyz0123456789"})
    col["item"][0]["item"].append(copy.deepcopy(r))
    kinds = {p.split(":")[0] for p in collection_lint.lint_collection(col)}
    assert {"hardcoded-host", "secret", "duplicate"} <= kinds


def test_lint_requires_secret_variables_to_be_type_secret_and_empty():
    env = {"values": [{"key": "apiToken", "value": "abc", "type": "default"}]}
    assert collection_lint.lint_environment(env)
    env = {"values": [{"key": "apiToken", "value": "", "type": "secret"}]}
    assert collection_lint.lint_environment(env) == []


def test_lint_cli_exit_codes(tmp_path):
    ok = subprocess.run([sys.executable, str(API_TESTS / "tools" / "collection_lint.py"), str(COLLECTION), str(ENVIRONMENT)],
                        capture_output=True, text=True)
    assert ok.returncode == 0 and "10 requests" in ok.stdout
    bad = copy.deepcopy(COL)
    find(bad, "GET healthz")["event"] = []
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    res = subprocess.run([sys.executable, str(API_TESTS / "tools" / "collection_lint.py"), str(p)], capture_output=True, text=True)
    assert res.returncode == 1 and "no-tests" in res.stdout


# --------------------------------------------------------------------------------- OpenAPI coverage
def test_every_operation_and_documented_status_is_covered():
    lines, problems = openapi_coverage.check(SPEC, COL)
    assert problems == []
    assert len(lines) == 4


def test_a_new_endpoint_in_the_spec_fails_until_the_collection_catches_up():
    spec = copy.deepcopy(SPEC)
    spec["paths"]["/orders/{id}/cancel"] = {"post": {"responses": {"200": {}, "404": {}}}}
    _, problems = openapi_coverage.check(spec, COL)
    assert problems == ["POST /orders/{id}/cancel has no request in the collection"]


def test_a_documented_status_nobody_asserts_is_reported():
    spec = copy.deepcopy(SPEC)
    spec["paths"]["/orders"]["post"]["responses"]["409"] = {"description": "Conflict"}
    _, problems = openapi_coverage.check(spec, COL)
    assert problems == ["POST /orders: documented but never asserted: 409"]


def test_a_request_for_an_endpoint_that_no_longer_exists_is_reported():
    spec = copy.deepcopy(SPEC)
    del spec["paths"]["/orders/{id}"]
    _, problems = openapi_coverage.check(spec, COL)
    orphans = sorted(p.split("'")[1] for p in problems if "matches no operation" in p)
    assert orphans == ["Orders / Order id is not a number", "Orders / Order not found", "Orders / Read the order back"]
    assert len(problems) == 3


@pytest.mark.parametrize("template,path,expected", [
    ("/orders/{id}", "/orders/{{orderId}}", True), ("/orders/{id}", "/orders/abc", True), ("/orders/{id}", "/orders/:id", True),
    ("/orders/{id}", "/orders", False), ("/orders", "/orders/1", False), ("/orders", "/customers", False)])
def test_path_matching(template, path, expected):
    assert openapi_coverage.fits(template, path) is expected


def test_query_strings_and_the_base_url_variable_are_ignored():
    col = {"item": [{"name": "r", "event": [], "request": {"method": "GET", "url": {"raw": "{{baseUrl}}/orders?page=0"}}}]}
    [r] = openapi_coverage.requests(col)
    assert (r["method"], r["path"]) == ("GET", "/orders")


# --------------------------------------------------------------------------------------- JUnit gate
SUITE = """<?xml version="1.0"?><testsuites><testsuite name="a" tests="{n}">{cases}</testsuite></testsuites>"""


def junit(tmp_path, passed=0, failed=0, skipped=0):
    cases = "".join(f'<testcase name="p{i}" classname="c"/>' for i in range(passed))
    cases += "".join(f'<testcase name="f{i}" classname="c"><failure message="boom"/></testcase>' for i in range(failed))
    cases += "".join(f'<testcase name="s{i}" classname="c"><skipped/></testcase>' for i in range(skipped))
    p = tmp_path / "r.xml"
    p.write_text(SUITE.format(n=passed + failed + skipped, cases=cases))
    return str(p)


def test_gate_passes_when_enough_tests_ran(tmp_path, capsys):
    assert junit_gate.main([junit(tmp_path, passed=5), "--min-tests", "5"]) == 0
    assert "5 passed, 0 failed" in capsys.readouterr().out


def test_gate_fails_on_a_failure(tmp_path, capsys):
    assert junit_gate.main([junit(tmp_path, passed=4, failed=1)]) == 1
    assert "failed: f0" in capsys.readouterr().out


def test_gate_fails_when_nothing_ran_even_though_nothing_failed(tmp_path, capsys):
    assert junit_gate.main([junit(tmp_path)]) == 1
    assert "only 0 assertions ran" in capsys.readouterr().out


def test_gate_fails_when_too_few_ran_and_when_tests_were_skipped(tmp_path):
    assert junit_gate.main([junit(tmp_path, passed=3), "--min-tests", "5"]) == 1
    assert junit_gate.main([junit(tmp_path, passed=5, skipped=1)]) == 1
    assert junit_gate.main([junit(tmp_path, passed=5, skipped=1), "--max-skipped", "1"]) == 0


def test_gate_fails_on_a_missing_or_broken_report(tmp_path):
    assert junit_gate.main([str(tmp_path / "nope.xml")]) == 1
    bad = tmp_path / "bad.xml"
    bad.write_text("<testsuites>")
    assert junit_gate.main([str(bad)]) == 1
