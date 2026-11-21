"""The whole episode, for real: build the slow and the fixed API in Release, put the same load on each, and profile it with
scripts/profile.sh (dotnet-counters + dotnet-trace, then the summaries). Needs the dotnet SDK, a NuGet feed for the two pinned
tools and about two minutes. One API at a time, only processes started here are stopped."""
from __future__ import annotations

import re
import subprocess

import pytest

from conftest import apply_patch, build_release, copy_app, dotnet_env, free_port, needs_dotnet, needs_patch, wait_healthy

SEED = 50_000


def profile(app, dll, tmp_path, label):
    port = free_port()
    log = tmp_path / f"{label}-api.log"
    env = dotnet_env(ASPNETCORE_URLS=f"http://127.0.0.1:{port}", ASPNETCORE_ENVIRONMENT="Production",
                     Orders__SeedCount=str(SEED), ConnectionStrings__Orders=f"Data Source={tmp_path / (label + '.db')}")
    with log.open("w") as out:
        proc = subprocess.Popen(["dotnet", str(dll)], cwd=dll.parent, env=env, stdout=out, stderr=subprocess.STDOUT)
    try:
        wait_healthy(port, proc, log)
        done = subprocess.run(["bash", "scripts/profile.sh", f"http://127.0.0.1:{port}", str(proc.pid), "8", str(tmp_path / f"{label}-profile")],
                              cwd=app, env=dotnet_env(), capture_output=True, text=True, timeout=600)
        assert done.returncode == 0, done.stdout + done.stderr
        return done.stdout
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


def number(pattern, text):
    match = re.search(pattern, text)
    assert match, f"{pattern!r} not found in:\n{text}"
    return float(match.group(1))


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    slow, fast = copy_app(tmp, "slow"), copy_app(tmp, "fast")
    apply_patch(slow, "01-load-everything.patch")
    out = {}
    for label, app in (("slow", slow), ("fast", fast)):
        dll = build_release(app)
        out[label] = profile(app, dll, tmp, label)
    return out


@needs_dotnet
@needs_patch
def test_the_load_sees_the_slow_report_and_the_fixed_one(runs):
    slow, fast = (number(r"== load:.*p50 ([\d.]+) ms", runs[k]) for k in ("slow", "fast"))
    assert slow > 3 * fast, f"slow p50 {slow} ms, fast p50 {fast} ms"


@needs_dotnet
@needs_patch
def test_the_trace_puts_the_busy_time_in_the_report_method_and_sqlite_reads(runs):
    text = runs["slow"]
    share = number(r"([\d.]+)%  Contoso\.Orders\.Api!Contoso\.Orders\.Api\.Reports\.MonthlyRevenueAsync", text)
    assert share > 50, text
    assert "Busy thread time in the trace" in text
    assert re.search(r"Sqlite", text), "the top self frames should be the data reader, not the string formatting"


@needs_dotnet
@needs_patch
def test_the_counters_show_what_the_fix_saves(runs):
    slow = number(r"allocated ([\d.]+) MB", runs["slow"])
    fast_text = runs["fast"]
    fast = number(r"allocated ([\d.]+) MB", fast_text)
    slow_rate = number(r"\(([\d.]+) MB/s\)", runs["slow"])
    fast_rate = number(r"\(([\d.]+) MB/s\)", fast_text)
    slow_pause = number(r"GC pause ([\d.]+) s", runs["slow"])
    fast_pause = number(r"GC pause ([\d.]+) s", fast_text)
    print(f"allocated slow {slow} MB fast {fast} MB, rate {slow_rate} vs {fast_rate}, pause {slow_pause} vs {fast_pause}")
    assert slow_pause > fast_pause, f"GC pause: slow {slow_pause} s, fast {fast_pause} s"
