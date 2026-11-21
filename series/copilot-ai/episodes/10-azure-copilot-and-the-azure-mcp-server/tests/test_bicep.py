"""`bicep build` the demo template and check the properties the episode relies on (skipped without the bicep CLI)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

BICEP = shutil.which("bicep")
TEMPLATE = Path(__file__).resolve().parents[1] / "src" / "infra" / "main.bicep"
pytestmark = pytest.mark.skipif(BICEP is None, reason="bicep not installed")


@pytest.fixture(scope="module")
def arm():
    out = subprocess.run([BICEP, "build", str(TEMPLATE), "--stdout"], capture_output=True, text=True, check=True, timeout=120)
    return json.loads(out.stdout)


def by_type(arm, t):
    res = arm["resources"]
    res = res.values() if isinstance(res, dict) else res
    return [r for r in res if r["type"].lower() == t.lower()]


def test_builds_and_has_the_five_resources(arm):
    types = sorted(r["type"] for r in (arm["resources"].values() if isinstance(arm["resources"], dict) else arm["resources"]))
    assert types == ["Microsoft.Authorization/locks", "Microsoft.Authorization/roleAssignments", "Microsoft.KeyVault/vaults",
                     "Microsoft.KeyVault/vaults/secrets", "Microsoft.Storage/storageAccounts"]


def test_storage_is_cheap_and_locked_down(arm):
    (s,) = by_type(arm, "Microsoft.Storage/storageAccounts")
    assert s["sku"]["name"] == "Standard_LRS"
    assert s["properties"]["minimumTlsVersion"] == "TLS1_2" and s["properties"]["allowBlobPublicAccess"] is False
    (lock,) = by_type(arm, "Microsoft.Authorization/locks")
    assert lock["properties"]["level"] == "CanNotDelete"


def test_vault_uses_rbac_and_has_no_purge_protection(arm):
    (v,) = by_type(arm, "Microsoft.KeyVault/vaults")
    assert v["properties"]["enableRbacAuthorization"] is True
    assert "enablePurgeProtection" not in v["properties"]


def test_reader_assignment_is_optional_and_uses_the_reader_role(arm):
    (ra,) = by_type(arm, "Microsoft.Authorization/roleAssignments")
    assert "readerObjectId" in ra["condition"]
    assert "acdd72a7-3385-48ef-bd42-f606fba81ae7" in json.dumps(arm["variables"])


def test_names_fit_the_length_limits():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "'stmglab10${uniqueString(resourceGroup().id)}'" in text      # 9 + 13 = 22 <= 24
    assert "'kv-mglab10-${take(uniqueString(resourceGroup().id), 8)}'" in text   # 11 + 8 = 19 <= 24
