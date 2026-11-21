"""The build-test job's own `run:` commands, executed for real in a clean copy of the app, then the smoke test
against the API built by them. Plus the lock-file rules: locked restore, the Dockerfile's `-a <arch>` restore,
and what happens when the graph changes."""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from conftest import APP, copy_app, dotnet_env, load_workflow, needs_dotnet, run

pytestmark = needs_dotnet


@pytest.fixture(scope="module")
def job(tmp_path_factory):
    """Run every `run:` step of build-test, in order, like the runner (bash, repo root, summary file)."""
    root = copy_app(tmp_path_factory.mktemp("build-test"))
    summary = root.parent / "summary.md"
    env = dict(dotnet_env(), GITHUB_STEP_SUMMARY=str(summary), CI="true")
    results = []
    for step in load_workflow()["jobs"]["build-test"]["steps"]:
        if "run" in step:
            r = run(["bash", "-eo", "pipefail", "-c", step["run"]], cwd=root, env=env, timeout=900)
            results.append((step["run"], r))
            assert r.returncode == 0, f"{step['run']}\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}"
    return root, summary, results


def test_build_test_job_steps_pass_and_write_the_summary(job):
    root, summary, results = job
    assert [cmd.split()[0:2] for cmd, _ in results] == [
        ["dotnet", "restore"], ["dotnet", "build"], ["dotnet", "test"], ["python3", "tools/trx_check.py"]]
    test_out = results[2][1].stdout
    assert re.search(r"Passed:\s+21, Skipped:\s+4, Total:\s+25", test_out), test_out[-500:]
    assert "| unit.trx | 21 | 0 | 4 |" in summary.read_text()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def api(job, tmp_path_factory):
    root = job[0]
    dll = root / "src" / "Contoso.Orders.Api" / "bin" / "Release" / "net10.0" / "Contoso.Orders.Api.dll"
    port, db = free_port(), tmp_path_factory.mktemp("db") / "orders.db"
    env = dict(dotnet_env(), ASPNETCORE_URLS=f"http://127.0.0.1:{port}", Database__Provider="Sqlite",
               ConnectionStrings__Orders=f"Data Source={db}", App__Version="3f2c1e0")
    proc = subprocess.Popen(["dotnet", str(dll)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    proc.wait(timeout=30)


def smoke(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(APP / "tools" / "smoke.py"), *args],
                          capture_output=True, text=True, timeout=120)


def order_total(base: str) -> int:
    with urllib.request.urlopen(f"{base}/orders?pageSize=1", timeout=10) as r:
        return json.load(r)["total"]


def test_smoke_passes_against_the_real_api_once_it_reports_the_version(api):
    r = smoke(api, "--database", "Sqlite", "--version", "3f2c1e0", "--timeout", "60", "--interval", "0.5")
    assert r.returncode == 0, r.stdout
    assert r.stdout.splitlines()[-1] == "7 passed, 0 failed"


def test_smoke_fails_when_the_old_version_is_still_running(api):
    # What a deploy looks like while the platform still serves the previous container.
    r = smoke(api, "--version", "0000000", "--timeout", "2", "--interval", "0.5", "--read-only")
    assert r.returncode == 1
    assert "✗ /healthz ok and version 0000000" in r.stdout and "'version': '3f2c1e0'" in r.stdout


def test_smoke_wrong_database_is_a_failure(api):
    r = smoke(api, "--database", "SqlServer", "--timeout", "10", "--read-only")
    assert r.returncode == 1 and "✗ database is SqlServer (got Sqlite)" in r.stdout


def test_read_only_smoke_writes_nothing(api):
    before = order_total(api)
    assert smoke(api, "--read-only", "--timeout", "10").returncode == 0
    assert order_total(api) == before


def test_smoke_against_nothing_fails_after_the_timeout():
    start = time.monotonic()
    r = smoke(f"http://127.0.0.1:{free_port()}", "--timeout", "1.5", "--interval", "0.5")
    assert r.returncode == 1 and "Connection refused" in r.stdout
    assert time.monotonic() - start < 20


# ------------------------------------------------------------------------------------------- lock files
def test_locked_restore_for_each_docker_architecture(tmp_path):
    root = copy_app(tmp_path)
    for arch in ("x64", "arm64"):
        r = run(["dotnet", "restore", "src/Contoso.Orders.Api/Contoso.Orders.Api.csproj", "-a", arch, "--locked-mode"],
                cwd=root, env=dotnet_env())
        assert r.returncode == 0, r.stdout + r.stderr


def test_without_runtime_identifiers_the_dockerfile_restore_fails_NU1004(tmp_path):
    root = copy_app(tmp_path)
    csproj = root / "src" / "Contoso.Orders.Api" / "Contoso.Orders.Api.csproj"
    csproj.write_text(re.sub(r"\s*<RuntimeIdentifiers>.*?</RuntimeIdentifiers>", "", csproj.read_text()))
    run(["dotnet", "restore", "--force-evaluate"], cwd=root, env=dotnet_env())          # regenerate the lock file
    r = run(["dotnet", "restore", str(csproj), "-a", "x64", "--locked-mode"], cwd=root, env=dotnet_env())
    assert r.returncode != 0 and "NU1004" in r.stdout


def test_a_dependency_change_without_updating_the_lock_file_fails_in_ci(tmp_path):
    root = copy_app(tmp_path)
    csproj = root / "src" / "Contoso.Orders.Api" / "Contoso.Orders.Api.csproj"
    csproj.write_text(re.sub(r'\s*<PackageReference Include="Microsoft.EntityFrameworkCore.SqlServer"[^>]*/>', "",
                             csproj.read_text()))
    r = run(["dotnet", "restore", "--locked-mode"], cwd=root, env=dotnet_env())
    assert r.returncode != 0 and "NU1004" in r.stdout
