#!/usr/bin/env bash
# Deploy the identity side of the orders API (Entra app + service principal + managed identity + app role assignments).
# Needs: az >= 2.73 (Microsoft Graph Bicep), signed in as a user who can create app registrations and app role
# assignments in the tenant, and Contributor on the resource group (for the managed identity).
# Usage: infra/deploy.sh <resource-group> [region]
set -euo pipefail
RG=${1:?usage: deploy.sh <resource-group> [region]}
REGION=${2:-swedencentral}
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${OUT:-$HOME/.contoso-orders}          # outputs (IDs only, no secrets) for the other scripts; outside the repo
mkdir -p "$OUT"

ME=$(az ad signed-in-user show --query id --output tsv)
az group create --name "$RG" --location "$REGION" \
  --tags workload=contoso environment=lab owner=platform-team --output none

echo "== what-if"
az deployment group what-if --resource-group "$RG" --parameters "$HERE/env/lab.bicepparam" \
  --parameters readerPrincipalIds="[\"$ME\"]" ownerObjectIds="[\"$ME\"]"

echo "== deploy"
# The .bicepparam file comes first; inline values override it (you as reader and owner, never committed).
az deployment group create --resource-group "$RG" --name identity \
  --parameters "$HERE/env/lab.bicepparam" \
  --parameters readerPrincipalIds="[\"$ME\"]" ownerObjectIds="[\"$ME\"]" \
  --query properties.outputs --output json > "$OUT/outputs.json"

python3 - "$OUT/outputs.json" <<'PY'
import json, sys
o = {k: v["value"] for k, v in json.load(open(sys.argv[1])).items()}
json.dump(o, open(sys.argv[1], "w"), indent=2)
for k, v in o.items():
    print(f"  {k:22} {v}")
PY
echo "outputs saved to $OUT/outputs.json"
