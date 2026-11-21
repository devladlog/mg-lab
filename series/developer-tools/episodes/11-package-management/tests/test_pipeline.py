"""azure-pipelines.yml: its structure, and its own script steps executed for real (except the push, see below)."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from conftest import APP, needs_dotnet, run

PIPELINE = yaml.safe_load((APP / "azure-pipelines.yml").read_text())
JOBS = {j["job"]: j for j in PIPELINE["jobs"]}


def step(job: str, name: str) -> dict:
    return next(s for s in JOBS[job]["steps"] if s.get("displayName", "").startswith(name))


def test_triggers_and_schedule():
    assert PIPELINE["trigger"]["branches"]["include"] == ["main"]
    assert "pr" not in PIPELINE                                  # Azure Repos: build validation policy, not `pr:`
    [schedule] = PIPELINE["schedules"]
    assert schedule["cron"] == "0 6 * * 1" and schedule["always"] is True
    assert PIPELINE["pool"] == {"vmImage": "ubuntu-latest"}


def test_tasks_are_the_documented_ones_with_documented_inputs():
    tasks = [s for j in PIPELINE["jobs"] for s in j["steps"] if "task" in s]
    assert {t["task"] for t in tasks} == {"UseDotNet@2", "NuGetAuthenticate@1"}
    for t in tasks:
        if t["task"] == "UseDotNet@2":
            assert t["inputs"] == {"packageType": "sdk", "useGlobalJson": True}
        else:
            assert "inputs" not in t                                     # same organization: no service connection
    publish = step("build", "Keep the package")
    assert publish["publish"] == "$(Build.ArtifactStagingDirectory)/nupkg" and publish["artifact"] == "nupkg"


def test_the_order_of_the_build_job():
    names = [s["displayName"] for s in JOBS["build"]["steps"]]
    assert names == ["Install the SDK from global.json", "Restore (locked)", "Build", "Test", "Package audit",
                     "Pack Contoso.Orders.Contracts", "Keep the package with the run",
                     "Authenticate to Azure Artifacts", "Push to the feed"]
    assert step("build", "Restore")["script"] == "dotnet restore --locked-mode"
    assert "pkg_audit.py --format azure --min-severity critical" in step("build", "Package audit")["script"]


def test_authenticate_and_push_only_run_outside_pull_requests():
    for name in ("Authenticate", "Push"):
        assert step("build", name)["condition"] == "and(succeeded(), ne(variables['Build.Reason'], 'PullRequest'))"


def test_push_uses_a_dummy_api_key_and_skip_duplicate_against_the_same_projects_feed():
    script = step("build", "Push")["bash"]
    assert "--api-key az --skip-duplicate" in script
    assert "https://pkgs.dev.azure.com/${org}/${SYSTEM_TEAMPROJECT}/_packaging/${FEED_NAME}/nuget/v3/index.json" in script
    assert "$(" not in script                                    # no macro syntax inside bash: env vars only
    assert PIPELINE["variables"]["feedName"] == "contoso-packages"


def test_audit_job_is_independent_and_turns_audit_warnings_into_errors():
    assert JOBS["audit"]["dependsOn"] == []
    assert step("audit", "Restore with audit")["script"] == "dotnet restore -p:AuditPipeline=true"


# --- run the scripts ----------------------------------------------------------------------------------------------

def run_bash(script: str, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(["bash", "-c", script], cwd=cwd, env={**os.environ, **env}, capture_output=True, text=True, check=False)
    proc.output = proc.stdout + proc.stderr  # type: ignore[attr-defined]
    return proc


@needs_dotnet
@pytest.mark.parametrize(("branch", "build_id", "expected"), [
    ("refs/heads/main", "57", "Contoso.Orders.Contracts.1.0.0.nupkg"),
    ("refs/heads/feature/csv-export", "58", "Contoso.Orders.Contracts.1.0.0-ci.58.nupkg"),
])
def test_pack_step_makes_a_release_only_on_main(app, dotnet_env, tmp_path, branch, build_id, expected):
    run(["dotnet", "restore", "src/Contoso.Orders.Contracts"], app, dotnet_env, check=True)
    staging = tmp_path / "staging"
    proc = run_bash(step("build", "Pack Contoso")["bash"], app, {**dotnet_env, "BUILD_SOURCEBRANCH": branch, "BUILD_BUILDID": build_id,
                                                        "BUILD_ARTIFACTSTAGINGDIRECTORY": str(staging)})
    assert proc.returncode == 0, proc.output
    assert [p.name for p in (staging / "nupkg").glob("*.nupkg")] == [expected]


def test_push_step_builds_the_feed_url_from_the_run_and_calls_dotnet_nuget_push(tmp_path):
    """The only stand-in in this file: a `dotnet` shim that records its arguments, because a test can't sign in to
    Azure Artifacts. The real push is recorded in demo.md."""
    shim = tmp_path / "bin"
    shim.mkdir()
    log = tmp_path / "calls.txt"
    (shim / "dotnet").write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{log}"\n')
    (shim / "dotnet").chmod((shim / "dotnet").stat().st_mode | stat.S_IEXEC)
    staging = tmp_path / "staging"
    (staging / "nupkg").mkdir(parents=True)
    (staging / "nupkg" / "Contoso.Orders.Contracts.1.0.0.nupkg").write_bytes(b"x")
    env = {"PATH": f"{shim}:{os.environ['PATH']}", "SYSTEM_COLLECTIONURI": "https://dev.azure.com/contoso/",
           "SYSTEM_TEAMPROJECT": "orders", "FEED_NAME": "contoso-packages", "BUILD_ARTIFACTSTAGINGDIRECTORY": str(staging)}
    proc = run_bash(step("build", "Push")["bash"], tmp_path, env)
    assert proc.returncode == 0, proc.output
    assert log.read_text().strip() == (
        f"nuget push {staging}/nupkg/Contoso.Orders.Contracts.1.0.0.nupkg "
        "--source https://pkgs.dev.azure.com/contoso/orders/_packaging/contoso-packages/nuget/v3/index.json "
        "--api-key az --skip-duplicate")


@needs_dotnet
@pytest.mark.skipif(shutil.which("python3") is None, reason="python3 needed")
def test_python_step_installs_only_hashed_requirements_and_audits_them(app):
    script = step("audit", "Python packages")["bash"]
    proc = run_bash(script, app, {})
    assert proc.returncode == 0, proc.output
    assert "No known vulnerabilities found" in proc.output
    assert (app / ".venv/bin/ruff").exists()
    ruff = subprocess.run([str(app / ".venv/bin/ruff"), "--version"], capture_output=True, text=True, check=True)
    assert ruff.stdout.strip() == "ruff 0.16.9"


def test_this_file_runs_with_the_interpreter_that_runs_the_tests():
    assert sys.version_info >= (3, 10)
