#!/usr/bin/env python3
"""Generate ClaudeTriage/workflow.json: an instant flow that reads the secret environment variable and calls the Claude connector.

Why a flow: a secret environment variable can be read by a cloud flow (and in a connector's Security tab), but not by a
canvas app or by a connector action header. So the key travels Key Vault -> flow -> connector parameter and never touches the app.
Run:  python build_flow.py   (rewrites ClaudeTriage/workflow.json; the prompt text comes from ../prompts/system.md)
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROMPT = (HERE.parent / "prompts" / "system.md").read_text(encoding="utf-8").strip()
SECRET_VAR = "cin_AnthropicApiKey"
DV = {"connectionName": "shared_commondataserviceforapps", "apiId": "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps"}
CLAUDE = {"connectionName": "shared_contosoclaudetriage", "apiId": "/providers/Microsoft.PowerApps/apis/shared_contosoclaudetriage"}


def respond(text_expr, error_expr):
    schema = {"type": "object", "properties": {"text": {"type": "string", "title": "text"}, "error": {"type": "string", "title": "error"}}}
    return {"type": "Response", "kind": "PowerApp",
            "inputs": {"statusCode": 200, "body": {"text": text_expr, "error": error_expr}, "schema": schema}}


def build():
    trigger = {"manual": {"type": "Request", "kind": "Button", "inputs": {"schema": {"type": "object", "properties": {
        "notes": {"title": "Notes", "type": "string", "x-ms-dynamically-added": True, "description": "Inspector notes", "x-ms-content-hint": "TEXT"},
        "photo": {"title": "Photo base64", "type": "string", "x-ms-dynamically-added": True, "description": "JPEG as base64 without the data: prefix, or empty", "x-ms-content-hint": "TEXT"},
        "model": {"title": "Model id", "type": "string", "x-ms-dynamically-added": True, "description": "Claude model id, for example the one on the Anthropic models page that day", "x-ms-content-hint": "TEXT"}},
        "required": ["notes", "model"]}}}}
    actions = {
        "Get_key": {"type": "OpenApiConnection", "runAfter": {},
                    "inputs": {"host": {**DV, "operationId": "PerformUnboundAction"},
                               "parameters": {"actionName": "RetrieveEnvironmentVariableSecretValue", "item/EnvironmentVariableName": SECRET_VAR},
                               "authentication": "@parameters('$authentication')"},
                    "runtimeConfiguration": {"secureData": {"properties": ["outputs"]}}},
        "System_prompt": {"type": "Compose", "runAfter": {"Get_key": ["Succeeded"]}, "inputs": PROMPT},
        "Text_part": {"type": "Compose", "runAfter": {"System_prompt": ["Succeeded"]},
                      "inputs": {"type": "text", "text": "@{concat('Notes: ', triggerBody()?['notes'])}"}},
        "Image_part": {"type": "Compose", "runAfter": {"Text_part": ["Succeeded"]},
                       "inputs": {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "@{triggerBody()?['photo']}"}}},
        "Triage": {"type": "OpenApiConnection", "runAfter": {"Image_part": ["Succeeded"]},
                   "inputs": {"host": {**CLAUDE, "operationId": "TriageFinding"},
                              "parameters": {
                                  "x-api-key": "@outputs('Get_key')?['body/EnvironmentVariableSecretValue']",
                                  "anthropic-version": "2026-10-21",
                                  "body/model": "@triggerBody()?['model']",
                                  "body/max_tokens": 300,
                                  "body/system": "@outputs('System_prompt')",
                                  "body/messages": [{"role": "user", "content": "@if(empty(triggerBody()?['photo']), createArray(outputs('Text_part')), createArray(outputs('Image_part'), outputs('Text_part')))"}]},
                              "authentication": "@parameters('$authentication')"},
                   "runtimeConfiguration": {"secureData": {"properties": ["inputs"]}}},
        "Respond_ok": {**respond("@{first(body('Triage')?['content'])?['text']}", ""), "runAfter": {"Triage": ["Succeeded"]}},
        "Respond_error": {**respond("", "The model did not answer. The key or the connector may be wrong; nothing was changed."),
                          "runAfter": {"Triage": ["Failed", "TimedOut"], "Get_key": ["Failed", "TimedOut"]}},
    }
    return {"schemaVersion": "1.0.0.0", "properties": {
        "connectionReferences": {
            "shared_commondataserviceforapps": {"api": {"name": "shared_commondataserviceforapps"}, "connection": {"connectionReferenceLogicalName": "cin_sharedcommondataserviceforapps_ai"}, "runtimeSource": "embedded"},
            "shared_contosoclaudetriage": {"api": {"name": "shared_contosoclaudetriage"}, "connection": {"connectionReferenceLogicalName": "cin_sharedcontosoclaudetriage_ai"}, "runtimeSource": "embedded"}},
        "definition": {"$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
                       "contentVersion": "1.0.0.0",
                       "parameters": {"$connections": {"defaultValue": {}, "type": "Object"}, "$authentication": {"defaultValue": {}, "type": "SecureObject"}},
                       "triggers": trigger, "actions": actions},
        "templateName": None}}


if __name__ == "__main__":
    out = HERE / "ClaudeTriage" / "workflow.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
