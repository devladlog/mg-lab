"""Writes the four demo flows in src/flows/ (solution-format JSON, same layout as episodes 1 to 9).

  acknowledge-it-request.json   SharePoint + Outlook          passes every policy in this episode
  request-weather-note.json     SharePoint + MSN Weather      mixed groups, or blocked by the baseline
  request-asset-lookup.json     SharePoint + HTTP             mixed groups: HTTP is Non-business by default
  request-external-copy.json    SharePoint + Outlook          passes, but emails someone outside contoso.com

The flows are for the data-policy demo and for tests; they are not a solution to deploy.
Run: python tools/build_flows.py   (idempotent)
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "flows"
SITE = "https://contoso.sharepoint.com/sites/ITHelpdesk"
SCHEMA = "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#"
API = {"shared_sharepointonline": "cts_sharedsharepointonline_guardrails",
       "shared_office365": "cts_sharedoffice365_guardrails",
       "shared_msnweather": "cts_sharedmsnweather_guardrails"}


def host(api: str, op: str) -> dict:
    return {"apiId": f"/providers/Microsoft.PowerApps/apis/{api}", "connectionName": api, "operationId": op}


def trigger() -> dict:
    return {"type": "OpenApiConnection",
            "recurrence": {"interval": 1, "frequency": "Minute"},
            "splitOn": "@triggerOutputs()?['body/value']",
            "inputs": {"host": host("shared_sharepointonline", "GetOnNewItems"),
                       "parameters": {"dataset": SITE, "table": "IT Requests"},
                       "authentication": "@parameters('$authentication')"}}


def email(after: str | None, to: str, subject: str, body: str) -> dict:
    return {"type": "OpenApiConnection",
            "runAfter": {after: ["Succeeded"]} if after else {},
            "inputs": {"host": host("shared_office365", "SendEmailV2"),
                       "parameters": {"emailMessage/To": to, "emailMessage/Subject": subject,
                                      "emailMessage/Body": body, "emailMessage/Importance": "Normal"},
                       "authentication": "@parameters('$authentication')"}}


def flow(apis: list[str], actions: dict) -> dict:
    return {"properties": {
        "connectionReferences": {a: {"runtimeSource": "embedded", "connection": {"connectionReferenceLogicalName": API[a]},
                                     "api": {"name": a}} for a in apis},
        "definition": {"$schema": SCHEMA, "contentVersion": "1.0.0.0",
                       "parameters": {"$connections": {"defaultValue": {}, "type": "Object"},
                                      "$authentication": {"defaultValue": {}, "type": "SecureObject"}},
                       "triggers": {"When_an_IT_request_is_created": trigger()},
                       "actions": actions},
        "templateName": ""}, "schemaVersion": "1.0.0.0"}


FLOWS = {
    "acknowledge-it-request.json": flow(["shared_sharepointonline", "shared_office365"], {
        "Send_acknowledgement": email(None, "@triggerBody()?['Author']?['Email']",
                                      "IT request #@{triggerBody()?['ID']} received",
                                      "<p>We have your request <b>@{triggerBody()?['Title']}</b>.</p>")}),
    "request-weather-note.json": flow(["shared_sharepointonline", "shared_msnweather", "shared_office365"], {
        "Get_current_weather": {
            "type": "OpenApiConnection", "runAfter": {},
            "inputs": {"host": host("shared_msnweather", "CurrentWeather"),
                       "parameters": {"Location": "Lisbon", "units": "Metric"},
                       "authentication": "@parameters('$authentication')"}},
        "Send_weather_note": email("Get_current_weather", "@triggerBody()?['Author']?['Email']",
                                   "IT request #@{triggerBody()?['ID']}: the office weather",
                                   "<p>It is @{body('Get_current_weather')?['responses/weather/current/cap']} in Lisbon.</p>")}),
    "request-asset-lookup.json": flow(["shared_sharepointonline"], {
        "Look_up_asset": {
            "type": "Http", "runAfter": {},
            "inputs": {"method": "GET",
                       "uri": "https://assets.contoso.example/api/assets",
                       "queries": {"owner": "@triggerBody()?['Author']?['Email']"},
                       "retryPolicy": {"type": "fixed", "count": 3, "interval": "PT20S"}}}}),
    "request-external-copy.json": flow(["shared_sharepointonline", "shared_office365"], {
        "Send_copy_to_partner": email(None, "reports@fabrikam.example",
                                      "IT request #@{triggerBody()?['ID']}: copy",
                                      "<p>@{triggerBody()?['Title']}</p>")}),
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, body in FLOWS.items():
        (OUT / name).write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", len(FLOWS), "flows to", OUT)


if __name__ == "__main__":
    main()
