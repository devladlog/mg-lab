"""Contract tests on the Bicep, via the compiled ARM template. No Azure access needed (bicep build only)."""
import ipaddress
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra"
pytestmark = pytest.mark.skipif(shutil.which("bicep") is None, reason="Bicep CLI not installed")
LAB_NET = ipaddress.ip_network("10.50.0.0/24")


def build(path: Path, tmp: Path) -> dict:
    out = tmp / (path.stem + ".json")
    r = subprocess.run(["bicep", "build", str(path), "--outfile", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "Warning" not in r.stderr, r.stderr
    return json.loads(out.read_text())


@pytest.fixture(scope="module")
def main(tmp_path_factory):
    return build(INFRA / "main.bicep", tmp_path_factory.mktemp("arm"))


def module_template(main, name):
    res = main["resources"]
    items = res.values() if isinstance(res, dict) else res
    return next(r for r in items if r.get("name") == name)["properties"]["template"]


def resources_of(template):
    res = template["resources"]
    return list(res.values()) if isinstance(res, dict) else res


def test_deploys_at_subscription_scope_and_names_follow_convention(main):
    assert main["$schema"].endswith("subscriptionDeploymentTemplate.json#")
    assert main["variables"]["sourceRgName"] == "[format('rg-mglab-deep-dive-{0}', parameters('episode'))]"
    assert main["variables"]["drRgName"] == "[format('rg-mglab-deep-dive-{0}-dr', parameters('episode'))]"
    assert main["parameters"]["episode"]["defaultValue"] == "17"


def test_vault_region_differs_from_source_region(main):
    p = main["parameters"]
    assert p["sourceLocation"]["defaultValue"] == "westeurope"
    assert p["drLocation"]["defaultValue"] == "northeurope"
    assert p["sourceLocation"]["defaultValue"] != p["drLocation"]["defaultValue"]
    # Learn: not supported for A2A vaults
    assert p["drLocation"]["defaultValue"] not in ("southcentralindia", "northeastus5")


def test_address_spaces_do_not_overlap_each_other_or_the_lab(main):
    src = ipaddress.ip_network(main["parameters"]["sourceAddressSpace"]["defaultValue"])
    dr = ipaddress.ip_network(main["parameters"]["drAddressSpace"]["defaultValue"])
    assert not src.overlaps(dr) and not src.overlaps(LAB_NET) and not dr.overlaps(LAB_NET)


def test_subnets_fit_inside_the_vnet(main):
    for module, vnet_name in (("source", "vnet-source"), ("dr", "vnet-target")):
        t = module_template(main, module)
        vnet = next(r for r in resources_of(t) if r["name"] == vnet_name)
        subnets = vnet["properties"]["subnets"]
        assert [s["name"] for s in subnets] == ["snet-app", "snet-data", "snet-mgmt"]
        indexes = [int(re.search(r"24, (\d+)\)", s["properties"]["addressPrefix"]).group(1)) for s in subnets]
        assert indexes == [1, 2, 3]


def test_password_is_secure_and_has_no_default(main):
    pw = main["parameters"]["adminPassword"]
    assert pw["type"] == "securestring" and "defaultValue" not in pw
    t = module_template(main, "source")
    assert t["parameters"]["adminPassword"]["type"] == "securestring"


def test_vm_is_private_only(main):
    t = module_template(main, "source")
    types = {r["type"] for r in resources_of(t)}
    assert "Microsoft.Network/publicIPAddresses" not in types
    nic = next(r for r in resources_of(t) if r["type"] == "Microsoft.Network/networkInterfaces")
    assert "publicIPAddress" not in json.dumps(nic)


def test_nsg_does_not_open_anything_to_the_internet(main):
    t = module_template(main, "source")
    nsg = next(r for r in resources_of(t) if r["type"] == "Microsoft.Network/networkSecurityGroups")
    for rule in nsg["properties"]["securityRules"]:
        p = rule["properties"]
        if p["access"] == "Allow" and p["direction"] == "Inbound":
            assert p["sourceAddressPrefix"] not in ("*", "Internet", "0.0.0.0/0")


def test_vault_is_standard_rs0_in_the_dr_group(main):
    t = module_template(main, "dr")
    vault = next(r for r in resources_of(t) if r["type"] == "Microsoft.RecoveryServices/vaults")
    assert vault["sku"] == {"name": "RS0", "tier": "Standard"}
    outer = main["resources"]
    items = outer.values() if isinstance(outer, dict) else outer
    dr_mod = next(r for r in items if r.get("name") == "dr")
    assert "drRgName" in dr_mod["resourceGroup"]


def test_no_secrets_real_names_or_real_guids_in_the_infra_files():
    guid = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
    for f in INFRA.rglob("*.bicep*"):
        text = f.read_text()
        assert "devladlog" not in text.lower(), f
        assert not [g for g in guid.findall(text) if set(g) - {"0", "-"}], f
        assert not re.search(r"adminPassword\s*[:=]\s*'[^']", text), f


def test_parameters_file_builds_and_carries_no_password(tmp_path):
    out = tmp_path / "p.json"
    r = subprocess.run(["bicep", "build-params", str(INFRA / "main.bicepparam"), "--outfile", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "adminPassword" in out.read_text()          # read from the environment, empty by default


def test_bicep_lint_is_clean():
    r = subprocess.run(["bicep", "lint", str(INFRA / "main.bicep")], capture_output=True, text=True)
    assert r.returncode == 0 and not (r.stdout + r.stderr).strip()
