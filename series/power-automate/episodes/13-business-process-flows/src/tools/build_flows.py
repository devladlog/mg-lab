"""Writes the two cloud flows of the 'PurchaseBpf' solution (unpacked `pac solution unpack` layout).

Run: python tools/build_flows.py   (rewrites solution/Workflows/*.json and the .data.xml files)
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "solution" / "Workflows"
CONN = "shared_commondataserviceforapps"
HOST = {"apiId": f"/providers/Microsoft.PowerApps/apis/{CONN}", "connectionName": CONN}
APPROVALS = {"apiId": "/providers/Microsoft.PowerApps/apis/shared_approvals", "connectionName": "shared_approvals"}
SCHEMA = "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#"
AUTH = "@parameters('$authentication')"
# Choice values: publisher prefix 44446 (see Solution.xml) + 0000, 0001
APPROVED, REJECTED = 444460000, 444460001

# Learn: Create instant flows in business process flows (Parse JSON schema of the flow-step payload)
ENTITY_FIELDS = ["FlowsWorkflowLogId", "BPFInstanceId", "BPFInstanceEntityName", "BPFDefinitionId",
                 "BPFDefinitionEntityName", "StepId", "BPFDefinitionName", "BPFInstanceName",
                 "BPFFlowStageLocalizedName", "BPFFlowStageEntityName", "BPFFlowStageEntityCollectionName",
                 "BPFFlowStageTableRowID", "BPFActiveStageId", "BPFActiveStageEntityName",
                 "BPFActiveStageLocalizedName"]
PAYLOAD_SCHEMA = {"type": "object", "properties": {"entity": {"type": "object",
                  "properties": {f: {"type": "string"} for f in ENTITY_FIELDS}}}}


def dv(op, params):
    return {"host": {**HOST, "operationId": op}, "parameters": params, "authentication": AUTH}


def wrap(definition, refs):
    return {"properties": {
        "connectionReferences": {k: {"runtimeSource": "embedded", "connection": {"connectionReferenceLogicalName": v},
                                     "api": {"name": k}} for k, v in refs.items()},
        "definition": {"$schema": SCHEMA, "contentVersion": "1.0.0.0",
                       "parameters": {"$connections": {"defaultValue": {}, "type": "Object"},
                                      "$authentication": {"defaultValue": {}, "type": "SecureObject"}},
                       **definition},
    }, "schemaVersion": "1.0.0.0"}


def finish_log(status_code):
    """Flow steps show 'Processing' until the process session row is completed (Learn: Flow step considerations)."""
    return {"type": "OpenApiConnection", "inputs": dv("UpdateOnlyRecord", {
        "entityName": "processsessions",
        "recordId": "@body('Parse_step_payload')?['entity']?['FlowsWorkflowLogId']",
        "item/statecode": 1, "item/statuscode": status_code})}


def finance_step():
    approved_branch = {
        "Record_approval": {"type": "OpenApiConnection", "runAfter": {}, "inputs": dv("UpdateOnlyRecord", {
            "entityName": "cts_purchaserequests",
            "recordId": "@body('Parse_step_payload')?['entity']?['BPFFlowStageTableRowID']",
            "item/cts_financedecision": APPROVED})},
        "Complete_flow_step": {**finish_log(4), "runAfter": {"Record_approval": ["Succeeded"]}},
    }
    rejected_branch = {
        "Record_rejection": {"type": "OpenApiConnection", "runAfter": {}, "inputs": dv("UpdateOnlyRecord", {
            "entityName": "cts_purchaserequests",
            "recordId": "@body('Parse_step_payload')?['entity']?['BPFFlowStageTableRowID']",
            "item/cts_financedecision": REJECTED})},
        "Complete_flow_step_rejected": {**finish_log(4), "runAfter": {"Record_rejection": ["Succeeded"]}},
    }
    return wrap({
        "triggers": {"When_a_row_is_selected": {"type": "OpenApiConnection", "inputs": {
            "host": {**HOST, "operationId": "SubscribeOnDemand"},
            "parameters": {"subscriptionRequest/entityname": "cts_purchaserequestprocess",
                           "subscriptionRequest/scope": 4},
            "authentication": AUTH}, "splitOn": "@triggerOutputs()?['body/value']"}},
        "actions": {
            "Parse_step_payload": {"type": "ParseJson", "runAfter": {}, "inputs": {
                "content": "@triggerOutputs()?['body']", "schema": PAYLOAD_SCHEMA}},
            "Get_purchase_request": {"type": "OpenApiConnection", "runAfter": {"Parse_step_payload": ["Succeeded"]},
                "inputs": dv("GetItem", {
                    "entityName": "cts_purchaserequests",
                    "recordId": "@body('Parse_step_payload')?['entity']?['BPFFlowStageTableRowID']"})},
            "Finance_approval": {"type": "OpenApiConnectionWebhook", "runAfter": {"Get_purchase_request": ["Succeeded"]},
                "limit": {"timeout": "P3D"},
                "inputs": {"host": {**APPROVALS, "operationId": "StartAndWaitForAnApproval"}, "parameters": {
                    "approvalType": "Basic",
                    "WebhookApprovalCreationInput/title":
                        "Finance review: @{outputs('Get_purchase_request')?['body/cts_justification']} "
                        "(@{outputs('Get_purchase_request')?['body/cts_amount']} EUR)",
                    "WebhookApprovalCreationInput/assignedTo": "finance-approvers@contoso.com",
                    "WebhookApprovalCreationInput/details":
                        "**Stage:** @{body('Parse_step_payload')?['entity']?['BPFActiveStageLocalizedName']}\n\n"
                        "**Process:** @{body('Parse_step_payload')?['entity']?['BPFDefinitionName']}",
                    "WebhookApprovalCreationInput/enableNotifications": True,
                    "WebhookApprovalCreationInput/enableReassignment": True},
                    "authentication": AUTH}},
            "Fail_flow_step_on_timeout": {**finish_log(6), "runAfter": {"Finance_approval": ["TimedOut"]}},
            "Finance_decision": {"type": "If", "runAfter": {"Finance_approval": ["Succeeded"]},
                "expression": {"equals": ["@body('Finance_approval')?['outcome']", "Approve"]},
                "actions": approved_branch, "else": {"actions": rejected_branch}},
            # both paths end here, so a handled timeout does not leave a Skipped last action (see episode 2)
            "Step_result": {"type": "Compose", "inputs": "@coalesce(body('Finance_approval')?['outcome'], 'TimedOut')",
                "runAfter": {"Finance_decision": ["Succeeded", "Skipped"],
                             "Fail_flow_step_on_timeout": ["Succeeded", "Skipped"]}},
        }}, {CONN: "cts_shareddataverse_purchasebpf", "shared_approvals": "cts_sharedapprovals_purchasebpf"})


def copy_active_stage():
    """Learn (best practices for BPF columns, option 2): copy the active stage to a column of the related table."""
    return wrap({
        "triggers": {"When_the_process_instance_moves": {"type": "OpenApiConnection", "inputs": {
            "host": {**HOST, "operationId": "SubscribeWebhookTrigger"},
            "parameters": {"subscriptionRequest/message": 3,  # 3 = Update (confirm in the designer)
                           "subscriptionRequest/entityname": "cts_purchaserequestprocess",
                           "subscriptionRequest/scope": 4,  # 4 = Organization
                           # activestageid is a lookup and lookups are not supported in Select columns:
                           # traversedpath (text) changes on every stage move, statecode on finish/abort
                           "subscriptionRequest/filteringattributes": "traversedpath,statecode"},
            "authentication": AUTH}}},
        "actions": {
            "Get_active_stage": {"type": "OpenApiConnection", "runAfter": {}, "inputs": dv("GetItem", {
                "entityName": "processstages",
                "recordId": "@triggerOutputs()?['body/_activestageid_value']",
                "$select": "stagename"})},
            "Copy_stage_to_request": {"type": "OpenApiConnection", "runAfter": {"Get_active_stage": ["Succeeded"]},
                "inputs": dv("UpdateOnlyRecord", {
                    "entityName": "cts_purchaserequests",
                    "recordId": "@triggerOutputs()?['body/_bpf_purchaserequestid_value']",
                    "item/cts_activestage": "@outputs('Get_active_stage')?['body/stagename']"})},
        }}, {CONN: "cts_shareddataverse_purchasebpf"})


FLOWS = [
    ("Financereviewstep", "Finance review step", "00000000-0000-0000-0000-000000000501", finance_step(), 1),
    ("Copyactivestagetorequest", "Copy active stage to request", "00000000-0000-0000-0000-000000000502", copy_active_stage(), 0),
]

DATA = """<?xml version="1.0" encoding="utf-8"?>
<Workflow WorkflowId="{{{gid}}}" Name="{name}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <JsonFileName>/Workflows/{fname}-{gid}.json</JsonFileName>
  <Type>1</Type>
  <Subprocess>0</Subprocess>
  <Category>5</Category>
  <Mode>0</Mode>
  <Scope>4</Scope>
  <OnDemand>{ondemand}</OnDemand>
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
    for fname, name, gid, flow, ondemand in FLOWS:
        (OUT / f"{fname}-{gid}.json").write_text(json.dumps(flow, indent=2) + "\n", encoding="utf-8")
        (OUT / f"{fname}-{gid}.json.data.xml").write_text(
            DATA.format(gid=gid, name=name, fname=fname, ondemand=ondemand), encoding="utf-8")
        print("wrote", fname)


if __name__ == "__main__":
    main()
