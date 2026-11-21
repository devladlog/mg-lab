#!/usr/bin/env bash
# Publish the controller API and deploy it to Azure App Service (Linux, Free F1, .NET 10),
# trusting access tokens from your Microsoft Entra tenant.
#
#   PACKAGE_ONLY=1 ./deploy/deploy-appservice.sh                       # build + zip only, no Azure calls
#   APP=contoso-claims-1234 TENANT_ID=<tenant-guid> API_CLIENT_ID=<app-registration-client-id> \
#     ./deploy/deploy-appservice.sh                                    # needs `az login`
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project="$here/../src/ExpenseClaims.Api/ExpenseClaims.Api.csproj"
out="$here/out"

RG="${RG:-rg-mglab-net02}"
LOCATION="${LOCATION:-westeurope}"
PLAN="${PLAN:-plan-mglab-net02}"

echo "==> dotnet publish (Release)"
rm -rf "$out"
dotnet publish "$project" --configuration Release --output "$out/publish" --nologo -v quiet
(cd "$out/publish" && zip -qr "$out/app.zip" .)
echo "    package: $out/app.zip ($(du -h "$out/app.zip" | cut -f1))"

if [[ "${PACKAGE_ONLY:-0}" == "1" ]]; then
  echo "PACKAGE_ONLY=1: skipping Azure."
  exit 0
fi

: "${APP:?Set APP to a globally unique web app name}"
: "${TENANT_ID:?Set TENANT_ID (Microsoft Entra tenant ID)}"
: "${API_CLIENT_ID:?Set API_CLIENT_ID (Application (client) ID of the API app registration)}"
az account show -o none   # fails fast if not signed in

echo "==> resource group, Free F1 Linux plan, web app (DOTNETCORE:10.0)"
az group create --name "$RG" --location "$LOCATION" --tags series=net episode=02 -o none
az appservice plan create --name "$PLAN" --resource-group "$RG" --sku F1 --is-linux -o none
az webapp create --name "$APP" --resource-group "$RG" --plan "$PLAN" --runtime "DOTNETCORE:10.0" -o none

echo "==> JWT bearer settings (Authentication:Schemes:Bearer:*, '__' on Linux)"
# v1.0 access tokens (the default for a new app registration) are issued by sts.windows.net with aud = api://<client-id>.
az webapp config appsettings set --name "$APP" --resource-group "$RG" -o none --settings \
  "Authentication__Schemes__Bearer__Authority=https://sts.windows.net/$TENANT_ID/" \
  "Authentication__Schemes__Bearer__ValidAudiences__0=api://$API_CLIENT_ID" \
  "RateLimits__SubmitPerMinute=5"

echo "==> zip deploy"
az webapp deploy --resource-group "$RG" --name "$APP" --src-path "$out/app.zip" --type zip -o none

host="$(az webapp show --name "$APP" --resource-group "$RG" --query defaultHostName -o tsv)"
echo "==> https://$host/healthz"
curl -fsS --retry 10 --retry-delay 6 --retry-all-errors "https://$host/healthz"; echo
