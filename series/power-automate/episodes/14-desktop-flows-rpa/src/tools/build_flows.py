"""Writes the cloud flow of the 'PurchaseRpa' solution (unpacked `pac solution unpack` layout).

Run: python tools/build_flows.py   (rewrites solution/Workflows/*.json and the .data.xml)
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "solution" / "Workflows"
SCHEMA = "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#"
AUTH = "@parameters('$authentication')"
SP = {"apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline", "connectionName": "shared_sharepointonline"}
MAIL = {"apiId": "/providers/Microsoft.PowerApps/apis/shared_office365", "connectionName": "shared_office365"}
UIFLOW = {"apiId": "/providers/Microsoft.PowerApps/apis/shared_uiflow", "connectionName": "shared_uiflow"}
SITE = "https://contoso.sharepoint.com/sites/Purchasing"
LIST = "Purchase Requests"
DESKTOP_FLOW_ID = "00000000-0000-0000-0000-000000000901"  # replaced by the id of the flow in the lab environment

# Without this the update below would trigger the flow again and again: the trigger fires on every modification.
TRIGGER_CONDITION = ("@and(equals(triggerBody()?['Status']?['Value'], 'Approved'), "
                     "empty(triggerBody()?['RpaStatus']))")


def patch(status_expr, extra=None, run_after=None):
    params = {"dataset": SITE, "table": LIST, "id": "@triggerBody()?['ID']",
              "item/Title": "@triggerBody()?['Title']", "item/RpaStatus": status_expr}
    params.update(extra or {})
    return {"type": "OpenApiConnection", "runAfter": run_after or {},
            "inputs": {"host": {**SP, "operationId": "PatchItem"}, "parameters": params, "authentication": AUTH}}


def mail(to, subject, body, run_after, importance=None):
    p = {"emailMessage/To": to, "emailMessage/Subject": subject, "emailMessage/Body": body}
    if importance:
        p["emailMessage/Importance"] = importance
    return {"type": "OpenApiConnection", "runAfter": run_after,
            "inputs": {"host": {**MAIL, "operationId": "SendEmailV2"}, "parameters": p, "authentication": AUTH}}


def flow():
    actions = {
        "Try": {"type": "Scope", "runAfter": {}, "actions": {
            "Run_desktop_flow": {"type": "OpenApiConnection", "runAfter": {}, "limit": {"timeout": "PT30M"},
                "inputs": {"host": {**UIFLOW, "operationId": "RunUIFlow_V2"}, "parameters": {
                    "uiFlowId": DESKTOP_FLOW_ID,
                    "runMode": "attended",
                    "item/Supplier": "@triggerBody()?['Supplier']",
                    "item/Description": "@coalesce(triggerBody()?['Justification'], triggerBody()?['Title'])",
                    # text on purpose: a number input is formatted by the culture of the machine
                    "item/Amount": "@formatNumber(triggerBody()?['Amount'], '0.00', 'en-US')",
                    "item/RequestId": "@string(triggerBody()?['ID'])"},
                    "authentication": AUTH}}}},
        "Order_saved": {"type": "If", "runAfter": {"Try": ["Succeeded"]},
            "expression": {"equals": ["@outputs('Run_desktop_flow')?['body/Status']", "Saved"]},
            "actions": {
                "Mark_entered": patch("Entered", {"item/PONumber": "@outputs('Run_desktop_flow')?['body/OrderNumber']"}),
                "Tell_requester_entered": mail(
                    "@triggerBody()?['Author']?['Email']", "Ordered: @{triggerBody()?['Title']}",
                    "<p>Your request was entered as order @{outputs('Run_desktop_flow')?['body/OrderNumber']}.</p>",
                    {"Mark_entered": ["Succeeded"]}),
            },
            "else": {"actions": {
                "Mark_rejected": patch("@concat('Rejected: ', outputs('Run_desktop_flow')?['body/Errors'])"),
                "Tell_requester_rejected": mail(
                    "@triggerBody()?['Author']?['Email']", "Needs a fix: @{triggerBody()?['Title']}",
                    "<p>The order was not entered: @{outputs('Run_desktop_flow')?['body/Errors']}</p>",
                    {"Mark_rejected": ["Succeeded"]}),
            }}},
        "Catch": {"type": "Scope", "runAfter": {"Try": ["Failed", "TimedOut"]}, "actions": {
            "Mark_failed": patch("Failed"),
            "Tell_purchasing_team": mail(
                "purchasing-team@contoso.com", "RPA failed: @{triggerBody()?['Title']}",
                "<p>The desktop flow did not finish: "
                "@{coalesce(first(result('Try'))?['error']?['message'], first(result('Try'))?['status'])}</p>"
                "<p><a href=\"@{triggerBody()?['{Link}']}\">Open the request</a></p>",
                {"Mark_failed": ["Succeeded"]}, importance="High"),
        }},
        "Result": {"type": "Compose", "inputs": "@coalesce(outputs('Run_desktop_flow')?['body/Status'], 'Failed')",
            "runAfter": {"Order_saved": ["Succeeded", "Skipped"], "Catch": ["Succeeded", "Skipped"]}},
    }
    return {"properties": {
        "connectionReferences": {k: {"runtimeSource": "embedded", "connection": {"connectionReferenceLogicalName": v},
                                     "api": {"name": k}} for k, v in {
            "shared_sharepointonline": "cts_sharedsharepointonline_rpa",
            "shared_office365": "cts_sharedoffice365_rpa",
            "shared_uiflow": "cts_shareduiflow_rpa"}.items()},
        "definition": {"$schema": SCHEMA, "contentVersion": "1.0.0.0",
            "parameters": {"$connections": {"defaultValue": {}, "type": "Object"},
                           "$authentication": {"defaultValue": {}, "type": "SecureObject"}},
            "triggers": {"When_a_purchase_request_is_approved": {
                "type": "OpenApiConnection", "recurrence": {"interval": 5, "frequency": "Minute"},
                "splitOn": "@triggerOutputs()?['body/value']",
                "conditions": [{"expression": TRIGGER_CONDITION}],
                "inputs": {"host": {**SP, "operationId": "GetOnUpdatedItems"},
                           "parameters": {"dataset": SITE, "table": LIST}, "authentication": AUTH}}},
            "actions": actions}}, "schemaVersion": "1.0.0.0"}


DATA = """<?xml version="1.0" encoding="utf-8"?>
<Workflow WorkflowId="{{{gid}}}" Name="{name}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <JsonFileName>/Workflows/{fname}-{gid}.json</JsonFileName>
  <Type>1</Type>
  <Subprocess>0</Subprocess>
  <Category>5</Category>
  <Mode>0</Mode>
  <Scope>4</Scope>
  <OnDemand>0</OnDemand>
  <TriggerOnCreate>0</TriggerOnCreate>
  <TriggerOnDelete>0</TriggerOnDelete>
  <AsyncAutodelete>0</AsyncAutodelete>
  <SyncWorkflowLogOnFailure>0</SyncWorkflowLogOnFailure>
  <StateCode>0</StateCode>
  <StatusCode>1</StatusCode>
  <RunAs>1</RunAs>
  <IsTransacted>1</IsTransacted>
  <IntroducedVersion>1.0.0.0</IntroducedVersion>
  <IsCustomizable>1</IsCustomizable>
  <BusinessProcessType>0</BusinessProcessType>
  <IsCustomProcessingStepAllowedForOtherPublishers>1</IsCustomProcessingStepAllowedForOtherPublishers>
  <PrimaryEntity>none</PrimaryEntity>
  <LocalizedNames>
    <LocalizedName languagecode="1033" description="{name}" />
  </LocalizedNames>
</Workflow>"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*"):
        old.unlink()
    fname, name, gid = "Enterapprovedpurchaseorders", "Enter approved purchase orders", "00000000-0000-0000-0000-000000000601"
    (OUT / f"{fname}-{gid}.json").write_text(json.dumps(flow(), indent=2) + "\n", encoding="utf-8")
    (OUT / f"{fname}-{gid}.json.data.xml").write_text(DATA.format(gid=gid, name=name, fname=fname), encoding="utf-8")
    print("wrote", fname)


if __name__ == "__main__":
    main()
