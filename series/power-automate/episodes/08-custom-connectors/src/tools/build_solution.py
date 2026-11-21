"""Writes src/solution/ (pac solution unpack layout) for the GitHub issue to IT request flow.

The flow definition is the source of truth in the repo; this script keeps the JSON, the connection references and
the environment variables consistent. Run: python tools/build_solution.py
The custom connector itself is not in the solution folder: demo.md creates it with
`pac connector create --solution-unique-name GitHubIntake`, then exports the solution to replace the placeholder
connector id below with the real one.
"""
import json
import re
from pathlib import Path

SOL = Path(__file__).resolve().parents[1] / "solution"
FLOW_ID = "00000000-0000-0000-0000-000000000801"
NAME = "GitHub issue to IT request"
UNIQUE = "GitHubIntake"
CONNECTOR_API = "shared_contoso-5fit-5fgithub-5f0000000000000801"   # placeholder: the export gives the real one

ENV = {  # schema name: (display name, default, description)
    "cts_HelpdeskSiteUrl": ("IT Helpdesk site URL", "https://contoso.sharepoint.com/sites/ITHelpdesk",
                            "Site that holds the IT Requests list (same variable as episode 6)"),
    "cts_GitHubOwner": ("GitHub owner", "contoso", "Account or organization that owns the repository"),
    "cts_GitHubRepo": ("GitHub repository", "it-automation", "Repository whose new issues become IT requests"),
}


def p(schema):
    return f"@parameters('{ENV[schema][0]} ({schema})')"


def conn(api):
    return {"apiId": f"/providers/Microsoft.PowerApps/apis/{api}", "connectionName": api}


ISSUE = "triggerBody()?['issue']"
actions = {
    "Label_names": {
        "type": "Select", "runAfter": {},
        "inputs": {"from": f"@coalesce({ISSUE}?['labels'], createArray())", "select": "@item()?['name']"},
    },
    "Is_urgent": {
        "type": "Compose", "runAfter": {"Label_names": ["Succeeded"]},
        "inputs": "@contains(body('Label_names'), 'urgent')",
    },
    "Create_IT_request": {
        "type": "OpenApiConnection", "runAfter": {"Is_urgent": ["Succeeded"]},
        "inputs": {
            "host": {**conn("shared_sharepointonline"), "operationId": "PostItem"},
            "parameters": {
                "dataset": p("cts_HelpdeskSiteUrl"),
                "table": "IT Requests",
                "item/Title": f"@take(concat('[GitHub] ', coalesce({ISSUE}?['title'], '')), 255)",
                "item/Category/Value": "Other",
                "item/Priority/Value": "@if(outputs('Is_urgent'), 'High', 'Normal')",
                "item/Status/Value": "New",
                "item/SourceLink": f"@{ISSUE}?['html_url']",
            },
            "authentication": "@parameters('$authentication')",
        },
    },
    "Comment_on_issue": {
        "type": "OpenApiConnection", "runAfter": {"Create_IT_request": ["Succeeded"]},
        "inputs": {
            "host": {**conn(CONNECTOR_API), "operationId": "AddIssueComment"},
            "parameters": {
                "owner": "@split(triggerBody()?['repository']?['full_name'], '/')[0]",
                "repo": "@split(triggerBody()?['repository']?['full_name'], '/')[1]",
                "issue_number": f"@{ISSUE}?['number']",
                "body/body": (f"Thanks, @{{{ISSUE}?['user']?['login']}}. Contoso IT is tracking this as IT request "
                              "#@{body('Create_IT_request')?['ID']}: @{body('Create_IT_request')?['{Link}']}"),
            },
            "authentication": "@parameters('$authentication')",
        },
    },
}

params = {"$connections": {"defaultValue": {}, "type": "Object"},
          "$authentication": {"defaultValue": {}, "type": "SecureObject"}}
for schema, (disp, default, desc) in ENV.items():
    params[f"{disp} ({schema})"] = {"defaultValue": default, "type": "String",
                                    "metadata": {"schemaName": schema, "description": desc}}

CONNS = {"shared_sharepointonline": ("cts_sharedsharepointonline_githubintake", "SharePoint (GitHub intake)"),
         CONNECTOR_API: ("cts_sharedcontosoitgithub_githubintake", "Contoso IT GitHub (GitHub intake)")}

flow = {"properties": {
    "connectionReferences": {api: {"runtimeSource": "embedded", "connection": {"connectionReferenceLogicalName": ln},
                                   "api": {"name": api}} for api, (ln, _) in CONNS.items()},
    "definition": {
        "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
        "contentVersion": "1.0.0.0",
        "parameters": params,
        "triggers": {"When_an_issue_is_opened": {
            "type": "OpenApiConnectionWebhook",
            "conditions": [{"expression": "@equals(triggerBody()?['action'], 'opened')"}],
            "inputs": {"host": {**conn(CONNECTOR_API), "operationId": "WhenAnIssueIsOpened"},
                       "parameters": {"owner": p("cts_GitHubOwner"), "repo": p("cts_GitHubRepo")},
                       "authentication": "@parameters('$authentication')"}}},
        "actions": actions,
    },
    "templateName": ""}, "schemaVersion": "1.0.0.0"}

wf = SOL / "Workflows"
wf.mkdir(parents=True, exist_ok=True)
json_name = f"GitHubissuetoITrequest-{FLOW_ID}.json"
(wf / json_name).write_text(json.dumps(flow, indent=2, ensure_ascii=False), encoding="utf-8")
(wf / f"{json_name}.data.xml").write_text(f"""﻿<?xml version="1.0" encoding="utf-8"?>
<Workflow WorkflowId="{{{FLOW_ID}}}" Name="{NAME}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <JsonFileName>/Workflows/{json_name}</JsonFileName>
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
    <LocalizedName languagecode="1033" description="{NAME}" />
  </LocalizedNames>
</Workflow>""", encoding="utf-8")

for schema, (disp, default, desc) in ENV.items():
    d = SOL / "environmentvariabledefinitions" / schema
    d.mkdir(parents=True, exist_ok=True)
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

other = SOL / "Other"
other.mkdir(parents=True, exist_ok=True)
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

# Solution.xml: start from episode 6's (same publisher), change the name and the root components
ep6 = Path(__file__).resolve().parents[3] / "06-microsoft-teams-integration" / "src" / "solution" / "Other" / "Solution.xml"
xml = (ep6 if ep6.exists() else other / "Solution.xml").read_text(encoding="utf-8-sig")
xml = re.sub(r"<UniqueName>(ITOnCall|GitHubIntake)</UniqueName>", f"<UniqueName>{UNIQUE}</UniqueName>", xml, count=1)
xml = re.sub(r'description="(IT On-call|GitHub intake)"', 'description="GitHub intake"', xml, count=1)
roots = "\n".join([f'      <RootComponent type="29" id="{{{FLOW_ID}}}" behavior="0" />'] +
                  [f'      <RootComponent type="380" schemaName="{s}" behavior="0" />' for s in sorted(ENV)])
xml = re.sub(r"<RootComponents>.*?</RootComponents>", f"<RootComponents>\n{roots}\n    </RootComponents>", xml, flags=re.S)
(other / "Solution.xml").write_text("﻿" + xml, encoding="utf-8")
print("wrote", SOL)
