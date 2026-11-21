"""The .NET quality rules, proven with a real "bad pull request": a file that breaks eight rules is added to a clean
copy of the app, built, auto-fixed with `dotnet format`, then fixed by hand. Every step is a real SDK command."""
from __future__ import annotations

import json
import re
import shutil

import pytest

from conftest import APP, FIXTURES, copy_app, dotnet_env, load_workflow, needs_dotnet, run

pytestmark = needs_dotnet
DIAG = re.compile(r"([\w./-]+\.cs)\((\d+),(\d+)\): (error|warning) ([A-Z]+\d+|WHITESPACE): ")


def diagnostics(output: str) -> set[tuple[str, int, str]]:
    return {(m.group(1).rsplit("/", 1)[-1], int(m.group(2)), m.group(5)) for m in DIAG.finditer(output)}


@pytest.fixture(scope="module")
def bad_pr(tmp_path_factory):
    root = copy_app(tmp_path_factory.mktemp("bad-pr"))
    target = root / "src" / "Contoso.Orders.Api" / "OrderExport.cs"
    shutil.copy(FIXTURES / "OrderExport.bad.cs", target)
    env, api = dotnet_env(), "src/Contoso.Orders.Api/Contoso.Orders.Api.csproj"
    steps = {"build": run(["dotnet", "build", api, "-clp:NoSummary"], cwd=root, env=env)}
    steps["verify"] = run(["dotnet", "format", "--verify-no-changes"], cwd=root, env=env)
    steps["untouched"] = target.read_text() == (FIXTURES / "OrderExport.bad.cs").read_text()
    steps["format"] = run(["dotnet", "format"], cwd=root, env=env)
    steps["after_format"] = target.read_text()
    steps["build2"] = run(["dotnet", "build", api, "-clp:NoSummary"], cwd=root, env=env)
    # the one a human fixes: say which culture
    fixed = steps["after_format"].replace('o.Total.ToString("N2")', 'o.Total.ToString("N2", CultureInfo.InvariantCulture)')
    target.write_text("using System.Globalization;\n" + fixed)
    steps["build3"] = run(["dotnet", "build", api, "-clp:NoSummary"], cwd=root, env=env)
    return root, steps


def test_clean_repo_passes_the_dotnet_steps_of_the_quality_job(tmp_path):
    root = copy_app(tmp_path)
    steps = [s["run"] for s in load_workflow()["jobs"]["quality"]["steps"] if s.get("run", "").startswith("dotnet ")]
    assert steps == ["dotnet restore --locked-mode", "dotnet format --verify-no-changes --no-restore"]
    for cmd in steps:                                  # the workflow's own commands, in its own order
        r = run(["bash", "-eo", "pipefail", "-c", cmd], cwd=root, env=dotnet_env())
        assert r.returncode == 0, r.stdout + r.stderr


def test_the_bad_file_fails_the_build_on_eight_rules(bad_pr):
    _, s = bad_pr
    assert s["build"].returncode != 0
    assert diagnostics(s["build"].stdout) == {
        ("OrderExport.cs", 2, "IDE0005"),    # unnecessary using (needs GenerateDocumentationFile on build)
        ("OrderExport.cs", 5, "IDE0161"),    # block-scoped namespace
        ("OrderExport.cs", 9, "IDE0040"),    # missing accessibility modifier
        ("OrderExport.cs", 9, "IDE0051"),    # unused private member
        ("OrderExport.cs", 9, "CS0169"),     # ...which the compiler also reports
        ("OrderExport.cs", 14, "CA2016"),    # CancellationToken not forwarded
        ("OrderExport.cs", 16, "IDE0055"),   # indentation
        ("OrderExport.cs", 16, "CA1305"),    # culture-dependent ToString
    }
    assert all(f" error {c}" in s["build"].stdout for c in ("IDE0005", "CA2016"))    # warnings as errors


def test_verify_no_changes_reports_without_touching_files(bad_pr):
    _, s = bad_pr
    assert s["verify"].returncode != 0
    assert s["untouched"]
    out = s["verify"].stdout + s["verify"].stderr          # dotnet format writes its findings to stderr
    assert "error WHITESPACE: Fix whitespace formatting" in out and "error IDE0161" in out


def test_dotnet_format_fixes_everything_except_the_culture_rule(bad_pr):
    _, s = bad_pr
    assert "Unable to fix CA1305. No associated code fix found." in s["format"].stdout + s["format"].stderr
    after = s["after_format"]
    assert "namespace Contoso.Orders.Api;" in after                      # IDE0161 fixed
    assert "using System.Globalization;" not in after                    # IDE0005 fixed
    assert "exported" not in after                                       # IDE0051 fixed: unused field removed
    assert "ToListAsync(cancellationToken: cancellationToken)" in after  # CA2016 fixed
    assert diagnostics(s["build2"].stdout) == {("OrderExport.cs", 13, "CA1305")}


def test_after_the_human_fix_the_build_is_green(bad_pr):
    root, s = bad_pr
    assert s["build3"].returncode == 0, s["build3"].stdout[-2000:]
    # the end state is the fixture the recording (and the coverage test) starts the "fixed" commit from
    assert (root / "src" / "Contoso.Orders.Api" / "OrderExport.cs").read_text() == (FIXTURES / "OrderExport.fixed.cs").read_text()


def test_problem_matcher_turns_build_errors_into_annotations(bad_pr):
    # setup-dotnet registers this matcher (its .github/csc.json); GitHub's regex flavour has the same meaning here.
    pattern = json.loads((FIXTURES / "setup-dotnet-csc.json").read_text())["problemMatcher"][0]["pattern"][0]
    rx = re.compile(pattern["regexp"])
    hits = [rx.match(line) for line in bad_pr[1]["build"].stdout.splitlines()]
    found = {(m.group(pattern["file"]).rsplit("/", 1)[-1], int(m.group(pattern["line"])), m.group(pattern["code"]))
             for m in hits if m}
    assert found == diagnostics(bad_pr[1]["build"].stdout)


def test_underscore_names_are_only_allowed_in_tests(tmp_path):
    root = copy_app(tmp_path)
    (root / "src" / "Contoso.Orders.Api" / "Naming.cs").write_text(
        "namespace Contoso.Orders.Api;\n\npublic static class Naming\n{\n    public static int Order_count() => 0;\n}\n")
    r = run(["dotnet", "build", "src/Contoso.Orders.Api/Contoso.Orders.Api.csproj", "-clp:NoSummary"],
            cwd=root, env=dotnet_env())
    assert ("Naming.cs", 5, "CA1707") in diagnostics(r.stdout)
    assert "[tests/**.cs]\n# xUnit test names" in (APP / ".editorconfig").read_text()


def test_settings_live_in_one_place():
    props = (APP / "Directory.Build.props").read_text()
    for prop in ("<AnalysisLevel>10.0-recommended</AnalysisLevel>", "<EnforceCodeStyleInBuild>true</EnforceCodeStyleInBuild>",
                 "<TreatWarningsAsErrors>true</TreatWarningsAsErrors>", "<GenerateDocumentationFile>true</GenerateDocumentationFile>"):
        assert prop in props
    for csproj in APP.glob("**/*.csproj"):
        assert "TreatWarningsAsErrors" not in csproj.read_text() and "AnalysisLevel" not in csproj.read_text()


def test_ide0005_on_build_needs_xml_documentation_and_the_compiler_says_so(tmp_path):
    # Learn (IDE0005): "to enable this rule on build, you need to enable XML documentation comments".
    root = copy_app(tmp_path)
    props = root / "Directory.Build.props"
    props.write_text(props.read_text().replace("<GenerateDocumentationFile>true<", "<GenerateDocumentationFile>false<"))
    (root / "src" / "Contoso.Orders.Api" / "Unused.cs").write_text(
        "using System.Text;\n\nnamespace Contoso.Orders.Api;\n\npublic static class Unused\n{\n    public static int One() => 1;\n}\n")
    r = run(["dotnet", "build", "src/Contoso.Orders.Api/Contoso.Orders.Api.csproj", "-clp:NoSummary"],
            cwd=root, env=dotnet_env())
    assert r.returncode != 0 and "IDE0005" not in {code for _, _, code in diagnostics(r.stdout)}
    assert "error EnableGenerateDocumentationFile: Set MSBuild property 'GenerateDocumentationFile' to 'true'" in r.stdout
    with_docs = copy_app(tmp_path / "with-docs")
    (with_docs / "src" / "Contoso.Orders.Api" / "Unused.cs").write_text(
        (root / "src" / "Contoso.Orders.Api" / "Unused.cs").read_text())
    r = run(["dotnet", "build", "src/Contoso.Orders.Api/Contoso.Orders.Api.csproj", "-clp:NoSummary"],
            cwd=with_docs, env=dotnet_env())
    assert ("Unused.cs", 1, "IDE0005") in diagnostics(r.stdout)


def test_xml_documentation_brings_cs1591_which_the_props_file_switches_off(tmp_path):
    root = copy_app(tmp_path)
    props = root / "Directory.Build.props"
    props.write_text(props.read_text().replace("<NoWarn>$(NoWarn);CS1591</NoWarn>", ""))
    r = run(["dotnet", "build", "src/Contoso.Orders.Api/Contoso.Orders.Api.csproj", "-clp:NoSummary"],
            cwd=root, env=dotnet_env())
    assert r.returncode != 0 and "CS1591" in {code for _, _, code in diagnostics(r.stdout)}


def test_problem_matcher_also_annotates_dotnet_format_findings(bad_pr):
    # `dotnet format` prints the same "file(line,col): error ID: text [project]" shape, on stderr; the runner reads both.
    pattern = json.loads((FIXTURES / "setup-dotnet-csc.json").read_text())["problemMatcher"][0]["pattern"][0]
    rx = re.compile(pattern["regexp"])
    out = bad_pr[1]["verify"].stderr
    found = {(m.group(pattern["file"]).rsplit("/", 1)[-1], int(m.group(pattern["line"])), m.group(pattern["code"]))
             for m in map(rx.match, out.splitlines()) if m}
    assert found == diagnostics(out) and ("OrderExport.cs", 16, "WHITESPACE") in found
