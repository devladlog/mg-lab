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
az ad app permission admin-consent --id "$APP_ID"
echo "PnP client id: $APP_ID"
