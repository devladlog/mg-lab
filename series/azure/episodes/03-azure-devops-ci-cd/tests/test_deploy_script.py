"""deploy.sh end to end with a fake `az` and `curl` on PATH: the order of calls and what the gate stops."""
import os
import subprocess

import pytest

from conftest import EP, FIXTURES

SCRIPT = EP / "pipelines" / "scripts" / "deploy.sh"
PARAMS = EP.parent / "02-cloud-architecture" / "infra" / "env" / "lab.bicepparam"
POLICY = EP / "pipelines" / "gate-policy.json"


@pytest.fixture
def run(tmp_path):
    log = tmp_path / "calls.log"

    def go(fixture, *extra, fail_whatif=False):
        env = dict(os.environ, PATH=f"{EP / 'tests' / 'fakes'}:{os.environ['PATH']}", FAKE_LOG=str(log),
                   FAKE_WHATIF=str(FIXTURES / f"whatif-{fixture}.json"), BUILD_BUILDID="42")
        if fail_whatif:
            env["FAKE_WHATIF_FAIL"] = "1"
        p = subprocess.run(["bash", str(SCRIPT), "--resource-group", "rg-contoso-lab", "--parameters", str(PARAMS),
                            "--policy", str(POLICY), *extra], env=env, capture_output=True, text=True)
        calls = log.read_text().splitlines() if log.exists() else []
        return p, calls
    return go


def verbs(calls):
    return [" ".join(c.split()[:4]) if c.startswith("az") else "curl" for c in calls]


def test_clean_change_deploys_in_order(run, tmp_path):
    p, calls = run("tags-only", "--package", "probe.zip", "--summary", str(tmp_path / "s.md"))
    assert p.returncode == 0, p.stderr
    assert verbs(calls) == ["az deployment group what-if", "az deployment group create",
                            "az deployment group show", "az webapp deploy --resource-group", "curl"]
    assert "--name workload-42" in calls[1]
    assert "--no-pretty-print" in calls[0] and "--template-file" not in calls[0]
    assert "## What-if gate: rg-contoso-lab: GO" in (tmp_path / "s.md").read_text()


def test_protected_drift_stops_before_deployment(run):
    p, calls = run("drift-public-access", "--package", "probe.zip")
    assert p.returncode == 1
    assert verbs(calls) == ["az deployment group what-if"]
    assert "nothing was deployed" in p.stderr


def test_accept_protected_true_lets_the_run_continue(run):
    p, calls = run("drift-public-access", "--package", "probe.zip", "--accept-protected", "True")
    assert p.returncode == 0, p.stderr
    assert "az deployment group create" in verbs(calls)


def test_plan_only_saves_whatif_and_never_deploys(run, tmp_path):
    out = tmp_path / "whatif" / "whatif.json"
    p, calls = run("first-deploy", "--plan-only", "--save-whatif", str(out), "--azure-devops",
                   "--summary", str(tmp_path / "whatif" / "summary.md"))
    assert p.returncode == 0, p.stderr
    assert verbs(calls) == ["az deployment group what-if"]
    assert out.read_text() == (FIXTURES / "whatif-first-deploy.json").read_text()
    assert "##vso[task.uploadsummary]" in p.stdout


def test_unusable_whatif_and_failing_az(run):
    p, _ = run("failed", "--package", "probe.zip")
    assert p.returncode == 2
    p, calls = run("tags-only", "--package", "probe.zip", fail_whatif=True)
    assert p.returncode == 1                                  # az's own exit code, set -e stops the script
    assert verbs(calls) == ["az deployment group what-if"] * 2  # one per run, nothing after the failure


def test_usage_errors(run):
    p, calls = run("tags-only")                               # no --package and not --plan-only
    assert p.returncode == 2 and calls == []
    assert "deploy.sh --resource-group" in p.stderr


def test_scripts_parse():
    for s in (EP / "pipelines" / "scripts").glob("*.sh"):
        subprocess.run(["bash", "-n", str(s)], check=True)
