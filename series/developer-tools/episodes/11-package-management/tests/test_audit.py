"""NuGet Audit and tools/pkg_audit.py against a real vulnerable transitive package (needs network: nuget.org).

The "demo pull request" is real: `dotnet new console` plus `dotnet package add Microsoft.AspNet.WebApi.Client
--version 5.2.9`, whose dependency Newtonsoft.Json 10.0.1 has advisory GHSA-5crp-9r3c-p9vr (high). If nuget.org
ever stops reporting it, these tests fail and the episode needs a new example."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import APP, FIXTURES, copy_tree, needs_dotnet, run

pytestmark = needs_dotnet
ADVISORY = "https://github.com/advisories/GHSA-5crp-9r3c-p9vr"
AUDIT = [sys.executable, str(APP / "tools" / "pkg_audit.py")]


def add_legacy_client(app: Path, env: dict[str, str]) -> Path:
    project = app / "src" / "Contoso.Orders.LegacyClient"
    run(["dotnet", "new", "console", "-o", str(project), "--no-restore"], app, env, check=True)
    run(["dotnet", "package", "add", "Microsoft.AspNet.WebApi.Client", "--version", "5.2.9",
         "--project", str(project)], app, env, check=True)
    run(["dotnet", "sln", "OrdersApp.slnx", "add", str(project)], app, env, check=True)      # so CI builds it
    return project


@pytest.fixture(scope="module")
def legacy_app(tmp_path_factory, dotnet_env) -> Path:
    app = copy_tree(APP, tmp_path_factory.mktemp("legacy") / "orders-app")
    add_legacy_client(app, dotnet_env)
    return app


def test_the_pull_request_added_a_central_version_and_a_versionless_reference(legacy_app):
    assert '<PackageVersion Include="Microsoft.AspNet.WebApi.Client" Version="5.2.9" />' in \
        (legacy_app / "Directory.Packages.props").read_text()
    csproj = (legacy_app / "src/Contoso.Orders.LegacyClient/Contoso.Orders.LegacyClient.csproj").read_text()
    assert '<PackageReference Include="Microsoft.AspNet.WebApi.Client" />' in csproj


def test_the_pull_request_builds_and_the_advisory_is_only_a_warning(legacy_app, dotnet_env):
    """What the build job of the pipeline sees: the whole solution builds (analyzers on), NU1903 stays a warning."""
    proc = run(["dotnet", "build", "-m:1"], legacy_app, dotnet_env)
    assert proc.returncode == 0, proc.output
    assert "warning NU1903" in proc.output and "0 Error(s)" in proc.output


def test_restore_reports_the_advisory_as_a_warning_in_the_normal_build(legacy_app, dotnet_env):
    proc = run(["dotnet", "restore", "src/Contoso.Orders.LegacyClient"], legacy_app, dotnet_env)
    assert proc.returncode == 0, proc.output
    assert f"warning NU1903: Package 'Newtonsoft.Json' 10.0.1 has a known high severity vulnerability, {ADVISORY}" \
        in proc.output


def test_the_audit_pipeline_property_turns_the_same_warning_into_an_error(legacy_app, dotnet_env):
    proc = run(["dotnet", "restore", "src/Contoso.Orders.LegacyClient", "-p:AuditPipeline=true"], legacy_app, dotnet_env)
    assert proc.returncode != 0
    assert "error NU1903: Warning As Error: Package 'Newtonsoft.Json' 10.0.1" in proc.output


def test_without_the_pattern_treat_warnings_as_errors_breaks_everybodys_build(tmp_path, dotnet_env, legacy_app):
    """Why Directory.Build.props has the two WarningsAsErrors / WarningsNotAsErrors lines."""
    app = copy_tree(legacy_app, tmp_path / "app")
    props = app / "Directory.Build.props"
    lines = [ln for ln in props.read_text().splitlines() if "WarningsNotAsErrors" not in ln]
    props.write_text("\n".join(lines) + "\n")
    proc = run(["dotnet", "restore", "src/Contoso.Orders.LegacyClient"], app, dotnet_env)
    assert proc.returncode != 0
    assert "error NU1903" in proc.output, proc.output


def test_pkg_audit_finds_the_transitive_package_and_fails_the_run(legacy_app, dotnet_env):
    proc = run([*AUDIT, "--project", "src/Contoso.Orders.LegacyClient"], legacy_app, dotnet_env)
    assert proc.returncode == 1, proc.output
    assert "HIGH" in proc.stdout and "Newtonsoft.Json 10.0.1" in proc.stdout
    assert "transitive" in proc.stdout and ADVISORY in proc.stdout
    assert "dotnet nuget why Contoso.Orders.LegacyClient Newtonsoft.Json" in proc.stdout


def test_the_pipelines_exact_audit_command_warns_on_high_and_passes_the_build_job(legacy_app, dotnet_env):
    """azure-pipelines.yml, build job: `python3 tools/pkg_audit.py --format azure --min-severity critical`, run from
    the repository root against the whole solution (not one project)."""
    proc = run([*AUDIT, "--format", "azure", "--min-severity", "critical"], legacy_app, dotnet_env)
    assert proc.returncode == 0, proc.output
    assert proc.stdout.startswith("##vso[task.logissue type=warning;code=vulnerable;]Contoso.Orders.LegacyClient: Newtonsoft.Json 10.0.1")
    strict = run([*AUDIT, "--format", "azure"], legacy_app, dotnet_env)
    assert strict.returncode == 1 and "type=error" in strict.stdout


def test_pkg_audit_threshold_decides_the_exit_code(legacy_app, dotnet_env):
    proc = run([*AUDIT, "--project", "src/Contoso.Orders.LegacyClient", "--min-severity", "critical"],
               legacy_app, dotnet_env)
    assert proc.returncode == 0, proc.output
    assert "1 known vulnerabilities (0 at critical or above)" in proc.stdout


def test_pkg_audit_azure_format_writes_logging_commands(legacy_app, dotnet_env):
    proc = run([*AUDIT, "--project", "src/Contoso.Orders.LegacyClient", "--format", "azure"], legacy_app, dotnet_env)
    assert proc.returncode == 1
    line = proc.stdout.strip().splitlines()[0]
    assert line.startswith("##vso[task.logissue type=error;code=vulnerable;]Contoso.Orders.LegacyClient: ")
    assert "Newtonsoft.Json 10.0.1" in line and "%3B" not in line


def test_pkg_audit_markdown_table(legacy_app, dotnet_env):
    proc = run([*AUDIT, "--project", "src/Contoso.Orders.LegacyClient", "--format", "markdown"], legacy_app, dotnet_env)
    assert f"| high | Newtonsoft.Json | 10.0.1 | Contoso.Orders.LegacyClient | transitive | {ADVISORY} |" in proc.stdout


def test_the_clean_repository_has_no_findings(restored_app, dotnet_env):
    proc = run(AUDIT, restored_app, dotnet_env)
    assert proc.returncode == 0, proc.output
    assert "No known vulnerabilities" in proc.stdout


def test_outdated_lists_what_is_behind_by_how_much(legacy_app, dotnet_env):
    proc = run([*AUDIT, "--outdated", "--project", "src/Contoso.Orders.LegacyClient"], legacy_app, dotnet_env)
    assert proc.returncode == 0, proc.output
    assert "major  Microsoft.AspNet.WebApi.Client 5.2.9 -> " in proc.stdout


def test_package_update_vulnerable_adds_a_direct_reference_and_a_central_version(tmp_path, dotnet_env, legacy_app):
    app = copy_tree(legacy_app, tmp_path / "app")
    proc = run(["dotnet", "package", "update", "--vulnerable", "--project", "src/Contoso.Orders.LegacyClient"],
               app, dotnet_env)
    assert proc.returncode == 0, proc.output
    assert "Updating Newtonsoft.Json 10.0.1 to 13.0.1" in proc.output
    assert '<PackageVersion Include="Newtonsoft.Json" Version="13.0.1" />' in (app / "Directory.Packages.props").read_text()
    # The fix for a transitive package is a new DIRECT reference in the project that pulled it in (the option
    # Learn lists as "add the fixed version as a direct package reference"): remove it when the parent is updated.
    assert '<PackageReference Include="Newtonsoft.Json" />' in \
        (app / "src/Contoso.Orders.LegacyClient/Contoso.Orders.LegacyClient.csproj").read_text()
    restore = run(["dotnet", "restore", "src/Contoso.Orders.LegacyClient", "-p:AuditPipeline=true"], app, dotnet_env)
    assert restore.returncode == 0, restore.output
    assert run(AUDIT, app, dotnet_env).returncode == 0


def test_a_hand_written_central_pin_fixes_it_without_touching_any_project(tmp_path, dotnet_env, legacy_app):
    app = copy_tree(legacy_app, tmp_path / "app")
    props = app / "Directory.Packages.props"
    props.write_text(props.read_text().replace(
        '<ItemGroup Label="Tests">',
        '<ItemGroup Label="Pinned transitive packages">\n    <PackageVersion Include="Newtonsoft.Json" Version="13.0.4" />\n'
        '  </ItemGroup>\n\n  <ItemGroup Label="Tests">'))
    run(["dotnet", "restore", "src/Contoso.Orders.LegacyClient", "-p:AuditPipeline=true"], app, dotnet_env, check=True)
    listing = run(["dotnet", "package", "list", "--include-transitive", "--project", "src/Contoso.Orders.LegacyClient"],
                  app, dotnet_env).stdout
    top_level, transitive = listing.split("Transitive Package")
    assert "Newtonsoft.Json" not in top_level                       # still nobody's direct reference...
    assert "> Newtonsoft.Json " in transitive and "13.0.4" in transitive.split("> Newtonsoft.Json ")[1].split("\n")[0]
    assert "Newtonsoft.Json" not in (app / "src/Contoso.Orders.LegacyClient/Contoso.Orders.LegacyClient.csproj").read_text()
    assert run(AUDIT, app, dotnet_env).returncode == 0


@pytest.mark.skipif(shutil.which("script") is None, reason="needs util-linux `script` to give dotnet a terminal")
def test_nuget_why_shows_the_path_but_only_on_a_terminal(legacy_app, dotnet_env):
    plain = run(["dotnet", "nuget", "why", "src/Contoso.Orders.LegacyClient", "Newtonsoft.Json"], legacy_app, dotnet_env)
    on_tty = subprocess.run(
        ["script", "-qc", "dotnet nuget why src/Contoso.Orders.LegacyClient Newtonsoft.Json", "/dev/null"],
        cwd=legacy_app, env={**__import__("os").environ, **dotnet_env}, capture_output=True, text=True, check=False)
    assert "Microsoft.AspNet.WebApi.Client (v5.2.9)" in on_tty.stdout
    assert "Newtonsoft.Json (v10.0.1)" in on_tty.stdout
    assert plain.stdout.strip() == "", "SDK 10.0.115 prints nothing when its output is redirected (observed)"


# --- unit tests of the parser on real saved reports -------------------------------------------------------------

def load(name: str) -> dict:
    return json.loads((FIXTURES / f"dotnet-package-list-{name}.json").read_text())


def test_parse_vulnerable_report_with_a_transitive_package():
    sys.path.insert(0, str(APP / "tools"))
    import pkg_audit
    report = pkg_audit.parse(load("vuln"), "vulnerable")
    [f] = report.findings
    assert (f.package, f.resolved, f.direct, f.severity, f.advisory) == ("Newtonsoft.Json", "10.0.1", False, "high", ADVISORY)
    assert [x.package for x in report.at_least("high")] == ["Newtonsoft.Json"]
    assert report.at_least("critical") == []


def test_parse_projects_without_findings_have_no_frameworks_key():
    sys.path.insert(0, str(APP / "tools"))
    import pkg_audit
    assert pkg_audit.parse(load("clean"), "vulnerable").findings == []


def test_parse_deprecated_and_outdated_reports():
    sys.path.insert(0, str(APP / "tools"))
    import pkg_audit
    [dep] = pkg_audit.parse(load("deprecated"), "deprecated").findings
    assert (dep.package, dep.reasons, dep.alternative) == ("Microsoft.Azure.Storage.Blob", ("Legacy",), "Azure.Storage.Blobs")
    [old] = pkg_audit.parse(load("outdated"), "outdated").findings
    assert (old.package, old.resolved, old.latest) == ("Microsoft.AspNet.WebApi.Client", "5.2.9", "6.0.0")
    assert pkg_audit.gap("5.2.9", "6.0.0") == "major" and pkg_audit.gap("1.2.3", "1.4.0") == "minor"
    assert pkg_audit.gap("1.2.3", "1.2.9") == "patch" and pkg_audit.gap("1.0.0", "1.0.0") == "other"


def test_from_json_reads_a_saved_report_without_running_dotnet(tmp_path):
    saved = FIXTURES / "dotnet-package-list-vuln.json"
    proc = subprocess.run([*AUDIT, "--from-json", str(saved)], capture_output=True, text=True, check=False)
    assert proc.returncode == 1 and "Newtonsoft.Json 10.0.1" in proc.stdout
    proc = subprocess.run([*AUDIT, "--from-json", str(FIXTURES / "dotnet-package-list-clean.json")],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0


def test_azure_values_are_escaped():
    sys.path.insert(0, str(APP / "tools"))
    import pkg_audit
    report = pkg_audit.Report([pkg_audit.Finding("P;Q", "net10.0", "A]B", "1.0.0", True, "vulnerable", "high", "u")])
    line = pkg_audit.render_azure(report, "vulnerable", "high")
    assert "P%3BQ" in line and "A%5DB" in line
