#!/usr/bin/env bash
# Governance first, then the workload, then the app. Needs: az (signed in, Owner or
# Contributor + Resource Policy Contributor + User Access Administrator on the group), dotnet 10, zip, curl.
# Usage: infra/deploy.sh <resource-group> [region] [lab|prod]
set -euo pipefail
RG=${1:?usage: deploy.sh <resource-group> [region] [lab|prod]}
REGION=${2:-swedencentral}
ENVIRONMENT=${3:-lab}
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)

az group create --name "$RG" --location "$REGION" \
  --tags workload=contoso environment="$ENVIRONMENT" owner=platform-team --output none

echo "== 1. governance (allowed locations, required tag)"
az deployment group create --resource-group "$RG" --name governance \
  --parameters "$HERE/env/governance.bicepparam" --parameters allowedLocations="[\"$REGION\"]" --output none
echo "   new assignments take about five minutes to apply to the scope"

echo "== 2. what-if"
# A .bicepparam file names its template ("using '../main.bicep'"); don't pass --template-file as well.
az deployment group what-if --resource-group "$RG" --parameters "$HERE/env/$ENVIRONMENT.bicepparam"

echo "== 3. deploy the workload"
APP=$(az deployment group create --resource-group "$RG" --name workload \
  --parameters "$HERE/env/$ENVIRONMENT.bicepparam" \
  --query properties.outputs.appName.value --output tsv)

echo "== 4. publish the readiness probe to $APP"
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT
dotnet publish "$ROOT/src/ReadinessProbe/ReadinessProbe.csproj" -c Release -o "$OUT/publish"
(cd "$OUT/publish" && zip -qr "$OUT/app.zip" .)
az webapp deploy --resource-group "$RG" --name "$APP" --src-path "$OUT/app.zip" --type zip

HOST=$(az webapp show --resource-group "$RG" --name "$APP" --query defaultHostName --output tsv)
echo "== 5. health: https://$HOST/healthz"
curl -sS --retry 5 --retry-delay 10 --retry-all-errors "https://$HOST/healthz"; echo
