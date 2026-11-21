"""The two bugs the recording hits, as patches against the healthy source, and what each one does for real."""
from __future__ import annotations

import re
import subprocess
import threading
import time

import pytest

from conftest import APP, BUGS, apply_patch, build_api, copy_app, free_port, get, needs_dotnet, run, running_api

PATCHES = ["01-month-end-off-by-one.patch", "02-lock-order-deadlock.patch"]


@pytest.mark.parametrize("name", PATCHES)
def test_patches_apply_cleanly_to_the_shipped_source(tmp_path, name):
    app = copy_app(tmp_path)
    apply_patch(app, name)
    assert (app / "src/Contoso.Orders.Api/Reports.cs").read_text() != (APP / "src/Contoso.Orders.Api/Reports.cs").read_text()


def test_each_patch_changes_only_reports_cs_and_a_handful_of_lines():
    for name in PATCHES:
        text = (BUGS / name).read_text()
        files = re.findall(r"^\+\+\+ b/(.+)$", text, flags=re.M)
        changed = [line for line in text.splitlines() if re.match(r"[+-][^+-]", line)]
        assert files == ["src/Contoso.Orders.Api/Reports.cs"], name
        assert len(changed) <= 6, name


@needs_dotnet
def test_month_end_patch_fails_exactly_the_two_report_tests(tmp_path):
    app = copy_app(tmp_path)
    apply_patch(app, "01-month-end-off-by-one.patch")
    result = run(["dotnet", "test", "-m:1", "--nologo"], app)
    out = result.stdout
    assert result.returncode == 1, out
    failed = sorted(re.findall(r"^\s+Failed (\S+) \[", out, flags=re.M))
    assert failed == ["Contoso.Orders.Api.Tests.ReportsTests.Every_order_lands_in_exactly_one_month",
                      "Contoso.Orders.Api.Tests.ReportsTests.MonthEnd_orders_are_part_of_the_month"], out
    # January has 31 days and 30 seeded orders; the bug drops the one on the 31st. Over the year it drops 7 of 237.
    assert re.search(r"MonthEnd_orders_are_part_of_the_month.*?Expected: 30\s+Actual:\s+29", out, flags=re.S)
    assert re.search(r"Every_order_lands_in_exactly_one_month.*?Expected: 237\s+Actual:\s+230", out, flags=re.S)
    assert re.search(r"Failed!\s+- Failed:\s+2, Passed:\s+33, Skipped:\s+4, Total:\s+39", out), out


@needs_dotnet
def test_the_healthy_source_has_no_deadlock_and_the_patched_one_hangs_for_real(tmp_path):
    """Two concurrent requests, Invalidate and Snapshot, with the 50 ms 'database call' made while a lock is held."""
    def two_requests(port: int, timeout: float) -> list:
        results: list = [None, None]

        def call(i: int, method: str, path: str):
            try:
                results[i] = get(f"http://127.0.0.1:{port}{path}", method=method, timeout=timeout)[0]
            except OSError as error:                  # TimeoutError is an OSError
                results[i] = type(error).__name__

        threads = [threading.Thread(target=call, args=(0, "POST", "/reports/cache/invalidate")),
                   threading.Thread(target=call, args=(1, "GET", "/reports/cache"))]
        started = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        results.append(round(time.time() - started, 1))
        return results

    healthy = copy_app(tmp_path / "healthy")
    build_api(healthy)
    port = free_port()
    with running_api(healthy, port, {"Orders__Cache__HoldMs": "50"}):
        invalidate, snapshot, seconds = two_requests(port, timeout=10)
    assert (invalidate, snapshot) == (204, 200) and seconds < 5

    broken = copy_app(tmp_path / "broken")
    apply_patch(broken, "02-lock-order-deadlock.patch")
    build_api(broken)
    port = free_port()
    with running_api(broken, port, {"Orders__Cache__HoldMs": "50"}):
        invalidate, snapshot, seconds = two_requests(port, timeout=5)
        assert (invalidate, snapshot) == ("TimeoutError", "TimeoutError"), (invalidate, snapshot)
        # The process is alive and other requests are fine: only the two that need both locks are stuck.
        assert get(f"http://127.0.0.1:{port}/healthz")[0] == 200
        assert get(f"http://127.0.0.1:{port}/orders?pageSize=1")[0] == 200
        # ... and the next caller of the cache hangs too, which is what the user sees after the first hang.
        with pytest.raises(OSError):
            get(f"http://127.0.0.1:{port}/reports/cache", timeout=3)


def test_deadlock_test_in_the_suite_is_the_guard(tmp_path):
    """The xUnit test that guards the lock order must fail on the patched source (and be fast about it)."""
    if run(["dotnet", "--version"], tmp_path).returncode != 0:
        pytest.skip("dotnet SDK not installed")
    app = copy_app(tmp_path)
    apply_patch(app, "02-lock-order-deadlock.patch")
    started = time.time()
    result = run(["dotnet", "test", "-m:1", "--nologo", "--filter", "FullyQualifiedName~Invalidate_and_Snapshot"], app, timeout=300)
    assert result.returncode == 1, result.stdout
    assert "did not finish in 20 s: the two locks are taken in different orders" in result.stdout
    assert time.time() - started < 200


def test_patch_command_is_available_for_the_other_tests():
    assert subprocess.run(["patch", "--version"], capture_output=True).returncode == 0
