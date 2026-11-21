"""Writes the two releases of the IT Request Notices solution (pac solution unpack layout).

  src/releases/1.0.0.0/   first release: two flows, five environment variables
  src/solution/           current release 1.1.0.0: the weekly summary is gone (the daily digest from
                          episode 1 covers it), so its flow and its environment variable are removed

The flow JSON is the source of truth in the repo; this script only keeps the JSON, the connection
references, the environment variables and Solution.xml consistent. Run: python tools/build_solution.py

The folders are written the way `pac solution unpack --packagetype Both` writes Solution.xml
(<Managed>2</Managed>). With Unmanaged only (0), `pac solution pack --packagetype Managed` fails with
"Solution package type did not match requested type" (see tests/test_pac.py).
"""
import json
import shutil
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
UNIQUE = "ITRequestNotices"
DISPLAY = "IT Request Notices"
ACK_ID = "00000000-0000-0000-0000-000000000901"
STALE_ID = "00000000-0000-0000-0000-000000000902"

ENV = {  # schema name: (display name, default value, description)
    "cts_ITSiteUrl": ("IT site URL", "https://contoso.sharepoint.com/sites/ITHelpdesk",
                      "SharePoint site that holds the IT Requests list, no trailing slash"),
    "cts_ITRequestsList": ("IT Requests list", "IT Requests", "Name of the IT Requests list"),
    "cts_ServiceDeskMailbox": ("Service desk mailbox", "servicedesk@contoso.com",
                               "Gets a copy of every acknowledgement"),
    "cts_EnvironmentLabel": ("Environment label", "DEV",
                             "Short name of the environment (DEV, TEST, PROD), shown at the end of every subject"),
    "cts_StaleDays": ("Stale after days", "5", "Days without a change after which a triaged request is stale"),
}
CONNS = {
    "shared_sharepointonline": ("cts_sharedsharepointonline_itnotices", "SharePoint (IT notices)"),
    "shared_office365": ("cts_sharedoffice365_itnotices", "Office 365 Outlook (IT notices)"),
}


def p(schema: str) -> str:
    return f"@parameters('{ENV[schema][0]} ({schema})')"


def conn(api: str) -> dict:
    return {"apiId": f"/providers/Microsoft.PowerApps/apis/{api}", "connectionName": api}


def flow_json(actions: dict, trigger_name: str, trigger: dict, used_env: list[str], used_conns: list[str]) -> dict:
    params = {"$connections": {"defaultValue": {}, "type": "Object"},
              "$authentication": {"defaultValue": {}, "type": "SecureObject"}}
    for schema in used_env:
        disp, default, desc = ENV[schema]
        params[f"{disp} ({schema})"] = {"defaultValue": default, "type": "String",
                                        "metadata": {"schemaName": schema, "description": desc}}
    return {"properties": {
        "connectionReferences": {api: {"runtimeSource": "embedded",
                                       "connection": {"connectionReferenceLogicalName": CONNS[api][0]},
                                       "api": {"name": api}} for api in used_conns},
        "definition": {
            "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
            "contentVersion": "1.0.0.0",
            "parameters": params,
            "triggers": {trigger_name: trigger},
            "actions": actions},
        "templateName": ""}, "schemaVersion": "1.0.0.0"}


def acknowledge_flow() -> dict:
    trigger = {
        "type": "OpenApiConnection",
        "recurrence": {"interval": 1, "frequency": "Minute"},
        "splitOn": "@triggerOutputs()?['body/value']",
        "conditions": [{"expression": "@not(startsWith(toLower(coalesce(triggerBody()?['Title'], '')), '[test]'))"}],
        "inputs": {"host": {**conn("shared_sharepointonline"), "operationId": "GetOnNewItems"},
                   "parameters": {"dataset": p("cts_ITSiteUrl"), "table": p("cts_ITRequestsList")},
                   "authentication": "@parameters('$authentication')"},
    }
    actions = {
        "Send_acknowledgement": {
            "type": "OpenApiConnection",
            "runAfter": {},
            "inputs": {
                "host": {**conn("shared_office365"), "operationId": "SendEmailV2"},
                "parameters": {
                    "emailMessage/To": "@triggerBody()?['Author']?['Email']",
                    "emailMessage/Cc": p("cts_ServiceDeskMailbox"),
                    "emailMessage/Subject": "IT request #@{triggerBody()?['ID']} received [@{parameters('Environment label (cts_EnvironmentLabel)')}]",
                    "emailMessage/Body": "<p>We have your request <b>@{triggerBody()?['Title']}</b>. "
                                         "The service desk will triage it today.</p>",
                    "emailMessage/Importance": "Normal",
                },
                "authentication": "@parameters('$authentication')",
            },
        }
    }
    return flow_json(actions, "When_an_IT_request_is_created", trigger,
                     ["cts_ITSiteUrl", "cts_ITRequestsList", "cts_ServiceDeskMailbox", "cts_EnvironmentLabel"],
                     ["shared_sharepointonline", "shared_office365"])


def stale_flow() -> dict:
    trigger = {"type": "Recurrence", "recurrence": {
        "frequency": "Week", "interval": 1, "timeZone": "GMT Standard Time",
        "schedule": {"weekDays": ["Monday"], "hours": ["7"], "minutes": [0]}}}
    actions = {
        "Stale_cutoff": {
            "type": "Compose", "runAfter": {},
            "inputs": f"@formatDateTime(addDays(utcNow(), mul(-1, int({p('cts_StaleDays')[1:]}))), 'yyyy-MM-ddTHH:mm:ssZ')"},
        "Get_stale_requests": {
            "type": "OpenApiConnection",
            "runAfter": {"Stale_cutoff": ["Succeeded"]},
            "inputs": {
                "host": {**conn("shared_sharepointonline"), "operationId": "GetItems"},
                "parameters": {"dataset": p("cts_ITSiteUrl"), "table": p("cts_ITRequestsList"),
                               "$filter": "Status eq 'Triaged' and Modified lt '@{outputs('Stale_cutoff')}'",
                               "$top": 500},
                "authentication": "@parameters('$authentication')"}},
        "Any_stale": {
            "type": "If",
            "runAfter": {"Get_stale_requests": ["Succeeded"]},
            "expression": {"and": [{"greater": ["@length(body('Get_stale_requests')?['value'])", 0]}]},
            "actions": {
                "Send_stale_summary": {
                    "type": "OpenApiConnection", "runAfter": {},
                    "inputs": {
                        "host": {**conn("shared_office365"), "operationId": "SendEmailV2"},
                        "parameters": {
                            "emailMessage/To": p("cts_ServiceDeskMailbox"),
                            "emailMessage/Subject": "@{length(body('Get_stale_requests')?['value'])} triaged IT requests are stale",
                            "emailMessage/Body": "<p>Triaged and not touched for @{parameters('Stale after days (cts_StaleDays)')} days or more.</p>",
                            "emailMessage/Importance": "Normal"},
                        "authentication": "@parameters('$authentication')"}}},
            "else": {"actions": {}}},
    }
    return flow_json(actions, "Every_Monday_at_7", trigger,
                     ["cts_ITSiteUrl", "cts_ITRequestsList", "cts_ServiceDeskMailbox", "cts_StaleDays"],
                     ["shared_sharepointonline", "shared_office365"])


def solution_xml(version: str, flows: dict[str, str], env: list[str]) -> str:
    roots = "\n".join([f'      <RootComponent type="29" id="{{{fid}}}" behavior="0" />' for fid in flows] +
                      [f'      <RootComponent type="380" schemaName="{s}" behavior="0" />' for s in sorted(env)])
    return f"""﻿<?xml version="1.0" encoding="utf-8"?>
<ImportExportXml version="9.1.0.643" SolutionPackageVersion="9.1" languagecode="1033" generatedBy="CrmLive" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <SolutionManifest>
    <UniqueName>{UNIQUE}</UniqueName>
    <LocalizedNames>
      <LocalizedName description="{DISPLAY}" languagecode="1033" />
    </LocalizedNames>
    <Descriptions />
    <Version>{version}</Version>
    <!-- Solution Package Type: Unmanaged(0)/Managed(1)/Both(2) -->
    <Managed>2</Managed>
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
</ImportExportXml>"""


def write_release(folder: Path, version: str, flows: dict[str, tuple[str, dict]], env: list[str]) -> None:
    if folder.exists():
        shutil.rmtree(folder)
    wf = folder / "Workflows"
    wf.mkdir(parents=True)
    for fid, (name, body) in flows.items():
        file = f"{name.replace(' ', '')}-{fid}.json"
        (wf / file).write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
        (wf / f"{file}.data.xml").write_text(f"""﻿<?xml version="1.0" encoding="utf-8"?>
<Workflow WorkflowId="{{{fid}}}" Name="{name}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
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
  <StateCode>1</StateCode>
  <StatusCode>2</StatusCode>
  <RunAs>1</RunAs>
  <IsTransacted>1</IsTransacted>
  <IntroducedVersion>{version if fid == STALE_ID else '1.0.0.0'}</IntroducedVersion>
  <IsCustomizable>1</IsCustomizable>
  <BusinessProcessType>0</BusinessProcessType>
  <IsCustomProcessingStepAllowedForOtherPublishers>1</IsCustomProcessingStepAllowedForOtherPublishers>
  <PrimaryEntity>none</PrimaryEntity>
  <LocalizedNames>
    <LocalizedName languagecode="1033" description="{name}" />
  </LocalizedNames>
</Workflow>""", encoding="utf-8")
    for schema in env:
        disp, default, desc = ENV[schema]
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
    (other / "Solution.xml").write_text(solution_xml(version, {fid: n for fid, (n, _) in flows.items()}, env),
                                        encoding="utf-8")


def main() -> None:
    ack = ("Acknowledge IT request", acknowledge_flow())
    stale = ("Weekly stale summary", stale_flow())
    base_env = ["cts_ITSiteUrl", "cts_ITRequestsList", "cts_ServiceDeskMailbox", "cts_EnvironmentLabel"]
    write_release(SRC / "releases" / "1.0.0.0", "1.0.0.0", {ACK_ID: ack, STALE_ID: stale}, base_env + ["cts_StaleDays"])
    write_release(SRC / "solution", "1.1.0.0", {ACK_ID: ack}, base_env)
    print("wrote", SRC / "releases" / "1.0.0.0", "and", SRC / "solution")


if __name__ == "__main__":
    main()
