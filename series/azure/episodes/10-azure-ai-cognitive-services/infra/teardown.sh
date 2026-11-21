#!/usr/bin/env bash
# Deletes the resource group, then PURGES the soft-deleted Language resource. Without the purge the account name (also the
# custom subdomain) stays reserved for 48 hours (Learn: recover or purge deleted resources) and the free-tier slot stays taken.
# Usage: infra/teardown.sh <resource-group> [location]
set -euo pipefail
RG=${1:?usage: teardown.sh <resource-group> [location]}
LOC=${2:-westeurope}
NAME=$(jq -r '.accountName.value' "$HOME/.contoso-ai/outputs.json")
az group delete --name "$RG" --yes
az cognitiveservices account purge --location "$LOC" --resource-group "$RG" --name "$NAME"
rm -rf "$HOME/.contoso-ai"
echo "Deleted and purged $NAME. Check: az cognitiveservices account list-deleted -o table   (empty)"
