"""The VS Code files, checked by doing what they say: the task builds, the launch configuration's program exists and starts
with the configuration's environment, and every request in the .http file gets the status the comments promise."""
from __future__ import annotations

import re

from conftest import APP, API_DLL, copy_app, free_port, get, jsonc, needs_dotnet, run, running_api

VSCODE = APP / ".vscode"
LAUNCH = jsonc(VSCODE / "launch.json")
TASKS = jsonc(VSCODE / "tasks.json")
CONFIGS = {c["name"]: c for c in LAUNCH["configurations"]}


def test_launch_json_has_a_launch_and_an_attach_configuration():
    assert set(CONFIGS) == {"Orders API (debug)", "Orders API (attach to a running process)"}
    launch, attach = CONFIGS["Orders API (debug)"], CONFIGS["Orders API (attach to a running process)"]
    assert (launch["type"], launch["request"]) == ("coreclr", "launch")
    assert (attach["type"], attach["request"]) == ("coreclr", "attach")
    assert attach["processId"] == "${command:pickProcess}"
    assert launch["justMyCode"] is True and attach["justMyCode"] is True


def test_launch_runs_the_task_that_exists_and_the_task_builds_the_api_project():
    launch = CONFIGS["Orders API (debug)"]
    task = next(t for t in TASKS["tasks"] if t["label"] == launch["preLaunchTask"])
    assert (task["command"], task["type"], task["args"][0]) == ("dotnet", "process", "build")
    project = task["args"][1].replace("${workspaceFolder}", str(APP))
    assert (APP / "src/Contoso.Orders.Api/Contoso.Orders.Api.csproj").samefile(project)
    assert task["problemMatcher"] == "$msCompile"


def test_launch_program_and_cwd_are_where_dotnet_build_puts_them():
    launch = CONFIGS["Orders API (debug)"]
    assert launch["program"] == "${workspaceFolder}/" + API_DLL.as_posix()
    assert launch["cwd"] == "${workspaceFolder}/src/Contoso.Orders.Api"
    assert "<TargetFramework>net10.0</TargetFramework>" in (APP / "src/Contoso.Orders.Api/Contoso.Orders.Api.csproj").read_text()


def test_every_environment_variable_in_launch_json_is_one_the_app_reads():
    program = (APP / "src/Contoso.Orders.Api/Program.cs").read_text()
    for name in CONFIGS["Orders API (debug)"]["env"]:
        if name.startswith("ASPNETCORE_"):
            continue                                   # read by the host itself
        assert name.replace("__", ":") in program, f"{name} is not a setting Program.cs reads"


def test_the_http_file_matches_the_routes():
    program = (APP / "src/Contoso.Orders.Api/Program.cs").read_text()
    http = (VSCODE / "orders.http").read_text()
    for method, path in re.findall(r"^(GET|POST) http://localhost:8080(/[a-z/]+)", http, flags=re.M):
        assert f'Map{method.title()}("{path}"' in program, f"{method} {path}"
    assert http.count("###") == 4


@needs_dotnet
def test_launch_configuration_really_starts_the_api_and_the_http_file_requests_work(tmp_path):
    app = copy_app(tmp_path)
    task = TASKS["tasks"][0]                            # the preLaunchTask, run exactly as VS Code would
    args = [a.replace("${workspaceFolder}", str(app)) for a in task["args"]]
    built = run([task["command"], *args], app)
    assert built.returncode == 0, built.stdout + built.stderr
    assert (app / API_DLL).exists()                     # the launch configuration's "program"

    port = free_port()
    env = {k: v for k, v in CONFIGS["Orders API (debug)"]["env"].items() if k != "ASPNETCORE_URLS"}   # 8080 may be taken here
    with running_api(app, port, env):
        base = f"http://127.0.0.1:{port}"
        assert get(f"{base}/reports/monthly?month=2026-01")[0] == 200
        assert get(f"{base}/reports/monthly?month=2026-13")[0] == 400
        assert get(f"{base}/reports/cache")[0] == 200
        assert get(f"{base}/reports/cache/invalidate", method="POST")[0] == 204
