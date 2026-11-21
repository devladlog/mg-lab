"""Lints the two pipeline files, and proves the linter catches the mistakes it exists for."""
import copy
import re
from pathlib import Path

import pytest

import pipeline_lint as L
from conftest import PIPELINES, SCRIPTS

RELEASE = PIPELINES / "build-and-release.yml"
EXPORT = PIPELINES / "export-solution-to-git.yml"
TEMPLATE = PIPELINES / "templates" / "deploy-managed.yml"


def test_the_fixture_is_Learns_task_list():
    import json

    data = json.loads((L.FIXTURES / "build-tools-tasks.json").read_text())
    assert data["source"].startswith("https://learn.microsoft.com/power-platform/alm/")
    assert len(data["tasks"]) >= 25
    assert L.INSTALLER in data["tasks"]


def test_build_and_release_passes_every_rule():
    assert L.lint_release(RELEASE, SCRIPTS) == []


def test_export_pipeline_passes_every_rule():
    assert L.lint_export(EXPORT, SCRIPTS) == []


def test_the_deploy_template_is_used_by_both_deploy_stages_with_their_own_target():
    doc = L.load(RELEASE, L.defaults(__import__("yaml").safe_load(RELEASE.read_text())))
    seen = {}
    for stage in doc["stages"][1:]:
        job = stage["jobs"][0]
        step = job["strategy"]["runOnce"]["deploy"]["steps"][0]
        assert step["template"] == "templates/deploy-managed.yml"
        seen[stage["stage"]] = (step["parameters"]["target"], step["parameters"]["serviceConnection"])
    assert seen == {"Test": ("test", "mglab-test"), "Prod": ("prod", "mglab-prod")}


# --- mutations: the linter has to fail on each of these -----------------------------------------

def lint_text(tmp_path, source_file, old, new, fn, extra_templates=True):
    """Copy the pipelines folder, apply one text edit, lint."""
    import shutil

    dst = tmp_path / "pipelines"
    shutil.copytree(PIPELINES, dst)
    target = dst / source_file
    text = target.read_text()
    assert old in text, f"{old!r} not in {source_file}"
    target.write_text(text.replace(old, new, 1))
    return fn(dst / ("build-and-release.yml" if fn is L.lint_release else "export-solution-to-git.yml"), SCRIPTS)


RELEASE_MUTATIONS = [
    ("an input that Learn doesn't list", "build-and-release.yml", "ErrorThreshold: 0", "ErrorThreshold: 0\n              Severity: high", "has no input 'Severity' on Learn"),
    ("an unknown task", "build-and-release.yml", "PowerPlatformChecker@2", "PowerPlatformCheckr@2", "unknown Build Tools task"),
    ("a mixed task version", "templates/deploy-managed.yml", "PowerPlatformWhoAmi@2", "PowerPlatformWhoAmi@1", "unknown Build Tools task"),
    ("no tool installer before the checker", "build-and-release.yml", "PowerPlatformToolInstaller@2", "PowerPlatformWhoAmi@2", "runs before the Power Platform Tool Installer"),
    ("a script that doesn't exist", "build-and-release.yml", "Test-SolutionSource.ps1", "Test-Solutionn.ps1", "does not exist"),
    ("Prod depending on Build, skipping TEST", "build-and-release.yml", "dependsOn: Test", "dependsOn: Build", "Prod must depend on Test"),
    ("deploying for pull requests", "build-and-release.yml", "and(succeeded(), ne(variables['Build.Reason'], 'PullRequest'))", "succeeded()", "never for a pull request"),
    ("PROD using the TEST environment", "build-and-release.yml", "environment: equipmentdesk-prod", "environment: equipmentdesk-test", "Prod job uses environment"),
    ("PROD using the TEST service connection", "build-and-release.yml", "serviceConnection: mglab-prod", "serviceConnection: mglab-test", "Prod uses service connections"),
    ("a service connection nobody created", "build-and-release.yml", "serviceConnection: mglab-prod", "serviceConnection: contoso-prod", "is not one of"),
    ("importing the unmanaged zip", "templates/deploy-managed.yml", "SolutionInputFile: $(managedZip)", "SolutionInputFile: $(Pipeline.Workspace)/drop/solution/EquipmentDesk.zip", "only the managed zip may be deployed"),
    ("importing without the settings file", "templates/deploy-managed.yml", "UseDeploymentSettingsFile: true", "UseDeploymentSettingsFile: false", "does not use a deployment settings file"),
    ("a settings file the resolve step never writes", "templates/deploy-managed.yml", "DeploymentSettingsFile: $(Agent.TempDirectory)/${{ parameters.target }}.settings.json", "DeploymentSettingsFile: $(Build.SourcesDirectory)/settings/x.json", "not the file the resolve step writes"),
    ("overwriting unmanaged customizations", "templates/deploy-managed.yml", "MaxAsyncWaitTime: 60\n      UseDeploymentSettingsFile", "MaxAsyncWaitTime: 60\n      OverwriteUnmanagedCustomizations: true\n      UseDeploymentSettingsFile", "overwrites unmanaged customizations"),
    ("a synchronous import", "templates/deploy-managed.yml", "AsyncOperation: true\n      MaxAsyncWaitTime: 60\n      UseDeploymentSettingsFile", "AsyncOperation: false\n      MaxAsyncWaitTime: 60\n      UseDeploymentSettingsFile", "import is not asynchronous"),
    ("the checker looking at the unmanaged zip", "build-and-release.yml", "*_managed.zip\n              ErrorLevel", "*.zip\n              ErrorLevel", "Checker must analyze the managed zip"),
    ("a checker that doesn't fail the build", "build-and-release.yml", "FailOnPowerAppsCheckerAnalysisError: true", "FailOnPowerAppsCheckerAnalysisError: false", "Checker must fail on analysis errors"),
    ("another checker rule set", "build-and-release.yml", "RuleSet: 0ad12346-e108-40b8-a956-9a8f95ea18c9", "RuleSet: 3a1b2c3d-0000-0000-0000-000000000000", "literal GUID"),
    ("a version that isn't from the build number", "build-and-release.yml", "'$(Build.BuildNumber)'.Split('.')", "'1.2'.Split('.')", "stamped from $(Build.BuildNumber)"),
    ("an environment URL pasted in", "build-and-release.yml", "solutionName: EquipmentDesk", "solutionName: EquipmentDesk\n  orgUrl: https://org123.crm4.dynamics.com", "literal environment URL"),
    ("the deployment as a plain job (no approvals possible)", "build-and-release.yml", "- deployment: deploy_prod", "- job: deploy_prod", "must be a deployment job"),
]


@pytest.mark.parametrize("label, file, old, new, expected", RELEASE_MUTATIONS, ids=[m[0] for m in RELEASE_MUTATIONS])
def test_release_linter_catches(tmp_path, label, file, old, new, expected):
    probs = lint_text(tmp_path, file, old, new, L.lint_release)
    assert any(expected in p for p in probs), probs


EXPORT_MUTATIONS = [
    ("unpacking as Unmanaged", "SolutionType: Both", "SolutionType: Unmanaged", "unpack must use SolutionType Both"),
    ("unpacking straight into the repo", "SolutionTargetFolder: $(Agent.TempDirectory)/unpacked", "SolutionTargetFolder: $(Build.SourcesDirectory)/$(sourceFolder)", "empty temp folder"),
    ("a managed zip that isn't next to the unmanaged one by name", "$(Agent.TempDirectory)/export/$(solutionName)_managed.zip", "$(Agent.TempDirectory)/export/$(solutionName)-managed.zip", "managed zip must be the unmanaged name plus _managed"),
    ("pushing to main", 'git push origin "$branch"', "git push origin HEAD:main", "never to main"),
    ("no persisted credentials", "persistCredentials: true", "persistCredentials: false", "persistCredentials"),
    ("an export that is triggered on every push", "trigger: none", "trigger:\n  branches:\n    include: [main]", "trigger must be none"),
    ("skipping the mirror step", "Sync-SolutionSource.ps1", "Test-SolutionSource.ps1", "must go through Sync-SolutionSource.ps1"),
]


@pytest.mark.parametrize("label, old, new, expected", EXPORT_MUTATIONS, ids=[m[0] for m in EXPORT_MUTATIONS])
def test_export_linter_catches(tmp_path, label, old, new, expected):
    probs = lint_text(tmp_path, "export-solution-to-git.yml", old, new, L.lint_export)
    assert any(expected in p for p in probs), probs


def test_a_script_that_needs_pac_before_the_installer_is_caught(tmp_path):
    p = tmp_path / "p.yml"
    p.write_text(
        "trigger: none\nsteps:\n"
        "  - pwsh: ./scripts/Invoke-SolutionPack.ps1 -SourcePath x -OutputDirectory y\n"
        "  - task: microsoft-IsvExpTools.PowerPlatform-BuildTools.tool-installer.PowerPlatformToolInstaller@2\n"
    )
    probs = L.lint(p, SCRIPTS)
    assert any("needs pac but runs before the Tool Installer" in x for x in probs), probs
