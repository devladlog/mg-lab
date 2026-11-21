"""Writes the IT Invoice Intake solution (pac solution unpack layout): one flow, seven environment variables.

The flow reads a row of the staging list "Invoice Extractions" (what the AI Builder flow wrote, see demo.md)
and decides auto-post, review or reject with the same rules as src/invoicekit/triage.py.
Run: python tools/build_solution.py (idempotent). Solution.xml has <Managed>2</Managed> like episode 9.
"""
import json
import shutil
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
UNIQUE = "ITInvoiceIntake"
DISPLAY = "IT Invoice Intake"
TRIAGE_ID = "00000000-0000-0000-0000-000000001201"

ENV = {  # schema name: (display name, default value, description)
    "cts_FinanceSiteUrl": ("Finance site URL", "https://contoso.sharepoint.com/sites/Finance",
                           "SharePoint site that holds the Invoice Extractions and Invoices lists, no trailing slash"),
    "cts_ExtractionsList": ("Extractions list", "Invoice Extractions",
                            "Staging list: one row per invoice the AI Builder flow has read"),
    "cts_InvoicesList": ("Invoices list", "Invoices", "Posted invoices; also the source for the duplicate check"),
    "cts_ReviewerMailbox": ("Reviewer mailbox", "accounts@contoso.com", "Gets the invoices that need a person"),
    "cts_MinConfidence": ("Minimum confidence", "0.8",
                          "Every required field must reach this score (0 to 1) to be posted without a person"),
    "cts_AmountLimit": ("Amount limit", "5000", "Invoices above this total always go to a person"),
    "cts_MaxAgeDays": ("Maximum invoice age in days", "365", "Older invoice dates are sent to review"),
}
CONNS = {
    "shared_sharepointonline": ("cts_sharedsharepointonline_invoices", "SharePoint (invoice intake)"),
    "shared_office365": ("cts_sharedoffice365_invoices", "Office 365 Outlook (invoice intake)"),
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


def T(col: str) -> str:
    return f"triggerBody()?['{col}']"


def triage_flow() -> dict:
    trigger = {
        "type": "OpenApiConnection",
        "recurrence": {"interval": 1, "frequency": "Minute"},
        "splitOn": "@triggerOutputs()?['body/value']",
        "inputs": {"host": {**conn("shared_sharepointonline"), "operationId": "GetOnNewItems"},
                   "parameters": {"dataset": p("cts_FinanceSiteUrl"), "table": p("cts_ExtractionsList")},
                   "authentication": "@parameters('$authentication')"},
    }
    minconf, limit, maxage = (p(k)[1:] for k in ("cts_MinConfidence", "cts_AmountLimit", "cts_MaxAgeDays"))
    sp = {"type": "OpenApiConnection", "authentication": "@parameters('$authentication')"}
    req = ("InvoiceId", "VendorName", "InvoiceDate", "InvoiceTotal")
    inv, due, tot, sub, tax = T("InvoiceDate"), T("DueDate"), T("InvoiceTotal"), T("SubTotal"), T("TotalTax")
    base = "startOfDay(utcNow())"
    # No function is evaluated on null: (the simulator, and to be safe the service, don't short-circuit if/and/or)
    n = lambda e: f"coalesce({e}, 0)"                      # noqa: E731
    # 0.010001, not 0.01: 100 + 20 - 120.01 is 0.010000000000005 in floating point and must count as one cent
    st = f"add({n(sub)}, {n(tax)})"
    invs = f"coalesce({inv}, '2000-01-01')"
    dues = f"coalesce({due}, {invs})"
    actions = {
        "Get_possible_duplicates": {
            "type": "OpenApiConnection", "runAfter": {},
            "inputs": {"host": {**conn("shared_sharepointonline"), "operationId": "GetItems"},
                       "parameters": {
                           "dataset": p("cts_FinanceSiteUrl"), "table": p("cts_InvoicesList"),
                           "$filter": "VendorName eq '@{replace(coalesce(" + T("VendorName") + ", ''), '''', '''''')}' "
                                      "and InvoiceId eq '@{replace(coalesce(" + T("InvoiceId") + ", ''), '''', '''''')}'",
                           "$top": 1},
                       "authentication": "@parameters('$authentication')"}},
        "Is_not_an_invoice": {
            "type": "Compose", "runAfter": {"Get_possible_duplicates": ["Succeeded"]},
            "inputs": f"@and(empty({T('InvoiceId')}), empty({T('VendorName')}), equals({tot}, null))"},
        "Is_duplicate": {
            "type": "Compose", "runAfter": {"Is_not_an_invoice": ["Succeeded"]},
            "inputs": f"@and(not(empty({T('InvoiceId')})), greater(length(body('Get_possible_duplicates')?['value']), 0))"},
        "Has_missing_fields": {
            "type": "Compose", "runAfter": {"Is_duplicate": ["Succeeded"]},
            "inputs": "@or(" + ", ".join(f"empty({T(f)})" for f in req[:3]) + f", equals({tot}, null))"},
        "Has_low_confidence": {
            "type": "Compose", "runAfter": {"Has_missing_fields": ["Succeeded"]},
            "inputs": "@less(min(" + ", ".join(f"coalesce({T(f + 'Conf')}, 0)" for f in req) + f"), float({minconf}))"},
        "Total_does_not_add_up": {
            "type": "Compose", "runAfter": {"Has_low_confidence": ["Succeeded"]},
            "inputs": f"@and(not(equals({sub}, null)), not(equals({tax}, null)), not(equals({tot}, null)), "
                      f"greater(max(sub({st}, {n(tot)}), sub({n(tot)}, {st})), 0.010001))"},
        "Is_over_the_limit": {
            "type": "Compose", "runAfter": {"Total_does_not_add_up": ["Succeeded"]},
            "inputs": f"@and(not(equals({tot}, null)), greater({n(tot)}, float({limit})))"},
        "Has_suspicious_dates": {
            "type": "Compose", "runAfter": {"Is_over_the_limit": ["Succeeded"]},
            "inputs": f"@and(not(empty({inv})), or(greater(ticks({invs}), ticks(addDays({base}, 1))), "
                      f"less(ticks({invs}), ticks(addDays({base}, mul(-1, int({maxage}))))), "
                      f"less(ticks({dues}), ticks({invs}))))"},
        "Decision": {
            "type": "Compose", "runAfter": {"Has_suspicious_dates": ["Succeeded"]},
            "inputs": "@if(or(outputs('Is_not_an_invoice'), outputs('Is_duplicate')), 'reject', "
                      "if(or(outputs('Has_missing_fields'), outputs('Has_low_confidence'), outputs('Total_does_not_add_up'), "
                      "outputs('Is_over_the_limit'), outputs('Has_suspicious_dates')), 'review', 'auto-post'))"},
        "Record_decision": {
            "runAfter": {"Decision": ["Succeeded"]},
            "inputs": {"host": {**conn("shared_sharepointonline"), "operationId": "PatchItem"},
                       "parameters": {"dataset": p("cts_FinanceSiteUrl"), "table": p("cts_ExtractionsList"),
                                      "id": "@triggerBody()?['ID']", "item/Decision/Value": "@outputs('Decision')"},
                       "authentication": "@parameters('$authentication')"}, **{"type": "OpenApiConnection"}},
        "Route": {
            "type": "If", "runAfter": {"Record_decision": ["Succeeded"]},
            "expression": {"and": [{"equals": ["@outputs('Decision')", "auto-post"]}]},
            "actions": {
                "Post_invoice": {
                    "type": "OpenApiConnection", "runAfter": {},
                    "inputs": {"host": {**conn("shared_sharepointonline"), "operationId": "PostItem"},
                               "parameters": {"dataset": p("cts_FinanceSiteUrl"), "table": p("cts_InvoicesList"),
                                              "item/Title": "@triggerBody()?['InvoiceId']",
                                              "item/InvoiceId": "@triggerBody()?['InvoiceId']",
                                              "item/VendorName": "@triggerBody()?['VendorName']",
                                              "item/InvoiceDate": "@triggerBody()?['InvoiceDate']",
                                              "item/InvoiceTotal": "@triggerBody()?['InvoiceTotal']"},
                               "authentication": "@parameters('$authentication')"}}},
            "else": {"actions": {
                "Needs_a_person": {
                    "type": "If", "runAfter": {},
                    "expression": {"and": [{"equals": ["@outputs('Decision')", "review"]}]},
                    "actions": {
                        "Ask_reviewer": {
                            "type": "OpenApiConnection", "runAfter": {},
                            "inputs": {"host": {**conn("shared_office365"), "operationId": "SendEmailV2"},
                                       "parameters": {
                                           "emailMessage/To": p("cts_ReviewerMailbox"),
                                           "emailMessage/Subject": "Invoice " + "@{coalesce(triggerBody()?['InvoiceId'], '(no id)')}"
                                                                   " needs a look",
                                           "emailMessage/Body": "<p>Vendor: <b>@{coalesce(triggerBody()?['VendorName'], '(not read)')}</b>, "
                                                                "total @{coalesce(triggerBody()?['InvoiceTotal'], '(not read)')}.</p>"
                                                                "<p>Open the row in the Invoice Extractions list and compare it with the file.</p>",
                                           "emailMessage/Importance": "Normal"},
                                       "authentication": "@parameters('$authentication')"}}},
                    "else": {"actions": {}}}}},
        },
    }
    return flow_json(actions, "When_an_extraction_is_added", trigger,
                     list(ENV), ["shared_sharepointonline", "shared_office365"])


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
  <IntroducedVersion>1.0.0.0</IntroducedVersion>
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
    write_release(SRC / "solution", "1.0.0.0", {TRIAGE_ID: ("Triage invoice extraction", triage_flow())}, list(ENV))
    print("wrote", SRC / "solution")


if __name__ == "__main__":
    main()
