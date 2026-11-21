"""The two Azure DevOps pipelines (and the template they share) use only Build Tools tasks and inputs that Learn lists.

The task names and inputs below were copied from "Microsoft Power Platform Build Tools tasks"
(learn.microsoft.com/power-platform/alm/devops-build-tool-tasks) on 2026-11-21. We can't run Azure Pipelines
here: this checks the YAML parses, uses real task inputs, and keeps the order that makes the deployment safe.
"""
import re

import pytest
import yaml
from conftest import SRC

P = "microsoft-IsvExpTools.PowerPlatform-BuildTools."
AUTH = {"authenticationType", "PowerPlatformEnvironment", "PowerPlatformSPN"}
TASKS = {
    P + "tool-installer.PowerPlatformToolInstaller@2": {"DefaultVersion", "AddToolsToPath", "PowerAppsAdminVersion"},
    P + "export-solution.PowerPlatformExportSolution@2": AUTH | {"SolutionName", "SolutionOutputFile", "AsyncOperation", "MaxAsyncWaitTime", "Managed"},
    P + "unpack-solution.PowerPlatformUnpackSolution@2": {"SolutionInputFile", "SolutionTargetFolder", "SolutionType"},
    P + "pack-solution.PowerPlatformPackSolution@2": {"SolutionOutputFile", "SolutionSourceFolder", "SolutionType"},
    P + "import-solution.PowerPlatformImportSolution@2": AUTH | {
        "SolutionInputFile", "HoldingSolution", "OverwriteUnmanagedCustomizations", "SkipProductUpdateDependencies",
        "AsyncOperation", "MaxAsyncWaitTime", "PublishWorkflows", "UseDeploymentSettingsFile", "DeploymentSettingsFile"},
    P + "apply-solution-upgrade.PowerPlatformApplySolutionUpgrade@2": AUTH | {"SolutionName", "AsyncOperation", "MaxAsyncWaitTime"},
    P + "set-solution-version.PowerPlatformSetSolutionVersion@2": AUTH | {"SolutionName", "SolutionVersionNumber"},
}
REQUIRED = {
    P + "export-solution.PowerPlatformExportSolution@2": {"SolutionName", "SolutionOutputFile"},
    P + "unpack-solution.PowerPlatformUnpackSolution@2": {"SolutionInputFile", "SolutionTargetFolder", "SolutionType"},
    P + "pack-solution.PowerPlatformPackSolution@2": {"SolutionOutputFile", "SolutionSourceFolder", "SolutionType"},
    P + "import-solution.PowerPlatformImportSolution@2": {"SolutionInputFile"},
    P + "apply-solution-upgrade.PowerPlatformApplySolutionUpgrade@2": {"SolutionName"},
    P + "set-solution-version.PowerPlatformSetSolutionVersion@2": {"SolutionName", "SolutionVersionNumber"},
}
FILES = ["export-from-dev.yml", "deploy-steps.yml", "release.yml"]


def load(name):
    return yaml.safe_load((SRC / "pipelines" / name).read_text(encoding="utf-8"))


def walk_steps(node):
    """Every step dict, also inside deployment jobs and `${{ if }}` blocks."""
    if isinstance(node, dict):
        if "task" in node or "bash" in node or "template" in node:
            yield node
        for k, v in node.items():
            yield from walk_steps(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk_steps(v)


def inputs_of(step):
    out = {}
    for k, v in step.get("inputs", {}).items():
        if k.startswith("${{"):
            out.update(v)
        else:
            out[k] = v
    return out


def tasks():
    for f in FILES:
        for s in walk_steps(load(f)):
            if "task" in s:
                yield f, s


def test_every_task_is_a_build_tools_v2_task_with_known_inputs():
    seen = 0
    for f, s in tasks():
        assert s["task"] in TASKS, f"{f}: {s['task']}"
        unknown = set(inputs_of(s)) - TASKS[s["task"]]
        assert not unknown, f"{f}: {s['task']} has unknown inputs {unknown}"
        missing = REQUIRED.get(s["task"], set()) - set(inputs_of(s))
        assert not missing, f"{f}: {s['task']} lacks {missing}"
        seen += 1
    assert seen >= 9


def test_versions_are_not_mixed():
    versions = {s["task"].rsplit("@", 1)[1] for _, s in tasks()}
    assert versions == {"2"}  # Learn: you can't mix task versions in one pipeline


def test_export_takes_both_package_types_and_unpacks_both():
    steps = list(walk_steps(load("export-from-dev.yml")))
    exports = [s for s in steps if s.get("task", "").endswith("PowerPlatformExportSolution@2")]
    assert [e["inputs"]["Managed"] for e in exports] == [False, True]
    assert exports[1]["inputs"]["SolutionOutputFile"].endswith("_managed.zip")
    unpack = next(s for s in steps if s.get("task", "").endswith("PowerPlatformUnpackSolution@2"))
    assert unpack["inputs"]["SolutionType"] == "Both"
    # the version is set in DEV before the export, so the zip and the source folder carry it
    order = [s["task"].split(".")[-1] for s in steps if "task" in s]
    assert order.index("PowerPlatformSetSolutionVersion@2") < order.index("PowerPlatformExportSolution@2")


def test_release_packs_managed_once_and_checks_before_packing():
    steps = list(walk_steps(load("release.yml")))
    pack = [s for s in steps if s.get("task", "").endswith("PowerPlatformPackSolution@2")]
    assert len(pack) == 1 and pack[0]["inputs"]["SolutionType"] == "Managed"
    kinds = ["check" if "almkit check" in s.get("displayName", "") else "pack" if "task" in s and "Pack" in s["task"] else None for s in steps]
    assert kinds.index("check") < kinds.index("pack")


def test_deploy_renders_settings_then_imports_with_them():
    steps = [s for s in walk_steps(load("deploy-steps.yml")) if "template" not in s]
    names = [s.get("displayName", "") for s in steps]
    render = next(i for i, n in enumerate(names) if n.startswith("Render"))
    imp = next(i for i, n in enumerate(names) if n.startswith("Import"))
    assert render < imp
    inputs = inputs_of(steps[imp])
    assert inputs["UseDeploymentSettingsFile"] is True
    assert inputs["DeploymentSettingsFile"].endswith("settings.json")
    assert "render-settings" in steps[render]["bash"]


def test_upgrade_mode_imports_as_holding_then_applies_it():
    text = (SRC / "pipelines" / "deploy-steps.yml").read_text(encoding="utf-8")
    assert re.search(r"if eq\(parameters.mode, 'Upgrade'\) \}\}:\s*\n\s+HoldingSolution: true", text)
    assert text.count("PowerPlatformApplySolutionUpgrade@2") == 1
    # the apply step only exists in Upgrade mode
    assert re.search(r"- \$\{\{ if eq\(parameters.mode, 'Upgrade'\) \}\}:\s*\n\s+- task: .*ApplySolutionUpgrade", text)


def test_the_same_package_goes_to_test_then_prod():
    rel = load("release.yml")
    stages = {s["stage"]: s for s in rel["stages"]}
    assert stages["Test"]["dependsOn"] == "Build" and stages["Prod"]["dependsOn"] == "Test"
    envs = [j["environment"] for st in ("Test", "Prod") for j in stages[st]["jobs"]]
    assert envs == ["test", "prod"]
    assert [s["name"] for s in rel["parameters"]] == ["solutionName", "mode"]


def test_no_secrets_or_real_identifiers_in_the_pipelines():
    for f in FILES:
        text = (SRC / "pipelines" / f).read_text(encoding="utf-8")
        assert not re.search(r"(?i)client_?secret|password|\.crm\d*\.dynamics\.com|devladlog", text), f
        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text), f
