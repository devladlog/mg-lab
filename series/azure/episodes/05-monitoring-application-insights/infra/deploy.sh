#!/usr/bin/env bash
# Provision (Bicep), publish the .NET 10 API, deploy the zip, check /healthz.
# Needs: az (signed in), dotnet 10, zip, curl. Usage: ALERT_EMAIL=you@example.com infra/deploy.sh <rg> [region]
set -euo pipefail
RG=${1:?usage: ALERT_EMAIL=... deploy.sh <resource-group> [region]}
REGION=${2:-swedencentral}
: "${ALERT_EMAIL:?set ALERT_EMAIL to the address that should receive the alerts}"
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
STATE="$HOME/.contoso-orders-monitoring/outputs.json"   # deployment outputs, kept outside the repo
mkdir -p "$(dirname "$STATE")"

az group create --name "$RG" --location "$REGION" --tags workload=contoso-orders environment=lab --output none

echo "== what-if"
# The .bicepparam file names its template; it reads ALERT_EMAIL with readEnvironmentVariable().
az deployment group what-if --resource-group "$RG" --parameters "$HERE/main.bicepparam"

echo "== deploy infrastructure"
az deployment group create --resource-group "$RG" --name orders-monitoring \
  --parameters "$HERE/main.bicepparam" --query properties.outputs --output json > "$STATE"
APP=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["appName"]["value"])' "$STATE")
URL=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["appUrl"]["value"])' "$STATE")

echo "== publish $APP"
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT
dotnet publish "$ROOT/src/Contoso.Orders.Api/Contoso.Orders.Api.csproj" -c Release -o "$OUT/publish"
(cd "$OUT/publish" && zip -qr "$OUT/app.zip" .)
az webapp deploy --resource-group "$RG" --name "$APP" --src-path "$OUT/app.zip" --type zip

echo "== smoke"
for i in $(seq 1 30); do
  if curl -fsS "$URL/healthz"; then echo; echo "API: $URL"; exit 0; fi
  sleep 10
done
echo "healthz did not answer in 5 minutes" >&2
exit 1
