"""The pull request we review in the episode, for real: two commits made with git, replayed with `git am` onto the
baseline; the author's tests are green, the reviewer's reproduction is red, GitHub's "Commit suggestion" is applied
exactly as GitHub would, and the follow-up commit makes everything green. Needs dotnet (a few builds, ~1 minute)."""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from conftest import APP, DEMO, git, load_json, needs_dotnet, needs_git, run_cli
from review_kit import description, owners, size

pytestmark = [needs_dotnet, needs_git]
SUMMARY = re.compile(r"(Passed|Failed)!\s+- Failed:\s+(\d+), Passed:\s+(\d+), Skipped:\s+(\d+)")


@pytest.fixture(scope="module")
def pr(tmp_path_factory):
    root = tmp_path_factory.mktemp("pr") / "orders-app"
    shutil.copytree(APP, root, ignore=shutil.ignore_patterns("bin", "obj", "TestResults", "__pycache__"))
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: baseline (orders API from episode 5)")
    git(root, "switch", "-q", "-c", "feat/cancel-order")
    patches = sorted(DEMO.glob("000*.patch"))
    assert len(patches) == 2
    shas = []
    for patch in patches:
        git(root, "am", "-q", str(patch))
        shas.append(git(root, "rev-parse", "HEAD"))
    return {"root": root, "c1": shas[0], "c2": shas[1]}


def dotnet_test(root: Path) -> tuple[str, int, int, int, str]:
    env = {**os.environ, "DOTNET_NOLOGO": "1", "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "MSBUILDDISABLENODEREUSE": "1"}
    env.pop("ORDERS_SQLSERVER_TESTS", None)
    res = subprocess.run(["dotnet", "test", "-m:1", "-nologo"], cwd=root, env=env, capture_output=True, text=True, timeout=900)
    m = SUMMARY.search(res.stdout)
    assert m, res.stdout[-3000:] + res.stderr[-1000:]
    return m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), res.stdout


def failed_names(out: str) -> list[str]:
    return sorted(re.findall(r"^\s+Failed Contoso\.Orders\.Api\.Tests\.\w+\.(\w+)", out, re.M))


def test_the_pull_request_as_submitted_is_small_and_has_its_four_description_sections(pr):
    root = pr["root"]
    assert git(root, "log", "--format=%an <%ae> %s", "main..").splitlines() == [
        "Alex Demo <alex.demo@contoso.example> fix(orders): answer 404 for an unknown order and 409 when cancelling twice",
        "Alex Demo <alex.demo@contoso.example> feat(orders): cancel an order"]
    report = size.analyze(size.diff_numstat("main", pr["c1"], cwd=str(root)))
    assert (report.label, report.lines) == ("S", 31)
    assert report.by_area() == [("tests/Contoso.Orders.Api.Tests", 1, 22), ("src/Contoso.Orders.Api", 2, 9)]
    assert description.check((DEMO / "pr-body.good.md").read_text()) == []


def test_codeowners_routes_the_pull_request_to_the_orders_team_and_qa(pr):
    rules, warnings = owners.parse((APP / ".github" / "CODEOWNERS").read_text())
    files = [c.path for c in size.diff_numstat("main", pr["c1"], cwd=str(pr["root"]))]
    routing = owners.route(files, rules)
    assert warnings == [] and routing == {
        ("@contoso/orders-team",): ["src/Contoso.Orders.Api/Orders.cs", "src/Contoso.Orders.Api/Program.cs"],
        ("@contoso/orders-team", "@contoso/qa"): ["tests/Contoso.Orders.Api.Tests/CancelTests.cs"]}


def test_every_review_comment_points_at_the_line_it_talks_about(pr):
    root = pr["root"]
    anchors = {101: ("tests/Contoso.Orders.Api.Tests/CancelTests.cs", "Cancel_marks_the_order_cancelled"),
               102: ("src/Contoso.Orders.Api/Program.cs", 'order!.Status = "cancelled";'),
               103: ("src/Contoso.Orders.Api/Program.cs", 'order!.Status = "cancelled";'),
               104: ("src/Contoso.Orders.Api/Orders.cs", 'public string Status'),
               105: ("tests/Contoso.Orders.Api.Tests/CancelTests.cs", "Cancel_marks_the_order_cancelled"),
               106: ("src/Contoso.Orders.Api/Program.cs", 'app.MapPost("/orders/{id:int}/cancel"'),
               107: ("src/Contoso.Orders.Api/Program.cs", 'app.MapPost("/orders/{id:int}/cancel"')}
    for c in load_json(DEMO / "review-comments.json"):
        if c["id"] in anchors:
            path, text = anchors[c["id"]]
            assert c["path"] == path
            assert text in git(root, "show", f"{pr['c1']}:{path}").splitlines()[c["line"] - 1], c["id"]


def test_green_ci_red_reproduction_applied_suggestion_green_follow_up(pr):
    root = pr["root"]

    # 1. The author's commit: their own test passes. CI is green, the bug is still there.
    git(root, "checkout", "-q", "-f", pr["c1"])
    verdict, failed, passed, skipped, _ = dotnet_test(root)
    assert (verdict, failed, passed, skipped) == ("Passed", 0, 22, 4)

    # 2. The reviewer's reproduction of two of the comments: both fail on the code as submitted.
    repro = root / "tests" / "Contoso.Orders.Api.Tests" / "CancelRepro.cs"
    shutil.copy(DEMO / "CancelRepro.cs", repro)
    verdict, failed, passed, _, out = dotnet_test(root)
    assert (verdict, failed, passed) == ("Failed", 2, 22)
    assert failed_names(out) == ["Cancelling_an_unknown_order_is_404_not_500", "Cancelling_twice_is_a_409_with_a_reason"]
    assert "Expected: NotFound" in out and "Actual:   InternalServerError" in out      # the 500 from `order!`
    assert "Expected: Conflict" in out and "Actual:   OK" in out

    # 3. "Commit suggestion" on the issue comment: replace the commented lines with the suggestion block.
    comment = next(c for c in load_json(DEMO / "review-comments.json") if c["id"] == 102)
    suggestion = re.search(r"```suggestion\n(.*?)\n```", comment["body"], re.S).group(1)
    program = root / "src" / "Contoso.Orders.Api" / "Program.cs"
    lines = program.read_text().split("\n")
    lines[comment["start_line"] - 1:comment["line"]] = suggestion.split("\n")
    program.write_text("\n".join(lines))
    verdict, failed, passed, _, out = dotnet_test(root)
    assert failed_names(out) == ["Cancelling_twice_is_a_409_with_a_reason"]            # 404 fixed, the other comment still open
    assert (failed, passed) == (1, 23)

    # 4. The author's follow-up commit answers all the blocking comments.
    repro.unlink()
    git(root, "checkout", "-q", "-f", pr["c2"])
    verdict, failed, passed, skipped, _ = dotnet_test(root)
    assert (verdict, failed, passed, skipped) == ("Passed", 0, 24, 4)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_the_risk_named_in_the_description_is_real_an_existing_database_has_no_status_column(pr, tmp_path):
    """EnsureCreated only creates a schema when no tables exist (Learn). An orders.db from before the PR breaks the new code."""
    import sqlite3
    root = pr["root"]
    git(root, "checkout", "-q", "-f", pr["c2"])
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE "Orders" ("Id" INTEGER NOT NULL CONSTRAINT "PK_Orders" PRIMARY KEY AUTOINCREMENT, '
                '"Customer" TEXT NOT NULL, "Total" TEXT NOT NULL, "Created" TEXT NOT NULL)')
    con.execute("INSERT INTO Orders (Customer, Total, Created) VALUES ('Fabrikam', '10.0', '2026-01-01')")
    con.commit()
    con.close()
    port = free_port()
    log = tmp_path / "api.log"
    env = {**os.environ, "ASPNETCORE_ENVIRONMENT": "Production", "Database__Provider": "Sqlite",
           "ConnectionStrings__Orders": f"Data Source={db};Pooling=False", "DOTNET_NOLOGO": "1"}
    proc = subprocess.Popen(["dotnet", "run", "--no-launch-profile", "--project", str(root / "src" / "Contoso.Orders.Api"),
                             "--urls", f"http://127.0.0.1:{port}"], env=env, stdout=log.open("w"), stderr=subprocess.STDOUT)
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2).read()
                break
            except (OSError, urllib.error.URLError):
                time.sleep(1)
        else:
            pytest.fail("API did not start:\n" + log.read_text())
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/orders", timeout=10)
        assert err.value.code == 500
    finally:
        proc.terminate()
        proc.wait(20)
    assert "no such column: o.Status" in log.read_text()
