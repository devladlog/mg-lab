#!/usr/bin/env bash
# MG Lab #6 — create your own Entra app for PnP PowerShell (the shared "PnP Management Shell" app was retired in 2024).
# Delegated permissions only: the app can never do more than the signed-in user can.
# Run in Azure Cloud Shell (Bash) as an admin. Prints the client id to use with Connect-PnPOnline.
set -euo pipefail
NAME="${1:-MG Lab PnP}"
SPO=00000003-0000-0ff1-ce00-000000000000      # SharePoint Online
GRAPH=00000003-0000-0000-c000-000000000000    # Microsoft Graph
scope() { az ad sp show --id "$1" --query "oauth2PermissionScopes[?value=='$2'].id | [0]" -o tsv; }

APP_ID=$(az ad app list --display-name "$NAME" --query "[0].appId" -o tsv)
if [ -z "$APP_ID" ]; then
  APP_ID=$(az ad app create --display-name "$NAME" --sign-in-audience AzureADMyOrg \
           --is-fallback-public-client true --public-client-redirect-uris "http://localhost" --query appId -o tsv)
  az ad sp create --id "$APP_ID" -o none
fi
az ad app permission add --id "$APP_ID" --api $SPO   --api-permissions "$(scope $SPO AllSites.FullControl)=Scope" -o none 2>/dev/null || true
az ad app permission add --id "$APP_ID" --api $GRAPH --api-permissions "$(scope $GRAPH User.Read)=Scope" -o none 2>/dev/null || true
sleep 20   # let the new service principal replicate before consenting
# Admin consent for the whole tenant = one oauth2PermissionGrant per API (works in Cloud Shell, unlike
# 'az ad app permission admin-consent', which needs a token Cloud Shell's managed identity can't get).
CLIENT_SP=$(az ad sp show --id "$APP_ID" --query id -o tsv)
grant() {   # $1 = resource appId, $2 = scopes
  local RES; RES=$(az ad sp show --id "$1" --query id -o tsv)
  local EXISTING; EXISTING=$(az rest -u "https://graph.microsoft.com/v1.0/oauth2PermissionGrants?\$filter=clientId eq '$CLIENT_SP' and resourceId eq '$RES'" --query "value[0].id" -o tsv)
  if [ -n "$EXISTING" ]; then
    az rest -m PATCH -u "https://graph.microsoft.com/v1.0/oauth2PermissionGrants/$EXISTING" --headers Content-Type=application/json -b "{\"scope\":\"$2\"}" -o none
  else
    az rest -m POST -u "https://graph.microsoft.com/v1.0/oauth2PermissionGrants" --headers Content-Type=application/json \
      -b "{\"clientId\":\"$CLIENT_SP\",\"consentType\":\"AllPrincipals\",\"resourceId\":\"$RES\",\"scope\":\"$2\"}" -o none
  fi
}
grant $SPO   "AllSites.FullControl"
grant $GRAPH "User.Read"
echo "PnP client id: $APP_ID"
