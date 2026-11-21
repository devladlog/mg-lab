"""Compile infra/main.bicep and check the settings the design depends on (needs the Bicep CLI)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("bicep") is None, reason="Bicep CLI not installed")


@pytest.fixture(scope="module")
def arm():
    out = subprocess.run(["bicep", "build", str(ROOT / "infra" / "main.bicep"), "--stdout"],
                         capture_output=True, text=True, check=True, timeout=120)
    t = json.loads(out.stdout)
    res = t["resources"]
    return {"list": list(res.values()) if isinstance(res, dict) else res, "vars": t["variables"]}


def of_type(arm, t):
    return [r for r in arm["list"] if r["type"] == t]


def test_document_intelligence_is_keyless_with_a_custom_subdomain(arm):
    (di,) = of_type(arm, "Microsoft.CognitiveServices/accounts")
    assert di["kind"] == "FormRecognizer"
    assert di["properties"]["disableLocalAuth"] is True and "customSubDomainName" in di["properties"]


def test_function_identity_gets_cognitive_services_user_on_that_account(arm):
    assert arm["vars"]["roles"]["cognitiveServicesUser"] == "a97b65f3-24c7-4388-baec-2e87135dc908"
    (ra,) = [r for r in of_type(arm, "Microsoft.Authorization/roleAssignments") if "cognitiveServicesUser" in json.dumps(r)]
    assert "di-" in json.dumps(ra["scope"]) or "CognitiveServices/accounts" in json.dumps(ra["scope"])
    assert ra["properties"]["principalType"] == "ServicePrincipal"


def test_storage_has_no_shared_keys_and_flex_app_is_python(arm):
    (st,) = of_type(arm, "Microsoft.Storage/storageAccounts")
    assert st["properties"]["allowSharedKeyAccess"] is False
    (site,) = of_type(arm, "Microsoft.Web/sites")
    cfg = site["properties"]["functionAppConfig"]
    assert cfg["runtime"] == {"name": "python", "version": "3.11"}
    assert cfg["deployment"]["storage"]["authentication"]["type"] == "UserAssignedIdentity"
    assert cfg["scaleAndConcurrency"]["maximumInstanceCount"] >= 40     # Learn: below 40 can throttle HTTP apps


def test_policy_settings_reach_the_function(arm):
    (settings,) = [r for r in of_type(arm, "Microsoft.Web/sites/config") if "appsettings" in r["name"]]
    p = settings["properties"]
    assert {"DOCINTEL_ENDPOINT", "AZURE_CLIENT_ID", "MIN_CONFIDENCE", "APPROVAL_LIMIT", "ALLOWED_CURRENCIES"} <= set(p)
