import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import ROOT
from slabreach import cli

AML = ROOT / "aml"


# ---- the YAML is valid for the Azure ML CLI v2 / SDK v2 schemas (offline validation by the SDK) ------------------
def test_yaml_files_load_with_the_azure_ml_sdk():
    pytest.importorskip("azure.ai.ml")
    from azure.ai.ml import load_component, load_job, load_online_deployment, load_online_endpoint
    for c in ("prepare", "train", "evaluate"):
        comp = load_component(AML / "components" / f"{c}.yml")
        assert comp.name == f"slabreach_{c}" and comp.version == "1"
    job = load_job(AML / "pipeline.yml")
    assert list(job.jobs) == ["prepare", "train", "evaluate"]
    assert set(job.outputs) == {"model", "decision"}
    assert load_online_endpoint(AML / "endpoint.yml").auth_mode == "aad_token"       # no keys
    d = load_online_deployment(AML / "deployment.yml")
    assert d.instance_type == "Standard_DS3_v2" and "sla-breach" in str(d.model)
    assert not getattr(d, "scoring_script", None) and not getattr(d, "code_configuration", None)   # MLflow: no scoring script


def test_a_broken_pipeline_yaml_is_caught_by_that_validation(tmp_path):
    pytest.importorskip("azure.ai.ml")
    from azure.ai.ml import load_job
    bad = (AML / "pipeline.yml").read_text().replace("baseline_auc: 0 ", "baseline_auc: {type: number} ")
    (tmp_path / "components").mkdir()
    for f in (AML / "components").glob("*.yml"):
        shutil.copy(f, tmp_path / "components" / f.name)
    (tmp_path / "pipeline.yml").write_text(bad)
    with pytest.raises(Exception, match="baseline_auc"):
        load_job(tmp_path / "pipeline.yml")


# ---- run the pipeline LOCALLY, using the exact commands written in the component YAML -------------------------------
def _resolve(text, ctx):
    return re.sub(r"\$\{\{\s*([^}]+?)\s*\}\}", lambda m: str(ctx[m.group(1)]), text)


def test_the_pipeline_commands_in_the_yaml_run_end_to_end(tmp_path):
    raw = tmp_path / "raw"
    assert cli.main(["generate", "--out", str(raw), "--seed", "2"]) == 0
    pipe = yaml.safe_load((AML / "pipeline.yml").read_text())
    outputs = {}
    env = {**os.environ, "MLFLOW_TRACKING_URI": (tmp_path / "mlruns").as_uri()}
    codes = {}
    for name, job in pipe["jobs"].items():
        comp = yaml.safe_load((AML / job["component"]).read_text())
        ctx = {}
        for k, spec in comp["inputs"].items():
            v = job.get("inputs", {}).get(k, spec.get("default"))
            if isinstance(v, str) and v.startswith("${{parent.inputs."):
                src = v[len("${{parent.inputs."):-2]
                pv = pipe["inputs"][src]
                v = raw if isinstance(pv, dict) else pv
            elif isinstance(v, str) and v.startswith("${{parent.jobs."):
                _, _, j, _, o = v[2:-2].split(".")
                v = outputs[(j, o)]
            ctx[f"inputs.{k}"] = v
        for k in comp["outputs"]:
            out = tmp_path / name / k
            out.mkdir(parents=True, exist_ok=True)
            outputs[(name, k)] = out
            ctx[f"outputs.{k}"] = out
        cmd = _resolve(" ".join(comp["command"].split()), ctx).replace("python ", f"{sys.executable} ", 1)
        code_dir = (AML / "components" / comp["code"]).resolve()
        r = subprocess.run(cmd, shell=True, cwd=code_dir, env=env, capture_output=True, text=True)
        codes[name] = r.returncode
        assert r.returncode == 0, f"{name}: {r.stdout[-400:]} {r.stderr[-800:]}"
    assert (outputs[("prepare", "train")] / "tickets.csv").exists()
    assert (outputs[("train", "model_out")] / "MLmodel").exists()
    assert json.loads((outputs[("evaluate", "decision")] / "decision.json").read_text())["promote"] is True


def test_components_mount_the_same_code_folder_and_environment():
    envs = set()
    for f in (AML / "components").glob("*.yml"):
        c = yaml.safe_load(f.read_text())
        assert c["code"] == "../../src" and c["environment"]["conda_file"] == "../environment/conda.yml"
        envs.add(c["environment"]["image"])
    assert len(envs) == 1
    conda = yaml.safe_load((AML / "environment" / "conda.yml").read_text())
    pins = " ".join(conda["dependencies"][-1]["pip"])
    for pkg in ("mlflow-skinny==", "scikit-learn==", "pandas==", "cloudpickle=="):
        assert pkg in pins


# ---- the CI workflow ---------------------------------------------------------------------------------------------
def test_workflow_uses_oidc_and_no_stored_credentials():
    text = (ROOT / "ci" / "mlops.yml").read_text()
    wf = yaml.safe_load(text)
    assert wf["permissions"]["id-token"] == "write"
    steps = [s for j in wf["jobs"].values() for s in j["steps"]]
    login = next(s for s in steps if s.get("uses", "").startswith("azure/login@"))
    assert set(login["with"]) == {"client-id", "tenant-id", "subscription-id"}
    assert "creds:" not in text and "AZURE_CREDENTIALS" not in text and "client-secret" not in text
    assert wf["jobs"]["train"]["needs"] == "test" and "workflow_dispatch" in str(wf["jobs"]["train"]["if"])   # training never runs on a pull request


# ---- the scripts, against a stand-in az --------------------------------------------------------------------------
@pytest.fixture
def sh(tmp_path):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    fake = bin_ / "az"
    fake.write_text(f"#!/bin/sh\nexec {sys.executable} {ROOT / 'tests' / 'fake_az.py'} \"$@\"\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "az.log"
    decision = tmp_path / "decision.json"
    decision.write_text(json.dumps({"promote": True, "metrics": {"auc": 0.7712}}))

    def run(script, *args, **env):
        e = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "FAKE_AZ_LOG": str(log), "FAKE_DECISION": str(decision),
             "RG": "rg-x", "WS": "ws-x", "ENDPOINT_NAME": "ep-x", "POLL_SECONDS": "0", "OUT_DIR": str(tmp_path / "out")}
        e.update({k: str(v) for k, v in env.items()})
        r = subprocess.run(["bash", str(ROOT / "scripts" / script), *args], cwd=ROOT, env=e, capture_output=True, text=True)
        return r, (log.read_text().splitlines() if log.exists() else [])
    run.decision, run.tmp = decision, tmp_path
    return run


def test_train_and_register_first_run_registers_with_the_auc_tag(sh):
    r, calls = sh("train-and-register.sh")
    assert r.returncode == 0, r.stderr
    assert any("job create -f aml/pipeline.yml --set inputs.baseline_auc=0" in c for c in calls)
    create = next(c for c in calls if c.startswith("ml model create"))
    assert "--path azureml://jobs/job-123/outputs/model" in create and "tags.test_auc=0.7712" in create and "--type mlflow_model" in create
    assert (sh.tmp / "out" / "model_version.txt").read_text().strip() == "5"


def test_train_and_register_passes_the_production_auc_as_the_baseline(sh):
    r, calls = sh("train-and-register.sh", FAKE_PROD_AUC="0.7801")
    assert r.returncode == 0 and any("inputs.baseline_auc=0.7801" in c for c in calls)


@pytest.mark.parametrize("status", ["Failed", "Canceled"])
def test_a_failed_job_registers_nothing(sh, status):
    r, calls = sh("train-and-register.sh", FAKE_STATUS=status)
    assert r.returncode == 1 and "nothing is registered" in r.stdout
    assert not any(c.startswith("ml model create") for c in calls)


def test_a_completed_job_whose_decision_says_no_registers_nothing(sh):
    sh.decision.write_text(json.dumps({"promote": False, "metrics": {"auc": 0.6}}))
    r, calls = sh("train-and-register.sh")
    assert r.returncode != 0 and not any(c.startswith("ml model create") for c in calls)


def test_deploy_creates_the_endpoint_and_blue_on_the_first_version(sh):
    r, calls = sh("deploy-canary.sh", "1")
    assert r.returncode == 0, r.stderr
    assert any(c.startswith("ml online-endpoint create") and "aml/endpoint.yml" in c for c in calls)
    blue = next(c for c in calls if c.startswith("ml online-deployment create"))
    assert "--all-traffic" in blue and "model=azureml:sla-breach:1" in blue and "name=blue" in blue


@pytest.mark.parametrize("live,new", [("blue", "green"), ("green", "blue")])
def test_later_versions_go_to_the_other_colour_with_a_smoke_test_then_ten_percent(sh, live, new):
    r, calls = sh("deploy-canary.sh", "2", FAKE_EP_EXISTS="1", FAKE_TRAFFIC=json.dumps({live: 100}))
    assert r.returncode == 0, r.stderr
    create = next(c for c in calls if c.startswith("ml online-deployment create"))
    assert f"--name {new}" in create and "--all-traffic" not in create and "model=azureml:sla-breach:2" in create
    order = [i for i, c in enumerate(calls) if c.startswith(("ml online-deployment create", "ml online-endpoint invoke", "ml online-endpoint update"))]
    assert order == sorted(order)
    assert any(f"online-endpoint invoke" in c and f"--deployment-name {new}" in c and "sample-request.json" in c for c in calls)
    assert any(f'--traffic {live}=90 {new}=10' in c for c in calls)


def test_promote_moves_all_traffic_then_deletes_the_old_deployment(sh):
    r, calls = sh("promote.sh", "green", "blue")
    assert r.returncode == 0
    assert "--traffic blue=0 green=100" in calls[0] and calls[1].startswith("ml online-deployment delete --name blue")


def test_scripts_refuse_to_run_without_their_settings(sh):
    r, _ = sh("train-and-register.sh", RG="")
    assert r.returncode != 0 and "set RG" in r.stderr


# ---- infrastructure ------------------------------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("bicep"), reason="Bicep CLI not installed")
def test_bicep_workspace_with_a_cluster_that_scales_to_zero():
    t = json.loads(subprocess.run(["bicep", "build", str(ROOT / "infra" / "main.bicep"), "--stdout"], capture_output=True, text=True, check=True).stdout)
    res = list(t["resources"].values()) if isinstance(t["resources"], dict) else t["resources"]
    ws = next(r for r in res if r["type"] == "Microsoft.MachineLearningServices/workspaces")
    assert ws["identity"]["type"] == "SystemAssigned"
    cl = next(r for r in res if r["type"].endswith("/computes"))
    s = cl["properties"]["properties"]["scaleSettings"]
    assert s["minNodeCount"] == 0 and s["nodeIdleTimeBeforeScaleDown"] == "PT2M"
    assert t["variables"]["azureMlDataScientist"] == "f6c7c914-8db3-469d-8ca1-694a8f32e121"
