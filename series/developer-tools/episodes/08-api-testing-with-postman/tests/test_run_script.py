"""The collection, run for real: the actual API (dotnet run), Newman, the run script CI calls, and a regression
the collection has to catch. Slow (a few builds); needs dotnet and Newman (npm ci in api-tests)."""
from __future__ import annotations

import copy
import json
import subprocess
import sys

import pytest

import junit_gate
from conftest import (API_TESTS, APP, COLLECTION, ENVIRONMENT, NEWMAN, OPENAPI, SCRIPT, copy_app, load_json, needs_bash,
                      needs_dotnet, needs_newman, run_script)

pytestmark = [needs_dotnet, needs_newman, needs_bash]


def newman(args, cwd=API_TESTS):
    return subprocess.run([str(NEWMAN), "run", *args], cwd=cwd, capture_output=True, text=True, timeout=300)


def test_the_script_starts_the_api_runs_both_newman_runs_and_passes(tmp_path):
    res = run_script(APP, tmp_path / "results", EXPECTED_VERSION="abc1234")
    assert res.returncode == 0, res.stdout[-3000:] + res.stderr[-2000:]
    assert "Starting the API on http://127.0.0.1:" in res.stdout
    main = junit_gate.summarize(str(tmp_path / "results" / "junit-main.xml"))
    data = junit_gate.summarize(str(tmp_path / "results" / "junit-data.xml"))
    assert (main["total"], main["passed"]) == (32, 32)        # Health (+1 when a version is expected), Orders, Validation
    assert (data["total"], data["passed"]) == (24, 24)        # 6 rows x (400, field, row present, speed)
    assert "healthz: version is the one just deployed" in (tmp_path / "results" / "junit-main.xml").read_text()
    assert "6/6" in res.stdout                                 # six iterations of the data file


def test_against_an_api_that_is_already_running(api, tmp_path):
    res = run_script(APP, tmp_path / "r", "--no-start", BASE_URL=api.base_url, EXPECTED_VERSION="test-sha")
    assert res.returncode == 0, res.stdout[-3000:]
    assert "Starting the API" not in res.stdout


def test_the_deployed_version_check_fails_when_the_api_reports_another_commit(api, tmp_path):
    res = run_script(APP, tmp_path / "r", "--no-start", BASE_URL=api.base_url, EXPECTED_VERSION="not-the-commit")
    assert res.returncode == 1
    main = junit_gate.summarize(str(tmp_path / "r" / "junit-main.xml"))
    assert main["failed"] == [("HealthGetHealthz", "healthz: version is the one just deployed")]


def test_the_committed_openapi_snapshot_is_what_the_api_generates_now(api, tmp_path):
    out = tmp_path / "openapi.json"
    res = subprocess.run([sys.executable, str(API_TESTS / "tools" / "export_openapi.py"), api.base_url, str(out)],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert load_json(out) == load_json(OPENAPI), "contract changed: re-run tools/export_openapi.py and commit the diff"
    assert load_json(OPENAPI)["openapi"].startswith("3.1")


def test_a_regression_in_the_api_fails_exactly_the_test_that_describes_it(tmp_path):
    """Paging.MaxPageSize 100 -> 1000 in a copy of the app: asking for 500 now returns 500."""
    app = copy_app(tmp_path)
    orders = app / "src" / "Contoso.Orders.Api" / "Orders.cs"
    text = orders.read_text()
    assert "MaxPageSize = 100;" in text
    orders.write_text(text.replace("MaxPageSize = 100;", "MaxPageSize = 1000;"))
    res = run_script(app, tmp_path / "results")
    assert res.returncode == 1
    main = junit_gate.summarize(str(tmp_path / "results" / "junit-main.xml"))
    assert main["failed"] == [("OrdersListOrdersPageSizeIsCapped", "cap: asking for 500 returns at most 100")]
    assert main["passed"] == main["total"] - 1
    assert "1 failed" in res.stdout or "✗ failed: cap: asking for 500" in res.stdout


def test_a_collection_without_tests_exits_zero_in_newman_and_the_gate_catches_it(api, tmp_path):
    """The gotcha: nothing to fail is not the same as everything passed."""
    col = copy.deepcopy(load_json(COLLECTION))

    def strip(items):
        for it in items:
            if "item" in it:
                strip(it["item"])
            else:
                it["event"] = [e for e in it.get("event", []) if e["listen"] != "test"]
    strip(col["item"])
    col["event"] = []
    path = tmp_path / "notests.json"
    path.write_text(json.dumps(col))
    report = tmp_path / "junit.xml"
    res = newman([str(path), "-e", str(ENVIRONMENT), "--env-var", f"baseUrl={api.base_url}", "--folder", "Health",
                  "--folder", "Orders", "--reporters", "cli,junit", "--reporter-junit-export", str(report)])
    assert res.returncode == 0, "Newman 6.2.3 says success when there are no tests"
    assert "assertions" in res.stdout and junit_gate.summarize(str(report))["total"] == 0
    assert junit_gate.main([str(report), "--min-tests", "1"]) == 1


def test_an_unknown_folder_and_an_unreachable_api_are_failures_not_silent_passes(api, tmp_path):
    base = ["-e", str(ENVIRONMENT), "--env-var", f"baseUrl={api.base_url}"]
    typo = newman([str(COLLECTION), *base, "--folder", "Helth"])
    assert typo.returncode == 1 and 'Unable to find a folder or request: "Helth"' in typo.stderr + typo.stdout
    down = newman([str(COLLECTION), "-e", str(ENVIRONMENT), "--env-var", "baseUrl=http://127.0.0.1:1", "--folder", "Health"])
    assert down.returncode == 1


def test_the_data_driven_folder_fails_loudly_without_its_data_file(api):
    res = newman([str(COLLECTION), "-e", str(ENVIRONMENT), "--env-var", f"baseUrl={api.base_url}", "--folder", "Data-driven"])
    assert res.returncode == 1
    assert "run with -d data/invalid-orders.json" in res.stdout


def test_reruns_create_fresh_orders_and_do_not_depend_on_the_seed_data(api):
    """The create request builds its own customer name, so a second run neither collides nor needs a clean database."""
    base = ["-e", str(ENVIRONMENT), "--env-var", f"baseUrl={api.base_url}", "--folder", "Orders"]
    before = json.loads(subprocess.run(["curl", "-s", f"{api.base_url}/orders"], capture_output=True, text=True).stdout)["total"]
    assert newman([str(COLLECTION), *base]).returncode == 0
    assert newman([str(COLLECTION), *base]).returncode == 0
    after = json.loads(subprocess.run(["curl", "-s", f"{api.base_url}/orders"], capture_output=True, text=True).stdout)["total"]
    assert after == before + 2
