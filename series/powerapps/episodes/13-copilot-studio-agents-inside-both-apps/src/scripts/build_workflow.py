"""Generates src/agent/workflows/CreateFinding/workflow.json from the shared schema, so the option values and logical names in the
agent flow cannot drift from ContosoInspections. Run: python3 build_workflow.py (writes the file). Tests re-run it and compare."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = json.loads((HERE.parent / "schema" / "contosoinspections.schema.json").read_text(encoding="utf-8"))
OUT = HERE.parent / "agent" / "workflows" / "CreateFinding" / "workflow.json"
PREFIX = SCHEMA["publisher"]["optionValuePrefix"] * 10000


def choice_map(table, column):
    t = next(t for t in SCHEMA["tables"] if t["logicalName"] == table)
    c = next(c for c in t["columns"] if c["logicalName"] == column)
    return {label: PREFIX + value for label, value in c["options"]}


def compact(d):
    return json.dumps(d, separators=(",", ":"))


def respond(message, run_after=None):
    a = {"type": "Response", "kind": "Skills", "inputs": {"statusCode": 200, "body": {"result": message}, "schema": {
        "type": "object", "properties": {"result": {"title": "result", "type": "string", "x-ms-content-hint": "TEXT", "x-ms-dynamically-added": True}}}}}
    if run_after:
        a["runAfter"] = run_after
    return a


def text_input(title, description):
    return {"title": title, "type": "string", "x-ms-dynamically-added": True, "description": description, "x-ms-content-hint": "TEXT"}


def guard(expression, then_actions, else_actions, run_after=None):
    a = {"type": "If", "expression": expression, "actions": then_actions, "else": {"actions": else_actions}}
    if run_after:
        a["runAfter"] = run_after
    return a


def build():
    cats = choice_map("cin_inspectionitem", "cin_category")
    sevs = choice_map("cin_inspectionitem", "cin_severity")
    status = choice_map("cin_inspection", "cin_status")
    host = {"connectionName": "shared_commondataserviceforapps", "apiId": "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps"}
    auth = "@parameters('$authentication')"
    find = {"type": "OpenApiConnection", "inputs": {"host": dict(host, operationId="ListRecords"), "parameters": {
        "entityName": "cin_inspections", "$select": "cin_inspectionid,cin_name,cin_status",
        "$filter": "cin_name eq '@{replace(triggerBody()?['text'],'''','''''')}'", "$top": 1}, "authentication": auth}, "runAfter": {}}
    create = {"type": "OpenApiConnection", "inputs": {"host": dict(host, operationId="CreateRecord"), "parameters": {
        "entityName": "cin_inspectionitems",
        "item/cin_name": "@{triggerBody()?['text_1']}",
        "item/cin_inspectionid@odata.bind": "/cin_inspections(@{first(outputs('Find_inspection')?['body/value'])?['cin_inspectionid']})",
        "item/cin_category": f"@json('{compact(cats)}')?[triggerBody()?['text_2']]",
        "item/cin_severity": f"@json('{compact(sevs)}')?[triggerBody()?['text_3']]",
        "item/cin_passed": False,
        "item/cin_notes": "@concat('[Agent] ', triggerBody()?['text_4'])"}, "authentication": auth}, "runAfter": {}}
    bad_input = f"@or(empty(json('{compact(cats)}')?[triggerBody()?['text_2']]),empty(json('{compact(sevs)}')?[triggerBody()?['text_3']]))"
    no_notes = "@and(contains(createArray('Major','Critical'),triggerBody()?['text_3']),less(length(trim(triggerBody()?['text_4'])),10))"
    not_found = "@equals(length(outputs('Find_inspection')?['body/value']),0)"
    closed = f"@contains(createArray({status['Approved']},{status['Rejected']}),first(outputs('Find_inspection')?['body/value'])?['cin_status'])"
    created = respond("Finding created: @{triggerBody()?['text_1']} on @{triggerBody()?['text']}. Add a photo in the field app for a Major or Critical finding.",
                      {"Create_finding": ["Succeeded"]})
    inner = guard(closed, {"Respond_closed": respond("That inspection is already approved or rejected. A reviewer must reopen it. Nothing was written.")},
                  {"Create_finding": create, "Respond_created": created})
    inner = guard(not_found, {"Respond_not_found": respond("No inspection with that number. Nothing was written.")}, {"Check_open": inner})
    inner = guard(no_notes, {"Respond_notes": respond("A Major or Critical finding needs notes of at least 10 characters. Nothing was written.")}, {"Check_found": inner})
    inner = guard(bad_input, {"Respond_bad_input": respond("Category or severity is not one of the allowed values. Nothing was written.")}, {"Check_notes": inner},
                  {"Find_inspection": ["Succeeded"]})
    trigger = {"manual": {"type": "Request", "kind": "Skills", "inputs": {"schema": {"type": "object", "properties": {
        "text": text_input("Inspection number", "Inspection number such as INS-00003"),
        "text_1": text_input("Finding title", "Short name of the finding"),
        "text_2": text_input("Category", "Safety, Electrical, Fire, Structural or Housekeeping"),
        "text_3": text_input("Severity", "Info, Minor, Major or Critical"),
        "text_4": text_input("Notes", "Notes, at least 10 characters for Major or Critical")},
        "required": ["text", "text_1", "text_2", "text_3", "text_4"]}}}}
    return {"properties": {"connectionReferences": {"shared_commondataserviceforapps": {"api": {"name": "shared_commondataserviceforapps"},
            "connection": {"connectionReferenceLogicalName": "cin_sharedcommondataserviceforapps_agent"}, "runtimeSource": "embedded"}},
            "definition": {"$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
            "contentVersion": "1.0.0.0", "parameters": {"$connections": {"defaultValue": {}, "type": "Object"}, "$authentication": {"defaultValue": {}, "type": "SecureObject"}},
            "triggers": trigger, "actions": {"Find_inspection": find, "Check_input": inner}}, "templateName": ""}, "schemaVersion": "1.0.0.0"}


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
    print("wrote", OUT)
