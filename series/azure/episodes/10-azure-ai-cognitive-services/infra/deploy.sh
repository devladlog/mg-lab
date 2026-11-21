#!/usr/bin/env bash
# Creates (or updates) the free-tier Language resource. Two steps on purpose, so the demo can show the failure first:
#   infra/deploy.sh <rg> [location]           resource only: key access off, nobody has a role yet
#   infra/deploy.sh <rg> [location] --role    same template again, now granting "Cognitive Services Language Reader"
#                                             to the signed-in user (role assignments can take up to five minutes)
# Needs `az login` as an identity that can create role assignments (Owner on the subscription is enough).
set -euo pipefail
RG=${1:?usage: deploy.sh <resource-group> [location] [--role]}
LOC=${2:-westeurope}
ROLE=${3:-}
HERE=$(cd "$(dirname "$0")" && pwd)
STATE="$HOME/.contoso-ai"
mkdir -p "$STATE"

# Learn: only one F0 Language resource is allowed per subscription. Stop early with a readable message.
EXISTING=$(az cognitiveservices account list --query "[?kind=='TextAnalytics' && sku.name=='F0' && resourceGroup!='$RG'].{name:name, rg:resourceGroup}" -o tsv)
if [ -n "$EXISTING" ]; then
  echo "Another free (F0) Language resource already exists in this subscription:" >&2
  echo "$EXISTING" >&2
  echo "Delete it (and purge it) first, or use a Standard (S) tier for this demo." >&2
  exit 1
fi

az group create --name "$RG" --location "$LOC" --tags workload=contoso-support-triage environment=lab -o none

ARGS=()
if [ "$ROLE" = "--role" ]; then
  ARGS+=(--parameters "principalId=$(az ad signed-in-user show --query id -o tsv)" "principalType=User")
fi

az deployment group what-if --resource-group "$RG" --template-file "$HERE/main.bicep" "${ARGS[@]}" --no-pretty-print \
  --query "properties.changes[].{op:changeType, resource:resourceId}" -o table
az deployment group create --resource-group "$RG" --name ai10 --template-file "$HERE/main.bicep" "${ARGS[@]}" \
  --query "properties.outputs" -o json | tee "$STATE/outputs.json"
jq -r '.endpoint.value' "$STATE/outputs.json" > "$STATE/endpoint"
echo "endpoint saved in $STATE/endpoint"
