#!/usr/bin/env bash
# MG Lab #5 — deploy from Azure Cloud Shell (Bash). Usage: ./deploy.sh <resource-group> "<graph-site-id>"
set -euo pipefail
RG="$1"; SITE_ID="$2"
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "1/3 Infrastructure (Bicep)"
OUT=$(az deployment group create -g "$RG" -f "$HERE/infra/main.bicep" -p sharePointSiteId="$SITE_ID" \
      --query properties.outputs -o json)
APP=$(echo "$OUT" | jq -r .functionAppName.value)
echo "   Function App: $APP   principalId: $(echo "$OUT" | jq -r .principalId.value)"

echo "2/3 Build and publish"
dotnet publish "$HERE/src/MGLab.GraphFunction" -c Release -o "$HERE/out" --nologo -v q
(cd "$HERE/out" && zip -qr ../app.zip .)

echo "3/3 Deploy code"
az functionapp deployment source config-zip -g "$RG" -n "$APP" --src "$HERE/app.zip" -o none
echo "Done. Next: grant Graph access (infra/grant-graph-access.http), then call /api/whoami and /api/requests."
