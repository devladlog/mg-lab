"""scripts/triage-hang.sh against the real deadlocked API: dotnet-stack, a dump with heap, syncblk and clrstack.
Needs the two local tools from dotnet-tools.json (dotnet tool restore, from NuGet) and permission to read the process
(ptrace): the tests skip, loudly, when either is missing."""
from __future__ import annotations

import json
import re
import subprocess
import threading

import pytest

from conftest import APP, apply_patch, build_api, copy_app, dotnet_env, free_port, get, needs_bash, needs_dotnet, running_api


def test_tool_manifest_pins_exact_versions():
    manifest = json.loads((APP / ".config" / "dotnet-tools.json").read_text())
    assert manifest["isRoot"] is True
    assert set(manifest["tools"]) == {"dotnet-stack", "dotnet-dump"}
    for name, tool in manifest["tools"].items():
        assert re.fullmatch(r"\d+\.\d+\.\d+", tool["version"]), name
        assert tool["commands"] == [name] and tool["rollForward"] is False


@pytest.fixture(scope="module")
def deadlocked(tmp_path_factory):
    app = copy_app(tmp_path_factory.mktemp("hang"))
    apply_patch(app, "02-lock-order-deadlock.patch")
    build_api(app)
    restore = subprocess.run(["dotnet", "tool", "restore"], cwd=app, env=dotnet_env(), capture_output=True, text=True)
    if restore.returncode != 0:
        pytest.skip(f"dotnet tool restore failed (offline?): {restore.stdout}{restore.stderr}")
    port = free_port()
    with running_api(app, port, {"Orders__Cache__HoldMs": "50"}) as (proc, _):
        def call(method, path):
            try:
                get(f"http://127.0.0.1:{port}{path}", method=method, timeout=4)
            except OSError:
                pass
        threads = [threading.Thread(target=call, args=("POST", "/reports/cache/invalidate")),
                   threading.Thread(target=call, args=("GET", "/reports/cache"))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        yield app, proc


@needs_dotnet
@needs_bash
def test_triage_script_shows_both_stuck_threads_and_who_owns_which_lock(deadlocked):
    app, proc = deadlocked
    result = subprocess.run(["bash", "scripts/triage-hang.sh", str(proc.pid), "triage"], cwd=app, env=dotnet_env(),
                            capture_output=True, text=True, timeout=300)
    out = result.stdout
    if result.returncode != 0 and "ptrace" in result.stderr.lower():
        pytest.skip(f"this environment does not allow reading process memory: {result.stderr}")
    assert result.returncode == 0, out + result.stderr

    # 1. dotnet-stack: both request threads wait in Monitor.Enter, in the two methods of the cache.
    stacks = (app / "triage/stacks.txt").read_text()
    waiting = re.findall(r"Monitor\.Enter_Slowpath.*?\n.*?\n\s+Contoso\.Orders\.Api!Contoso\.Orders\.Api\.ReportCache\.(\w+)\(\)", stacks, flags=re.S)
    assert sorted(waiting) == ["Invalidate", "Snapshot"], stacks

    # 2. syncblk: two monitors, each held (MonitorHeld 3 for both) by a different thread.
    table = re.findall(r"^\s*\d+\s+[0-9A-Fa-f]+\s+(\d+)\s+(\d+)\s+[0-9A-Fa-f]+\s+[0-9a-f]+\s+(\d+)\s", out, flags=re.M)
    owners = {thread for _, _, thread in table}
    assert len(table) == 2 and len(owners) == 2, out
    assert all(held == "3" for held, _, _ in table), table

    # 3. clrstack -all: file and line, because the dump knows the pdb.
    assert re.search(r"ReportCache\.Snapshot\(\) \[.*Reports\.cs @ \d+\]", out)
    assert re.search(r"ReportCache\.Invalidate\(\) \[.*Reports\.cs @ \d+\]", out)
    assert "threads:" in out and (app / "triage/hang.dmp").stat().st_size > 10_000_000
    (app / "triage/hang.dmp").unlink()
