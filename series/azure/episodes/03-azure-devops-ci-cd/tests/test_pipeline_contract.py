"""The pipeline contract: the real pipeline passes, and each rule catches the mistake it exists for."""
import shutil

import pytest
import yaml

from conftest import EP
from pipeline_contract import check, expand
from pipeline_contract.contract import Report

PIPE = EP / "pipelines"


@pytest.fixture
def copy(tmp_path):
    """A writable copy of pipelines/ plus helpers to edit one file."""
    dst = tmp_path / "pipelines"
    shutil.copytree(PIPE, dst)

    def edit(rel, old, new):
        p = dst / rel
        text = p.read_text()
        assert old in text, f"{old!r} not in {rel}"
        p.write_text(text.replace(old, new, 1))
    return dst, edit


def rules(report):
    return sorted({p.split()[0] for p in report.problems})


def test_real_pipeline_has_no_problems():
    r = check(PIPE / "azure-pipelines.yml", {"contoso-prod"})
    assert r.problems == []
    assert [s["stage"] for s in r.stages] == ["ci", "lab", "prod_plan", "prod"]


def test_expansion_keeps_types_and_fills_values():
    root = expand(PIPE / "azure-pipelines.yml", Report())
    prod = root["stages"][3]
    assert prod["dependsOn"] == ["prod_plan"]                       # list stays a list
    job = prod["jobs"][0]
    assert job["environment"] == "contoso-prod"
    task = job["strategy"]["runOnce"]["deploy"]["steps"][1]
    assert task["inputs"]["azureSubscription"] == "sc-contoso-prod"
    assert "--accept-protected False" in task["inputs"]["arguments"]  # boolean default rendered like Azure Pipelines


def test_graph_lists_each_stage():
    lines = check(PIPE / "azure-pipelines.yml", {"contoso-prod"}).graph()
    assert lines[2].startswith("prod_plan") and "(plan)" in lines[2]
    assert "deploy -> contoso-prod" in lines[3]


def test_T1_missing_required_parameter(copy):
    d, edit = copy
    edit("azure-pipelines.yml", "      resourceGroup: rg-contoso-lab\n", "")
    assert rules(check(d / "azure-pipelines.yml", set())) == ["T1"]


def test_T1_unknown_parameter_and_missing_template(copy):
    d, edit = copy
    edit("azure-pipelines.yml", "      environment: contoso-lab\n", "      environment: contoso-lab\n      enviroment: x\n")
    edit("azure-pipelines.yml", "templates/plan-stage.yml", "templates/plan.yml")
    r = check(d / "azure-pipelines.yml", set())
    assert any("'enviroment' is passed but not declared" in p for p in r.problems)
    assert any("template not found: templates/plan.yml" in p for p in r.problems)


def test_T2_conditional_expressions_are_refused(copy):
    d, edit = copy
    edit("templates/ci-stage.yml", "          - checkout: self\n",
         "          - ${{ if eq(parameters.x, true) }}:\n            - checkout: self\n")
    assert "T2" in rules(check(d / "azure-pipelines.yml", set()))


def test_S1_dependency_on_a_later_stage(copy):
    d, edit = copy
    edit("azure-pipelines.yml", "dependsOn: [ci]", "dependsOn: [prod]")
    assert rules(check(d / "azure-pipelines.yml", set())) == ["S1"]


def test_S2_deploy_from_any_branch(copy):
    d, edit = copy
    edit("templates/deploy-stage.yml",
         "condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))", "condition: succeeded()")
    r = check(d / "azure-pipelines.yml", set())
    assert rules(r) == ["S2"] and len(r.problems) == 2            # lab and prod


def test_S3_prod_without_a_plan_stage(copy):
    d, edit = copy
    edit("azure-pipelines.yml", "dependsOn: [prod_plan]", "dependsOn: [lab]")
    assert rules(check(d / "azure-pipelines.yml", {"contoso-prod"})) == ["S3"]


def test_S3_plan_with_another_connection_does_not_count(copy):
    d, edit = copy
    edit("azure-pipelines.yml", "serviceConnection: sc-contoso-prod         # no checks",
         "serviceConnection: sc-contoso-lab         # no checks")
    assert rules(check(d / "azure-pipelines.yml", {"contoso-prod"})) == ["S3"]


def test_J1_deployment_job_without_checkout(copy):
    d, edit = copy
    edit("templates/deploy-stage.yml", "                - checkout: self\n                  fetchDepth: 1\n", "")
    assert rules(check(d / "azure-pipelines.yml", set())) == ["J1"]


def test_K1_service_connection_from_a_runtime_variable(copy):
    d, edit = copy
    edit("templates/plan-stage.yml", "azureSubscription: ${{ parameters.serviceConnection }}",
         "azureSubscription: $(serviceConnection)")
    assert rules(check(d / "azure-pipelines.yml", set())) == ["K1"]


def test_K2_unpinned_task(copy):
    d, edit = copy
    edit("templates/ci-stage.yml", "task: UseDotNet@2", "task: UseDotNet")
    assert rules(check(d / "azure-pipelines.yml", set())) == ["K2"]


def test_R1_yaml_pr_trigger(copy):
    d, edit = copy
    edit("azure-pipelines.yml", "pr: none", "pr: [main]")
    assert rules(check(d / "azure-pipelines.yml", set())) == ["R1"]


def test_X1_secret_in_a_file(copy):
    d, edit = copy
    fake = "DefaultEndpointsProtocol=https;AccountName=x;AccountKey=" + "A" * 40
    edit("azure-pipelines.yml", "variables:\n", f"variables:\n  conn: '{fake}'\n")
    assert rules(check(d / "azure-pipelines.yml", set())) == ["X1"]


def test_every_yaml_file_parses():
    for f in PIPE.rglob("*.yml"):
        assert isinstance(yaml.safe_load(f.read_text()), dict), f
