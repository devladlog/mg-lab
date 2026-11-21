"""Policy-as-tests for the pipeline files. If someone loosens a guard, CI fails here, in review, before it runs."""
import json
import re
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

APP = Path(__file__).resolve().parents[2]
WORKFLOW = APP / ".github" / "workflows" / "ci.yml"
SHA = re.compile(r"^[0-9a-f]{40}$")


@pytest.fixture(scope="module")
def wf():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def all_steps(wf):
    for job_name, job in wf["jobs"].items():
        for step in job.get("steps", []):
            yield job_name, step


def test_yaml_on_key_parses_as_boolean_true(wf):
    # YAML 1.1 reads the bare key "on" as True. The tests below read triggers through this key.
    assert True in wf and "on" not in wf


def test_every_action_is_pinned_to_a_full_commit_sha(wf):
    uses = [(j, s["uses"]) for j, s in all_steps(wf) if "uses" in s]
    assert uses, "workflow has no actions?"
    bad = [(j, u) for j, u in uses if not SHA.match(u.split("@", 1)[1])]
    assert not bad, f"actions not pinned to a 40-character SHA: {bad}"


def test_no_local_or_docker_action_bypasses_pinning(wf):
    for _, step in all_steps(wf):
        if "uses" in step:
            assert "@" in step["uses"] and not step["uses"].startswith("docker://")


def test_workflow_token_starts_with_no_permissions(wf):
    assert wf["permissions"] == {}


def test_every_job_declares_its_own_permissions_and_never_write_all(wf):
    for name, job in wf["jobs"].items():
        perms = job.get("permissions")
        assert isinstance(perms, dict) and perms, f"job {name} has no explicit permissions"
        assert perms.get("contents") in (None, "read"), f"job {name} can write repository contents"


def test_only_the_deploy_job_can_request_an_oidc_token(wf):
    holders = [n for n, j in wf["jobs"].items() if "id-token" in j["permissions"]]
    assert holders == ["publish-and-deploy"]


def test_no_pull_request_target_or_workflow_run_trigger(wf):
    triggers = wf[True]
    assert "pull_request_target" not in triggers and "workflow_run" not in triggers


def test_checkout_never_persists_credentials(wf):
    checkouts = [s for _, s in all_steps(wf) if s.get("uses", "").startswith("actions/checkout@")]
    assert checkouts
    assert all(s.get("with", {}).get("persist-credentials") is False for s in checkouts)


def test_azure_login_uses_oidc_ids_only_no_stored_credential(wf):
    logins = [s for _, s in all_steps(wf) if s.get("uses", "").startswith("azure/login@")]
    assert len(logins) == 1
    inputs = set(logins[0]["with"])
    assert inputs == {"client-id", "tenant-id", "subscription-id"}
    assert "creds" not in inputs


def test_azure_login_job_is_gated_by_a_protected_environment_and_main_only(wf):
    job = wf["jobs"]["publish-and-deploy"]
    assert job["environment"] == "prod-lab"
    assert "refs/heads/main" in job["if"]
    assert "pull_request" in job["if"]


def test_no_secret_is_interpolated_into_a_run_script(wf):
    for name, step in all_steps(wf):
        if "run" in step:
            assert "${{ secrets." not in step["run"], f"secret expanded inline in {name}"
            assert "${{ github.event" not in step["run"], f"event data expanded inline in {name}"


def test_scan_happens_before_any_push(wf):
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.index("trivy-action") < text.index("docker push")
    assert text.index("vuln_gate.py") < text.index("docker push")
    assert wf["jobs"]["publish-and-deploy"]["needs"] == ["container", "codeql"]


def test_dockerfile_pins_every_base_image_by_digest_and_runs_non_root():
    lines = (APP / "Dockerfile").read_text(encoding="utf-8").splitlines()
    froms = [l for l in lines if l.startswith("FROM ")]
    assert len(froms) == 2
    assert all(re.search(r"@sha256:[0-9a-f]{64}", l) for l in froms)
    users = [l.split()[1] for l in lines if l.startswith("USER ")]
    assert users and users[-1].isdigit() and users[-1] != "0"


def test_dependabot_covers_every_ecosystem_the_repo_uses():
    cfg = yaml.safe_load((APP / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    ecosystems = {u["package-ecosystem"] for u in cfg["updates"]}
    assert ecosystems == {"nuget", "docker", "github-actions", "pip"}
    assert all(u["cooldown"]["default-days"] >= 7 for u in cfg["updates"])


@pytest.fixture(scope="module")
def bicep_json():
    tmp = Path(tempfile.mkdtemp()) / "main.json"
    try:
        subprocess.run(["bicep", "build", str(APP / "infra" / "main.bicep"), "--outfile", str(tmp)],
                       check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("bicep CLI not available")
    return json.loads(tmp.read_text(encoding="utf-8"))


def resources_of(doc, rtype):
    return [r for r in doc["resources"] if r["type"] == rtype]


def test_bicep_registry_has_admin_user_disabled(bicep_json):
    (acr,) = resources_of(bicep_json, "Microsoft.ContainerRegistry/registries")
    assert acr["properties"]["adminUserEnabled"] is False


def test_bicep_federated_subject_is_restricted_to_the_environment(bicep_json):
    (fic,) = resources_of(bicep_json, "Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials")
    p = fic["properties"]
    assert p["issuer"] == "https://token.actions.githubusercontent.com"
    assert p["audiences"] == ["api://AzureADTokenExchange"]
    # the subject is built from parameters, so assert on the expression text: ...:environment:<param>
    assert ":environment:" in p["subject"]
    assert "ref:refs/heads" not in p["subject"] and "pull_request" not in p["subject"]


def test_bicep_deploy_identity_is_contributor_on_the_app_only(bicep_json):
    assigns = resources_of(bicep_json, "Microsoft.Authorization/roleAssignments")
    contributor = [a for a in assigns if "contributor" in a["properties"]["roleDefinitionId"]]
    assert len(contributor) == 1
    assert "containerApps" in contributor[0]["scope"]
    assert "resourceGroup()" not in contributor[0]["scope"]
