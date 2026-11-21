"""Contract tests: compiled Bicep against the Stream Analytics project, the query and the simulator."""
from __future__ import annotations

import json
import re

from conftest import ASA, of_type
from iotlab.telemetry import ALERT_TEMP_C

QUERY = (ASA / "coldroom-telemetry.asaql").read_text(encoding="utf-8")


def load(name):
    return json.loads((ASA / name).read_text(encoding="utf-8-sig"))


def one(resources, type_name):
    found = of_type(resources, type_name)
    assert len(found) == 1, f"{type_name}: {len(found)}"
    return found[0]


def test_iot_hub_is_the_free_tier_with_tls_12(resources):
    hub = one(resources, "Microsoft.Devices/IotHubs")
    assert hub["sku"] == {"name": "F1", "capacity": 1}
    assert hub["properties"]["minTlsVersion"] == "1.2"
    assert hub["properties"]["eventHubEndpoints"]["events"]["partitionCount"] == 2


def test_consumer_group_is_the_one_the_asa_input_reads(resources, template):
    group = one(resources, "Microsoft.Devices/IotHubs/eventHubEndpoints/ConsumerGroups")
    assert group["properties"]["name"] == "[parameters('consumerGroupName')]"
    assert template["parameters"]["consumerGroupName"]["defaultValue"] == "asa"
    assert load("Inputs/telemetry.json")["IoTHubProperties"]["ConsumerGroupName"] == "asa"
    stream = one(resources, "Microsoft.StreamAnalytics/streamingjobs/inputs")
    assert stream["properties"]["datasource"]["properties"]["consumerGroupName"] == "[parameters('consumerGroupName')]"
    assert "$Default" not in json.dumps(stream)  # Learn: one consumer group per job


def test_input_and_output_aliases_agree_in_bicep_asa_project_and_query(resources, template):
    assert template["variables"]["inputAlias"] == load("Inputs/telemetry.json")["Name"] == "telemetry"
    assert "variables('inputAlias')" in one(resources, "Microsoft.StreamAnalytics/streamingjobs/inputs")["name"]
    assert re.findall(r"^\s*FROM\s+telemetry\s+TIMESTAMP BY observedAt", QUERY, re.M) == ["    FROM telemetry TIMESTAMP BY observedAt".lstrip()] or "FROM telemetry TIMESTAMP BY observedAt" in QUERY
    into = sorted(set(re.findall(r"^INTO\s+(\w+)", QUERY, re.M)))
    assert into == ["aggregates", "alerts"]
    assert sorted(load(f"Outputs/{n}.json")["Name"] for n in into) == into
    assert template["variables"]["outputAliases"] == into


def test_job_settings_in_bicep_equal_the_asa_project(resources):
    job = one(resources, "Microsoft.StreamAnalytics/streamingjobs")["properties"]
    cfg = load("JobConfig.json")
    assert job["eventsLateArrivalMaxDelayInSeconds"] == cfg["EventsLateArrivalMaxDelayInSeconds"]
    assert job["eventsOutOfOrderMaxDelayInSeconds"] == cfg["EventsOutOfOrderMaxDelayInSeconds"]
    assert job["eventsOutOfOrderPolicy"] == cfg["EventsOutOfOrderPolicy"]
    assert job["outputErrorPolicy"] == cfg["OutputErrorPolicy"]
    assert job["compatibilityLevel"] == cfg["CompatibilityLevel"]
    assert one(resources, "Microsoft.StreamAnalytics/streamingjobs/transformations")["properties"]["streamingUnits"] == cfg["StreamingUnits"] == 1


def test_the_deployed_query_is_the_tested_file(template, resources):
    ref = one(resources, "Microsoft.StreamAnalytics/streamingjobs/transformations")["properties"]["query"]
    name = re.fullmatch(r"\[variables\('(.+)'\)\]", ref).group(1)
    assert template["variables"][name].replace("\r\n", "\n") == QUERY.replace("\r\n", "\n")


def test_alert_threshold_in_the_query_equals_the_simulator_constant():
    assert f"AVG(temperatureC) > {ALERT_TEMP_C}" in QUERY


def test_blob_outputs_use_the_jobs_managed_identity_and_storage_has_no_shared_key(resources):
    storage = one(resources, "Microsoft.Storage/storageAccounts")["properties"]
    assert storage["allowSharedKeyAccess"] is False and storage["allowBlobPublicAccess"] is False
    outs = of_type(resources, "Microsoft.StreamAnalytics/streamingjobs/outputs")
    assert len(outs) == 1  # copy loop: one resource, two aliases
    assert outs[0]["properties"]["datasource"]["properties"]["authenticationMode"] == "Msi"
    assert one(resources, "Microsoft.StreamAnalytics/streamingjobs")["identity"]["type"] == "SystemAssigned"


def test_job_identity_gets_blob_contributor_on_its_two_containers_only(template, resources):
    roles = of_type(resources, "Microsoft.Authorization/roleAssignments")
    assert len(roles) == 2  # job loop + conditional operator
    job_role = next(r for r in roles if "job.id" in json.dumps(r["name"]) or "streamingjobs" in json.dumps(r["name"]))
    assert job_role["copy"]["count"] == "[length(variables('outputAliases'))]"
    assert template["variables"]["blobDataContributor"] == "ba92f5b4-2d11-453d-a403-e96b0029c9fe"  # Storage Blob Data Contributor
    assert "variables('blobDataContributor')" in job_role["properties"]["roleDefinitionId"]
    assert "containers" in job_role["scope"]
    operator = next(r for r in roles if r is not job_role)
    assert template["variables"]["blobDataReader"] == "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1"  # Storage Blob Data Reader
    assert "variables('blobDataReader')" in operator["properties"]["roleDefinitionId"]
    assert "condition" in operator


def test_iot_hub_input_uses_the_service_policy_key_and_never_outputs_a_secret(template, resources):
    stream = one(resources, "Microsoft.StreamAnalytics/streamingjobs/inputs")["properties"]["datasource"]["properties"]
    assert stream["sharedAccessPolicyName"] == "service"  # Learn: managed identity is not supported on the IoT Hub input
    assert "listKeys" in stream["sharedAccessPolicyKey"]
    assert set(template["outputs"]) == {"hubName", "hubHostName", "storageAccountName", "jobName"}
    assert "listKeys" not in json.dumps(template["outputs"]) and "Key" not in json.dumps(template["outputs"])


def test_no_literal_secrets_anywhere_in_the_infra_or_asa_files(root):
    for path in [*root.glob("infra/*"), *ASA.rglob("*.json"), *ASA.glob("*.asaql")]:
        text = path.read_text(encoding="utf-8-sig")
        assert not re.search(r"SharedAccessKey=[A-Za-z0-9+/=]{8,}", text), path
        assert not re.search(r'"(AccountKey|SharedAccessPolicyKey)"\s*:\s*"[^"]', text), path


def test_asa_project_files_say_the_same_about_authentication_as_the_bicep():
    assert load("JobConfig.json")["UseSystemAssignedIdentity"] is True
    assert load("Outputs/aggregates.json")["BlobStorageProperties"]["AuthenticationMode"] == "Msi"
    assert load("Outputs/alerts.json")["BlobStorageProperties"]["AuthenticationMode"] == "Msi"
    assert load("Inputs/telemetry.json")["IoTHubProperties"]["SharedAccessPolicyName"] == "service"
