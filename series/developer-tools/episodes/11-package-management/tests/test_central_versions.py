"""Central Package Management, lock files and the shape of the repository, checked with the real dotnet SDK."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from conftest import APP, needs_dotnet, run

pytestmark = needs_dotnet


def csprojs(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.csproj") if not {"bin", "obj"} & set(p.parts))


def package_refs(csproj: Path) -> list[ET.Element]:
    return list(ET.parse(csproj).getroot().iter("PackageReference"))


def central_versions(root: Path) -> dict[str, str]:
    tree = ET.parse(root / "Directory.Packages.props").getroot()
    return {p.get("Include"): p.get("Version") for p in tree.iter("PackageVersion")}


def test_no_project_states_a_package_version():
    refs = [(p.name, r.get("Include")) for p in csprojs(APP) for r in package_refs(p)
            if r.get("Version") is not None or r.get("VersionOverride") is not None]
    assert refs == []


def test_every_reference_has_a_central_version_and_every_central_version_is_used():
    used = {r.get("Include") for p in csprojs(APP) for r in package_refs(p)}
    central = set(central_versions(APP))
    assert used <= central, f"no central version for: {sorted(used - central)}"
    assert central <= used, f"central versions nobody references: {sorted(central - used)}"


def test_cpm_switches_are_the_documented_properties():
    root = ET.parse(APP / "Directory.Packages.props").getroot()
    props = {e.tag: e.text for e in root.find("PropertyGroup")}
    assert props == {
        "ManagePackageVersionsCentrally": "true",
        "CentralPackageTransitivePinningEnabled": "true",
        "CentralPackageVersionOverrideEnabled": "false",
    }


def test_lock_files_are_committed_for_every_project():
    for project in csprojs(APP):
        assert (project.parent / "packages.lock.json").is_file(), project


def test_solution_builds_with_analyzers_and_all_tests_pass(restored_app, dotnet_env):
    """Episode 6's rules (analyzers as errors) still hold with central versions; the split-out Contracts project
    and its rules are tested by the same test project."""
    proc = run(["dotnet", "test", "-m:1", "--no-restore"], restored_app, dotnet_env)
    assert proc.returncode == 0, proc.output
    summary = re.search(r"Passed!\s+- Failed:\s+(\d+), Passed:\s+(\d+), Skipped:\s+(\d+), Total:\s+(\d+)", proc.output)
    assert summary, proc.output
    assert tuple(map(int, summary.groups())) == (0, 27, 4, 31)       # the 4 skipped need SQL Server


def test_locked_restore_passes_on_a_clean_checkout(app, dotnet_env):
    proc = run(["dotnet", "restore", "--locked-mode"], app, dotnet_env)
    assert proc.returncode == 0, proc.output
    assert "NU1004" not in proc.output


def test_changing_a_central_version_without_the_lock_file_fails_locked_restore(app, dotnet_env):
    """The gotcha: Directory.Packages.props and packages.lock.json must change in the same commit."""
    props = app / "Directory.Packages.props"
    props.write_text(props.read_text().replace('"xunit" Version="2.9.3"', '"xunit" Version="2.9.2"'))
    proc = run(["dotnet", "restore", "--locked-mode"], app, dotnet_env)
    assert proc.returncode != 0
    assert "NU1004" in proc.output, proc.output
    assert "lock file" in proc.output.lower()
    # A normal restore regenerates the lock file; after that the locked restore passes again.
    run(["dotnet", "restore"], app, dotnet_env, check=True)
    assert run(["dotnet", "restore", "--locked-mode"], app, dotnet_env).returncode == 0
    assert '"resolved": "2.9.2"' in (app / "tests/Contoso.Orders.Api.Tests/packages.lock.json").read_text()


def test_version_override_is_refused_because_central_overrides_are_off(app, dotnet_env):
    csproj = app / "tests/Contoso.Orders.Api.Tests/Contoso.Orders.Api.Tests.csproj"
    csproj.write_text(csproj.read_text().replace('<PackageReference Include="xunit" />',
                                                  '<PackageReference Include="xunit" VersionOverride="2.9.2" />'))
    proc = run(["dotnet", "restore"], app, dotnet_env)
    assert proc.returncode != 0
    assert re.search(r"NU1\d{3}", proc.output), proc.output
    assert "VersionOverride" in proc.output, proc.output


def test_a_version_next_to_the_package_reference_is_refused_under_cpm(app, dotnet_env):
    csproj = app / "tests/Contoso.Orders.Api.Tests/Contoso.Orders.Api.Tests.csproj"
    csproj.write_text(csproj.read_text().replace('<PackageReference Include="xunit" />',
                                                  '<PackageReference Include="xunit" Version="2.9.2" />'))
    proc = run(["dotnet", "restore"], app, dotnet_env)
    assert proc.returncode != 0
    assert "NU1008" in proc.output, proc.output
