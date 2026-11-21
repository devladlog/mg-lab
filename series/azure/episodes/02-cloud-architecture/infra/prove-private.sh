#!/usr/bin/env bash
# From OUTSIDE the VNet: storage and Key Vault must refuse us, the app must answer.
# Usage: infra/prove-private.sh <resource-group>
set -uo pipefail
RG=${1:?usage: prove-private.sh <resource-group>}
ST=$(az storage account list -g "$RG" --query "[0].name" -o tsv)
KV=$(az keyvault list -g "$RG" --query "[0].name" -o tsv)
APP=$(az webapp list -g "$RG" --query "[0].name" -o tsv)

echo "--- public DNS for the storage account (CNAME chain via privatelink)"
nslookup "$ST.blob.core.windows.net" | sed -n '1,12p'

echo "--- storage data plane from here (expect a refusal: public network access is disabled)"
az storage container show --account-name "$ST" --name probe --auth-mode login --output none 2>&1 | tail -2

echo "--- Key Vault data plane from here (expect a refusal)"
az keyvault secret show --vault-name "$KV" --name probe-secret --query name --output tsv 2>&1 | tail -2

echo "--- the app, which reaches both through private endpoints"
curl -sS "https://$(az webapp show -g "$RG" -n "$APP" --query defaultHostName -o tsv)/healthz"; echo
