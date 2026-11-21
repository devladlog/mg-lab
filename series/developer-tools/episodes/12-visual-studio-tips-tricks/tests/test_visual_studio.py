"""What Visual Studio does with those files, reproduced with the dotnet CLI on real builds and real processes."""

from __future__ import annotations

import os
import re
import time

from conftest import (
    APP,
    SMOKE_NAMES,
    app_pids,
    copy_app,
    free_port,
    get,
    run,
    server,
    tool,
    wait_for,
)

PROFILE = "Orders API (20 orders, OpenAPI)"
TESTS_SLNF = "OrdersApp.Tests.slnf"


def dll(repo, project, name):
    return repo / project / "bin" / "Debug" / "net10.0" / f"{name}.dll"


# ---- solution filters -----------------------------------------------------------------------------------------------


def test_api_filter_builds_the_api_and_not_the_tests(tmp_path, dotnet_env):
    repo = copy_app(tmp_path / "orders-app")
    run(["dotnet", "build", "OrdersApp.Api.slnf", "-m:1"], repo, dotnet_env, check=True)
    assert dll(repo, "src/Contoso.Orders.Api", "Contoso.Orders.Api").is_file()
    assert not (repo / "tests" / "Contoso.Orders.Api.Tests" / "bin").exists()


def test_tests_filter_pulls_in_the_project_it_references(built):
    assert dll(built, "tests/Contoso.Orders.Api.Tests", "Contoso.Orders.Api.Tests").is_file()
    assert dll(built, "src/Contoso.Orders.Api", "Contoso.Orders.Api").is_file()


def test_dotnet_sln_lists_the_projects_of_a_filter(built, dotnet_env):
    code, out = run(["dotnet", "sln", "OrdersApp.Api.slnf", "list"], built, dotnet_env)
    assert code == 0
    assert "src/Contoso.Orders.Api/Contoso.Orders.Api.csproj" in out and "Tests" not in out


def test_without_a_name_dotnet_build_takes_the_slnx_not_a_filter(built, dotnet_env):
    code, out = run(["dotnet", "build", "--no-restore", "-m:1"], built, dotnet_env)
    assert code == 0, out[-1500:]
    assert "Contoso.Orders.Api ->" in out and "Contoso.Orders.Api.Tests ->" in out


# ---- run settings ---------------------------------------------------------------------------------------------------


def test_smoke_trait_selects_exactly_the_tests_the_playlist_describes(built, dotnet_env):
    code, out = run(["dotnet", "test", TESTS_SLNF, "--no-build", "--list-tests", "--filter", "Category=Smoke"], built, dotnet_env)
    assert code == 0
    names = [line.strip() for line in out.split("The following Tests are available:")[1].splitlines() if line.strip() and not line.startswith(("VSTEST", "  VSTEST"))]
    assert len(names) == SMOKE_NAMES, names
    assert any("The_repository_runsettings_reached_the_test_host" in n for n in names)


def test_the_runsettings_reach_the_test_host_through_the_property(built, dotnet_env):
    code, out = run(["dotnet", "test", TESTS_SLNF, "--no-build", "--filter", "FullyQualifiedName~RunSettingsTests"], built, dotnet_env)
    assert code == 0 and "Passed:     1" in out, out[-1500:]


def test_dotnet_test_does_not_autodetect_the_root_runsettings(built, dotnet_env):
    """Without the property the file sits in the solution root, where Visual Studio would auto-detect it. dotnet test does not."""
    code, out = run(["dotnet", "test", TESTS_SLNF, "--no-build", "-p:RunSettingsFilePath=", "--filter", "FullyQualifiedName~RunSettingsTests"], built, dotnet_env)
    assert code != 0
    assert "CONTOSO_REGION is '(not set)'" in out


def test_the_settings_option_is_the_command_line_way(built, dotnet_env):
    code, out = run(["dotnet", "test", TESTS_SLNF, "--no-build", "-p:RunSettingsFilePath=", "--settings", ".runsettings", "--filter", "FullyQualifiedName~RunSettingsTests"], built, dotnet_env)
    assert code == 0 and "Passed:     1" in out, out[-1500:]


def test_a_filter_that_matches_nothing_fails_only_with_the_runsettings(built, dotnet_env):
    args = ["dotnet", "test", TESTS_SLNF, "--no-build", "--filter", "Category=Nothing"]
    code, out = run(args, built, dotnet_env)
    assert code != 0 and "No test matches the given testcase filter" in out
    code, out = run([*args, "-p:RunSettingsFilePath="], built, dotnet_env)
    assert code == 0 and "No test matches the given testcase filter" in out


def test_the_whole_suite_passes_with_the_settings(built, dotnet_env):
    code, out = run(["dotnet", "test", TESTS_SLNF, "--no-build"], built, dotnet_env)
    assert code == 0
    assert re.search(r"Passed!\s+- Failed:\s+0, Passed:\s+36, Skipped:\s+4, Total:\s+40", out), out[-800:]


def test_session_timeout_aborts_a_hung_run(built, dotnet_env, tmp_path):
    hang = built / "tests" / "Contoso.Orders.Api.Tests" / "HangTests.cs"
    hang.write_text("namespace Contoso.Orders.Api.Tests;\npublic class HangTests { [Fact] public void Hangs() => Thread.Sleep(TimeSpan.FromMinutes(5)); }\n")
    short = tmp_path / "short.runsettings"
    short.write_text("<RunSettings><RunConfiguration><TestSessionTimeout>8000</TestSessionTimeout></RunConfiguration></RunSettings>")
    try:
        start = time.time()
        code, out = run(["dotnet", "test", TESTS_SLNF, "-m:1", "--settings", str(short), "--filter", "FullyQualifiedName~HangTests"], built, dotnet_env, timeout=240)
        elapsed = time.time() - start
    finally:
        hang.unlink()
        run(["dotnet", "build", TESTS_SLNF, "-m:1"], built, dotnet_env, check=True)  # the test dll no longer holds the hanging test
    assert "test run timeout of 8000 milliseconds exceeded" in out and "Test Run Aborted" in out, out[-1500:]
    assert code != 0
    assert elapsed < 120, f"the run took {elapsed:.0f}s: the timeout did not end it"


# ---- launch profiles and Hot Reload -------------------------------------------------------------------------------


def run_app(repo, env, tmp_path, *extra):
    port = free_port()
    args = ["dotnet", "run", "--no-build", "--project", "src/Contoso.Orders.Api", *extra, "--", "--urls", f"http://127.0.0.1:{port}"]
    for leftover in (repo / "src" / "Contoso.Orders.Api").glob("orders.db*"):
        leftover.unlink()
    with server(args, repo, env, tmp_path / f"run-{port}.log"):
        wait_for(port, "/healthz", 90)
        return get(port, "/healthz"), get(port, "/orders?pageSize=1")


def test_the_launch_profile_sets_the_environment_the_app_reads(built, dotnet_env, tmp_path):
    health, orders = run_app(built, dotnet_env, tmp_path, "--launch-profile", PROFILE)
    assert health["version"] == "vs-profile" and orders["total"] == 20
    health, orders = run_app(built, dotnet_env, tmp_path, "--no-launch-profile")
    assert health["version"] == "dev" and orders["total"] == 237


def save_until(path, port, url, predicate, wait=45, attempts=3):
    """The file is already edited. If the watcher has not reacted after `wait` seconds, save it again (a new modification time)."""
    for attempt in range(attempts):
        try:
            wait_for(port, url, wait, predicate)
            return attempt
        except BaseException as error:  # pytest.fail raises a BaseException subclass (Failed)
            if attempt == attempts - 1:
                raise
            print("not applied yet:", type(error).__name__)
            os.utime(path, (time.time() + attempt + 1, time.time() + attempt + 1))
            path.write_text(path.read_text() + "\n" if attempt % 2 == 0 else path.read_text().rstrip("\n") + "\n")


def test_hot_reload_applies_a_method_edit_and_a_top_level_edit_restarts(tmp_path, dotnet_env):
    repo = copy_app(tmp_path / "orders-app")
    env = {**dotnet_env, "DOTNET_USE_POLLING_FILE_WATCHER": "1", "DOTNET_WATCH_SUPPRESS_LAUNCH_BROWSER": "1", "DOTNET_WATCH_SUPPRESS_EMOJIS": "1"}
    port = free_port()
    log = tmp_path / "watch.log"
    args = ["dotnet", "watch", "--non-interactive", "--project", "src/Contoso.Orders.Api", "--launch-profile", PROFILE, "--", "--urls", f"http://127.0.0.1:{port}"]
    orders_cs = repo / "src" / "Contoso.Orders.Api" / "Orders.cs"
    program_cs = repo / "src" / "Contoso.Orders.Api" / "Program.cs"
    with server(args, repo, env, log) as proc:
        assert wait_for(port, "/orders?pageSize=1", 240)["pageSize"] == 1
        before = app_pids(proc.pid)
        assert len(before) == 1

        # 1. a method body in a normal class: applied to the running process
        time.sleep(10)  # a save in the first seconds after startup can be missed by the watcher: let it settle, then retry
        orders_cs.write_text(orders_cs.read_text().replace("Math.Clamp(pageSize ?? DefaultPageSize, 1, MaxPageSize)", "Math.Clamp(pageSize ?? DefaultPageSize, 2, MaxPageSize)"))
        saved_again = save_until(orders_cs, port, "/orders?pageSize=1", lambda body: body["pageSize"] == 2)
        print("saved again:", saved_again)
        assert "Hot reload succeeded" in log.read_text()
        assert app_pids(proc.pid) == before, "Hot Reload must not restart the process"
        assert "Exited" not in log.read_text()

        # 2. a change in the top-level statements of Program.cs: dotnet watch needs a restart (non-interactive restarts)
        program_cs.write_text(program_cs.read_text().replace('? "ok" : "degraded"', '? "fine" : "degraded"'))
        save_until(program_cs, port, "/healthz", lambda body: body["status"] == "fine", wait=120)
        text = log.read_text()
        assert "Restart is needed to apply the changes" in text
        after = app_pids(proc.pid)
        assert len(after) == 1 and after != before, "the app process should be a new one after the restart"


# ---- snippets -------------------------------------------------------------------------------------------------------


def test_the_snippets_expand_to_code_that_compiles_and_passes(built, dotnet_env):
    first = tool("expand", APP / "snippets" / "ordtest.snippet")[1]
    second = tool("expand", APP / "snippets" / "ordtest.snippet", "--set", "name=Unknown_order_answers_404", "--set", "path=/orders/99999", "--set", "status=NotFound")[1]
    scoped = tool(
        "expand", APP / "snippets" / "ordscope.snippet", "--selected",
        'var body = await _client.GetStringAsync("/healthz");\n            Assert.Contains("ok", body);',
    )[1]
    source = f"""using System.Net;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Contoso.Orders.Api.Tests;

public class GeneratedSnippetTests(ApiFactory factory) : IClassFixture<ApiFactory>
{{
    private readonly HttpClient _client = factory.CreateClient();
    private readonly ILogger _log = NullLogger.Instance;

    {first}

    {second}

    [Fact]
    public async Task Health_is_ok_inside_a_scope()
    {{
        {scoped}
    }}
}}
"""
    target = built / "tests" / "Contoso.Orders.Api.Tests" / "GeneratedSnippetTests.cs"
    target.write_text(source)
    try:
        code, out = run(["dotnet", "test", TESTS_SLNF, "-m:1", "--filter", "FullyQualifiedName~GeneratedSnippetTests"], built, dotnet_env)
    finally:
        target.unlink()
    assert code == 0, out[-2500:]
    assert re.search(r"Passed!\s+- Failed:\s+0, Passed:\s+3, Skipped:\s+0, Total:\s+3", out), out[-800:]
