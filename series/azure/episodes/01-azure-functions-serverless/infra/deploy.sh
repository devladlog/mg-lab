#!/usr/bin/env bash
# Provision with Bicep, publish the .NET 10 app, deploy the zip. Needs: az (signed in), dotnet 10, zip.
# Usage: infra/deploy.sh <resource-group> [region]
set -euo pipefail
RG=${1:?usage: deploy.sh <resource-group> [region]}
REGION=${2:-swedencentral}
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)

az group create --name "$RG" --location "$REGION" --tags workload=order-intake environment=lab --output none

echo "== what-if"
# A .bicepparam file names its template ("using 'main.bicep'"); passing --template-file too is an error.
az deployment group what-if --resource-group "$RG" --parameters "$HERE/main.bicepparam"

echo "== deploy infrastructure"
APP=$(az deployment group create --resource-group "$RG" --name order-intake \
  --parameters "$HERE/main.bicepparam" \
  --query properties.outputs.functionAppName.value --output tsv)

echo "== publish $APP"
OUT=$(mktemp -d)   # keep build output out of the repo
trap 'rm -rf "$OUT"' EXIT
dotnet publish "$ROOT/src/OrderIntake/OrderIntake.csproj" -c Release -o "$OUT/publish"
(cd "$OUT/publish" && zip -qr "$OUT/app.zip" .)
az functionapp deployment source config-zip --resource-group "$RG" --name "$APP" --src "$OUT/app.zip"

az functionapp function list --resource-group "$RG" --name "$APP" --query "[].name" --output tsv
echo "Function app: https://$(az functionapp show -g "$RG" -n "$APP" --query defaultHostName -o tsv)"
