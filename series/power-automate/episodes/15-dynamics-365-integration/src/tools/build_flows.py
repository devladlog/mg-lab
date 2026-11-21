"""Writes the two cloud flows of the 'SalesFollowUp' solution (unpacked `pac solution unpack` layout).

Run: python tools/build_flows.py   (rewrites solution/Workflows/*.json and the .data.xml files)
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "solution" / "Workflows"
DV, O365 = "shared_commondataserviceforapps", "shared_office365"
SCHEMA = "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#"
AUTH = "@parameters('$authentication')"
BIG_DEAL_EUR = 5000  # same threshold as the purchasing episodes 2, 3, 4 and 13


def host(api, op):
    return {"apiId": f"/providers/Microsoft.PowerApps/apis/{api}", "connectionName": api, "operationId": op}


def act(api, op, params, run_after=None, **extra):
    return {"type": "OpenApiConnection", "runAfter": run_after or {},
            "inputs": {"host": host(api, op), "parameters": params, "authentication": AUTH}, **extra}


def wrap(definition, refs):
    return {"properties": {
        "connectionReferences": {k: {"runtimeSource": "embedded", "connection": {"connectionReferenceLogicalName": v},
                                     "api": {"name": k}} for k, v in refs.items()},
        "definition": {"$schema": SCHEMA, "contentVersion": "1.0.0.0",
                       "parameters": {"$connections": {"defaultValue": {}, "type": "Object"},
                                      "$authentication": {"defaultValue": {}, "type": "SecureObject"}},
                       **definition},
    }, "schemaVersion": "1.0.0.0"}


def deal_won_follow_up():
    """When an opportunity is closed as won: one kick-off task for the owner, and finance hears about big deals."""
    opp = "@triggerOutputs()?['body/opportunityid']"
    value = ("coalesce(outputs('Get_opportunity')?['body/actualvalue'], "
             "outputs('Get_opportunity')?['body/estimatedvalue'], 0)")
    account = "outputs('Get_opportunity')?['body/parentaccountid']?['name']"
    return wrap({
        "triggers": {"When_an_opportunity_is_won": {"type": "OpenApiConnection", "inputs": {
            "host": host(DV, "SubscribeWebhookTrigger"),
            "parameters": {"subscriptionRequest/message": 3,  # Update (numbering: confirm from an export)
                           "subscriptionRequest/entityname": "opportunity",
                           "subscriptionRequest/scope": 4,  # Organization
                           # scalar column only: lookups aren't supported in Select columns (Learn)
                           "subscriptionRequest/filteringattributes": "statecode",
                           "subscriptionRequest/filterexpression": "statecode eq 1"},  # 1 = Won
            "authentication": AUTH}}},
        "actions": {
            "Get_opportunity": act(DV, "GetItem", {
                "entityName": "opportunities", "recordId": opp,
                "$select": "name,estimatedvalue,actualvalue,_ownerid_value",
                "$expand": "parentaccountid($select=name)"}),
            # The trigger can fire twice for one deal (won, reopened, won again): look before you create.
            "List_existing_kickoff_tasks": act(DV, "ListRecords", {
                "entityName": "tasks", "$select": "activityid", "$top": 1,
                "$filter": f"_regardingobjectid_value eq @{{{opp[1:]}}} and subject eq 'Kick-off call'"},
                {"Get_opportunity": ["Succeeded"]}),
            "Already_has_kickoff_task": {"type": "If", "runAfter": {"List_existing_kickoff_tasks": ["Succeeded"]},
                "expression": {"equals": ["@length(outputs('List_existing_kickoff_tasks')?['body/value'])", 0]},
                "actions": {
                    "Create_kickoff_task": act(DV, "CreateRecord", {
                        "entityName": "tasks",
                        "item/subject": "Kick-off call",
                        "item/description": f"Won: @{{outputs('Get_opportunity')?['body/name']}} for @{{{account}}}",
                        "item/scheduledend": "@addDays(utcNow(), 3)",
                        # lookups: <entity set name>(<id>); regarding is a multi-table lookup, so the navigation
                        # property carries the table name; the owner can also be a team (teams(...))
                        "item/regardingobjectid_opportunity@odata.bind": f"opportunities(@{{{opp[1:]}}})",
                        "item/ownerid@odata.bind": "systemusers(@{outputs('Get_opportunity')?['body/_ownerid_value']})"}),
                    "Big_deal": {"type": "If", "runAfter": {"Create_kickoff_task": ["Succeeded"]},
                        "expression": {"greaterOrEquals": [f"@{value}", BIG_DEAL_EUR]},
                        "actions": {"Tell_finance": act(O365, "SendEmailV2", {
                            "emailMessage/To": "finance@contoso.com",
                            "emailMessage/Subject": "Deal won: @{outputs('Get_opportunity')?['body/name']}",
                            "emailMessage/Body": f"<p>@{{outputs('Get_opportunity')?['body/name']}} for "
                                                 f"@{{{account}}} was closed as won, value @{{{value}}} EUR.</p>"})},
                        "else": {"actions": {}}}},
                "else": {"actions": {}}},
        }}, {DV: "cts_shareddataverse_salesfollowup", O365: "cts_sharedoffice365_salesfollowup"})


def overdue_digest():
    """Every Monday: open opportunities whose estimated close date has passed, as one table to the sales managers."""
    rows = "@outputs('List_overdue_opportunities')?['body/value']"
    return wrap({
        "triggers": {"Every_Monday_morning": {"type": "Recurrence", "recurrence": {
            "frequency": "Week", "interval": 1, "timeZone": "GMT Standard Time",
            "startTime": "2026-11-23T08:00:00",  # a time zone only applies together with a start time (Learn, Recurrence)
            "schedule": {"weekDays": ["Monday"], "hours": ["8"], "minutes": [0]}}}},
        "actions": {
            "List_overdue_opportunities": act(DV, "ListRecords", {
                "entityName": "opportunities",
                "$select": "name,estimatedvalue,estimatedclosedate,_ownerid_value",
                "$expand": "parentaccountid($select=name)",
                "$filter": "statecode eq 0 and estimatedclosedate lt @{formatDateTime(utcNow(), 'yyyy-MM-dd')}",
                # unique column last: a deterministic order (Learn, Page results by using OData)
                "$orderby": "estimatedclosedate asc,opportunityid asc",
                "$top": 50}),
            "Any_overdue": {"type": "If", "runAfter": {"List_overdue_opportunities": ["Succeeded"]},
                "expression": {"greater": [f"@length({rows[1:]})", 0]},
                "actions": {
                    "Overdue_table": {"type": "Table", "runAfter": {}, "inputs": {
                        "from": rows, "format": "HTML", "columns": [
                            {"header": "Opportunity", "value": "@item()?['name']"},
                            {"header": "Account", "value": "@item()?['parentaccountid']?['name']"},
                            {"header": "Owner", "value": "@item()?['_ownerid_value@OData.Community.Display.V1.FormattedValue']"},
                            {"header": "Estimated value", "value": "@item()?['estimatedvalue']"},
                            {"header": "Should have closed", "value": "@item()?['estimatedclosedate']"}]}},
                    "Send_digest": act(O365, "SendEmailV2", {
                        "emailMessage/To": "sales-managers@contoso.com",
                        "emailMessage/Subject": "Overdue opportunities: @{length(" + rows[1:] + ")}",
                        "emailMessage/Body": "<p>Open opportunities past their estimated close date:</p>"
                                             "@{body('Overdue_table')}"}, {"Overdue_table": ["Succeeded"]})},
                "else": {"actions": {}}},
        }}, {DV: "cts_shareddataverse_salesfollowup", O365: "cts_sharedoffice365_salesfollowup"})


FLOWS = [
    ("Wonopportunityfollowup", "Won opportunity follow-up", "00000000-0000-0000-0000-000000000511", deal_won_follow_up(), 0),
    ("Overdueopportunitiesdigest", "Overdue opportunities digest", "00000000-0000-0000-0000-000000000512", overdue_digest(), 0),
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
