"""Compile infra/main.bicep and check the keyless Document Intelligence resource and its role."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("bicep") is None, reason="Bicep CLI not installed")

COGNITIVE_SERVICES_USER = "a97b65f3-24c7-4388-baec-2e87135dc908"


@pytest.fixture(scope="module")
def arm(tmp_path_factory):
    out = tmp_path_factory.mktemp("arm") / "main.json"
    subprocess.run(["bicep", "build", str(Path(__file__).resolve().parents[1] / "infra" / "main.bicep"),
                    "--outfile", str(out)], check=True, capture_output=True, text=True)
    t = json.loads(out.read_text())
    res = t["resources"]
    return t, list(res.values()) if isinstance(res, dict) else res


def test_single_service_keyless_resource_with_custom_subdomain(arm):
    template, resources = arm
    (acct,) = [r for r in resources if r["type"] == "Microsoft.CognitiveServices/accounts"]
    assert acct["kind"] == "FormRecognizer"
    assert acct["properties"]["disableLocalAuth"] is True
    assert acct["properties"]["customSubDomainName"] == "[variables('name')]"
    assert template["parameters"]["sku"]["defaultValue"] == "F0"


def test_developer_gets_cognitive_services_user(arm):
    template, resources = arm
    (ra,) = [r for r in resources if r["type"] == "Microsoft.Authorization/roleAssignments"]
    assert template["variables"]["cognitiveServicesUser"] == COGNITIVE_SERVICES_USER
    assert "cognitiveServicesUser" in ra["properties"]["roleDefinitionId"]
    assert ra["condition"].startswith("[not(empty(parameters('developerPrincipalId')))")
