#!/usr/bin/env bash
# Deletes the resource group (the policy assignments live in it too) and purges the lab Key Vault,
# which is soft-deleted, not gone. Usage: infra/teardown.sh <resource-group>
set -euo pipefail
RG=${1:?usage: teardown.sh <resource-group>}
KV=$(az keyvault list -g "$RG" --query "[0].name" -o tsv || true)
az group delete --name "$RG" --yes
if [[ -n "$KV" ]]; then
  az keyvault purge --name "$KV" || echo "Purge failed: if purge protection is on (prod), the vault stays until retention ends."
fi
az keyvault list-deleted --query "[?name=='$KV'].name" -o tsv
