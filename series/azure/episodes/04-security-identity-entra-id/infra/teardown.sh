#!/usr/bin/env bash
# Remove everything. The app registration and its service principal live in Entra ID, not in the resource group,
# so deleting the group is not enough. Deleted app registrations stay restorable for 30 days; this script deletes
# the app and then removes it from the deleted items too (lab: we want the name and the quota back).
# Usage: infra/teardown.sh <resource-group>
set -euo pipefail
RG=${1:?usage: teardown.sh <resource-group>}
OUT=${OUT:-$HOME/.contoso-orders}

if [[ -f "$OUT/outputs.json" ]]; then
  API_CLIENT_ID=$(python3 -c "import json;print(json.load(open('$OUT/outputs.json'))['apiClientId'])")
  OBJECT_ID=$(az ad app show --id "$API_CLIENT_ID" --query id --output tsv 2>/dev/null || true)
  if [[ -n "$OBJECT_ID" ]]; then
    az ad sp delete --id "$API_CLIENT_ID" || true
    az ad app delete --id "$API_CLIENT_ID"
    az rest --method DELETE --uri "https://graph.microsoft.com/v1.0/directory/deletedItems/$OBJECT_ID"
    echo "app registration $API_CLIENT_ID deleted permanently"
  fi
fi
az group delete --name "$RG" --yes                               # the managed identity
rm -rf "$OUT"
