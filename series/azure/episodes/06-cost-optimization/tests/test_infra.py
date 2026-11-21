"""Guardrails on the compiled Bicep (bicep build, no Azure) and on the query files and scripts."""
import json
import re
import subprocess
from pathlib import Path

import pytest

from costwatch.waste import CHECKS, QUERY_DIR

INFRA = Path(__file__).resolve().parents[1] / "infra"


def build(name: str) -> dict:
    p = subprocess.run(["bicep", "build", str(INFRA / name), "--stdout"], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


@pytest.fixture(scope="module")
def budget():
    return build("budget.bicep")


def test_budget_is_subscription_scoped_monthly_and_tag_filtered(budget):
    assert "subscriptionDeploymentTemplate" in budget["$schema"]
    [res] = budget["resources"]
    props = res["properties"]
    assert res["type"] == "Microsoft.Consumption/budgets"
    assert props["timeGrain"] == "Monthly" and props["category"] == "Cost"
    assert props["filter"]["tags"]["name"] == "workload"
    assert budget["parameters"]["workloads"]["defaultValue"] == ["order-intake", "contoso", "contoso-orders"]


def test_budget_starts_on_the_first_of_the_month(budget):
    assert budget["parameters"]["startDate"]["defaultValue"] == "[utcNow('yyyy-MM-01')]"


def test_budget_warns_early_with_actual_and_forecast(budget):
    notes = budget["resources"][0]["properties"]["notifications"]
    kinds = sorted((n["thresholdType"], n["threshold"]) for n in notes.values())
    assert kinds == [("Actual", 50), ("Actual", 90), ("Forecasted", 100)]
    assert all(n["contactEmails"] == "[parameters('contactEmails')]" for n in notes.values())
    assert budget["parameters"]["contactEmails"]["maxLength"] == 5      # Learn: up to five recipients


def test_waste_demo_leaves_exactly_the_things_the_queries_look_for():
    t = build("waste-demo.bicep")
    by_type = {r["type"]: r for r in t["resources"]}
    ip = by_type["Microsoft.Network/publicIPAddresses"]
    assert ip["sku"]["name"] == "Standard" and ip["properties"]["publicIPAllocationMethod"] == "Static"
    assert "tags" not in ip                                         # the untagged query must find it
    assert "ipConfiguration" not in ip["properties"]
    plan = by_type["Microsoft.Web/serverfarms"]
    assert plan["sku"]["name"] == "B1" and plan["properties"]["reserved"] is True
    assert "Microsoft.Web/sites" not in by_type                     # no apps on the plan


@pytest.mark.parametrize("file", sorted(CHECKS))
def test_check_queries_keep_id_for_paging_and_the_fields_the_pricer_needs(file):
    text = (QUERY_DIR / file).read_text()
    project = next(line for line in text.splitlines() if line.lstrip().startswith("| project"))
    for field in ("id", "type", "location", "resourceGroup"):
        assert f" {field}," in project + ","                         # ARG needs id for a skip token
    assert "| take" not in text and "| limit" not in text           # both disable paging


def test_queries_follow_the_learn_finops_filters():
    disks = (QUERY_DIR / "unattached-disks.kql").read_text()
    ips = (QUERY_DIR / "unattached-public-ips.kql").read_text()
    plans = (QUERY_DIR / "empty-app-service-plans.kql").read_text()
    assert "managedBy == \"\"" in disks and "ActiveSAS" in disks and "ASR-ReplicaDisk" in disks
    assert "isempty(properties.ipConfiguration)" in ips and "isempty(properties.natGateway)" in ips
    assert "numberOfSites) == 0" in plans and "!~ 'Free'" in plans


def test_shell_scripts_parse():
    for script in INFRA.glob("*.sh"):
        assert subprocess.run(["bash", "-n", str(script)]).returncode == 0, script.name


def test_no_real_address_is_committed():
    allowed = {"alex.demo@contoso.com", "you@example.com"}   # fictional / documentation-only
    for f in list(INFRA.glob("*.sh")) + list(INFRA.glob("*.bicep*")):
        found = set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", f.read_text()))
        assert found <= allowed, (f.name, found - allowed)
