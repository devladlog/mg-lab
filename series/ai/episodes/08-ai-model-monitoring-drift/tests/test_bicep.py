"""Compile infra/main.bicep and check keyless telemetry, the pinned deployment, the alert rule and the roles."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("bicep") is None, reason="Bicep CLI not installed")


@pytest.fixture(scope="module")
def arm(tmp_path_factory):
    infra = Path(__file__).resolve().parents[1] / "infra"
    out = tmp_path_factory.mktemp("arm") / "main.json"
    subprocess.run(["bicep", "build", str(infra / "main.bicep"), "--outfile", str(out)], check=True,
                   capture_output=True, text=True)
    t = json.loads(out.read_text())
    res = t["resources"]
    return t, list(res.values()) if isinstance(res, dict) else res


def of_type(resources, type_):
    return [r for r in resources if r["type"] == type_]


def test_telemetry_is_keyless_and_workspace_based(arm):
    _, resources = arm
    (appi,) = of_type(resources, "Microsoft.Insights/components")
    assert appi["properties"]["DisableLocalAuth"] is True and "WorkspaceResourceId" in appi["properties"]
    (acc,) = of_type(resources, "Microsoft.CognitiveServices/accounts")
    assert acc["properties"]["disableLocalAuth"] is True


def test_deployment_is_pinned(arm):
    t, resources = arm
    (dep,) = of_type(resources, "Microsoft.CognitiveServices/accounts/deployments")
    assert dep["properties"]["versionUpgradeOption"] == "NoAutoUpgrade"
    assert t["parameters"]["chatSku"]["defaultValue"] == "DataZoneStandard"


def test_drift_alert_reads_the_monitor_records(arm):
    t, resources = arm
    (rule,) = of_type(resources, "Microsoft.Insights/scheduledQueryRules")
    crit = rule["properties"]["criteria"]["allOf"][0]
    assert crit["timeAggregation"] == "Count" and crit["operator"] == "GreaterThan" and crit["threshold"] == 0
    assert "drift_report" in t["variables"]["driftQuery"] and 'Properties["hr_max_psi"]' in t["variables"]["driftQuery"]
    assert t["parameters"]["psiAlertThreshold"]["defaultValue"] == "0.2"
    assert rule["properties"]["evaluationFrequency"] == "PT5M"


def test_developer_gets_exactly_the_three_data_roles(arm):
    t, resources = arm
    assert len(of_type(resources, "Microsoft.Authorization/roleAssignments")) == 3
    assert set(t["variables"]["roles"].values()) == {"5e0bd9bd-7b93-4f28-af87-19fc36ad61bd",
                                                     "3913510d-42f4-4e42-8a64-420c390055eb",
                                                     "73c42c96-874c-492b-b04d-ab87d138a893"}


def test_request_usage_logs_and_metrics_go_to_the_workspace(arm):
    _, resources = arm
    (diag,) = of_type(resources, "Microsoft.Insights/diagnosticSettings")
    assert diag["properties"]["logs"][0]["category"] == "AzureOpenAIRequestUsage"
    assert diag["properties"]["metrics"][0]["category"] == "AllMetrics"
