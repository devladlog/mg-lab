#!/usr/bin/env bash
# Project requests API on Azure: App Service (Linux, Free F1) + Azure SQL Database (free offer), passwordless.
#
#   PACKAGE_ONLY=1 ./deploy/deploy-azure.sh            # dotnet publish + zip only, no Azure calls
#   APP=contoso-requests-1234 SQL=contoso-sql-1234 ./deploy/deploy-azure.sh infra
#       -> resource group, Entra-only logical server, free serverless database, F1 plan, web app,
#          system-assigned identity, connection string. Then run the two SQL files (see the output).
#   APP=contoso-requests-1234 SQL=contoso-sql-1234 ./deploy/deploy-azure.sh app
#       -> zip deploy + /healthz (which includes a database check)
#
# Needs: az login (an account that can create resources and is allowed to be the SQL Microsoft Entra admin).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project="$here/../src/ProjectRequests.Api/ProjectRequests.Api.csproj"
out="$here/out"

RG="${RG:-rg-mglab-net03}"
LOCATION="${LOCATION:-westeurope}"
PLAN="${PLAN:-plan-mglab-net03}"
DB="${DB:-requests}"

package() {
  echo "==> dotnet publish (Release)"
  rm -rf "$out/publish" "$out/app.zip"
  # linux-x64 only: SqlClient/SQLite native assets for every other OS would triple the package
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

phase="${1:?Usage: deploy-azure.sh infra|app}"
: "${APP:?Set APP to a globally unique web app name (a-z, 0-9, -)}"
: "${SQL:?Set SQL to a globally unique logical server name (a-z, 0-9, -)}"
az account show --query "{subscription:name}" -o tsv >/dev/null   # fails fast if not signed in

case "$phase" in
  infra)
    echo "==> resource group"
    az group create --name "$RG" --location "$LOCATION" --tags series=net episode=03 -o none

    echo "==> logical server, Microsoft Entra-only authentication, you as the Entra admin"
    me_upn="$(az ad signed-in-user show --query userPrincipalName -o tsv)"
    me_oid="$(az ad signed-in-user show --query id -o tsv)"
    az sql server create --name "$SQL" --resource-group "$RG" --location "$LOCATION" \
      --enable-ad-only-auth --external-admin-principal-type User \
      --external-admin-name "$me_upn" --external-admin-sid "$me_oid" -o none

    # 0.0.0.0 - 0.0.0.0 = "Allow Azure services" (App Service). It admits ALL Azure services, so the
    # database users/roles are what keep others out. A private endpoint is the production answer.
    az sql server firewall-rule create --server "$SQL" --resource-group "$RG" \
      --name AllowAllWindowsAzureIps --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 -o none

    echo "==> database on the free offer (pauses at the monthly free limit, never bills)"
    az sql db create --name "$DB" --server "$SQL" --resource-group "$RG" \
      --edition GeneralPurpose --family Gen5 --capacity 2 --compute-model Serverless \
      --use-free-limit true --free-limit-exhaustion-behavior AutoPause -o none

    echo "==> Free F1 Linux plan, web app (DOTNETCORE:10.0), system-assigned managed identity"
    az appservice plan create --name "$PLAN" --resource-group "$RG" --sku F1 --is-linux -o none
    az webapp create --name "$APP" --resource-group "$RG" --plan "$PLAN" --runtime "DOTNETCORE:10.0" -o none
    az webapp identity assign --name "$APP" --resource-group "$RG" -o none

    # No password anywhere: "Active Directory Default" = the app's managed identity in Azure.
    # App Service exposes it as SQLAZURECONNSTR_Requests -> ConnectionStrings:Requests in the app.
    az webapp config connection-string set --name "$APP" --resource-group "$RG" -o none \
      --connection-string-type SQLAzure --settings \
      "Requests=Server=tcp:$SQL.database.windows.net,1433;Database=$DB;Authentication=Active Directory Default;Encrypt=True;"
    az webapp config appsettings set --name "$APP" --resource-group "$RG" -o none \
      --settings Database__Provider=SqlServer Database__MigrateOnStartup=false

    mkdir -p "$out"
    sed "s/__APP_NAME__/$APP/g" "$here/grant-app-identity.template.sql" > "$out/grant-app-identity.sql"
    cat <<NEXT

Next, in the portal: SQL database '$DB' > Query editor > sign in as $me_upn, then run, in this order:
  1. $here/sqlserver-migrations.sql      (schema + seed, idempotent: safe to run twice)
  2. $out/grant-app-identity.sql         (the app's identity: read/write data only)
Then: APP=$APP SQL=$SQL ./deploy/deploy-azure.sh app
NEXT
    ;;

  app)
    package
    echo "==> zip deploy"
    az webapp deploy --resource-group "$RG" --name "$APP" --src-path "$out/app.zip" --type zip -o none
    host="$(az webapp show --name "$APP" --resource-group "$RG" --query defaultHostName -o tsv)"
    echo "==> https://$host/healthz  (first call may take a while: the free database resumes from auto-pause)"
    curl -fsS --retry 10 --retry-delay 10 --retry-all-errors "https://$host/healthz"; echo
    echo "Demo: ./deploy/local-demo.sh https://$host"
    ;;

  *)
    echo "Unknown phase '$phase' (infra|app)" >&2; exit 2 ;;
esac
