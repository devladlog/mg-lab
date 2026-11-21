#!/usr/bin/env bash
# Provision storage + Azure SQL (free tier), then create the schema as the signed-in Entra admin.
# Needs: az (signed in), dotnet 10, curl. Usage: infra/deploy.sh <resource-group> [region]
set -euo pipefail
RG=${1:?usage: deploy.sh <resource-group> [region]}
REGION=${2:-westeurope}
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
STATE="$HOME/.contoso-orders-data/outputs.json"   # deployment outputs, kept outside the repo
mkdir -p "$(dirname "$STATE")"

# The .bicepparam file reads these three with readEnvironmentVariable()
export ADMIN_OBJECT_ID=${ADMIN_OBJECT_ID:-$(az ad signed-in-user show --query id -o tsv)}
export ADMIN_LOGIN=${ADMIN_LOGIN:-$(az ad signed-in-user show --query userPrincipalName -o tsv)}
export CLIENT_IP=${CLIENT_IP:-$(curl -fsS https://api.ipify.org)}

az group create --name "$RG" --location "$REGION" --tags workload=contoso-orders environment=lab --output none

echo "== what-if"
az deployment group what-if --resource-group "$RG" --parameters "$HERE/main.bicepparam"

echo "== deploy"
az deployment group create --resource-group "$RG" --name orders-data \
  --parameters "$HERE/main.bicepparam" --query properties.outputs --output json > "$STATE"
out() { python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]]["value"])' "$STATE" "$1"; }

echo "== free tier check"
az sql db show --resource-group "$RG" --server "$(out sqlServerFqdn | cut -d. -f1)" --name "$(out databaseName)" \
  --query "{sku:currentSku.name, useFreeLimit:useFreeLimit, atLimit:freeLimitExhaustionBehavior, status:status}" -o table

echo "== create schema (as you, the Entra admin; no SQL password exists)"
Database__Provider=SqlServer Database__Server="$(out sqlServerFqdn)" Database__Database="$(out databaseName)" \
  dotnet run --project "$ROOT/src/Contoso.Orders.Api" -- --create-schema

echo "Done. Start the API with: infra/run-api.sh"
