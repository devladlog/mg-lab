import copy
import json
import subprocess
import sys

import netplan
from conftest import ROOT

PLAN_DIR = ROOT / "src" / "netplan"


def errors(plan):
    return [f.message for f in netplan.check(plan) if f.level == "error"]


def test_the_shipped_plan_is_clean(plan):
    assert errors(plan) == []


def test_azure_keeps_five_addresses_per_subnet():
    assert netplan.usable_addresses("10.61.0.0/24") == 251  # Learn's own example
    assert netplan.usable_addresses("10.61.0.0/29") == 3    # smallest subnet: 8 - 5
    assert netplan.usable_addresses("10.60.0.0/27") == 27   # GatewaySubnet /27: 27 usable (Learn's table)


def test_first_vm_address_is_dot_four():
    assert netplan.workload_vm_ip("10.61.0.0/26") == "10.61.0.4"
    assert netplan.workload_vm_ip("10.61.0.64/26") == "10.61.0.68"


def test_overlap_with_the_hyperv_lab_is_rejected(plan):
    bad = copy.deepcopy(plan)
    bad["hub"]["addressSpace"] = "10.50.0.0/16"
    bad["hub"]["subnets"][0]["prefix"] = "10.50.255.0/27"
    assert any("overlaps" in e and "lab-hyperv" in e for e in errors(bad))


def test_p2s_pool_must_not_overlap_a_vnet(plan):
    bad = copy.deepcopy(plan)
    bad["p2sPool"] = "10.61.0.128/25"
    assert any("point-to-site client pool" in e and "overlaps" in e for e in errors(bad))


def test_gateway_subnet_rules(plan):
    small = copy.deepcopy(plan)
    small["hub"]["subnets"][0]["prefix"] = "10.60.0.0/28"
    assert any("needs /27 or larger" in e for e in errors(small))
    renamed = copy.deepcopy(plan)
    renamed["hub"]["subnets"][0]["name"] = "gateway"
    assert any("GatewaySubnet" in e for e in errors(renamed))


def test_firewall_and_bastion_need_a_slash_26(plan):
    p = copy.deepcopy(plan)
    p["hub"]["addressSpace"] = "10.60.0.0/23"
    p["hub"]["subnets"] += [{"name": "AzureFirewallSubnet", "prefix": "10.60.1.0/27"},
                            {"name": "AzureBastionSubnet", "prefix": "10.60.1.64/26"}]
    found = errors(p)
    assert any("AzureFirewallSubnet" in e and "/26" in e for e in found)
    assert not any("AzureBastionSubnet" in e for e in found)


def test_subnet_outside_its_vnet_and_subnet_overlap(plan):
    p = copy.deepcopy(plan)
    p["spoke"]["subnets"] = [{"name": "a", "prefix": "10.61.0.0/26"}, {"name": "b", "prefix": "10.61.0.32/27"},
                             {"name": "c", "prefix": "10.99.0.0/26"}]
    found = errors(p)
    assert any("overlaps subnet 'a'" in e for e in found)
    assert any("outside the VNet address space" in e for e in found)


def test_public_and_malformed_ranges_are_rejected(plan):
    p = copy.deepcopy(plan)
    p["spoke"]["addressSpace"] = "20.1.0.0/24"
    p["p2sPool"] = "172.16.201.7/24"  # host bits set
    found = errors(p)
    assert any("not a private range" in e for e in found)
    assert any("not a valid IPv4 CIDR" in e for e in found)


def run_cli(*args):
    return subprocess.run([sys.executable, str(PLAN_DIR / "netplan.py"), *args], capture_output=True, text=True)


def test_cli_check_good_and_bad_plan():
    good = run_cli("check", str(PLAN_DIR / "plan.json"))
    assert good.returncode == 0 and "OK:" in good.stdout and "VM gets 10.61.0.4" in good.stdout
    bad = run_cli("check", str(PLAN_DIR / "plan-overlap.json"))
    assert bad.returncode == 1
    assert "overlaps" in bad.stdout and "too small" in bad.stdout  # the demo plan breaks three rules at once


def test_cli_params_refuses_a_bad_plan():
    r = run_cli("params", str(PLAN_DIR / "plan-overlap.json"))
    assert r.returncode == 1 and r.stdout == ""


def test_params_match_what_main_bicep_asks_for(main):
    params = json.loads(run_cli("params", str(PLAN_DIR / "plan.json")).stdout)["parameters"]
    wanted = {name for name, p in main["parameters"].items() if "defaultValue" not in p}
    secrets_added_by_deploy_sh = {"p2sRootCertData", "sshPublicKey"}
    assert wanted == set(params) | secrets_added_by_deploy_sh
    assert set(params) <= set(main["parameters"])
    assert params["workloadVmIp"]["value"] == "10.61.0.4"
