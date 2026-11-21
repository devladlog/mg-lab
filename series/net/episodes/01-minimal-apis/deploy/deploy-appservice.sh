#!/usr/bin/env bash
# Publish the Minimal API and deploy it to Azure App Service (Linux, Free F1 plan, .NET 10).
#
#   PACKAGE_ONLY=1 ./deploy/deploy-appservice.sh       # build + zip only, no Azure calls (runs anywhere)
#   APP=contoso-requests-1234 ./deploy/deploy-appservice.sh   # needs `az login` first
#
# Commands follow the App Service .NET quickstart (Azure CLI tab), with the plan on the Free F1 tier.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project="$here/../src/ProjectRequests.Api/ProjectRequests.Api.csproj"
out="$here/out"

RG="${RG:-rg-mglab-net01}"
LOCATION="${LOCATION:-westeurope}"
PLAN="${PLAN:-plan-mglab-net01}"

echo "==> dotnet publish (Release)"
rm -rf "$out"
dotnet publish "$project" --configuration Release --output "$out/publish" --nologo -v quiet
(cd "$out/publish" && zip -qr "$out/app.zip" .)    # zip the CONTENTS of publish/, not the folder
echo "    package: $out/app.zip ($(du -h "$out/app.zip" | cut -f1))"

if [[ "${PACKAGE_ONLY:-0}" == "1" ]]; then
  echo "PACKAGE_ONLY=1: skipping Azure."
  exit 0
fi

: "${APP:?Set APP to a globally unique web app name (a-z, 0-9, -)}"
az account show --query "{subscription:name}" -o tsv >/dev/null   # fails fast if not signed in

echo "==> resource group, Free F1 Linux plan, web app (DOTNETCORE:10.0)"
az group create --name "$RG" --location "$LOCATION" --tags series=net episode=01 -o none
az appservice plan create --name "$PLAN" --resource-group "$RG" --sku F1 --is-linux -o none
az webapp create --name "$APP" --resource-group "$RG" --plan "$PLAN" --runtime "DOTNETCORE:10.0" -o none

# Hierarchical keys use a double underscore on Linux: Api:ReadOnly -> Api__ReadOnly
az webapp config appsettings set --name "$APP" --resource-group "$RG" --settings Api__ReadOnly=false -o none

echo "==> zip deploy"
az webapp deploy --resource-group "$RG" --name "$APP" --src-path "$out/app.zip" --type zip -o none

host="$(az webapp show --name "$APP" --resource-group "$RG" --query defaultHostName -o tsv)"
echo "==> https://$host/healthz"
curl -fsS --retry 10 --retry-delay 6 --retry-all-errors "https://$host/healthz"; echo
