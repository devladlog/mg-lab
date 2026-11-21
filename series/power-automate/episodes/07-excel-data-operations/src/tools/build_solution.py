"""Writes src/solution/ (pac solution unpack layout) for the Supplier price list import flow.

The flow definition is the source of truth in the repo; this script only exists so the JSON, the
connection references and the environment variables stay consistent. Run: python tools/build_solution.py
"""
import json
from pathlib import Path

SOL = Path(__file__).resolve().parents[1] / "solution"
FLOW_ID = "00000000-0000-0000-0000-000000000701"
NAME = "Supplier price list import"
UNIQUE = "PriceLists"

ENV = {  # schema name: (display name, default, description)
    "cts_PurchasingSiteUrl": ("Purchasing site URL", "https://contoso.sharepoint.com/sites/Purchasing",
                              "Purchasing site, no trailing slash"),
    "cts_PriceListsLibrary": ("Price lists library", "Price lists", "Library where suppliers' workbooks are saved"),
    "cts_PriceListsDriveId": ("Price lists drive ID", "b!00000000000000000000000000000000000000000000000000000701",
                              "Drive ID of the Price lists library (Excel connector Document Library value)"),
    "cts_DocumentsDriveId": ("Documents drive ID", "b!00000000000000000000000000000000000000000000000000000702",
                             "Drive ID of the Documents library with the catalogue and the Scripts folder"),
    "cts_UpsertScriptId": ("Upsert prices script", "Upsert prices.osts",
                           "Office Script file (.osts) in the Documents library, Scripts folder"),
    "cts_PurchasingMailbox": ("Purchasing mailbox", "purchasing@contoso.com", "Where the import summary goes"),
}


def p(schema):
    return f"@parameters('{ENV[schema][0]} ({schema})')"


def conn(api):
    return {"apiId": f"/providers/Microsoft.PowerApps/apis/{api}", "connectionName": api}


SKU = "toUpper(trim(coalesce(item()?['Item No_x002e_'], '')))"
PRICE = "trim(coalesce(item()?['Unit price'], ''))"
VALID = "take(coalesce(item()?['Valid from'], ''), 10)"
PROBLEM = (
    f"@if(empty({SKU}), 'Missing item number', "
    f"if(contains({PRICE}, ','), 'Price has a comma: use a number cell', "
    f"if(not(isFloat({PRICE})), 'Price is not a number', "
    f"if(lessOrEquals(float(if(isFloat({PRICE}), {PRICE}, '0')), 0), 'Price must be more than zero', "
    f"if(not(equals(indexOf({VALID}, '-'), 4)), 'Valid from is not a date', '')))))"
)

actions = {
    "List_price_rows": {
        "type": "OpenApiConnection",
        "runAfter": {},
        "runtimeConfiguration": {"paginationPolicy": {"minimumItemCount": 5000}},
        "inputs": {
            "host": {**conn("shared_excelonlinebusiness"), "operationId": "GetItems"},
            "parameters": {
                "source": p("cts_PurchasingSiteUrl"),
                "drive": p("cts_PriceListsDriveId"),
                "file": "@triggerBody()?['{Identifier}']",
                "table": "Prices",
                "dateTimeFormat": "ISO 8601",
            },
            "authentication": "@parameters('$authentication')",
        },
    },
    "Too_many_rows": {
        "type": "If",
        "runAfter": {"List_price_rows": ["Succeeded"]},
        "expression": {"and": [{"greaterOrEquals": ["@length(body('List_price_rows')?['value'])", 5000]}]},
        "actions": {
            "Stop_not_all_rows_read": {
                "type": "Terminate",
                "inputs": {"runStatus": "Failed", "runError": {
                    "code": "TooManyRows",
                    "message": "@{length(body('List_price_rows')?['value'])} rows read: the pagination threshold is 5000, the file may have more. Split the file."}},
            }
        },
        "else": {"actions": {}},
    },
    "Shape_rows": {
        "type": "Select",
        "runAfter": {"Too_many_rows": ["Succeeded"]},
        "inputs": {
            "from": "@body('List_price_rows')?['value']",
            "select": {
                "sku": f"@{SKU}",
                "description": "@trim(coalesce(item()?['Description'], ''))",
                "priceText": f"@{PRICE}",
                "validFrom": f"@{VALID}",
                "problem": PROBLEM,
            },
        },
    },
    "Valid_rows": {
        "type": "Query",
        "runAfter": {"Shape_rows": ["Succeeded"]},
        "inputs": {"from": "@body('Shape_rows')", "where": "@empty(item()?['problem'])"},
    },
    "Rejected_rows": {
        "type": "Query",
        "runAfter": {"Shape_rows": ["Succeeded"]},
        "inputs": {"from": "@body('Shape_rows')", "where": "@not(empty(item()?['problem']))"},
    },
    "Prices_for_script": {
        "type": "Select",
        "runAfter": {"Valid_rows": ["Succeeded"]},
        "inputs": {
            "from": "@body('Valid_rows')",
            "select": {"sku": "@item()?['sku']", "description": "@item()?['description']",
                       "price": "@float(item()?['priceText'])", "validFrom": "@item()?['validFrom']"},
        },
    },
    "Upsert_catalogue": {
        "type": "OpenApiConnection",
        "runAfter": {"Prices_for_script": ["Succeeded"]},
        "inputs": {
            "host": {**conn("shared_excelonlinebusiness"), "operationId": "RunScriptProdV2"},
            "parameters": {
                "source": p("cts_PurchasingSiteUrl"),
                "drive": p("cts_DocumentsDriveId"),
                "file": "Purchasing catalogue.xlsx",
                "scriptSource": p("cts_PurchasingSiteUrl"),
                "scriptDrive": p("cts_DocumentsDriveId"),
                "scriptId": p("cts_UpsertScriptId"),
                "ScriptParameters/prices": "@body('Prices_for_script')",
                "ScriptParameters/supplier": "Fabrikam",
                "ScriptParameters/sourceFile": "@triggerBody()?['{FilenameWithExtension}']",
            },
            "authentication": "@parameters('$authentication')",
        },
    },
    "Any_rejected": {
        "type": "If",
        "runAfter": {"Upsert_catalogue": ["Succeeded"], "Rejected_rows": ["Succeeded"]},
        "expression": {"and": [{"greater": ["@length(body('Rejected_rows'))", 0]}]},
        "actions": {
            "Rejected_csv": {
                "type": "Table",
                "runAfter": {},
                "inputs": {"from": "@body('Rejected_rows')", "format": "CSV", "columns": [
                    {"header": "Item No.", "value": "@item()?['sku']"},
                    {"header": "Description", "value": "@item()?['description']"},
                    {"header": "Unit price", "value": "@item()?['priceText']"},
                    {"header": "Valid from", "value": "@item()?['validFrom']"},
                    {"header": "Problem", "value": "@item()?['problem']"}]},
            },
            "Save_rejected_rows": {
                "type": "OpenApiConnection",
                "runAfter": {"Rejected_csv": ["Succeeded"]},
                "inputs": {
                    "host": {**conn("shared_sharepointonline"), "operationId": "CreateFile"},
                    "parameters": {
                        "dataset": p("cts_PurchasingSiteUrl"),
                        "folderPath": "/Price lists/Rejected",
                        "name": "@{triggerBody()?['{Name}']}-rejected.csv",
                        "body": "@body('Rejected_csv')",
                    },
                    "authentication": "@parameters('$authentication')",
                },
            },
        },
        "else": {"actions": {}},
    },
    "Big_changes_table": {
        "type": "Table",
        "runAfter": {"Upsert_catalogue": ["Succeeded"]},
        "inputs": {"from": "@body('Upsert_catalogue')?['result']?['bigChanges']", "format": "HTML", "columns": [
            {"header": "SKU", "value": "@item()?['sku']"},
            {"header": "Description", "value": "@item()?['description']"},
            {"header": "Old price", "value": "@item()?['oldPrice']"},
            {"header": "New price", "value": "@item()?['newPrice']"},
            {"header": "Change %", "value": "@item()?['changePercent']"}]},
    },
    "Send_summary": {
        "type": "OpenApiConnection",
        "runAfter": {"Any_rejected": ["Succeeded"], "Big_changes_table": ["Succeeded"]},
        "inputs": {
            "host": {**conn("shared_office365"), "operationId": "SendEmailV2"},
            "parameters": {
                "emailMessage/To": p("cts_PurchasingMailbox"),
                "emailMessage/Subject": "Price list @{triggerBody()?['{FilenameWithExtension}']}: @{body('Upsert_catalogue')?['result']?['updated']} updated, @{body('Upsert_catalogue')?['result']?['inserted']} new, @{length(body('Rejected_rows'))} rejected",
                "emailMessage/Body": (
                    "<p>@{length(body('List_price_rows')?['value'])} rows read from "
                    "<a href=\"@{triggerBody()?['{Link}']}\">@{triggerBody()?['{FilenameWithExtension}']}</a>.</p>"
                    "<ul><li>New: @{body('Upsert_catalogue')?['result']?['inserted']}</li>"
                    "<li>Updated: @{body('Upsert_catalogue')?['result']?['updated']}</li>"
                    "<li>Unchanged: @{body('Upsert_catalogue')?['result']?['unchanged']}</li>"
                    "<li>Listed twice in the file (last row used): @{body('Upsert_catalogue')?['result']?['duplicatesInFile']}</li>"
                    "<li>Extra catalogue rows with the same SKU (all updated): @{body('Upsert_catalogue')?['result']?['duplicateRowsInCatalogue']}</li>"
                    "<li>Rejected (see Price lists/Rejected): @{length(body('Rejected_rows'))}</li></ul>"
                    "<p>Price changes over 20 %, please check:</p>@{body('Big_changes_table')}"
                ),
                "emailMessage/Importance": "Normal",
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

CONNS = {"shared_sharepointonline": ("cts_sharedsharepointonline_pricelists", "SharePoint (price lists)"),
         "shared_excelonlinebusiness": ("cts_sharedexcelonlinebusiness_pricelists", "Excel Online (Business) (price lists)"),
         "shared_office365": ("cts_sharedoffice365_pricelists", "Office 365 Outlook (price lists)")}

flow = {"properties": {
    "connectionReferences": {api: {"runtimeSource": "embedded", "connection": {"connectionReferenceLogicalName": ln},
                                   "api": {"name": api}} for api, (ln, _) in CONNS.items()},
    "definition": {
        "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
        "contentVersion": "1.0.0.0",
        "parameters": params,
        "triggers": {"When_a_price_list_is_added": {
            "type": "OpenApiConnection",
            "recurrence": {"interval": 5, "frequency": "Minute"},
            "splitOn": "@triggerOutputs()?['body/value']",
            "conditions": [{"expression": "@and(endsWith(toLower(triggerBody()?['{FilenameWithExtension}']), '.xlsx'), not(equals(triggerBody()?['{IsFolder}'], true)))"}],
            "inputs": {"host": {**conn("shared_sharepointonline"), "operationId": "GetOnNewFileItems"},
                       "parameters": {"dataset": p("cts_PurchasingSiteUrl"), "table": p("cts_PriceListsLibrary")},
                       "authentication": "@parameters('$authentication')"}}},
        "actions": actions,
    },
    "templateName": ""}, "schemaVersion": "1.0.0.0"}

wf = SOL / "Workflows"
wf.mkdir(parents=True, exist_ok=True)
json_name = f"Supplierpricelistimport-{FLOW_ID}.json"
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

src = (Path(__file__).resolve().parents[3] / "06-microsoft-teams-integration" / "src" / "solution" / "Other" / "Solution.xml")
xml = src.read_text(encoding="utf-8-sig") if src.exists() else (other / "Solution.xml").read_text(encoding="utf-8-sig")
import re
xml = re.sub(r"<UniqueName>ITOnCall</UniqueName>", f"<UniqueName>{UNIQUE}</UniqueName>", xml)
xml = xml.replace('description="IT On-call"', 'description="Price lists"')
roots = "\n".join([f'      <RootComponent type="29" id="{{{FLOW_ID}}}" behavior="0" />'] +
                  [f'      <RootComponent type="380" schemaName="{s}" behavior="0" />' for s in sorted(ENV)])
xml = re.sub(r"<RootComponents>.*?</RootComponents>", f"<RootComponents>\n{roots}\n    </RootComponents>", xml, flags=re.S)
(other / "Solution.xml").write_text("﻿" + xml, encoding="utf-8")
print("wrote", SOL)
