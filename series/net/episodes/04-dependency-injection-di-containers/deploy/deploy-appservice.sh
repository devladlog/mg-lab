#!/usr/bin/env bash
# Episode 4 on Azure App Service (Linux, Free F1): watch the digest worker in the log stream, then break
# the configuration on purpose and watch ValidateOnStart stop the app.
#
#   PACKAGE_ONLY=1 ./deploy/deploy-appservice.sh                 # publish + zip only, no Azure calls
#   APP=contoso-requests-1234 ./deploy/deploy-appservice.sh      # needs `az login`
#   APP=... ./deploy/deploy-appservice.sh break                  # Notifications__Channel=webhook, no URL -> app won't start
#   APP=... ./deploy/deploy-appservice.sh fix                    # back to the log channel
#
# Storage: SQLite in /home (App Service's shared storage) to keep this episode about DI, not databases.
# Fine for one F1 instance and a demo; episode 3 shows the production path with Azure SQL Database.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project="$here/../src/ProjectRequests.Api/ProjectRequests.Api.csproj"
out="$here/out"

RG="${RG:-rg-mglab-net04}"
LOCATION="${LOCATION:-westeurope}"
PLAN="${PLAN:-plan-mglab-net04}"

package() {
  echo "==> dotnet publish (Release, linux-x64)"
  rm -rf "$out"
  dotnet publish "$project" --configuration Release --runtime linux-x64 --self-contained false \
    --output "$out/publish" --nologo -v quiet
  (cd "$out/publish" && zip -qr "$out/app.zip" .)
  echo "    package: $out/app.zip ($(du -h "$out/app.zip" | cut -f1))"
}

if [[ "${PACKAGE_ONLY:-0}" == "1" ]]; then
  package
  echo "PACKAGE_ONLY=1: skipping Azure."
  exit 0
fi

: "${APP:?Set APP to a globally unique web app name (a-z, 0-9, -)}"
az account show --query "{subscription:name}" -o tsv >/dev/null

case "${1:-deploy}" in
  deploy)
    package
    echo "==> resource group, Free F1 Linux plan, web app (DOTNETCORE:10.0)"
    az group create --name "$RG" --location "$LOCATION" --tags series=net episode=04 -o none
    az appservice plan create --name "$PLAN" --resource-group "$RG" --sku F1 --is-linux -o none
    az webapp create --name "$APP" --resource-group "$RG" --plan "$PLAN" --runtime "DOTNETCORE:10.0" -o none

    # Every setting below binds to an options class or to AddRequestsDatabase. '__' = ':' on Linux.
    az webapp config appsettings set --name "$APP" --resource-group "$RG" -o none --settings \
      "Database__Provider=Sqlite" \
      "ConnectionStrings__Requests=Data Source=/home/requests-net04.db" \
      "Database__MigrateOnStartup=true" \
      "Notifications__Channel=log" \
      "Notifications__StaleAfterDays=0" \
      "Notifications__DigestInterval=00:01:00"
    az webapp log config --name "$APP" --resource-group "$RG" --docker-container-logging filesystem -o none

    echo "==> zip deploy"
    az webapp deploy --resource-group "$RG" --name "$APP" --src-path "$out/app.zip" --type zip -o none
    host="$(az webapp show --name "$APP" --resource-group "$RG" --query defaultHostName -o tsv)"
    curl -fsS --retry 10 --retry-delay 6 --retry-all-errors "https://$host/healthz"; echo
    echo "Log stream: az webapp log tail -g $RG -n $APP   (or portal > Monitoring > Log stream)"
    ;;

  break)
    echo "==> Notifications__Channel=webhook without a WebhookUrl (the app restarts and must refuse to start)"
    az webapp config appsettings set --name "$APP" --resource-group "$RG" -o none \
      --settings "Notifications__Channel=webhook"
    ;;

  fix)
    az webapp config appsettings set --name "$APP" --resource-group "$RG" -o none \
      --settings "Notifications__Channel=log"
    ;;

  *) echo "Unknown phase '$1' (deploy|break|fix)" >&2; exit 2 ;;
esac
