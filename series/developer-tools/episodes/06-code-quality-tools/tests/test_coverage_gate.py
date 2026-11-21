"""tools/coverage_gate.py: a real pull request in a real git repository (the recording's, after the style fixes). The
branch adds a tested CSV export and a discount method nobody tests; the total stays above the line-coverage threshold
while the changed lines are mostly uncovered, so only the diff gate fails. Adding the test makes it pass. Coverage is
collected by the exact `dotnet test` command of the workflow."""
from __future__ import annotations

import re
import shutil
import subprocess
import textwrap

import pytest

import coverage_gate
from conftest import APP, FIXTURES, copy_app, dotnet_env, load_workflow, needs_dotnet, run

BUILD_CMDS = ["dotnet restore --locked-mode", "dotnet build --no-restore -c Release"]
TEST_CMD = next(s["run"] for s in load_workflow()["jobs"]["build-test"]["steps"] if s.get("run", "").startswith("dotnet test"))
GATE = "python3 tools/coverage_gate.py TestResults --include src/ --min-line 90 --diff-base main --min-diff 80"


def git(root, *args):
    return subprocess.run(["git", "-c", "user.name=Alex Demo", "-c", "user.email=alex@contoso.example", *args],
                          cwd=root, check=True, capture_output=True, text=True).stdout


def collect_and_gate(root, env):
    shutil.rmtree(root / "TestResults", ignore_errors=True)
    for cmd in (BUILD_CMDS, [TEST_CMD]):                                    # the workflow's own steps, in order
        for c in cmd:
            r = run(["bash", "-eo", "pipefail", "-c", c], cwd=root, env=env, timeout=900)
            assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    gate = run(["bash", "-c", GATE], cwd=root, env=dict(env, GITHUB_ACTIONS="true",
                                                        GITHUB_STEP_SUMMARY=str(root.parent / "summary.md")))
    return gate


def put(root, fixture: str, target: str) -> None:
    shutil.copy(FIXTURES / fixture, root / target)


@pytest.fixture(scope="module")
def pull_request(tmp_path_factory):
    """The recording's pull request after the style fixes: a tested CSV export and an untested discount method."""
    if shutil.which("dotnet") is None or shutil.which("git") is None:
        pytest.skip("needs dotnet and git")
    root, env = copy_app(tmp_path_factory.mktemp("pr")), dotnet_env()
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: baseline")
    git(root, "checkout", "-q", "-b", "feat/export-orders-csv")
    put(root, "OrderExport.fixed.cs", "src/Contoso.Orders.Api/OrderExport.cs")
    put(root, "OrderExportTests.cs", "tests/Contoso.Orders.Api.Tests/OrderExportTests.cs")
    put(root, "Discounts.cs", "src/Contoso.Orders.Api/Discounts.cs")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "feat(orders): export orders as csv and add discount codes")
    untested = collect_and_gate(root, env)
    put(root, "DiscountTests.cs", "tests/Contoso.Orders.Api.Tests/DiscountTests.cs")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "test(orders): cover discount codes")
    tested = collect_and_gate(root, env)
    return root, untested, tested


@needs_dotnet
def test_untested_new_code_fails_the_diff_gate_although_the_total_is_fine(pull_request):
    root, untested, _ = pull_request
    assert untested.returncode == 1, untested.stdout
    total = re.search(r"\| product code \| (\d+)/(\d+) \| ([\d.]+) \|", untested.stdout)
    assert float(total.group(3)) >= 90                                    # the total gate alone would have passed
    assert "| product code | 85/93 | 91.4 |" in untested.stdout and "| changed lines | 5/13 | 38.5 |" in untested.stdout
    assert "diff coverage 38.5% (5/13 changed lines) is below 80%" in untested.stdout
    assert "line coverage" not in untested.stdout.replace("diff coverage", "")  # only the diff gate failed


@needs_dotnet
def test_uncovered_changed_lines_are_annotated_for_the_pull_request(pull_request):
    _, untested, _ = pull_request
    notes = re.findall(r"::warning file=(\S+?),line=(\d+),title=Not covered::", untested.stdout)
    assert notes and {f for f, _ in notes} == {"src/Contoso.Orders.Api/Discounts.cs"}
    assert {int(n) for _, n in notes} == {7, 9, 12, 13, 14, 15, 16, 17}   # the if, its return, the switch and its arms
    assert "lines 7, 9, 12-17" in untested.stdout
    assert "Not covered, changed in this PR: `src/Contoso.Orders.Api/Discounts.cs` lines " in untested.stdout


@needs_dotnet
def test_adding_the_test_makes_the_same_gate_pass_and_the_summary_shows_it(pull_request):
    root, _, tested = pull_request
    assert tested.returncode == 0, tested.stdout
    assert "| product code | 93/93 | 100.0 |" in tested.stdout and "| changed lines | 13/13 | 100.0 |" in tested.stdout
    assert "::warning" not in tested.stdout
    summary = (root.parent / "summary.md").read_text()
    assert summary.count("### Coverage") == 2                              # appended once per run


# --------------------------------------------------------------------------------------------- no dotnet needed
DIFF = textwrap.dedent("""\
    diff --git a/src/A.cs b/src/A.cs
    --- a/src/A.cs
    +++ b/src/A.cs
    @@ -3,0 +4,2 @@ class A
    +x
    +y
    @@ -10 +12 @@
    -z
    +w
    diff --git a/src/Old.cs b/src/Old.cs
    deleted file mode 100644
    --- a/src/Old.cs
    +++ /dev/null
    @@ -1,3 +0,0 @@
    """)


def test_changed_lines_come_from_unified_zero_hunks():
    assert coverage_gate.changed_lines(DIFF) == {"src/A.cs": {4, 5, 12}}


def test_ranges_are_compact():
    assert coverage_gate.ranges([9, 10, 11, 14, 20, 21]) == "9-11, 14, 20-21"


def test_lines_outside_the_report_do_not_count_as_changed_code():
    cov = coverage_gate.Coverage()
    for line, hits in ((4, 1), (5, 0), (6, 1)):
        cov.add("src/A.cs", line, hits)
    res = coverage_gate.evaluate(cov, ["src/"], 0, {"src/A.cs": {5, 99}}, 80)       # 99 is a brace: not coverable
    assert res.diff == (0, 1) and res.uncovered_changed == {"src/A.cs": [5]} and len(res.problems) == 1


def test_a_wrong_include_is_an_error_not_a_pass():
    cov = coverage_gate.Coverage()
    cov.add("src/A.cs", 1, 1)
    assert "wrong --include" in coverage_gate.evaluate(cov, ["lib/"], 90).problems[0]


def test_no_report_is_an_error(tmp_path, capsys):
    assert coverage_gate.main([str(tmp_path)]) == 1                       # an empty folder
    assert coverage_gate.main([str(tmp_path / "TestResults")]) == 1       # a folder that was never created
    assert "no Cobertura report found" in capsys.readouterr().err


def test_report_paths_of_another_machine_are_kept_as_they_are(tmp_path):
    assert coverage_gate.relative("/home/runner/work/x/src/A.cs", tmp_path) == "/home/runner/work/x/src/A.cs"
    assert coverage_gate.relative(str(tmp_path / "src" / "A.cs"), tmp_path) == "src/A.cs"


def test_the_gate_is_a_tool_of_the_app_not_of_the_tests():
    assert (APP / "tools" / "coverage_gate.py").is_file()
