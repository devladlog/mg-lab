#!/usr/bin/env bash
# Deletes everything the episode created. Deleting the database also frees one of the
# subscription's ten free-tier database slots. Usage: infra/teardown.sh <resource-group>
set -euo pipefail
RG=${1:?usage: teardown.sh <resource-group>}
az group delete --name "$RG" --yes --no-wait
rm -f "$HOME/.contoso-orders-data/outputs.json"
echo "Deletion of $RG started. Check: az group exists --name $RG"
