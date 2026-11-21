#!/usr/bin/env bash
# LAB ONLY: pre-authorize the Azure CLI (first-party app 04b07795-8ddb-461a-bbee-02f9e1bf7b46) for the Orders.Read
# scope, so `az account get-access-token --scope .../Orders.Read` works without a consent prompt. A real client
# (SPA, web app) gets its own app registration instead. The next identity.bicep deployment removes this again,
# because the template owns the whole `api` block.
# Usage: infra/lab-preauthorize-cli.sh            (reads ~/.contoso-orders/outputs.json from deploy.sh)
set -euo pipefail
OUT=${OUT:-$HOME/.contoso-orders}
AZURE_CLI_APP_ID=04b07795-8ddb-461a-bbee-02f9e1bf7b46

API_CLIENT_ID=$(python3 -c "import json;print(json.load(open('$OUT/outputs.json'))['apiClientId'])")
OBJECT_ID=$(az ad app show --id "$API_CLIENT_ID" --query id --output tsv)
az ad app show --id "$API_CLIENT_ID" --query api --output json > "$OUT/api.json"

# Merge into the existing `api` object (scopes, token version) instead of replacing it.
python3 - "$OUT/api.json" "$AZURE_CLI_APP_ID" > "$OUT/patch.json" <<'PY'
import json, sys
api = json.load(open(sys.argv[1]))
scope = next(s["id"] for s in api["oauth2PermissionScopes"] if s["value"] == "Orders.Read")
others = [p for p in api.get("preAuthorizedApplications") or [] if p["appId"] != sys.argv[2]]
api["preAuthorizedApplications"] = others + [{"appId": sys.argv[2], "delegatedPermissionIds": [scope]}]
print(json.dumps({"api": api}))
PY

az rest --method PATCH --uri "https://graph.microsoft.com/v1.0/applications/$OBJECT_ID" \
  --headers Content-Type=application/json --body "@$OUT/patch.json"
echo "Azure CLI pre-authorized for Orders.Read on $API_CLIENT_ID (lab only)"
