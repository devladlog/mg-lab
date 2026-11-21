"""Writes the Archive done IT requests flow twice: our first draft (src/drafts) and the tuned one (src/solution).

The flow archives IT requests that have been Done for more than 30 days (Status = Archived) every night. Episode 1's
IT Requests list has Status New / Triaged / Done; this adds the choice Archived and a DoneOn date column.

Run: python tools/build_solution.py
"""
import json
import shutil
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
UNIQUE, DISPLAY = "ITHousekeeping", "IT Housekeeping"
FLOW_ID = "00000000-0000-0000-0000-000000001001"
FLOW_NAME = "Archive done IT requests"

ENV = {
    "cts_ITSiteUrl": ("IT site URL", "https://contoso.sharepoint.com/sites/ITHelpdesk", "Site that holds the IT Requests list"),
    "cts_ITRequestsList": ("IT Requests list", "IT Requests", "Name of the IT Requests list"),
    "cts_ArchiveAfterDays": ("Archive after days", "30", "Days a request stays Done before it is archived"),
    "cts_ServiceDeskMailbox": ("Service desk mailbox", "servicedesk@contoso.com", "Gets the nightly summary"),
}
CONNS = {
    "shared_sharepointonline": ("cts_sharedsharepointonline_ithousekeeping", "SharePoint (IT housekeeping)"),
    "shared_office365": ("cts_sharedoffice365_ithousekeeping", "Office 365 Outlook (IT housekeeping)"),
}


def p(schema):
    return f"@parameters('{ENV[schema][0]} ({schema})')"


def conn(api):
    return {"apiId": f"/providers/Microsoft.PowerApps/apis/{api}", "connectionName": api}


def sp(operation, **params):
    return {"host": {**conn("shared_sharepointonline"), "operationId": operation},
            "parameters": {"dataset": p("cts_ITSiteUrl"), "table": p("cts_ITRequestsList"), **params},
            "authentication": "@parameters('$authentication')"}


CUTOFF = {"type": "Compose", "runAfter": {},
          "inputs": f"@formatDateTime(addDays(utcNow(), mul(-1, int({p('cts_ArchiveAfterDays')[1:]}))), 'yyyy-MM-ddTHH:mm:ssZ')"}
ARCHIVE_ITEM = lambda item_id: {  # noqa: E731
    "type": "OpenApiConnection", "runAfter": {},
    "inputs": sp("PatchItem", id=item_id, **{"item/Title": "@items('Apply_to_each')?['Title']", "item/Status/Value": "Archived"})}


def summary(count_expr):
    return {"type": "OpenApiConnection", "inputs": {
        "host": {**conn("shared_office365"), "operationId": "SendEmailV2"},
        "parameters": {"emailMessage/To": p("cts_ServiceDeskMailbox"),
                       "emailMessage/Subject": f"IT housekeeping: @{{{count_expr}}} requests archived",
                       "emailMessage/Body": f"<p>@{{{count_expr}}} requests were Done for @{{parameters('Archive after days (cts_ArchiveAfterDays)')}} days or more and are now Archived.</p>",
                       "emailMessage/Importance": "Normal"},
        "authentication": "@parameters('$authentication')"}}


TRIGGER = {"type": "Recurrence", "recurrence": {
    "frequency": "Day", "interval": 1, "timeZone": "GMT Standard Time", "schedule": {"hours": ["2"], "minutes": [0]}}}


def slow_actions():
    """Draft 1: read everything, then look at every item one by one."""
    return {
        "Cutoff": CUTOFF,
        "Get_all_requests": {"type": "OpenApiConnection", "runAfter": {"Cutoff": ["Succeeded"]},
                             "runtimeConfiguration": {"paginationPolicy": {"minimumItemCount": 5000}},
                             "inputs": sp("GetItems")},
        "Init_archived_count": {"type": "InitializeVariable", "runAfter": {"Get_all_requests": ["Succeeded"]},
                                "inputs": {"variables": [{"name": "archivedCount", "type": "integer", "value": 0}]}},
        "Apply_to_each": {
            "type": "Foreach", "runAfter": {"Init_archived_count": ["Succeeded"]},
            "foreach": "@body('Get_all_requests')?['value']",
            "actions": {
                "Get_item_again": {"type": "OpenApiConnection", "runAfter": {},
                                   "inputs": sp("GetItem", id="@items('Apply_to_each')?['ID']")},
                "Is_done_and_old": {
                    "type": "If", "runAfter": {"Get_item_again": ["Succeeded"]},
                    "expression": {"and": [
                        {"equals": ["@body('Get_item_again')?['Status']?['Value']", "Done"]},
                        {"less": ["@ticks(coalesce(body('Get_item_again')?['DoneOn'], '9999-12-31T00:00:00Z'))",
                                  "@ticks(outputs('Cutoff'))"]}]},
                    "actions": {
                        "Archive_item": ARCHIVE_ITEM("@items('Apply_to_each')?['ID']"),
                        "Count_archived": {"type": "IncrementVariable", "runAfter": {"Archive_item": ["Succeeded"]},
                                           "inputs": {"name": "archivedCount", "value": 1}}},
                    "else": {"actions": {}}}}},
        "Send_summary": {**summary("variables('archivedCount')"), "runAfter": {"Apply_to_each": ["Succeeded"]}},
    }


def fast_actions():
    """Final: the list does the filtering, the loop only writes, several items at a time."""
    return {
        "Cutoff": CUTOFF,
        "Get_done_requests": {
            "type": "OpenApiConnection", "runAfter": {"Cutoff": ["Succeeded"]},
            "runtimeConfiguration": {"paginationPolicy": {"minimumItemCount": 5000}},
            "inputs": sp("GetItems", **{"$filter": "Status eq 'Done' and DoneOn lt '@{outputs('Cutoff')}'", "$top": 5000})},
        "Any_to_archive": {
            "type": "If", "runAfter": {"Get_done_requests": ["Succeeded"]},
            "expression": {"and": [{"greater": ["@length(body('Get_done_requests')?['value'])", 0]}]},
            "actions": {
                "Apply_to_each": {
                    "type": "Foreach", "runAfter": {},
                    "foreach": "@body('Get_done_requests')?['value']",
                    "runtimeConfiguration": {"concurrency": {"repetitions": 20}},
                    "actions": {"Archive_item": ARCHIVE_ITEM("@items('Apply_to_each')?['ID']")}},
                "Send_summary": {**summary("length(body('Get_done_requests')?['value'])"),
                                 "runAfter": {"Apply_to_each": ["Succeeded"]}}},
            "else": {"actions": {}}},
    }


def flow_json(actions, used_env):
    params = {"$connections": {"defaultValue": {}, "type": "Object"},
              "$authentication": {"defaultValue": {}, "type": "SecureObject"}}
    for schema in used_env:
        disp, default, desc = ENV[schema]
        params[f"{disp} ({schema})"] = {"defaultValue": default, "type": "String",
                                        "metadata": {"schemaName": schema, "description": desc}}
    return {"properties": {
        "connectionReferences": {api: {"runtimeSource": "embedded", "connection": {"connectionReferenceLogicalName": ln},
                                       "api": {"name": api}} for api, (ln, _) in CONNS.items()},
        "definition": {
            "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
            "contentVersion": "1.0.0.0", "parameters": params,
            "triggers": {"Every_night_at_2": TRIGGER}, "actions": actions},
        "templateName": ""}, "schemaVersion": "1.0.0.0"}


def write_solution(folder: Path, flow: dict):
    if folder.exists():
        shutil.rmtree(folder)
    (folder / "Workflows").mkdir(parents=True)
    file = f"{FLOW_NAME.replace(' ', '')}-{FLOW_ID}.json"
    (folder / "Workflows" / file).write_text(json.dumps(flow, indent=2, ensure_ascii=False), encoding="utf-8")
    (folder / "Workflows" / f"{file}.data.xml").write_text(f"""﻿<?xml version="1.0" encoding="utf-8"?>
<Workflow WorkflowId="{{{FLOW_ID}}}" Name="{FLOW_NAME}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <JsonFileName>/Workflows/{file}</JsonFileName>
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
    <LocalizedName languagecode="1033" description="{FLOW_NAME}" />
  </LocalizedNames>
</Workflow>""", encoding="utf-8")
    for schema, (disp, default, desc) in ENV.items():
        d = folder / "environmentvariabledefinitions" / schema
        d.mkdir(parents=True)
        (d / "environmentvariabledefinition.xml").write_text(f"""<environmentvariabledefinition schemaname="{schema}">
  <defaultvalue>{default}</defaultvalue>
  <description default="{desc}">
    <label description="{desc}" languagecode="1033" />
  </description>
  <displayname default="{disp}">
    <label description="{disp}" languagecode="1033" />
  </displayname>
  <introducedversion>1.0.0.0</introducedversion>
  <iscustomizable>1</iscustomizable>
  <isrequired>0</isrequired>
  <secretstore>0</secretstore>
  <type>100000000</type>
</environmentvariabledefinition>""", encoding="utf-8")
    other = folder / "Other"
    other.mkdir()
    refs = "\n".join(f"""    <connectionreference connectionreferencelogicalname="{ln}">
      <connectionreferencedisplayname>{disp}</connectionreferencedisplayname>
      <connectorid>/providers/Microsoft.PowerApps/apis/{api}</connectorid>
      <iscustomizable>1</iscustomizable>
      <statecode>0</statecode>
      <statuscode>1</statuscode>
    </connectionreference>""" for api, (ln, disp) in CONNS.items())
    (other / "Customizations.xml").write_text(f"""﻿<?xml version="1.0" encoding="utf-8"?>
<ImportExportXml xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Entities />
  <Roles />
  <Workflows />
  <FieldSecurityProfiles />
  <Templates />
  <EntityMaps />
  <EntityRelationships />
  <OrganizationSettings />
  <optionsets />
  <CustomControls />
  <EntityDataProviders />
  <connectionreferences>
{refs}
  </connectionreferences>
  <Languages>
    <Language>1033</Language>
  </Languages>
</ImportExportXml>""", encoding="utf-8")
    roots = "\n".join([f'      <RootComponent type="29" id="{{{FLOW_ID}}}" behavior="0" />'] +
                      [f'      <RootComponent type="380" schemaName="{s}" behavior="0" />' for s in sorted(ENV)])
    (other / "Solution.xml").write_text(f"""﻿<?xml version="1.0" encoding="utf-8"?>
<ImportExportXml version="9.1.0.643" SolutionPackageVersion="9.1" languagecode="1033" generatedBy="CrmLive" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <SolutionManifest>
    <UniqueName>{UNIQUE}</UniqueName>
    <LocalizedNames>
      <LocalizedName description="{DISPLAY}" languagecode="1033" />
    </LocalizedNames>
    <Descriptions />
    <Version>1.0.0.0</Version>
    <!-- Solution Package Type: Unmanaged(0)/Managed(1)/Both(2) -->
    <Managed>0</Managed>
    <Publisher>
      <UniqueName>contoso</UniqueName>
      <LocalizedNames>
        <LocalizedName description="contoso" languagecode="1033" />
      </LocalizedNames>
      <Descriptions>
        <Description description="contoso" languagecode="1033" />
      </Descriptions>
      <EMailAddress xsi:nil="true"></EMailAddress>
      <SupportingWebsiteUrl xsi:nil="true"></SupportingWebsiteUrl>
      <CustomizationPrefix>cts</CustomizationPrefix>
      <CustomizationOptionValuePrefix>44446</CustomizationOptionValuePrefix>
      <Addresses />
    </Publisher>
    <RootComponents>
{roots}
    </RootComponents>
    <MissingDependencies />
  </SolutionManifest>
</ImportExportXml>""", encoding="utf-8")


def main():
    write_solution(SRC / "solution", flow_json(fast_actions(), list(ENV)))
    drafts = SRC / "drafts"
    drafts.mkdir(exist_ok=True)
    (drafts / "slow-archive-done-requests.json").write_text(
        json.dumps(flow_json(slow_actions(), list(ENV)), indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", SRC / "solution", "and", drafts / "slow-archive-done-requests.json")


if __name__ == "__main__":
    main()
