"""infra/main.bicep, compiled with the real Bicep CLI and checked as ARM JSON (nothing is deployed here)."""
from __future__ import annotations

import json
import re
import subprocess

import pytest

from conftest import APP, needs_bicep

pytestmark = needs_bicep
BICEP = APP / "infra" / "main.bicep"


@pytest.fixture(scope="module")
def arm(tmp_path_factory):
    out = tmp_path_factory.mktemp("bicep") / "main.json"
    subprocess.run(["bicep", "build", str(BICEP), "--outfile", str(out)], check=True, capture_output=True, text=True)
    return json.loads(out.read_text())


def res(arm, type_):
    found = [r for r in arm["resources"].values()] if isinstance(arm["resources"], dict) else arm["resources"]
    return [r for r in found if r["type"] == type_]


def test_lint_is_clean():
    r = subprocess.run(["bicep", "lint", str(BICEP)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "" and "Warning" not in r.stderr, r.stdout + r.stderr


def test_federated_credential_trusts_github_with_the_exact_subject(arm):
    [fic] = res(arm, "Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials")
    p = fic["properties"]
    assert p["issuer"] == "https://token.actions.githubusercontent.com"
    assert p["audiences"] == ["api://AzureADTokenExchange"]          # the azure/login default audience
    assert p["subject"] == "[parameters('githubSubject')]"
    assert "*" not in json.dumps(p)                                    # wildcards aren't supported anyway


def test_deployer_gets_website_contributor_on_this_resource_group_only(arm):
    [ra] = res(arm, "Microsoft.Authorization/roleAssignments")
    assert ra["properties"]["roleDefinitionId"] == "[variables('websiteContributor')]"
    assert "de139f84-1756-47ae-9be6-808fbbe84772" in arm["variables"]["websiteContributor"]   # Website Contributor
    assert "scope" not in ra                                            # resource group of the deployment
    assert ra["properties"]["principalType"] == "ServicePrincipal"


def test_site_matches_the_image(arm):
    [site] = res(arm, "Microsoft.Web/sites")
    cfg = site["properties"]["siteConfig"]
    settings = {s["name"]: s["value"] for s in cfg["appSettings"]}
    expose = re.search(r"^EXPOSE (\d+)", (APP / "Dockerfile").read_text(), re.M).group(1)
    assert settings["WEBSITES_PORT"] == expose == "8080"
    assert cfg["healthCheckPath"] == "/healthz"
    assert 'app.MapGet("/healthz"' in (APP / "src" / "Contoso.Orders.Api" / "Program.cs").read_text()
    assert cfg["linuxFxVersion"].startswith("[format('DOCKER|{0}'")


def test_site_is_locked_down(arm):
    [site] = res(arm, "Microsoft.Web/sites")
    assert site["properties"]["httpsOnly"] is True
    cfg = site["properties"]["siteConfig"]
    assert cfg["ftpsState"] == "Disabled" and cfg["minTlsVersion"] == "1.2"
    policies = res(arm, "Microsoft.Web/sites/basicPublishingCredentialsPolicies")
    assert sorted(re.search(r"'(\w+)'\)\]$", p["name"]).group(1) for p in policies) == ["ftp", "scm"]
    assert all(p["properties"]["allow"] is False for p in policies)


def test_outputs_are_identifiers_not_secrets(arm):
    assert set(arm["outputs"]) == {"AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID",
                                   "AZURE_WEBAPP_NAME", "AZURE_RESOURCE_GROUP", "url"}
    assert all(o["type"] == "string" for o in arm["outputs"].values())
    assert not re.search(r"(?i)listKeys|publishingcredentials|password", json.dumps(arm["outputs"]))


def test_workflow_reads_the_names_bicep_outputs():
    wf = (APP / ".github" / "workflows" / "ci-cd.yml").read_text()
    for name in ("AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID"):
        assert f"secrets.{name}" in wf
    for name in ("AZURE_WEBAPP_NAME", "AZURE_RESOURCE_GROUP"):
        assert f"vars.{name}" in wf
